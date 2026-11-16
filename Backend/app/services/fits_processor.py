from typing import Any, Dict, Optional, Tuple

from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.nddata import Cutout2D
import astropy.units as u
from astropy.wcs import WCS
import numpy as np
import sep
from astropy.time import Time
from app.services.fits_inventory import release_from_hdul
from app.services.astrometry import (
    build_spatial_wcs,
    build_spectral_wcs,
    pixel_to_sky,
    sky_to_pixel,
)

class FITSProcessor:
  """Procesador científico de archivos Multi-Extension FITS (MEF) de SPHEREx Level 2.

  Implementa máscaras de calidad FLAGS, validación astrométrica WCS,
  recortes Cutout2D y extracción espectral segura.
  """

  FLAG_NAMES = {
      0: "TRANSIENT",
      1: "OVERFLOW",
      2: "SUR_ERROR",
      6: "NONFUNC",
      7: "DICHROIC",
      9: "MISSING_DATA",
      10: "HOT",
      11: "COLD",
      12: "FULLSAMPLE",
      14: "PHANMISS",
      15: "NONLINEAR",
      17: "PERSIST",
      19: "OUTLIER",
      20: "CROSSTALK",
      21: "SOURCE",
      22: "GHOST",
      23: "GHOST_FPA",
      24: "GHOST_EXT",
      25: "STREAK",
      26: "BLOOM",
      27: "SNOWBALL",
      28: "HALO",
      29: "SATELLITE_HALO",
  }
  # The Explanatory Supplement's L3 photometry mask is used conservatively for
  # single-pixel samples; DICHROIC is also excluded per its explicit warning.
  EXCLUDED_FLAG_BITS = frozenset({
      2, 6, 7, 9, 10, 11, 15, 17, 26, 27, 28, 29,
  })
  KNOWN_FLAG_MASK = sum(1 << bit for bit in FLAG_NAMES)
  EXCLUDED_FLAG_MASK = sum(1 << bit for bit in EXCLUDED_FLAG_BITS)
  UNKNOWN_FLAG_MASK = 0xFFFFFFFF ^ KNOWN_FLAG_MASK

  @classmethod
  def decode_flag_value(cls, value: int) -> Dict[str, Any]:
    """Decode a SPHEREx 32-bit FLAGS bitmap using Explanatory Supplement Table 16."""
    if not isinstance(value, (int, np.integer)):
      raise ValueError("FLAGS debe contener valores enteros.")
    flag_value = int(value) & 0xFFFFFFFF
    flag_bits = [
        bit for bit in cls.FLAG_NAMES
        if flag_value & (1 << bit)
    ]
    unknown_bits = [
        bit for bit in range(32)
        if flag_value & (1 << bit) and bit not in cls.FLAG_NAMES
    ]
    excluded_bits = [
        bit for bit in flag_bits
        if bit in cls.EXCLUDED_FLAG_BITS
    ]
    return {
        "flag": int(value),
        "flag_bits": flag_bits,
        "flag_names": [cls.FLAG_NAMES[bit] for bit in flag_bits],
        "excluded_flag_names": [cls.FLAG_NAMES[bit] for bit in excluded_bits],
        "unknown_flag_bits": unknown_bits,
        "quality_status": (
            "invalid"
            if excluded_bits
            else "unknown"
            if unknown_bits
            else "valid_with_warnings"
            if flag_bits
            else "valid"
        ),
    }

  @classmethod
  def flags_usable_mask(cls, flags: np.ndarray) -> np.ndarray:
    """Return pixels with no documented exclusion or undecoded flag bits."""
    if not np.issubdtype(flags.dtype, np.integer):
      raise ValueError("FLAGS debe contener valores enteros.")
    unsigned_flags = flags.astype(np.uint32, copy=False)
    rejected_mask = cls.EXCLUDED_FLAG_MASK | cls.UNKNOWN_FLAG_MASK
    return (unsigned_flags & np.uint32(rejected_mask)) == 0

  @classmethod
  def _measurement_quality(
      cls,
      flag_value: int,
      *,
      flux_valid: bool,
      spectral_coordinates_valid: bool,
      uncertainty_status: str,
  ) -> Dict[str, Any]:
    quality = cls.decode_flag_value(flag_value)
    warnings = []
    if quality["unknown_flag_bits"]:
      warnings.append(
          "FLAGS contiene bits sin definición documentada; la calidad es desconocida."
      )
    elif quality["excluded_flag_names"]:
      warnings.append(
          "La política documentada de calidad excluye este píxel por: "
          + ", ".join(quality["excluded_flag_names"])
          + "."
      )
    elif quality["flag_names"]:
      warnings.append(
          "El píxel tiene banderas reconocidas que requieren revisión: "
          + ", ".join(quality["flag_names"])
          + "."
      )

    if not flux_valid or not spectral_coordinates_valid:
      quality["quality_status"] = "invalid"
      warnings.append("El flujo o la coordenada espectral no es finito y válido.")
    elif quality["quality_status"] == "valid" and uncertainty_status != "available":
      quality["quality_status"] = "valid_with_warnings"
    is_valid = quality["quality_status"] in ("valid", "valid_with_warnings")
    if not is_valid and uncertainty_status == "available":
      uncertainty_status = "invalid_measurement"
      warnings.append("La incertidumbre no se reporta porque la medición no es válida.")
    if uncertainty_status != "available":
      warnings.append(f"La incertidumbre no está disponible ({uncertainty_status}).")

    quality.update({
        "is_valid_measurement": is_valid,
        "uncertainty_status": uncertainty_status,
        "measurement_status": (
            "valid"
            if is_valid
            else "unknown"
            if quality["quality_status"] == "unknown"
            else "invalid"
        ),
        "quality_warnings": warnings,
    })
    return quality

  @classmethod
  def load_and_clean_mef(
      cls, filepath: str
  ) -> Tuple[np.ndarray, np.ndarray, WCS, Dict[str, Any]]:
    """Abre un archivo MEF de SPHEREx leyendo explícitamente las extensiones

    'IMAGE', 'VARIANCE' y 'FLAGS' (nunca HDU[0]).
    Enmascara artefactos y rayos cósmicos asignando np.nan.
    """
    with fits.open(filepath, memmap=False) as hdul:
      required_exts = {"IMAGE", "VARIANCE", "FLAGS"}
      available_exts = {hdu.name.upper() for hdu in hdul}

      if not required_exts.issubset(available_exts):
        missing = required_exts - available_exts
        raise ValueError(
            f"El archivo FITS {filepath} no contiene las extensiones requeridas"
            f" de SPHEREx: {missing}"
        )

      image_hdu = hdul["IMAGE"]
      variance_hdu = hdul["VARIANCE"]
      flags_hdu = hdul["FLAGS"]
      if image_hdu.data is None or variance_hdu.data is None or flags_hdu.data is None:
        raise ValueError("IMAGE, VARIANCE y FLAGS deben contener arrays de datos.")
      if image_hdu.data.ndim != 2 or variance_hdu.data.shape != image_hdu.data.shape or flags_hdu.data.shape != image_hdu.data.shape:
        raise ValueError("IMAGE, VARIANCE y FLAGS deben ser matrices 2D de dimensiones idénticas.")
      if not np.issubdtype(flags_hdu.data.dtype, np.integer):
        raise ValueError("FLAGS debe contener valores enteros.")
      if image_hdu.header.get("BUNIT") is None:
        raise ValueError("IMAGE no declara BUNIT; no se puede verificar la unidad de flujo.")
      variance_bunit = variance_hdu.header.get("BUNIT")
      if variance_bunit is None:
        raise ValueError("VARIANCE no declara BUNIT; no se puede interpretar la incertidumbre.")
      try:
        image_unit = u.Unit(image_hdu.header["BUNIT"], format="fits")
        variance_unit = u.Unit(variance_bunit, format="fits")
      except ValueError as exc:
        raise ValueError("BUNIT de IMAGE o VARIANCE no se puede interpretar.") from exc
      if not variance_unit.is_equivalent(image_unit ** 2):
        raise ValueError("BUNIT de VARIANCE no corresponde al cuadrado de BUNIT de IMAGE.")
      if not np.issubdtype(image_hdu.data.dtype, np.number) or not np.issubdtype(variance_hdu.data.dtype, np.number):
        raise ValueError("IMAGE y VARIANCE deben contener datos numéricos.")

      # Preserve native IMAGE values while requiring a dimensionally valid variance map.
      raw_image = image_hdu.data.astype(np.float64)
      raw_variance = variance_hdu.data.astype(np.float64)
      flags = flags_hdu.data.astype(np.int64)

      # Flags excluded by the documented photometry policy and unknown bits are masked.
      valid_mask = cls.flags_usable_mask(flags)

      valid_mask = (
          valid_mask
          & np.isfinite(raw_image)
          & np.isfinite(raw_variance)
          & (raw_variance > 0.0)
      )

      clean_image = np.where(valid_mask, raw_image, np.nan)
      clean_variance = np.where(valid_mask, raw_variance, np.nan)

      wcs = build_spatial_wcs(image_hdu.header, fobj=hdul).wcs
      header_meta = {
          "date_obs": image_hdu.header.get("DATE-OBS", ""),
          "exptime": float(image_hdu.header.get("EXPTIME", 0.0)),
          "bunit": image_hdu.header["BUNIT"],
          "band": image_hdu.header.get("BAND", image_hdu.header.get("FILTER", "UNKNOWN")),
          "release": release_from_hdul(hdul),
          "psf_fwhm": image_hdu.header.get("PSF_FWHM", image_hdu.header.get("FWHM")),
          "calibration_level": image_hdu.header.get("CALLEVEL"),
          "calibration_version": image_hdu.header.get("CAL_VER", image_hdu.header.get("CALVERS")),
          "variance_bunit": variance_hdu.header.get("BUNIT"),
      }
      if not header_meta["band"] or str(header_meta["band"]).strip().upper() == "UNKNOWN":
        raise ValueError("IMAGE no declara BAND; no se puede verificar la compatibilidad espectral.")
      if not header_meta["date_obs"]:
        raise ValueError("IMAGE no declara DATE-OBS; no se puede comprobar la separación temporal.")
      if header_meta["psf_fwhm"] is None:
        raise ValueError("IMAGE no declara PSF_FWHM/FWHM; la compatibilidad de PSF no puede comprobarse.")
      header_meta["psf_fwhm"] = float(header_meta["psf_fwhm"])
      if not np.isfinite(header_meta["psf_fwhm"]) or header_meta["psf_fwhm"] <= 0:
        raise ValueError("PSF_FWHM/FWHM debe ser un valor finito positivo.")

      return clean_image, clean_variance, wcs, header_meta

  @staticmethod
  def subtract_sky_background(image_data: np.ndarray) -> np.ndarray:
    """Resta el fondo difuso infrarrojo utilizando SEP (Source Extractor).

    Aplica conversión explícita de byte-order nativo para evitar fallos en Cython/SEP.
    """
    # Convertir a byte-order nativo ('=') requerido por sep.Background
    native_img = np.ascontiguousarray(
        image_data.astype(image_data.dtype.newbyteorder("="))
    )

    # SEP requiere máscara booleana donde True indica píxel inválido/enmascarado
    nan_mask = ~np.isfinite(native_img)
    filled_img = np.nan_to_num(native_img, nan=0.0)

    bkg = sep.Background(filled_img, mask=nan_mask, bw=32, bh=32, fw=3, fh=3)
    bkg_sub = filled_img - bkg.back()

    # Restaurar np.nan en píxeles que estaban enmascarados originalmente
    return np.where(nan_mask, np.nan, bkg_sub)

  @classmethod
  def align_and_cutout_pair(
      cls,
      filepath_t1: str,
      filepath_t2: str,
      ra: float,
      dec: float,
      cutout_size_px: int = 150,
      subtract_background: bool = True,
  ) -> Dict[str, Any]:
    """Pipeline astrométrico completo para preparar dos épocas (t1 y t2):

    1. Lee y limpia MEFs con máscara FLAGS.
    2. Comprueba que WCS y resolución coincidan exactamente para evitar
    interpolar imagen o varianza.
    3. Aplica Cutout2D en ambas épocas garantizando matrices idénticas
    (150x150).
    """
    img_t1, var_t1, wcs_t1, meta_t1 = cls.load_and_clean_mef(filepath_t1)
    img_t2, var_t2, wcs_t2, meta_t2 = cls.load_and_clean_mef(filepath_t2)
    cls.validate_temporal_pair(
        wcs_t1, wcs_t2, img_t1.shape, img_t2.shape, meta_t1, meta_t2
    )
    date_t1 = Time(meta_t1["date_obs"])
    date_t2 = Time(meta_t2["date_obs"])
    if not date_t1.isscalar or not date_t2.isscalar or date_t1 == date_t2:
      raise ValueError("DATE-OBS debe definir dos épocas escalares distintas.")
    if str(meta_t1["bunit"]).strip() != str(meta_t2["bunit"]).strip():
      raise ValueError("Las imágenes tienen unidades BUNIT diferentes.")
    if not np.isclose(float(meta_t1["psf_fwhm"]), float(meta_t2["psf_fwhm"]), rtol=0.01, atol=0.0):
      raise ValueError("Las FWHM de PSF difieren más de 1%; el pipeline no realiza igualación de PSF.")
    release_t1 = str(meta_t1.get("release") or "").strip().upper()
    release_t2 = str(meta_t2.get("release") or "").strip().upper()
    if release_t1 and release_t2 and release_t1 != release_t2:
      raise ValueError("No se comparan releases distintas (p. ej., DR1 y QR3) sin una validación de calibración.")
    if any(release and release not in ("DR1", "QR3") for release in (release_t1, release_t2)):
      raise ValueError("Este pipeline solo admite releases identificadas DR1 o QR3.")
    if not meta_t1["calibration_level"] or not meta_t2["calibration_level"]:
      raise ValueError("Falta CALLEVEL; no se puede verificar la compatibilidad de calibración.")
    if meta_t1["calibration_level"] != meta_t2["calibration_level"]:
      raise ValueError("Los niveles de calibración de ambas épocas son diferentes.")
    if not meta_t1["calibration_version"] or not meta_t2["calibration_version"]:
      raise ValueError("Falta CAL_VER/CALVERS; no se puede verificar la versión de calibración.")
    if meta_t1["calibration_version"] != meta_t2["calibration_version"]:
      raise ValueError("Las versiones de calibración de ambas épocas son diferentes.")
    if str(meta_t1["band"]).strip().upper() != str(meta_t2["band"]).strip().upper():
      raise ValueError("Las imágenes corresponden a bandas distintas.")
    if not meta_t1["variance_bunit"] or not meta_t2["variance_bunit"]:
      raise ValueError("VARIANCE debe declarar BUNIT en ambas exposiciones.")
    if str(meta_t1["variance_bunit"]).strip() != str(meta_t2["variance_bunit"]).strip():
      raise ValueError("Las unidades BUNIT de VARIANCE difieren.")

    if subtract_background:
      img_t1 = cls.subtract_sky_background(img_t1)
      img_t2 = cls.subtract_sky_background(img_t2)

    img_t1_aligned = img_t1
    var_t1_aligned = var_t1

    # Recorte espacial exacto (Cutout2D) centrado en (RA, Dec) sobre la grilla común wcs_t2
    center_coord = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs")
    box_size = (cutout_size_px, cutout_size_px)

    cut_img_t1 = Cutout2D(
        img_t1_aligned, center_coord, size=box_size, wcs=wcs_t2, mode="partial"
    )
    cut_var_t1 = Cutout2D(
        var_t1_aligned, center_coord, size=box_size, wcs=wcs_t2, mode="partial"
    )
    cut_img_t2 = Cutout2D(
        img_t2, center_coord, size=box_size, wcs=wcs_t2, mode="partial"
    )
    cut_var_t2 = Cutout2D(
        var_t2, center_coord, size=box_size, wcs=wcs_t2, mode="partial"
    )

    return {
        "image_t1": cut_img_t1.data,
        "variance_t1": cut_var_t1.data,
        "image_t2": cut_img_t2.data,
        "variance_t2": cut_var_t2.data,
        "wcs": cut_img_t2.wcs,
        "meta_t1": meta_t1,
        "meta_t2": meta_t2,
    }

  @staticmethod
  def validate_temporal_pair(
        wcs_t1: WCS,
        wcs_t2: WCS,
        shape_t1: Tuple[int, ...],
        shape_t2: Tuple[int, ...],
        meta_t1: Dict[str, Any],
        meta_t2: Dict[str, Any],
  ) -> None:
    if shape_t1 != shape_t2:
        raise ValueError("Las imágenes tienen distinta resolución/dimensión de píxel.")
    for attribute in ("ctype", "cunit"):
        values_t1 = getattr(wcs_t1.wcs, attribute)
        values_t2 = getattr(wcs_t2.wcs, attribute)
        if list(values_t1) != list(values_t2):
          raise ValueError(f"Las grillas WCS difieren en {attribute}; el pipeline no remuestrea la varianza.")
    for attribute in ("crpix", "crval"):
        values_t1 = getattr(wcs_t1.wcs, attribute)
        values_t2 = getattr(wcs_t2.wcs, attribute)
        if len(values_t1) != len(values_t2) or not np.allclose(values_t1, values_t2, rtol=0.0, atol=1e-10):
          raise ValueError(f"Las grillas WCS difieren en {attribute}; el pipeline no remuestrea la varianza.")
    if not np.allclose(wcs_t1.pixel_scale_matrix, wcs_t2.pixel_scale_matrix, rtol=0.0, atol=1e-12):
        raise ValueError("La escala/resolución WCS difiere entre épocas; el pipeline no iguala la PSF.")
    if wcs_t1.celestial.pixel_n_dim != 2 or wcs_t2.celestial.pixel_n_dim != 2:
        raise ValueError("Se requiere una grilla WCS celeste bidimensional.")
    ny, nx = shape_t1[-2:]
    probe_pixels = np.array([
        [0.0, 0.0],
        [nx - 1.0, 0.0],
        [0.0, ny - 1.0],
        [nx - 1.0, ny - 1.0],
        [(nx - 1.0) / 2.0, (ny - 1.0) / 2.0],
    ])
    world_t1 = wcs_t1.celestial.all_pix2world(probe_pixels, 0)
    world_t2 = wcs_t2.celestial.all_pix2world(probe_pixels, 0)
    delta_ra = (world_t1[:, 0] - world_t2[:, 0] + 180.0) % 360.0 - 180.0
    if not np.allclose(delta_ra, 0.0, rtol=0.0, atol=1e-10) or not np.allclose(
        world_t1[:, 1], world_t2[:, 1], rtol=0.0, atol=1e-10
    ):
        raise ValueError("Las transformaciones WCS difieren; el pipeline no remuestrea la imagen ni la varianza.")
    releases = {
        str(meta.get("release") or "").strip().upper()
        for meta in (meta_t1, meta_t2)
        if meta.get("release")
    }
    if any(release not in ("DR1", "QR3") for release in releases):
      raise ValueError("Hay un release conocido no compatible con este pipeline.")
    if len(releases) > 1:
      raise ValueError("Los productos declaran releases diferentes.")

  @staticmethod
  def extract_spectral_profile_from_mef(
      filepath: str,
      ra: float,
      dec: float,
      spectral_wcs_filepath: Optional[str] = None,
  ) -> Dict[str, Any]:
    """Extrae la longitud de onda exacta (0.75 - 5.0 µm) en la coordenada (RA, Dec)

    utilizando el WCS espectral alternativo (key='W') con distorsión SIP desactivada.
    """
    with fits.open(filepath, memmap=False) as hdul:
      image_hdu = hdul["IMAGE"]
      flags_hdu = hdul["FLAGS"]
      try:
        image_unit = u.Unit(image_hdu.header["BUNIT"], format="fits")
      except (KeyError, ValueError) as exc:
        raise ValueError("BUNIT de IMAGE falta o no se puede interpretar.") from exc
      output_unit = u.MJy / u.sr
      if not image_unit.is_equivalent(output_unit):
        raise ValueError("El perfil espectral requiere unidades compatibles con MJy/sr.")
      if image_hdu.data is None or image_hdu.data.ndim != 2:
        raise ValueError("IMAGE debe contener una matriz bidimensional.")
      if flags_hdu.data is None or flags_hdu.data.shape != image_hdu.data.shape:
        raise ValueError("FLAGS debe tener las mismas dimensiones que IMAGE.")
      if not np.issubdtype(flags_hdu.data.dtype, np.integer):
        raise ValueError("FLAGS debe contener valores enteros.")

      ny, nx = image_hdu.data.shape
      spatial_wcs = build_spatial_wcs(image_hdu.header, fobj=hdul)
      selection = sky_to_pixel(spatial_wcs, ra, dec, image_hdu.data.shape)
      x_px, y_px = selection.x_pixel, selection.y_pixel
      ix, iy = selection.x_index, selection.y_index

      # Leer WCS espectral alternativo (key="W") y desactivar distorsión SIP obligatoriamente
      spectral_wcs, spectral_wcs_warnings = build_spectral_wcs(
          image_hdu.header, fobj=hdul, key="W"
      )

      # Transformar coordenadas de píxel a longitud de onda física
      spectral_world = spectral_wcs.pixel_to_world(x_px, y_px)

      # Extract wavelength only from a unit-bearing spectral coordinate.
      if hasattr(spectral_world, "to"):
        try:
          wavelength_um = float(
              spectral_world.to(u.um, equivalencies=u.spectral()).value
          )
        except u.UnitConversionError as exc:
          raise ValueError("El WCS alternativo no contiene una longitud de onda convertible a micrómetros.") from exc
      elif isinstance(spectral_world, (list, tuple)):
        wl_quantity = [w for w in spectral_world if hasattr(w, "to")]
        if not wl_quantity:
          raise ValueError("El WCS alternativo no devuelve una coordenada espectral con unidad.")
        try:
          wavelength_um = float(
              wl_quantity[0].to(u.um, equivalencies=u.spectral()).value
          )
        except u.UnitConversionError as exc:
          raise ValueError("El WCS alternativo no contiene una longitud de onda convertible a micrómetros.") from exc
      else:
        raise ValueError("El WCS alternativo no devuelve una coordenada espectral con unidad.")
      if not np.isfinite(wavelength_um) or wavelength_um <= 0:
        raise ValueError("El WCS alternativo devuelve una longitud de onda inválida.")
      bandwidth_um: Optional[float] = None
      wavelength_source = "IMAGE alternate WCS key W"
      if spectral_wcs_filepath is not None:
        with fits.open(spectral_wcs_filepath, mode="readonly", memmap=True) as calibration_hdul:
          if "CWAVE" not in calibration_hdul or "CBAND" not in calibration_hdul:
            raise ValueError("El Spectral WCS asociado no contiene CWAVE y CBAND.")
          cwave_hdu = calibration_hdul["CWAVE"]
          cband_hdu = calibration_hdul["CBAND"]
          if (
              cwave_hdu.data is None
              or cband_hdu.data is None
              or cwave_hdu.data.ndim != 2
              or cband_hdu.data.shape != cwave_hdu.data.shape
              or not (0 <= iy < cwave_hdu.data.shape[0] and 0 <= ix < cwave_hdu.data.shape[1])
          ):
            raise ValueError("Las mapas CWAVE/CBAND no contienen el píxel seleccionado.")
          try:
            cwave_unit = u.Unit(cwave_hdu.header["BUNIT"], format="fits")
            cband_unit = u.Unit(cband_hdu.header["BUNIT"], format="fits")
          except (KeyError, ValueError) as exc:
            raise ValueError("CWAVE/CBAND deben declarar unidades interpretables.") from exc
          if not cwave_unit.is_equivalent(u.um) or not cband_unit.is_equivalent(u.um):
            raise ValueError("CWAVE/CBAND deben tener unidades de longitud.")
          map_wavelength = float(
              (float(cwave_hdu.data[iy, ix]) * cwave_unit).to_value(u.um)
          )
          bandwidth_um = float(
              (float(cband_hdu.data[iy, ix]) * cband_unit).to_value(u.um)
          )
          if (
              not np.isfinite(map_wavelength)
              or map_wavelength <= 0
              or not np.isfinite(bandwidth_um)
              or bandwidth_um <= 0
          ):
            raise ValueError("CWAVE/CBAND contienen valores no válidos en el píxel seleccionado.")
          wavelength_um = map_wavelength
          wavelength_source = "Official Spectral WCS CWAVE/CBAND direct pixel lookup"

      flag_val = int(flags_hdu.data[iy, ix])
      raw_flux = float(image_hdu.data[iy, ix])
      variance_hdu = hdul["VARIANCE"] if "VARIANCE" in hdul else None
      variance_unit = None
      variance = None
      if variance_hdu is None:
        uncertainty_status = "missing"
      else:
        if variance_hdu.data is None or variance_hdu.data.shape != image_hdu.data.shape:
          raise ValueError("VARIANCE debe tener las mismas dimensiones que IMAGE.")
        variance = float(variance_hdu.data[iy, ix])
        variance_bunit = variance_hdu.header.get("BUNIT")
        if not variance_bunit:
          uncertainty_status = "invalid_unit"
        else:
          try:
            candidate_variance_unit = u.Unit(variance_bunit, format="fits")
          except ValueError:
            uncertainty_status = "invalid_unit"
          else:
            if not candidate_variance_unit.is_equivalent(image_unit ** 2):
              uncertainty_status = "invalid_unit"
            else:
              variance_unit = candidate_variance_unit
              uncertainty_status = (
                  "nonfinite"
                  if not np.isfinite(variance)
                  else "nonpositive"
                  if variance <= 0
                  else "available"
              )
      spectral_coordinates_valid = bool(
          np.isfinite(wavelength_um)
          and wavelength_um > 0
          and (bandwidth_um is None or (
              np.isfinite(bandwidth_um) and bandwidth_um > 0
          ))
      )
      quality = FITSProcessor._measurement_quality(
          flag_val,
          flux_valid=bool(np.isfinite(raw_flux)),
          spectral_coordinates_valid=spectral_coordinates_valid,
          uncertainty_status=uncertainty_status,
      )
      is_valid = bool(quality["is_valid_measurement"])
      uncertainty_status = quality["uncertainty_status"]
      uncertainty_available = uncertainty_status == "available"
      flux = (
          float((raw_flux * image_unit).to_value(output_unit))
          if is_valid
          else None
      )
      flux_error = (
          float(np.sqrt((variance * variance_unit).to_value(output_unit ** 2)))
          if uncertainty_available and variance is not None and variance_unit is not None
          else None
      )
      pixel_center = pixel_to_sky(
          spatial_wcs, ix, iy, image_hdu.data.shape
      )

      return {
          "pixel_x": ix,
          "pixel_y": iy,
          "pixel_x_unrounded": x_px,
          "pixel_y_unrounded": y_px,
          "pixel_center_ra": float(pixel_center.ra.deg),
          "pixel_center_dec": float(pixel_center.dec.deg),
          "detector": image_hdu.header.get("DETECTOR"),
          "date_obs": image_hdu.header.get("DATE-OBS"),
          "spatial_wcs_provenance": spatial_wcs.provenance(),
          "spectral_wcs_warnings": spectral_wcs_warnings,
          "wavelength_um": wavelength_um,
          "bandwidth_um": bandwidth_um,
          "wavelength_source": wavelength_source,
          "flux": flux,
          "flux_error": flux_error,
          "unit": str(image_hdu.header["BUNIT"]),
          "flux_mjy_sr": flux,
          "flux_error_mjy_sr": flux_error,
          **quality,
          "uncertainty_available": uncertainty_available,
          "uncertainty_status": uncertainty_status,
          "uncertainty_unit": str(output_unit) if uncertainty_available else None,
      }

  @staticmethod
  def extract_spectral_profile_from_cube(
      filepath: str, ra: float, dec: float
  ) -> Dict[str, Any]:
    """Extract native cube samples using its celestial WCS and tabulated channel wavelengths."""
    with fits.open(filepath, mode="readonly", memmap=True) as hdul:
      image_hdu = hdul["IMAGE"]
      flags_hdu = hdul["FLAGS"]
      if image_hdu.data is None or image_hdu.data.ndim != 3:
        raise ValueError("IMAGE debe ser un cubo numérico de tres dimensiones.")
      if flags_hdu.data is None or flags_hdu.data.shape != image_hdu.data.shape:
        raise ValueError("FLAGS debe tener las mismas dimensiones que IMAGE.")
      if not np.issubdtype(flags_hdu.data.dtype, np.integer):
        raise ValueError("FLAGS debe contener valores enteros.")
      if "SPECTRAL_CHANNELS" not in hdul:
        raise ValueError("Falta la tabla SPECTRAL_CHANNELS.")
      channels = hdul["SPECTRAL_CHANNELS"].data
      if channels is None or "WAVELENGTH" not in (channels.names or []):
        raise ValueError("SPECTRAL_CHANNELS no declara longitudes de onda.")
      spatial_wcs = build_spatial_wcs(image_hdu.header, fobj=hdul)
      wcs = spatial_wcs.full_wcs
      physical_types = wcs.world_axis_physical_types or []
      spectral_world_axes = [
          index
          for index, physical_type in enumerate(physical_types)
          if physical_type == "em.wl"
      ]
      if len(spectral_world_axes) != 1 or wcs.pixel_n_dim != 3:
        raise ValueError("El WCS debe identificar un único eje espectral de longitud de onda en un cubo 3D.")
      spectral_world_axis = spectral_world_axes[0]
      spectral_pixel_axes = np.flatnonzero(
          wcs.axis_correlation_matrix[spectral_world_axis]
      )
      if spectral_pixel_axes.size != 1:
        raise ValueError("El WCS no identifica un eje de píxel espectral independiente.")
      spectral_pixel_axis = int(spectral_pixel_axes[0])
      spectral_array_axis = wcs.pixel_n_dim - 1 - spectral_pixel_axis
      if spectral_array_axis != 0:
        raise ValueError("El eje espectral WCS no corresponde al eje de canales principal del array.")
      channels_count, height, width = image_hdu.data.shape
      if len(channels) != channels_count:
        raise ValueError("El número de canales no coincide con el eje espectral identificado por WCS.")

      wavelength_column = hdul["SPECTRAL_CHANNELS"].columns["WAVELENGTH"]
      if not wavelength_column.unit:
        raise ValueError("SPECTRAL_CHANNELS.WAVELENGTH no declara unidad; no se asumirá micrómetros.")
      try:
        wavelength_unit = u.Unit(wavelength_column.unit)
      except ValueError as exc:
        raise ValueError("La unidad de SPECTRAL_CHANNELS.WAVELENGTH no se puede interpretar.") from exc
      wavelengths = (
          np.asarray(channels["WAVELENGTH"], dtype=np.float64) * wavelength_unit
      ).to_value(u.um, equivalencies=u.spectral())
      if not np.all(np.isfinite(wavelengths)) or np.any(wavelengths <= 0):
        raise ValueError("SPECTRAL_CHANNELS contiene longitudes de onda inválidas.")
      bandwidths: Optional[np.ndarray] = None
      if "BANDWIDTH" in (channels.names or []):
        bandwidth_column = hdul["SPECTRAL_CHANNELS"].columns["BANDWIDTH"]
        if not bandwidth_column.unit:
          raise ValueError("SPECTRAL_CHANNELS.BANDWIDTH no declara unidad.")
        try:
          bandwidth_unit = u.Unit(bandwidth_column.unit)
          bandwidths = (
              np.asarray(channels["BANDWIDTH"], dtype=np.float64) * bandwidth_unit
          ).to_value(u.um, equivalencies=u.spectral())
        except (ValueError, u.UnitConversionError) as exc:
          raise ValueError("SPECTRAL_CHANNELS.BANDWIDTH no tiene una unidad de longitud válida.") from exc
        if not np.all(np.isfinite(bandwidths)) or np.any(bandwidths <= 0):
          raise ValueError("SPECTRAL_CHANNELS contiene anchos de banda inválidos.")

      if not spatial_wcs.wcs.has_celestial or wcs.pixel_n_dim != 3:
        raise ValueError("IMAGE no contiene un WCS celeste y espectral tridimensional.")
      try:
        image_unit = u.Unit(image_hdu.header["BUNIT"], format="fits")
      except (KeyError, ValueError) as exc:
        raise ValueError("BUNIT de IMAGE falta o no se puede interpretar.") from exc
      output_unit = u.MJy / u.sr
      if not image_unit.is_equivalent(output_unit):
        raise ValueError("La unidad de IMAGE no es compatible con MJy/sr.")

      channels_count, height, width = image_hdu.data.shape
      selection = sky_to_pixel(spatial_wcs, ra, dec, (height, width))
      x_pixel, y_pixel = selection.x_pixel, selection.y_pixel
      x_index, y_index = selection.x_index, selection.y_index

      spatial_world_axes = [wcs.wcs.lng, wcs.wcs.lat]
      spatial_pixel_axes = sorted({
          int(pixel_axis)
          for world_axis in spatial_world_axes
          for pixel_axis in np.flatnonzero(wcs.axis_correlation_matrix[world_axis])
          if int(pixel_axis) != spectral_pixel_axis
      })
      if spatial_pixel_axes != [0, 1] or spectral_pixel_axis != 2:
        raise ValueError("El orden de ejes del cubo no se puede asociar sin ambigüedad con (canal, y, x).")
      channel_indices = np.arange(channels_count, dtype=np.float64)
      pixel_grid = np.zeros((channels_count, wcs.pixel_n_dim), dtype=np.float64)
      pixel_grid[:, spatial_pixel_axes[0]] = x_pixel
      pixel_grid[:, spatial_pixel_axes[1]] = y_pixel
      pixel_grid[:, spectral_pixel_axis] = channel_indices
      wcs_wavelengths_native = np.asarray(
          wcs.all_pix2world(pixel_grid, 0)[:, spectral_world_axis], dtype=np.float64
      )
      try:
        wcs_wavelength_unit = u.Unit(wcs.world_axis_units[spectral_world_axis])
        wcs_wavelengths = (
            wcs_wavelengths_native * wcs_wavelength_unit
        ).to_value(u.um, equivalencies=u.spectral())
      except (IndexError, ValueError, u.UnitConversionError) as exc:
        raise ValueError("El WCS espectral no declara una unidad compatible con micrómetros.") from exc
      if not np.allclose(wcs_wavelengths, wavelengths, rtol=1e-5, atol=1e-7):
        raise ValueError(
            "Los canales de SPECTRAL_CHANNELS no coinciden con el WCS espectral del cubo."
        )

      flags = np.asarray(flags_hdu.data[:, y_index, x_index], dtype=np.int64)
      fluxes = np.asarray(image_hdu.data[:, y_index, x_index], dtype=np.float64)
      variance_hdu = hdul["VARIANCE"] if "VARIANCE" in hdul else None
      variances: Optional[np.ndarray] = None
      variance_unit = None
      uncertainty_status = "missing"
      if variance_hdu is not None:
        if variance_hdu.data is None or variance_hdu.data.shape != image_hdu.data.shape:
          raise ValueError("VARIANCE debe tener las mismas dimensiones que IMAGE.")
        if not variance_hdu.header.get("BUNIT"):
          raise ValueError("VARIANCE no declara BUNIT; no se puede interpretar su incertidumbre.")
        try:
          variance_unit = u.Unit(variance_hdu.header["BUNIT"], format="fits")
        except ValueError as exc:
          raise ValueError("La unidad BUNIT de VARIANCE no se puede interpretar.") from exc
        if not variance_unit.is_equivalent(image_unit ** 2):
          raise ValueError("BUNIT de VARIANCE no corresponde al cuadrado de BUNIT de IMAGE.")
        variances = np.asarray(
            variance_hdu.data[:, y_index, x_index],
            dtype=np.float64,
        )
        uncertainty_status = "available"
      measurements = []
      for channel, wavelength, flux, flag in zip(
          range(channels_count), wavelengths, fluxes, flags
      ):
        variance = variances[channel] if variances is not None else None
        channel_uncertainty_status = (
            "missing"
            if variance is None
            else "nonfinite"
            if not np.isfinite(variance)
            else "nonpositive"
            if variance <= 0
            else "available"
        )
        quality = FITSProcessor._measurement_quality(
            int(flag),
            flux_valid=bool(np.isfinite(flux)),
            spectral_coordinates_valid=bool(np.isfinite(wavelength) and wavelength > 0),
            uncertainty_status=channel_uncertainty_status,
        )
        valid = bool(quality["is_valid_measurement"])
        channel_uncertainty_status = quality["uncertainty_status"]
        uncertainty_available = channel_uncertainty_status == "available"
        measurements.append({
            "channel": channel,
            "wavelength_um": float(wavelength),
            "bandwidth_um": (
                float(bandwidths[channel]) if bandwidths is not None else None
            ),
            "flux": float((flux * image_unit).to_value(output_unit)) if valid else None,
            "flux_error": (
                float(np.sqrt((variance * variance_unit).to_value(output_unit ** 2)))
                if uncertainty_available and variance is not None and variance_unit is not None
                else None
            ),
            **quality,
            "uncertainty_status": channel_uncertainty_status,
        })
      channel_uncertainty_states = {
          item["uncertainty_status"] for item in measurements
      }
      if channel_uncertainty_states == {"available"}:
        uncertainty_status = "available"
      elif "available" in channel_uncertainty_states:
        uncertainty_status = "partially_available"
      elif "missing" in channel_uncertainty_states:
        uncertainty_status = "missing"
      else:
        uncertainty_status = "unavailable_invalid_values"
      quality_states = {item["quality_status"] for item in measurements}
      if quality_states == {"valid"}:
        quality_status = "valid"
      elif "invalid" in quality_states and len(quality_states) == 1:
        quality_status = "invalid"
      elif "unknown" in quality_states:
        quality_status = "unknown"
      else:
        quality_status = "valid_with_warnings"

      pixel_center = pixel_to_sky(
          spatial_wcs, x_index, y_index, (height, width)
      )
      return {
          "pixel_x": x_index,
          "pixel_y": y_index,
          "pixel_x_unrounded": x_pixel,
          "pixel_y_unrounded": y_pixel,
          "pixel_center_ra": float(pixel_center.ra.deg),
          "pixel_center_dec": float(pixel_center.dec.deg),
          "spatial_wcs_provenance": spatial_wcs.provenance(),
          "measurements": measurements,
          "quality_status": quality_status,
          "unit": str(output_unit),
          "uncertainty_unit": (
              str(output_unit) if uncertainty_status in ("available", "partially_available") else None
          ),
          "wavelength_source": "SPECTRAL_CHANNELS.WAVELENGTH; checked against 3D WCS",
          "bandwidth_available": bandwidths is not None,
          "bandwidth_unit": "um" if bandwidths is not None else None,
          "uncertainty_available": uncertainty_status in ("available", "partially_available"),
          "uncertainty_status": uncertainty_status,
          "valid_channel_count": sum(
              item["is_valid_measurement"] for item in measurements
          ),
          "channel_count": channels_count,
      }