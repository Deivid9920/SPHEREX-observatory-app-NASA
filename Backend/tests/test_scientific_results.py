from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.database_models import ScientificDetectionModel, ScientificRunModel
from app.services.scientific_results import (
    save_scientific_run,
    serialize_scientific_run,
)


def test_detection_runs_preserve_each_source_and_append_history() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        entry = {
            "file_id": "fits-1",
            "filename": "image.fits",
            "relative_path": "image.fits",
            "sha256": "a" * 64,
            "extensions": [{"index": 1, "name": "IMAGE"}],
        }
        source = {
            "source_id": "a" * 12 + ":4.000:5.000",
            "x": 4.0,
            "y": 5.0,
            "ra": 120.0,
            "dec": 10.0,
            "flux": 12.5,
            "peak": 2.5,
            "sharpness": 0.6,
            "roundness": 0.1,
        }
        result = {
            "status": "experimental_single_image_detection",
            "file_id": "fits-1",
            "sha256": "a" * 64,
            "threshold_sigma": 5.0,
            "threshold_definition": "global scatter; not calibrated significance",
            "fwhm_px": 2.5,
            "method": "DAOStarFinder",
            "candidate_scores_are_probabilities": False,
            "detections": [source],
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "software_version": "test",
            "warnings": ["Experimental only."],
        }

        first = save_scientific_run(
            db,
            run_type="source_detection",
            entry=entry,
            parameters={"threshold_sigma": 5.0, "quality_masks": {"FLAGS": "valid flags"}},
            result=result,
        )
        recovered = serialize_scientific_run(db, first)

        assert db.query(ScientificDetectionModel).filter_by(run_id=first.run_id).count() == 1
        assert recovered["source"]["sha256"] == entry["sha256"]
        assert recovered["result"]["detections"] == [source]
        assert recovered["result_sha256"] == first.result_sha256

        second = save_scientific_run(
            db,
            run_type="source_detection",
            entry=entry,
            parameters={"threshold_sigma": 5.0, "quality_masks": {"FLAGS": "valid flags"}},
            result=result,
        )
        assert second.run_id != first.run_id
        assert db.query(ScientificRunModel).count() == 2
        assert db.query(ScientificDetectionModel).filter_by(run_id=first.run_id).count() == 1
    engine.dispose()
