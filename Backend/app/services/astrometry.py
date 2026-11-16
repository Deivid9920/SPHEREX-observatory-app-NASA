from dataclasses import dataclass
from math import floor, isfinite
from typing import Any, Dict, List, Optional, Tuple

import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.io.fits import Header
from astropy.wcs import NoConvergence, WCS
import numpy as np


ASTROMETRY_VALIDATED = "ASTROMETRY_VALIDATED"
ASTROMETRY_PARTIALLY_VALIDATED = "ASTROMETRY_PARTIALLY_VALIDATED"
ASTROMETRY_UNVALIDATED = "ASTROMETRY_UNVALIDATED"
ASTROMETRY_BLOCKED = "ASTROMETRY_BLOCKED"

WCS_STRUCTURALLY_VALID = "WCS_STRUCTURALLY_VALID"
WCS_WITH_SIP_INCONSISTENCY = "WCS_WITH_SIP_INCONSISTENCY"
WCS_INCOMPLETE = "WCS_INCOMPLETE"

SIP_CONFIRMED_ACTIVE = "SIP_CONFIRMED_ACTIVE"
SIP_CONFIRMED_INACTIVE = "SIP_CONFIRMED_INACTIVE"
SIP_CONVENTION_INCONSISTENT = "SIP_CONVENTION_INCONSISTENT"
SIP_UNRESOLVED = "SIP_UNRESOLVED"


class AstrometryError(ValueError):
  """Base error for safe celestial-coordinate transformations."""


class InvalidSkyCoordinateError(AstrometryError):
  """The supplied RA/Dec is not a finite coordinate in the supported domain."""


class CoordinateOutsideImageError(AstrometryError):
  """A valid sky coordinate maps outside the image's pixel footprint."""


class WCSProjectionError(AstrometryError):
  """The WCS could not produce a finite coordinate transformation."""


class AstrometryBlockedError(AstrometryError):
  """The header does not support a safe sky-to-pixel transformation."""


@dataclass(frozen=True)
class SpatialWCS:
  wcs: WCS
  full_wcs: WCS
  variant: str
  structural_status: str
  sip_status: str
  astrometry_status: str
  finast: Optional[int]
  warnings: Tuple[str, ...]

  def provenance(self) -> Dict[str, Any]:
    return {
        "variant": self.variant,
        "structural_status": self.structural_status,
        "sip_status": self.sip_status,
        "astrometric_validation_status": self.astrometry_status,
        "finast": self.finast,
        "ctype": list(self.wcs.wcs.ctype),
        "warnings": list(self.warnings),
    }


@dataclass(frozen=True)
class PixelSelection:
  x_pixel: float
  y_pixel: float
  x_index: int
  y_index: int


def build_spatial_wcs(
    header: Header,
    *,
    fobj: Any = None,
) -> SpatialWCS:
  """Build the primary celestial WCS and record evidence without claiming accuracy."""
  full_wcs = WCS(header, fobj=fobj, relax=True)
  if not full_wcs.has_celestial:
    raise ValueError("El HDU no contiene ejes celestes WCS.")

  celestial = full_wcs.celestial
  ctype = [str(axis).upper() for axis in celestial.wcs.ctype]
  sip_present = celestial.sip is not None
  sip_declared = len(ctype) == 2 and all("-SIP" in axis for axis in ctype)
  warnings: List[str] = []

  if sip_present and sip_declared:
    sip_status = SIP_CONFIRMED_ACTIVE
    variant = "primary_spatial_wcs_with_sip"
  elif not sip_present and not sip_declared:
    sip_status = SIP_CONFIRMED_INACTIVE
    variant = "primary_spatial_wcs_without_sip"
  elif sip_present:
    sip_status = SIP_CONVENTION_INCONSISTENT
    variant = "primary_spatial_wcs_sip_ambiguous"
    warnings.append(
        "El WCS celeste contiene coeficientes SIP pero CTYPE no declara -SIP; "
        "la transformación no se considera segura."
    )
  else:
    sip_status = SIP_UNRESOLVED
    variant = "primary_spatial_wcs_sip_unresolved"
    warnings.append(
        "CTYPE declara -SIP pero Astropy no pudo construir coeficientes SIP."
    )

  raw_finast = header.get("FINAST")
  finast: Optional[int] = None
  if raw_finast is not None:
    try:
      finite_finast = float(raw_finast)
      if isfinite(finite_finast) and finite_finast.is_integer():
        finast = int(finite_finast)
    except (TypeError, ValueError):
      finast = None

  if raw_finast is None:
    warnings.append(
        "FINAST no está presente; su ausencia no se interpreta como una "
        "solución astrométrica buena."
    )
  elif finast is None:
    warnings.append("FINAST existe pero no contiene un entero finito interpretable.")
  elif finast > 0:
    warnings.append("FINAST > 0 indica una solución astrométrica pobre.")
  else:
    warnings.append(
        "FINAST=0 indica una solución buena según el pipeline, pero no es "
        "una validación astrométrica independiente."
    )

  warnings.append(
      "No se completó una comparación independiente con fuentes de referencia; "
      "las coordenadas celestes permanecen sin validar."
  )

  astrometry_status = (
      ASTROMETRY_BLOCKED
      if finast is not None and finast > 0
      or sip_status in (SIP_CONVENTION_INCONSISTENT, SIP_UNRESOLVED)
      else ASTROMETRY_UNVALIDATED
  )
  structural_status = (
      WCS_WITH_SIP_INCONSISTENCY
      if sip_status == SIP_CONVENTION_INCONSISTENT
      else WCS_INCOMPLETE
      if sip_status == SIP_UNRESOLVED
      else WCS_STRUCTURALLY_VALID
  )
  return SpatialWCS(
      wcs=celestial,
      full_wcs=full_wcs,
      variant=variant,
      structural_status=structural_status,
      sip_status=sip_status,
      astrometry_status=astrometry_status,
      finast=finast,
      warnings=tuple(warnings),
  )


def sky_to_pixel(
    spatial_wcs: SpatialWCS,
    ra_deg: float,
    dec_deg: float,
    image_shape: Tuple[int, int],
) -> PixelSelection:
  if (
      not isfinite(float(ra_deg))
      or not isfinite(float(dec_deg))
      or not 0.0 <= float(ra_deg) <= 360.0
      or not -90.0 <= float(dec_deg) <= 90.0
  ):
    raise InvalidSkyCoordinateError(
        "RA debe ser finita en [0, 360] y Dec finita en [-90, 90] grados."
    )
  if spatial_wcs.astrometry_status == ASTROMETRY_BLOCKED:
    raise AstrometryBlockedError(
        "El WCS espacial está bloqueado por metadatos astrométricos insuficientes."
    )
  if len(image_shape) != 2 or min(image_shape) <= 0:
    raise ValueError("La imagen debe tener dimensiones espaciales positivas.")

  coordinate = SkyCoord(
      ra=(float(ra_deg) % 360.0) * u.deg,
      dec=float(dec_deg) * u.deg,
      frame="icrs",
  )
  try:
    x_pixel, y_pixel = spatial_wcs.wcs.world_to_pixel(coordinate)
  except NoConvergence as exc:
    raise WCSProjectionError(
        "La inversión WCS no convergió para esta coordenada."
    ) from exc
  except (ValueError, FloatingPointError) as exc:
    raise WCSProjectionError("No se pudo invertir el WCS para esta coordenada.") from exc

  x_pixel = float(x_pixel)
  y_pixel = float(y_pixel)
  if not isfinite(x_pixel) or not isfinite(y_pixel):
    ctype = [str(axis).upper() for axis in spatial_wcs.wcs.wcs.ctype]
    if len(ctype) == 2 and all("-TAN" in axis for axis in ctype):
      tangent_point = SkyCoord(
          ra=float(spatial_wcs.wcs.wcs.crval[0]) * u.deg,
          dec=float(spatial_wcs.wcs.wcs.crval[1]) * u.deg,
          frame="icrs",
      )
      if coordinate.separation(tangent_point) >= 90.0 * u.deg:
        raise CoordinateOutsideImageError(
            "La coordenada celeste es válida, pero queda fuera del dominio "
            "proyectable y del campo de imagen TAN."
        )
    raise WCSProjectionError("La transformación WCS produjo un píxel no finito.")

  height, width = image_shape
  x_index = floor(x_pixel + 0.5)
  y_index = floor(y_pixel + 0.5)
  if not (0 <= x_index < width and 0 <= y_index < height):
    raise CoordinateOutsideImageError(
        "La coordenada celeste es válida, pero queda fuera del campo de imagen."
    )
  return PixelSelection(x_pixel, y_pixel, x_index, y_index)


def pixel_to_sky(
    spatial_wcs: SpatialWCS,
    x_pixel: float,
    y_pixel: float,
    image_shape: Tuple[int, int],
) -> SkyCoord:
  if spatial_wcs.astrometry_status == ASTROMETRY_BLOCKED:
    raise AstrometryBlockedError(
        "El WCS espacial está bloqueado por metadatos astrométricos insuficientes."
    )
  if (
      not isfinite(float(x_pixel))
      or not isfinite(float(y_pixel))
      or len(image_shape) != 2
      or not (0 <= float(x_pixel) < image_shape[1])
      or not (0 <= float(y_pixel) < image_shape[0])
  ):
    raise CoordinateOutsideImageError(
        "La coordenada de píxel debe ser finita y estar dentro de la imagen."
    )
  try:
    coordinate = spatial_wcs.wcs.pixel_to_world(float(x_pixel), float(y_pixel))
  except (ValueError, FloatingPointError) as exc:
    raise WCSProjectionError("No se pudo transformar el píxel al cielo.") from exc

  if (
      not np.isfinite(coordinate.ra.deg)
      or not np.isfinite(coordinate.dec.deg)
      or not -90.0 <= float(coordinate.dec.deg) <= 90.0
  ):
    raise WCSProjectionError("La transformación WCS produjo coordenadas celestes inválidas.")
  return SkyCoord(
      ra=(float(coordinate.ra.deg) % 360.0) * u.deg,
      dec=float(coordinate.dec.deg) * u.deg,
      frame="icrs",
  )


def build_spectral_wcs(
    header: Header,
    *,
    fobj: Any = None,
    key: str = "W",
) -> Tuple[WCS, List[str]]:
  """Build SPHEREx's alternate wavelength WCS without inherited spatial SIP."""
  spectral_wcs = WCS(header, fobj=fobj, relax=True, key=key)
  warnings: List[str] = []
  if spectral_wcs.sip is not None:
    spectral_wcs.sip = None
    warnings.append(
        "Astropy detectó coeficientes SIP del WCS espacial al construir el WCS "
        "espectral alternativo; se desactivaron solo en esta copia, según el "
        "tutorial oficial IRSA. La advertencia de CTYPE se conserva."
    )
  return spectral_wcs, warnings
