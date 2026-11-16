from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import logging
import math
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from astropy.utils.data import conf as astropy_data_conf
from astroquery.gaia import Gaia
from pyvo.dal import TAPService
from pyvo.dal.exceptions import DALFormatError, DALServiceError
import requests

from app.core.config import settings

logger = logging.getLogger("SPHEREx-IRSAClient")

# Configuración de timeouts para consultas astronómicas pesadas
astropy_data_conf.remote_timeout = 120
Gaia.ROW_LIMIT = 500


class IRSAQueryError(RuntimeError):
  """An IRSA TAP request or response could not be completed safely."""


class _TimeoutSession(requests.Session):
  def __init__(self, timeout_seconds: float) -> None:
    super().__init__()
    self.timeout_seconds = timeout_seconds

  def request(self, method, url, **kwargs):
    kwargs.setdefault("timeout", self.timeout_seconds)
    return super().request(method, url, **kwargs)


class IRSAClient:
  """Cliente científico para interactuar con NASA IPAC IRSA,

  el catálogo Gaia DR3 y generar enlaces de inspección en WiseView.
  Cero dependencias de FastAPI.
  """

  IRSA_TAP_URL = "https://irsa.ipac.caltech.edu/TAP"

  def __init__(
      self,
      raw_dir: str = settings.DATA_RAW_DIR,
      tap_timeout_seconds: float = 30.0,
  ):
    self.raw_dir = raw_dir
    self.tap_timeout_seconds = tap_timeout_seconds
    self.tap_service = TAPService(
        self.IRSA_TAP_URL,
        session=_TimeoutSession(tap_timeout_seconds),
    )
    os.makedirs(self.raw_dir, exist_ok=True)

  def _run_tap(self, query: str, *, maxrec: int) -> Any:
    try:
      result = self.tap_service.run_sync(query, maxrec=maxrec)
      return result.to_table() if hasattr(result, "to_table") else result
    except requests.Timeout as exc:
      logger.warning("IRSA TAP excedió el timeout de %.1f s.", self.tap_timeout_seconds)
      raise IRSAQueryError(
          f"IRSA no respondió dentro del timeout de {self.tap_timeout_seconds:g} segundos."
      ) from exc
    except requests.HTTPError as exc:
      status = exc.response.status_code if exc.response is not None else "desconocido"
      logger.warning("IRSA TAP devolvió HTTP %s.", status)
      raise IRSAQueryError(f"IRSA TAP devolvió HTTP {status}.") from exc
    except requests.RequestException as exc:
      logger.warning("Error de transporte al consultar IRSA TAP: %s", exc)
      raise IRSAQueryError("No se pudo establecer conexión con IRSA TAP.") from exc
    except DALServiceError as exc:
      logger.warning("IRSA TAP rechazó la consulta: %s", exc)
      raise IRSAQueryError("IRSA TAP rechazó la consulta o devolvió un error del servicio.") from exc
    except DALFormatError as exc:
      logger.warning("IRSA TAP devolvió una respuesta inválida o agotó el timeout: %s", exc)
      raise IRSAQueryError(
          f"IRSA TAP agotó el timeout de {self.tap_timeout_seconds:g} segundos o devolvió un formato inválido."
      ) from exc
    except ValueError as exc:
      logger.warning("IRSA TAP devolvió una respuesta no interpretable: %s", exc)
      raise IRSAQueryError("IRSA TAP devolvió una respuesta no interpretable.") from exc

  def _spherex_obscore_columns(self) -> Dict[str, Optional[str]]:
    columns = self._run_tap(
        "SELECT column_name, unit FROM TAP_SCHEMA.columns "
        "WHERE table_name = 'spherex.obscore'",
        maxrec=200,
    )
    result = {
        str(row["column_name"]).strip().lower(): (
            str(row["unit"]).strip() or None
            if row["unit"] is not None
            else None
        )
        for row in columns
    }
    if not result:
      raise IRSAQueryError("El esquema TAP de IRSA no publica spherex.obscore.")
    required = {
        "obs_id", "obs_collection", "s_ra", "s_dec", "t_min", "t_max",
        "em_min", "em_max", "access_url", "dataproduct_type",
    }
    missing = required - result.keys()
    if missing:
      raise IRSAQueryError(
          "El esquema IRSA spherex.obscore no incluye columnas requeridas: "
          f"{', '.join(sorted(missing))}."
      )
    return result

  @staticmethod
  def _wavelength_um(value: Any, unit_name: Optional[str]) -> Optional[float]:
    if value is None or getattr(value, "mask", False) or not unit_name:
      return None
    try:
      from astropy import units as u

      unit = u.Unit(unit_name)
      if not unit.is_equivalent(u.m):
        return None
      return float((float(value) * unit).to_value(u.um))
    except (TypeError, ValueError):
      return None

  def query_spherex_observations(
      self, ra: float, dec: float, fov_deg: float = 0.08, limit: int = 20
  ) -> List[Dict[str, Any]]:
    """Query verified TAP schema metadata before searching public SPHEREx observations."""
    if (
        not math.isfinite(ra) or not 0.0 <= ra <= 360.0
        or not math.isfinite(dec) or not -90.0 <= dec <= 90.0
        or not math.isfinite(fov_deg) or not 0.01 <= fov_deg <= 0.5
        or not 1 <= limit <= 500
    ):
      raise ValueError("RA, DEC, FOV o límite fuera del rango permitido.")
    columns = self._spherex_obscore_columns()
    adql_query = f"""
        SELECT TOP {limit}
            o.obs_id,
            o.obs_collection,
            o.t_min,
            o.t_max,
            o.em_min,
            o.em_max,
            o.access_url,
            o.dataproduct_type
        FROM spherex.obscore AS o
        WHERE CONTAINS(
            POINT('ICRS', o.s_ra, o.s_dec),
            CIRCLE('ICRS', {ra}, {dec}, {fov_deg})
        ) = 1
        """

    try:
      logger.info(
          f"Consultando TAP IRSA SPHEREx en RA={ra}, Dec={dec},"
          f" FOV={fov_deg} deg"
      )
      table = self._run_tap(adql_query, maxrec=limit)

      observations = []
      for row in table:
        observations.append({
            "obs_id": str(row["obs_id"]),
            "collection": str(row["obs_collection"]),
            "t_min": float(row["t_min"]),
            "t_max": float(row["t_max"]),
            "wavelength_min_um": self._wavelength_um(
                row["em_min"], columns.get("em_min")
            ),
            "wavelength_max_um": self._wavelength_um(
                row["em_max"], columns.get("em_max")
            ),
            "product_type": str(row["dataproduct_type"]),
            "base_uri": str(row["access_url"]),
        })
      return observations

    except IRSAQueryError:
      raise
    except (TypeError, ValueError, KeyError) as exc:
      logger.warning("La respuesta TAP de IRSA no cumple el contrato esperado: %s", exc)
      raise IRSAQueryError(
          "La respuesta TAP de IRSA no contiene los campos de observación esperados."
      ) from exc

  def _download_single_cutout(
      self, base_uri: str, ra: float, dec: float, fov_deg: float, obs_id: str
  ) -> str:
    """Descarga únicamente el recorte FITS solicitado desde el servidor IRSA

    anexando ?center={ra},{dec}d&size={fov_deg} a la URI para evitar bajar 300 MB.
    """
    separator = "&" if "?" in base_uri else "?"
    cutout_url = f"{base_uri}{separator}center={ra},{dec}d&size={fov_deg}"

    # Hash único para caché local en disco
    cache_key = hashlib.md5(f"{obs_id}_{ra}_{dec}_{fov_deg}".encode()).hexdigest()[
        :12
    ]
    local_filename = f"spx_{obs_id}_{cache_key}.fits"
    local_filepath = os.path.join(self.raw_dir, local_filename)

    if os.path.exists(local_filepath) and os.path.getsize(local_filepath) > 0:
      logger.info(f"Cutout FITS recuperado de caché local: {local_filename}")
      return local_filepath

    logger.info(f"Descargando cutout SPHEREx desde IRSA: {cutout_url}")
    response = requests.get(cutout_url, timeout=120, stream=True)
    response.raise_for_status()

    with open(local_filepath, "wb") as f:
      for chunk in response.iter_content(chunk_size=65536):
        if chunk:
          f.write(chunk)

    return local_filepath

  def download_cutouts_parallel(
      self,
      observations: List[Dict[str, Any]],
      ra: float,
      dec: float,
      fov_deg: float = 0.08,
  ) -> Dict[str, str]:
    """Descarga múltiples cutouts FITS en paralelo usando ThreadPoolExecutor(max_workers=8).

    Retorna un diccionario {obs_id: local_filepath}.
    """
    results: Dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=8) as executor:
      future_to_obs = {
          executor.submit(
              self._download_single_cutout,
              obs["base_uri"],
              ra,
              dec,
              fov_deg,
              obs["obs_id"],
          ): obs["obs_id"]
          for obs in observations
      }

      for future in as_completed(future_to_obs):
        obs_id = future_to_obs[future]
        try:
          filepath = future.result()
          results[obs_id] = filepath
        except Exception as exc:
          logger.error(f"Error descargando cutout para obs_id={obs_id}: {exc}")

    return results

  def query_gaia_dr3_crossmatch(
      self, ra: float, dec: float, radius_arcsec: float = 15.0
  ) -> List[Dict[str, Any]]:
    """Ejecuta un cone search ADQL en gaiadr3.gaia_source (TOP 500)

    para identificar estrellas conocidas con movimiento propio (pmra, pmdec) y paralaje.
    """
    radius_deg = radius_arcsec / 3600.0
    adql_gaia = f"""
        SELECT TOP 500
            source_id,
            ra,
            dec,
            pmra,
            pmdec,
            parallax,
            phot_g_mean_mag
        FROM gaiadr3.gaia_source
        WHERE CONTAINS(
            POINT('ICRS', ra, dec),
            CIRCLE('ICRS', {ra}, {dec}, {radius_deg})
        ) = 1
        ORDER BY phot_g_mean_mag ASC
        """

    try:
      job = Gaia.launch_job(adql_gaia)
      table = job.get_results()

      matches = []
      for row in table:
        matches.append({
            "source_id": str(row["source_id"]),
            "ra": float(row["ra"]),
            "dec": float(row["dec"]),
            "pmra_mas_yr": (
                float(row["pmra"])
                if row["pmra"] is not None and not getattr(row["pmra"], "mask", False)
                else 0.0
            ),
            "pmdec_mas_yr": (
                float(row["pmdec"])
                if row["pmdec"] is not None
                and not getattr(row["pmdec"], "mask", False)
                else 0.0
            ),
            "parallax_mas": (
                float(row["parallax"])
                if row["parallax"] is not None
                and not getattr(row["parallax"], "mask", False)
                else 0.0
            ),
            "g_mag": (
                float(row["phot_g_mean_mag"])
                if row["phot_g_mean_mag"] is not None
                and not getattr(row["phot_g_mean_mag"], "mask", False)
                else None
            ),
        })
      return matches

    except Exception as e:
      logger.warning(f"No se pudo completar cruce con Gaia DR3: {e}")
      return []

  @staticmethod
  def build_wiseview_url(ra: float, dec: float, size_arcsec: int = 60) -> str:
    """Genera el enlace parametrizado a WiseView para inspección visual

    del historial infrarrojo (2010-2024).
    """
    params = {
        "ra": round(ra, 6),
        "dec": round(dec, 6),
        "size": size_arcsec,
        "band": 3,
        "speed": 125,
    }
    return f"http://byw.tools/wiseview#{urlencode(params)}"