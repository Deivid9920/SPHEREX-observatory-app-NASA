from datetime import datetime, timezone
from app.core.database import Base
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)


class ObservationModel(Base):
  """Registra metadatos de las observaciones FITS de SPHEREx consultadas desde IRSA."""

  __tablename__ = "observations"

  id = Column(Integer, primary_key=True, index=True)
  epoch_id = Column(String(100), unique=True, index=True, nullable=False)
  ra = Column(Float, nullable=False, index=True)
  dec = Column(Float, nullable=False, index=True)
  band_index = Column(Integer, nullable=False, index=True)
  file_path = Column(String(500), nullable=False)
  survey_version = Column(String(50), default="DR1/QR3")
  created_at = Column(DateTime, default=datetime.utcnow)


class DetectionCandidateModel(Base):
  """Almacena los candidatos a objetos móviles o variables detectados."""

  __tablename__ = "detection_candidates"

  id = Column(Integer, primary_key=True, index=True)
  candidate_code = Column(String(50), unique=True, index=True, nullable=False)
  ra = Column(Float, nullable=False)
  dec = Column(Float, nullable=False)
  category = Column(String(100), nullable=False)
  peak_z_score = Column(Float, nullable=False)
  epochs_involved = Column(JSON, nullable=False)
  metrics_summary = Column(JSON, nullable=True)
  is_verified = Column(Boolean, default=False)
  notes = Column(Text, nullable=True)
  created_at = Column(DateTime, default=datetime.utcnow)


class ScientificRunModel(Base):
  """Append-only provenance record for a local scientific processing run."""

  __tablename__ = "scientific_runs"

  run_id = Column(String(36), primary_key=True)
  run_type = Column(String(50), nullable=False, index=True)
  file_id = Column(String(100), nullable=False, index=True)
  source_filename = Column(String(500), nullable=False)
  source_relative_path = Column(String(1000), nullable=False)
  source_sha256 = Column(String(64), nullable=False, index=True)
  source_hdu = Column(Integer, nullable=False)
  parameters = Column(JSON, nullable=False)
  units = Column(JSON, nullable=False)
  quality_masks = Column(JSON, nullable=False)
  warnings = Column(JSON, nullable=False)
  calibration_product_ids = Column(JSON, nullable=False)
  processed_at = Column(DateTime(timezone=True), nullable=False)
  software_version = Column(String(100), nullable=False)
  algorithm_version = Column(String(200), nullable=False)
  validation_status = Column(String(40), nullable=False)
  result_sha256 = Column(String(64), nullable=False)
  result_json = Column(JSON, nullable=False)
  created_at = Column(
      DateTime(timezone=True),
      default=lambda: datetime.now(timezone.utc),
      nullable=False,
  )


class ScientificDetectionModel(Base):
  """One experimentally detected source associated with an immutable run."""

  __tablename__ = "scientific_detections"
  __table_args__ = (
      UniqueConstraint("run_id", "source_id", name="uq_scientific_detection_run_source"),
  )

  id = Column(Integer, primary_key=True)
  run_id = Column(
      String(36),
      ForeignKey("scientific_runs.run_id", ondelete="CASCADE"),
      nullable=False,
      index=True,
  )
  ordinal = Column(Integer, nullable=False)
  source_id = Column(String(100), nullable=False)
  x = Column(Float, nullable=False)
  y = Column(Float, nullable=False)
  ra = Column(Float, nullable=False)
  dec = Column(Float, nullable=False)
  flux = Column(Float, nullable=False)
  peak = Column(Float, nullable=False)
  sharpness = Column(Float, nullable=False)
  roundness = Column(Float, nullable=False)