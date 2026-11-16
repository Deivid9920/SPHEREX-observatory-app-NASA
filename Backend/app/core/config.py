from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


def _choose_existing_path(*candidates: str) -> Optional[str]:
  for candidate in candidates:
    path = Path(candidate).expanduser()
    if not path.is_absolute():
      path = (BASE_DIR / path).resolve()
    if path.exists():
      return str(path)
  return None


def _resolve_backend_path(value: Optional[str]) -> Optional[str]:
  if value is None:
    return None
  path = Path(value).expanduser()
  if path.is_absolute():
    return str(path)
  candidates = [str((BASE_DIR / path).resolve())]
  if path.parts and path.parts[0] == "data":
    if len(path.parts) >= 2 and path.parts[1] in {"raw", "calibration"}:
      candidates.insert(0, str((BASE_DIR / "app" / path).resolve()))
    if len(path.parts) >= 2 and path.parts[1] == "processed":
      candidates.insert(0, str((BASE_DIR / "app" / path).resolve()))
  return next((candidate for candidate in candidates if Path(candidate).exists()), candidates[0])


class Settings(BaseSettings):
  PROJECT_NAME: str = "SPHEREx Temporal Observatory API"
  VERSION: str = "1.0.0"
  API_V1_STR: str = "/api/v1"

  # URL pública del backend desplegado (ej. https://spherex-api.onrender.com)
  PUBLIC_BASE_URL: str = "http://127.0.0.1:8000"
  CORS_ORIGINS: str = "http://127.0.0.1:5173,http://127.0.0.1:3000,http://127.0.0.1:8443,http://localhost:5173,http://localhost:3000,http://localhost:8443"

  @property
  def cors_origins_list(self) -> list[str]:
    return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

  # PostgreSQL (soporta URL directa de Supabase/Render o variables individuales)
  DATABASE_URL: Optional[str] = None
  POSTGRES_SERVER: str = "localhost"
  POSTGRES_USER: str = "postgres"
  POSTGRES_PASSWORD: str = "postgres"
  POSTGRES_DB: str = "spherex_db"
  POSTGRES_PORT: int = 5432

  @property
  def SQLALCHEMY_DATABASE_URI(self) -> str:
    if self.DATABASE_URL:
      # SQLAlchemy 2.0 exige 'postgresql://' en lugar de 'postgres://'
      return self.DATABASE_URL.replace("postgres://", "postgresql://", 1)
    return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

  # Redis (soporta URL directa de Upstash o host/puerto)
  REDIS_URL: Optional[str] = None
  REDIS_HOST: str = "localhost"
  REDIS_PORT: int = 6379
  REDIS_DB: int = 0

  # Directorios locales para FITS y PNGs estáticos
  DATA_RAW_DIR: str = "./data/raw"
  DATA_PROCESSED_DIR: str = "./data/processed"
  SPHEREX_RAW_DIR: str = "./data/raw/spherex"
  SPHEREX_PROCESSED_DIR: str = "./data/processed/spherex"
  SPHEREX_MANIFEST_PATH: str = "./data/processed/spherex/fits-manifest.json"
  SPHEREX_CONSUMERS_PATH: str = "./fits-consumers.json"
  SPHEREX_CALIBRATION_DIR: str = "./data/calibration/spherex"

  def model_post_init(self, __context) -> None:
    default_raw = _choose_existing_path("./app/data/raw", "./data/raw")
    default_processed = _choose_existing_path("./app/data/processed", "./data/processed")
    raw_spherex = _choose_existing_path("./app/data/raw/spherex", "./data/raw/spherex")
    processed_spherex = _choose_existing_path("./app/data/processed/spherex", "./data/processed/spherex")
    manifest_path = _choose_existing_path(
        "./app/data/processed/spherex/fits-manifest.json",
        "./data/processed/spherex/fits-manifest.json",
    )
    if default_raw is not None:
      self.DATA_RAW_DIR = default_raw
    if default_processed is not None:
      self.DATA_PROCESSED_DIR = default_processed
    if raw_spherex is not None:
      self.SPHEREX_RAW_DIR = raw_spherex
    if processed_spherex is not None:
      self.SPHEREX_PROCESSED_DIR = processed_spherex
    if manifest_path is not None:
      self.SPHEREX_MANIFEST_PATH = manifest_path

    for field_name in (
        "DATA_RAW_DIR",
        "DATA_PROCESSED_DIR",
        "SPHEREX_RAW_DIR",
        "SPHEREX_PROCESSED_DIR",
        "SPHEREX_MANIFEST_PATH",
        "SPHEREX_CONSUMERS_PATH",
        "SPHEREX_CALIBRATION_DIR",
    ):
      value = getattr(self, field_name, None)
      if value is not None:
        setattr(self, field_name, _resolve_backend_path(value))

  model_config = SettingsConfigDict(
      case_sensitive=True,
      env_file=str(BASE_DIR / ".env"),
      extra="ignore",
  )


settings = Settings()