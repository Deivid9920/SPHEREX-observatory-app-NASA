import hashlib
import json
from datetime import datetime
from typing import Any, Dict
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.database_models import ScientificDetectionModel, ScientificRunModel


def scientific_result_digest(
    run_type: str,
    result: Dict[str, Any],
    parameters: Dict[str, Any] | None = None,
) -> str:
  if run_type == "spectral_extraction":
    digest_payload = {
        key: result.get(key)
        for key in (
            "file_id",
            "sha256",
            "ra",
            "dec",
            "pixel_x",
            "pixel_y",
            "detector",
            "astrometric_validation_status",
            "coordinate_provenance",
            "product_type",
            "release",
            "measurement_type",
            "extraction_method",
            "unit",
            "uncertainty_unit",
            "uncertainty_available",
            "uncertainty_status",
            "wavelength_source",
            "quality_status",
            "calibration_status",
            "calibration_product_ids",
            "software_version",
            "algorithm_version",
            "measurements",
            "warnings",
        )
    }
    digest_payload["run_parameters"] = parameters or {}
    coordinate_provenance = digest_payload.get("coordinate_provenance")
    if isinstance(coordinate_provenance, dict):
      stable_provenance = dict(coordinate_provenance)
      stable_provenance.pop("processed_at", None)
      digest_payload["coordinate_provenance"] = stable_provenance
    calibration_profile = result.get("calibration_profile") or {}
    spectral_wcs = calibration_profile.get("calibrations", {}).get("spectral_wcs", {})
    selected_product = spectral_wcs.get("selected_product") or {}
    digest_payload["calibration_fingerprint"] = {
        key: selected_product.get(key)
        for key in (
            "calibration_id",
            "filename",
            "sha256",
            "calibration_status",
        )
    }
  elif run_type == "source_detection":
    digest_payload = {
        key: result.get(key)
        for key in (
            "file_id",
            "sha256",
            "threshold_sigma",
            "threshold_definition",
            "detections",
        )
    }
  else:
    raise ValueError(f"Unsupported scientific run type: {run_type}")
  normalized_payload = json.loads(
      json.dumps(digest_payload, separators=(",", ":"), allow_nan=False)
  )
  canonical = json.dumps(
      normalized_payload,
      sort_keys=True,
      separators=(",", ":"),
      allow_nan=False,
  ).encode("utf-8")
  return hashlib.sha256(canonical).hexdigest()


def save_scientific_run(
    db: Session,
    *,
    run_type: str,
    entry: Dict[str, Any],
    parameters: Dict[str, Any],
    result: Dict[str, Any],
) -> ScientificRunModel:
  if not entry.get("sha256") or not result.get("processed_at"):
    raise ValueError("A scientific run requires a source SHA-256 and processing timestamp.")
  image_hdu = next(
      (item["index"] for item in entry.get("extensions", []) if item.get("name") == "IMAGE"),
      None,
  )
  if image_hdu is None:
    raise ValueError("The source manifest entry has no IMAGE HDU.")

  processed_at = datetime.fromisoformat(
      str(result["processed_at"]).replace("Z", "+00:00")
  )
  result_digest = scientific_result_digest(run_type, result, parameters)
  result_summary = dict(result)
  detections = result_summary.pop("detections", []) if run_type == "source_detection" else []

  run = ScientificRunModel(
      run_id=str(uuid4()),
      run_type=run_type,
      file_id=str(entry["file_id"]),
      source_filename=str(entry["filename"]),
      source_relative_path=str(entry["relative_path"]),
      source_sha256=str(entry["sha256"]),
      source_hdu=int(image_hdu),
      parameters=parameters,
      units={
          "measurement": result.get("unit"),
          "uncertainty": result.get("uncertainty_unit"),
      },
      quality_masks=parameters.get("quality_masks", {}),
      warnings=result.get("warnings", []),
      calibration_product_ids=list(result.get("calibration_product_ids", [])),
      processed_at=processed_at,
      software_version=str(result.get("software_version", settings.VERSION)),
      algorithm_version=(
          "photutils.DAOStarFinder; FWHM and threshold recorded"
          if run_type == "source_detection"
          else str(result.get("algorithm_version", "FITSProcessor spectral sample"))
      ),
      validation_status=(
          (
              "BLOCKED"
              if result.get("quality_status") in ("invalid", "unknown")
              else "PASS_WITH_LIMITATIONS"
          )
          if run_type == "spectral_extraction"
          else "PASS_WITH_LIMITATIONS"
      ),
      result_sha256=result_digest,
      result_json=result_summary,
  )
  db.add(run)
  db.flush()
  if detections:
    db.bulk_insert_mappings(
        ScientificDetectionModel,
        [
            {
                "run_id": run.run_id,
                "ordinal": ordinal,
                "source_id": item["source_id"],
                "x": item["x"],
                "y": item["y"],
                "ra": item["ra"],
                "dec": item["dec"],
                "flux": item["flux"],
                "peak": item["peak"],
                "sharpness": item["sharpness"],
                "roundness": item["roundness"],
            }
            for ordinal, item in enumerate(detections)
        ],
    )
  db.commit()
  db.refresh(run)
  return run


def serialize_scientific_run(db: Session, run: ScientificRunModel) -> Dict[str, Any]:
  result = dict(run.result_json)
  if run.run_type == "source_detection":
    detections = (
        db.query(ScientificDetectionModel)
        .filter_by(run_id=run.run_id)
        .order_by(ScientificDetectionModel.ordinal)
        .all()
    )
    result["detections"] = [
        {
            "source_id": item.source_id,
            "x": item.x,
            "y": item.y,
            "ra": item.ra,
            "dec": item.dec,
            "flux": item.flux,
            "peak": item.peak,
            "sharpness": item.sharpness,
            "roundness": item.roundness,
        }
        for item in detections
    ]
  return {
      "run_id": run.run_id,
      "run_type": run.run_type,
      "source": {
          "file_id": run.file_id,
          "filename": run.source_filename,
          "relative_path": run.source_relative_path,
          "sha256": run.source_sha256,
          "hdu": run.source_hdu,
      },
      "parameters": run.parameters,
      "units": run.units,
      "quality_masks": run.quality_masks,
      "warnings": run.warnings,
      "calibration_product_ids": run.calibration_product_ids,
      "processed_at": run.processed_at.isoformat(),
      "software_version": run.software_version,
      "algorithm_version": run.algorithm_version,
      "validation_status": run.validation_status,
      "result_sha256": run.result_sha256,
      "result": result,
  }
