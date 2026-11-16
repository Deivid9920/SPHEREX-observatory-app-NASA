from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from astropy.io import fits
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
import numpy as np
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.database_models import ScientificRunModel
from app.services.calibration_manager import CalibrationManager
from app.services.fits_inventory import InventoryStaleError, MODULE_NAMES, fits_inventory
from app.services.image_renderer import ImageRenderer
from app.services.fits_processor import FITSProcessor
from app.services.astrometry import (
    ASTROMETRY_VALIDATED,
    AstrometryBlockedError,
    build_spatial_wcs,
    CoordinateOutsideImageError,
    InvalidSkyCoordinateError,
    WCSProjectionError,
)
from app.services.scientific_results import (
    save_scientific_run,
    serialize_scientific_run,
)
from app.services.temporal_engine import TemporalEngine

router = APIRouter()
image_renderer = ImageRenderer(output_dir=settings.SPHEREX_PROCESSED_DIR)


def _calibration_manager() -> CalibrationManager:
    return CalibrationManager(
        fits_inventory,
        calibration_root=Path(settings.SPHEREX_CALIBRATION_DIR),
    )


def _coordinate_provenance(
    entry: Dict[str, Any],
    point: Dict[str, Any],
    *,
    ra: float,
    dec: float,
) -> Dict[str, Any]:
    image_hdu = next(
        (
            item["index"]
            for item in entry.get("extensions", [])
            if item.get("name") == "IMAGE"
        ),
        None,
    )
    wcs_provenance = point["spatial_wcs_provenance"]
    astrometry_status = wcs_provenance["astrometric_validation_status"]
    warnings = list(dict.fromkeys([
        *wcs_provenance["warnings"],
        *point.get("spectral_wcs_warnings", []),
    ]))
    return {
        "input": {
            "ra_deg": ra,
            "dec_deg": dec,
            "coordinate_system": "ICRS",
            "reference_epoch": None,
        },
        "source": {
            "file_id": entry["file_id"],
            "filename": entry["filename"],
            "relative_path": entry["relative_path"],
            "sha256": entry["sha256"],
            "detector": point.get("detector"),
            "hdu_index": image_hdu,
            "hdu_name": "IMAGE",
            "observation_epoch": point.get("date_obs"),
        },
        "pixel": {
            "x_unrounded": point["pixel_x_unrounded"],
            "y_unrounded": point["pixel_y_unrounded"],
            "x_index": point["pixel_x"],
            "y_index": point["pixel_y"],
            "fits_x_1_based": point["pixel_x"] + 1,
            "fits_y_1_based": point["pixel_y"] + 1,
            "array_indexing": "0-based; x=column, y=row; nearest pixel center",
        },
        "pixel_center_sky": {
            "ra_deg": point["pixel_center_ra"],
            "dec_deg": point["pixel_center_dec"],
            "status": astrometry_status,
        },
        "wcs": {
            "identifier": (
                f"{entry['sha256']}:HDU{image_hdu}:{wcs_provenance['variant']}"
            ),
            **wcs_provenance,
        },
        "astrometric_validation_status": astrometry_status,
        "positional_uncertainty_arcsec": None,
        "method": "Astropy primary spatial WCS; world_to_pixel; nearest pixel center",
        "scientifically_validated": astrometry_status == ASTROMETRY_VALIDATED,
        "warnings": warnings,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/calibrations")
def list_local_calibrations() -> Dict[str, Any]:
    try:
        return _calibration_manager().catalog()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="El directorio de datos FITS local no está disponible.",
        ) from exc


@router.get("/fits/{file_id}/calibration")
def get_local_fits_calibration(file_id: str) -> Dict[str, Any]:
    try:
        entry = fits_inventory.find(file_id)
        path = fits_inventory.get_path(entry)
        return _calibration_manager().assess(entry, path)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Archivo FITS no encontrado en el inventario.") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InventoryStaleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"No se pudo validar el diagnóstico de calibración: {type(exc).__name__}.",
        ) from exc


@router.get("/fits")
def list_local_fits(
    module: Optional[str] = Query(default=None),
    validation_status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    if module and module not in MODULE_NAMES:
        raise HTTPException(status_code=422, detail="Módulo consumidor no reconocido.")
    try:
        manifest = fits_inventory.load()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="El directorio de datos FITS local no está disponible.") from exc
    files = manifest.get("files", [])
    if module:
        files = [entry for entry in files if module in entry.get("consumers", [])]
    if validation_status:
        files = [entry for entry in files if entry.get("validation_status") == validation_status]
    total = len(files)
    summary_fields = {
        "file_id", "relative_path", "filename", "size_bytes", "sha256", "consumers",
        "product_type", "source", "downloaded_at", "ingested_at", "duplicate_of",
        "validation_status", "validation_warnings", "hdu_count", "observation",
        "release", "release_metadata_present", "has_celestial_wcs", "has_spectral_wcs",
        "has_table_data", "spherex_mef_extensions", "compatibility", "metadata_presence",
        "spatial_center", "spatial_wcs", "astrometric_validation_status",
        "spectral_channel_count",
    }
    page_entries = files[offset:offset + limit]
    summarized_files = []
    for entry in page_entries:
        summary = {key: value for key, value in entry.items() if key in summary_fields}
        if (
            entry.get("has_celestial_wcs")
            and entry.get("spherex_mef_extensions", {}).get("image") is not None
            and not summary.get("spatial_wcs")
        ):
            try:
                summary.update(fits_inventory.spatial_wcs_metadata(entry))
            except (OSError, KeyError, ValueError) as exc:
                raise HTTPException(
                    status_code=422,
                    detail="No se pudo interpretar el WCS espacial del producto local.",
                ) from exc
        summarized_files.append(summary)
    return {
        "dataset_root": manifest.get("dataset_root"),
        "generated_at": manifest.get("generated_at"),
        "total": total,
        "files": summarized_files,
    }


@router.get("/fits/{file_id}/download")
def download_local_fits(file_id: str) -> FileResponse:
    try:
        entry = fits_inventory.find(file_id)
        path = fits_inventory.get_path(entry)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Archivo FITS no encontrado en el inventario.") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InventoryStaleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type="application/fits",
        filename=Path(entry["filename"]).name,
        headers={"X-Content-SHA256": entry["sha256"] or ""},
    )


@router.get("/fits/{file_id}/preview")
def preview_local_fits(
    file_id: str,
    hdu: Optional[int] = Query(default=None, ge=0),
    plane: int = Query(default=0, ge=0),
) -> FileResponse:
    try:
        entry = fits_inventory.find(file_id)
        path = fits_inventory.get_path(entry)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Archivo FITS no encontrado en el inventario.") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InventoryStaleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if not entry.get("compatibility", {}).get("sky_preview", {}).get("compatible"):
        raise HTTPException(status_code=422, detail="El archivo no supera la validación para generar una previsualización.")
    image_exts = [
        item["index"]
        for item in entry.get("extensions", [])
        if item.get("shape") is not None and len(item["shape"]) in (2, 3)
    ]
    selected_hdu = hdu if hdu is not None else next(
        (item["index"] for item in entry.get("extensions", []) if item.get("name") == "IMAGE" and item["index"] in image_exts),
        image_exts[0] if image_exts else None,
    )
    if selected_hdu is None or selected_hdu not in image_exts:
        raise HTTPException(status_code=422, detail="El HDU solicitado no contiene una imagen o cubo compatible.")
    filename = f"{file_id}_hdu{selected_hdu}.png"
    output = Path(settings.SPHEREX_PROCESSED_DIR).resolve() / filename
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with fits.open(path, mode="readonly", memmap=True) as hdul:
            data = hdul[selected_hdu].data
            if data is None or data.ndim not in (2, 3) or not np.issubdtype(data.dtype, np.number):
                raise ValueError("El HDU seleccionado no es una imagen numérica 2D o un cubo 3D.")
            if data.ndim == 3:
                if plane >= data.shape[0]:
                    raise ValueError(f"El canal solicitado está fuera del rango 0–{data.shape[0] - 1}.")
                image = data[plane]
            else:
                if plane != 0:
                    raise ValueError("Una imagen 2D solo admite plane=0.")
                image = data
            image_renderer._array_to_stretched_png(image.astype(np.float64), str(output))
    except (OSError, ValueError, IndexError) as exc:
        safe_error = str(exc).replace(str(path), entry["filename"])
        raise HTTPException(status_code=422, detail=f"No se pudo renderizar este HDU: {safe_error}") from exc
    return FileResponse(
        output,
        media_type="image/png",
        headers={
            "X-FITS-File-ID": file_id,
            "X-FITS-HDU": str(selected_hdu),
            "X-FITS-PLANE": str(plane),
        },
    )


@router.get("/fits/{file_id}")
def get_local_fits_metadata(file_id: str) -> Dict[str, Any]:
    try:
        entry = fits_inventory.find(file_id)
        fits_inventory.get_path(entry)
        metadata = dict(entry)
        if (
            entry.get("has_celestial_wcs")
            and entry.get("spherex_mef_extensions", {}).get("image") is not None
            and not metadata.get("spatial_wcs")
        ):
            metadata.update(fits_inventory.spatial_wcs_metadata(entry))
        return metadata
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Archivo FITS no encontrado en el inventario.") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InventoryStaleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail="No se pudo interpretar el WCS espacial del producto local.",
        ) from exc


@router.get("/fits/{file_id}/spectral-profile")
def get_local_fits_spectral_profile(
    file_id: str,
    ra: float = Query(...),
    dec: float = Query(...),
) -> Dict[str, Any]:
    try:
        entry = fits_inventory.find(file_id)
        path = fits_inventory.get_path(entry)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Archivo FITS no encontrado en el inventario.") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InventoryStaleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not entry.get("compatibility", {}).get("spectral_profile", {}).get("compatible"):
        raise HTTPException(status_code=422, detail="El archivo no declara extensiones y calibración espectral compatibles.")
    try:
        calibration_profile = _calibration_manager().assess(entry, path)
        if entry.get("product_type") == "all_sky_spectral_cube":
            cube_profile = FITSProcessor.extract_spectral_profile_from_cube(
                str(path), ra=ra, dec=dec
            )
            coordinate_provenance = _coordinate_provenance(
                entry, cube_profile, ra=ra, dec=dec
            )
            measurements = cube_profile["measurements"]
            return {
                "file_id": file_id,
                "filename": entry["filename"],
                "relative_path": entry["relative_path"],
                "sha256": entry["sha256"],
                "product_type": entry["product_type"],
                "release": entry.get("release"),
                "ra": ra,
                "dec": dec,
                "pixel_x": cube_profile["pixel_x"],
                "pixel_y": cube_profile["pixel_y"],
                "astrometric_validation_status": coordinate_provenance[
                    "astrometric_validation_status"
                ],
                "coordinate_provenance": coordinate_provenance,
                "measurement_type": "Native spectral cube channel samples",
                "extraction_method": "3D WCS spatial lookup; tabulated wavelength channels; no interpolation",
                "algorithm_version": "FITSProcessor SPHEREx FLAGS Table 16 pixel-sample v1",
                "wavelength_source": cube_profile["wavelength_source"],
                "bandwidth_available": cube_profile["bandwidth_available"],
                "bandwidth_unit": cube_profile["bandwidth_unit"],
                "unit": cube_profile["unit"],
                "uncertainty_unit": cube_profile["uncertainty_unit"],
                "uncertainty_available": cube_profile["uncertainty_available"],
                "uncertainty_status": cube_profile["uncertainty_status"],
                "quality_status": cube_profile["quality_status"],
                "calibration_status": "partial_unverified_provenance",
                "calibration_profile": calibration_profile,
                "calibration_product_ids": calibration_profile["calibration_product_ids_used"],
                "valid_channel_count": cube_profile["valid_channel_count"],
                "channel_count": cube_profile["channel_count"],
                "measurements": measurements,
                "warnings": [
                    *coordinate_provenance["warnings"],
                    *(
                        ["No VARIANCE extension is present; uncertainties are unavailable."]
                        if not cube_profile["uncertainty_available"]
                        else []
                    ),
                    *list(dict.fromkeys(
                        warning
                        for item in measurements
                        for warning in item["quality_warnings"]
                    )),
                    "The file has no verified release metadata; this is not a full calibration validation.",
                    *calibration_profile["warnings"],
                ],
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "software_version": settings.VERSION,
            }
        spectral_wcs = calibration_profile["calibrations"]["spectral_wcs"]
        selected_product = spectral_wcs.get("selected_product")
        calibration_path = None
        if selected_product:
            calibration_root = Path(settings.SPHEREX_CALIBRATION_DIR).resolve()
            relative_calibration_path = Path(selected_product["relative_path"])
            if relative_calibration_path.is_absolute() or ".." in relative_calibration_path.parts:
                raise HTTPException(status_code=409, detail="La ruta de calibración asociada no es válida.")
            resolved_calibration_path = (calibration_root / relative_calibration_path).resolve()
            if calibration_root not in resolved_calibration_path.parents or not resolved_calibration_path.is_file():
                raise HTTPException(status_code=409, detail="El producto Spectral WCS asociado ya no está disponible.")
            calibration_path = str(resolved_calibration_path)
        point = FITSProcessor.extract_spectral_profile_from_mef(
            str(path),
            ra=ra,
            dec=dec,
            spectral_wcs_filepath=calibration_path,
        )
        coordinate_provenance = _coordinate_provenance(
            entry, point, ra=ra, dec=dec
        )
    except CoordinateOutsideImageError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "COORDINATE_OUTSIDE_IMAGE", "message": str(exc)},
        ) from exc
    except AstrometryBlockedError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "ASTROMETRY_BLOCKED", "message": str(exc)},
        ) from exc
    except InvalidSkyCoordinateError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_SKY_COORDINATE", "message": str(exc)},
        ) from exc
    except WCSProjectionError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "WCS_TRANSFORM_FAILED", "message": str(exc)},
        ) from exc
    except (OSError, KeyError, ValueError, IndexError) as exc:
        safe_error = str(exc).replace(str(path), entry["filename"])
        raise HTTPException(status_code=422, detail=f"No se pudo extraer un perfil válido: {safe_error}") from exc
    return {
        "file_id": file_id,
        "filename": entry["filename"],
        "relative_path": entry["relative_path"],
        "sha256": entry["sha256"],
        "product_type": entry.get("product_type"),
        "release": entry.get("release"),
        "ra": ra,
        "dec": dec,
        "pixel_x": point["pixel_x"],
        "pixel_y": point["pixel_y"],
        "detector": point["detector"],
        "astrometric_validation_status": coordinate_provenance[
            "astrometric_validation_status"
        ],
        "coordinate_provenance": coordinate_provenance,
        "measurement_type": "One-pixel MEF sample; not an integrated or absolutely flux-calibrated spectrum",
        "algorithm_version": "FITSProcessor SPHEREx FLAGS Table 16 pixel-sample v1",
        "extraction_method": (
            "Direct spatial WCS and direct CWAVE/CBAND pixel-map lookup; no interpolation"
            if calibration_path
            else "Direct spatial WCS and alternate WCS-W preliminary lookup; no interpolation"
        ),
        "wavelength_source": point["wavelength_source"],
        "bandwidth_available": point["bandwidth_um"] is not None,
        "bandwidth_unit": "um" if point["bandwidth_um"] is not None else None,
        "unit": point["unit"],
        "uncertainty_unit": point["uncertainty_unit"],
        "uncertainty_available": point["uncertainty_available"],
        "uncertainty_status": point["uncertainty_status"],
        "quality_status": point["quality_status"],
        "calibration_status": spectral_wcs["status"],
        "calibration_profile": calibration_profile,
        "calibration_product_ids": calibration_profile["calibration_product_ids_used"],
        "valid_channel_count": int(point["is_valid_measurement"]),
        "channel_count": 1,
        "measurements": [{
            "channel": 0,
            "wavelength_um": point["wavelength_um"],
            "bandwidth_um": point["bandwidth_um"],
            "flux": point["flux"],
            "flux_error": point["flux_error"],
            "flag": point["flag"],
            "is_valid_measurement": point["is_valid_measurement"],
            "measurement_status": point["measurement_status"],
            "uncertainty_status": point["uncertainty_status"],
            "quality_status": point["quality_status"],
            "flag_bits": point["flag_bits"],
            "flag_names": point["flag_names"],
            "excluded_flag_names": point["excluded_flag_names"],
            "unknown_flag_bits": point["unknown_flag_bits"],
            "quality_warnings": point["quality_warnings"],
        }],
        "warnings": [
            "This is one direct MEF measurement, not a stitched or fully calibrated spectrum.",
            *coordinate_provenance["warnings"],
            *point["quality_warnings"],
            *(
                ["CWAVE/CBAND wavelength calibration is associated, but this does not establish absolute photometric calibration."]
                if calibration_path
                else ["No compatible external Spectral WCS is associated; WCS-W is a preliminary display/extraction fallback."]
            ),
            *calibration_profile["warnings"],
        ],
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "software_version": settings.VERSION,
    }


@router.get("/fits/{file_id}/detections")
def detect_local_fits_sources(
    file_id: str,
    threshold_sigma: float = Query(default=5.0, gt=0.0, le=20.0),
) -> Dict[str, Any]:
    try:
        entry = fits_inventory.find(file_id)
        path = fits_inventory.get_path(entry)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Archivo FITS no encontrado en el inventario.") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InventoryStaleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not entry.get("compatibility", {}).get("source_detection", {}).get("compatible"):
        raise HTTPException(status_code=422, detail="El producto no tiene una imagen 2D con WCS celeste apta para detección individual.")
    try:
        with fits.open(path, mode="readonly", memmap=True) as hdul:
            image_hdu = hdul["IMAGE"]
            if image_hdu.data is None or image_hdu.data.ndim != 2:
                raise ValueError("IMAGE no es una imagen 2D.")
            image = np.asarray(image_hdu.data, dtype=np.float64)
            valid = np.isfinite(image)
            warnings_list = []
            if "FLAGS" in hdul:
                flags = hdul["FLAGS"].data
                if flags is None or flags.shape != image.shape:
                    raise ValueError("FLAGS no tiene las mismas dimensiones que IMAGE.")
                valid &= FITSProcessor.flags_usable_mask(flags)
            else:
                warnings_list.append("No hay una extensión FLAGS; no se aplicó máscara de calidad.")
            if "VARIANCE" in hdul:
                variance = hdul["VARIANCE"].data
                if variance is None or variance.shape != image.shape:
                    raise ValueError("VARIANCE no tiene las mismas dimensiones que IMAGE.")
                valid &= np.isfinite(variance) & (variance > 0)
            else:
                warnings_list.append("No hay una extensión VARIANCE; la incertidumbre no se usó.")
            spatial_wcs = build_spatial_wcs(image_hdu.header, fobj=hdul)
            clean_image = np.where(valid, image, np.nan)
        detections = TemporalEngine.detect_sources_in_epoch(
            clean_image,
            spatial_wcs.wcs,
            threshold_sigma=threshold_sigma,
        )
        calibration_profile = CalibrationManager(fits_inventory).assess(entry, path)
    except (OSError, KeyError, ValueError, IndexError) as exc:
        safe_error = str(exc).replace(str(path), entry["filename"])
        raise HTTPException(status_code=422, detail=f"No se pudo ejecutar la detección individual: {safe_error}") from exc
    return {
        "status": "experimental_single_image_detection",
        "file_id": file_id,
        "filename": entry["filename"],
        "relative_path": entry["relative_path"],
        "sha256": entry["sha256"],
        "astrometric_validation_status": spatial_wcs.astrometry_status,
        "spatial_wcs": spatial_wcs.provenance(),
        "threshold_sigma": threshold_sigma,
        "fwhm_px": 2.5,
        "method": "DAOStarFinder on IMAGE with FLAGS/VARIANCE pixel mask",
        "threshold_definition": (
            "threshold = threshold_sigma × sigma-clipped standard deviation of "
            "finite unmasked IMAGE pixels; this is not a variance-calibrated "
            "significance estimate"
        ),
        "candidate_scores_are_probabilities": False,
        "detections": [
            {
                "source_id": f"{entry['sha256'][:12]}:{item['x']:.3f}:{item['y']:.3f}",
                **item,
            }
            for item in detections
        ],
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "software_version": settings.VERSION,
        "calibration_profile": calibration_profile,
        "calibration_product_ids": calibration_profile["calibration_product_ids_used"],
        "warnings": warnings_list + list(spatial_wcs.warnings) + [
            "The requested sigma multiplier uses global IMAGE scatter; VARIANCE is used only to mask invalid pixels, not as the detection noise model.",
            "Single-image detections are experimental sources, not validated discoveries.",
            "No temporal association or astrophysical classification was performed.",
        ],
    }


@router.post("/fits/{file_id}/spectral-runs", status_code=201)
def create_local_spectral_run(
    file_id: str,
    ra: float = Query(...),
    dec: float = Query(...),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    result = get_local_fits_spectral_profile(file_id=file_id, ra=ra, dec=dec)
    entry = fits_inventory.find(file_id)
    run = save_scientific_run(
        db,
        run_type="spectral_extraction",
        entry=entry,
        parameters={
            "ra": ra,
            "dec": dec,
            "pixel_x": result["pixel_x"],
            "pixel_y": result["pixel_y"],
            "quality_masks": {
                "FLAGS": {
                    "excluded_bits": sorted(FITSProcessor.EXCLUDED_FLAG_BITS),
                    "unknown_bits": "classified unknown and not treated as valid",
                    "decoded_names": FITSProcessor.FLAG_NAMES,
                },
                "VARIANCE": "uncertainty is reported only when a finite positive variance with compatible units is present",
            },
        },
        result=result,
    )
    return {
        **result,
        "run_id": run.run_id,
        "result_sha256": run.result_sha256,
    }


@router.post("/fits/{file_id}/detection-runs", status_code=201)
def create_local_detection_run(
    file_id: str,
    threshold_sigma: float = Query(default=5.0, gt=0.0, le=20.0),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    result = detect_local_fits_sources(
        file_id=file_id,
        threshold_sigma=threshold_sigma,
    )
    entry = fits_inventory.find(file_id)
    run = save_scientific_run(
        db,
        run_type="source_detection",
        entry=entry,
        parameters={
            "threshold_sigma": threshold_sigma,
            "fwhm_px": result["fwhm_px"],
            "quality_masks": {
                "FLAGS": {
                    "excluded_bits": sorted(FITSProcessor.EXCLUDED_FLAG_BITS),
                    "unknown_bits": "excluded from processing",
                    "decoded_names": FITSProcessor.FLAG_NAMES,
                },
                "VARIANCE": "finite positive values are included in the validity mask, not used as the noise model",
            },
        },
        result=result,
    )
    return {
        **result,
        "run_id": run.run_id,
        "result_sha256": run.result_sha256,
    }


@router.get("/scientific-runs/{run_id}")
def get_scientific_run(
    run_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    run = db.query(ScientificRunModel).filter_by(run_id=run_id).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Scientific run not found.")
    return serialize_scientific_run(db, run)


@router.post("/scientific-runs/{run_id}/replay")
def replay_scientific_run(
    run_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    original = db.query(ScientificRunModel).filter_by(run_id=run_id).first()
    if original is None:
        raise HTTPException(status_code=404, detail="Scientific run not found.")
    try:
        entry = fits_inventory.find(original.file_id)
        fits_inventory.get_path(entry)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Source FITS is not in the local inventory.") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InventoryStaleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if entry.get("sha256") != original.source_sha256:
        raise HTTPException(status_code=409, detail="Source FITS hash differs from the original run.")

    parameters = dict(original.parameters)
    if original.run_type == "spectral_extraction":
        result = get_local_fits_spectral_profile(
            file_id=original.file_id,
            ra=float(parameters["ra"]),
            dec=float(parameters["dec"]),
        )
    elif original.run_type == "source_detection":
        result = detect_local_fits_sources(
            file_id=original.file_id,
            threshold_sigma=float(parameters["threshold_sigma"]),
        )
    else:
        raise HTTPException(status_code=409, detail="This scientific run type cannot be replayed.")

    replay = save_scientific_run(
        db,
        run_type=original.run_type,
        entry=entry,
        parameters=parameters,
        result=result,
    )
    return {
        "original_run_id": original.run_id,
        "replay_run_id": replay.run_id,
        "original_result_sha256": original.result_sha256,
        "replay_result_sha256": replay.result_sha256,
        "exact_match": original.result_sha256 == replay.result_sha256,
        "source_sha256": original.source_sha256,
        "validation_status": replay.validation_status,
    }
