# SPHEREx Temporal Observatory

Astronomical exploration platform featuring a React/Vite frontend and a FastAPI backend. The project is organized into two independent applications to streamline installation, execution, and deployment.

## 1. Project Structure

```text
SPHEREx-temporal-observatory/
├── Frontend/
│   ├── public/                 # Static assets
│   ├── src/
│   │   ├── App.tsx              # Main interface
│   │   ├── fits.ts              # Frontend FITS reading/decoding
│   │   ├── index.css            # Global styles
│   │   └── main.tsx             # React entry point
│   ├── .figma/                  # Configuration used by Figma Make
│   ├── index.html
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── tsconfig.json
│   └── vite.config.ts
├── Backend/
│   ├── app/
│   │   ├── api/v1/endpoints/    # HTTP routes
│   │   ├── core/                # Configuration, cache, and database
│   │   ├── models/              # SQLAlchemy models
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── services/            # IRSA, FITS, rendering, and analysis
│   │   └── main.py              # FastAPI application and lifecycle
│   ├── data/
│   │   ├── raw/spherex/        # Raw FITS files (excluded from Git)
│   │   └── processed/spherex/  # Manifest and derived products
│   ├── tests/                  # Tests on synthetic temporal FITS
│   ├── fits-consumers.example.json
│   ├── .env.example
│   └── requirements.txt
├── .gitignore
└── README.md
```

The `node_modules` directories, Python bytecode, caches, and duplicate installation files were removed from the delivery package. Source files, public assets, Figma Make configuration, and the pnpm lockfile were preserved.

## 2. Prerequisites

- **Node.js:** 22.12.0 or later.
- **pnpm:** 10.34.3 (specified in `Frontend/package.json`).
- **Python:** 3.11 recommended.
- **PostgreSQL:** optional. If unavailable, the backend falls back to local SQLite.
- **Redis:** optional. If unavailable, caching falls back to local in-memory storage.

Python package versions are pinned in `Backend/requirements.txt`. Python 3.11 is recommended to maintain compatibility with the pinned versions of NumPy, SciPy, and Astropy.

## 3. Execution Order

The backend and frontend run in separate terminals.

### Step 1 — Install and Start the Backend

From the project root directory:

**Windows (PowerShell):**

```powershell
cd Backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Linux / macOS:**

```bash
cd Backend
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at:

- API: `http://localhost:8000`
- Interactive documentation: `http://localhost:8000/docs`
- Health status: `http://localhost:8000/health`

The backend automatically creates the `data/raw` and `data/processed` directories. You do not need to create them manually.

**Important:** Running Uvicorn from `Backend/` keeps relative paths for `.env`, `data/raw`, and `data/processed` consistent.

#### Adding Local FITS Files

Place the raw FITS files once inside `Backend/data/raw/spherex/`, organizing them into subdirectories if needed. Copy `Backend/fits-consumers.example.json` to `Backend/fits-consumers.json`: each path is relative to `data/raw/spherex` and can list multiple consumers. From `Backend/`, after copying FITS files or updating consumer assignments, rebuild the manifest with:

```powershell
python -m app.scripts.build_fits_inventory
```

The inventory maintains a single record per physical file, including its SHA-256 hash, HDU/WCS/checksum metadata, and assigned consumers. Raw files are excluded from Git; the backend can serve their original bytes over HTTP. PNG previews are derived products and do not replace the raw FITS files.

### Step 2 — Install and Start the Frontend

Open a second terminal from the project root directory:

```bash
cd Frontend
pnpm install --frozen-lockfile
pnpm dev
```

Vite uses port **8443** according to the current project configuration. Open:

`http://localhost:8443`

The backend is already configured to allow CORS requests from this local origin.
Configure `Frontend/.env` from `.env.example` before starting Vite; the default value works for local development.

### Step 3 — Build for Production

From `Frontend/`:

```bash
pnpm typecheck
pnpm build
pnpm preview
```

The compiled build artifacts are generated in `Frontend/dist/`.

## 4. Backend Environment Variables

Copy `Backend/.env.example` to `Backend/.env`. PostgreSQL and Redis variables are optional.

- `DATABASE_URL`: full PostgreSQL connection string.
- `POSTGRES_SERVER`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT`: individual connection fields alternative.
- `REDIS_URL`: Redis connection URL.
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`: individual connection fields alternative.
- `PUBLIC_BASE_URL`: public base URL of the backend.
- `CORS_ORIGINS`: exact allowed frontend origins, comma-separated; the example value permits `http://localhost:8443`.
- `DATA_RAW_DIR`: directory for downloaded FITS files.
- `DATA_PROCESSED_DIR`: directory for processed images.
- `SPHEREX_RAW_DIR`, `SPHEREX_PROCESSED_DIR`, `SPHEREX_MANIFEST_PATH`, `SPHEREX_CONSUMERS_PATH`: paths for local SPHEREx data and inventory files.

Do not commit real credentials to the repository.

## 5. Backend Execution Flow

1. `app.main` loads the configuration and initializes data directories.
2. FastAPI runs its lifespan startup: registers models, creates database tables, sets up indexes, and connects to Redis (or enables the in-memory fallback).
3. `app.api.v1.router` registers the endpoint groups.
4. Endpoints delegate operations to the IRSA, FITS, temporal analysis, and rendering services.
5. Processed visual outputs are saved in `data/processed` and served via `/static`.

## 6. Completed Checks and Scope

- Reorganized directory structure to avoid nested export paths.
- Consolidated backend dependencies into a single UTF-8 `requirements.txt` file.
- Preserved frontend dependencies and its `pnpm-lock.yaml`.
- Added `__init__.py` markers to make Python packages explicit.
- Added local port `8443` to allowed CORS origins, matching the configured Vite port.
- Updated Matplotlib/Pillow calls to replace deprecated APIs.
- Added installation, execution, and build instructions.

**Development Data:** `app/services/irsa_service.py` contains an explicitly synthetic FITS generation path for development purposes. It has not been substituted for, nor is it presented as, real NASA/IRSA downloads.

## 7. Frontend–Backend Integration

The centralized HTTP client in `Frontend/src/api/` uses native Fetch, types and validates expected response shapes, enforces request timeouts, and unifies HTTP, network, and JSON parsing errors. View requests can be aborted upon context changes; identical concurrent read requests without cancellation share the same in-flight promise.

Configure `Frontend/.env` from `Frontend/.env.example`:

```env
VITE_API_URL=http://localhost:8000
```

`VITE_API_URL` is public by design. Never store credentials or secrets in `VITE_` environment variables. In production deployments, set the public API URL for Vite and add the exact frontend origin to `CORS_ORIGINS` in `Backend/.env`; separate multiple origins with commas. Wildcards and regular expressions are not allowed for preview deployments.

### Module and Endpoint Matrix

| Module | Consumed Endpoint(s) | Mapping |
|---|---|---|
| Sky Explorer | `GET /api/v1/sky/regions/featured`; `GET /api/v1/sky/observations?ra=&dec=&fov_deg=` | Preloaded sky regions and observation metadata queried from IRSA. |
| Temporal Vision | `POST /api/v1/jobs/temporal`; `GET /api/v1/jobs/{job_id}` | Executes the WCS/FITS/Z-difference pipeline and presents derived PNG images, candidates, and metrics. |
| Spectral Analysis | `GET /api/v1/spectral/profile?ra=&dec=&fov_deg=` | Displays extracted spectral samples, wavelengths, flux, uncertainty, and observation metadata. |
| Object Detection | `POST /api/v1/jobs/temporal`; `GET /api/v1/jobs/{job_id}` | Detection is integrated into the temporal pipeline; there is no standalone detection endpoint. |
| Discovery Catalog | `GET /api/v1/detection/discoveries?limit=`; `GET /api/v1/detection/discoveries/{candidate_code}` | Lists and inspects evidence for candidates persisted by the pipeline. |

`GET /health` exists, but the UI connection status is verified by querying a live service endpoint (`/sky/regions/featured`). There is no endpoint for streaming raw FITS files to the browser: the backend downloads and processes MEF FITS files and delivers rendered PNGs as previews. Raw FITS files are not indiscriminately converted to JSON.

Legacy screens/controllers are retained with illustrative labeling. Panels labeled **Datos del Backend** (*Backend Data*) display real backend responses only; the pipeline's C-score is experimental and does not represent a calibrated probability. The backend does not provide persistent candidate validation, calibrated science images for Sky Explorer, or a standalone detection endpoint.

The detailed inventory of methods, parameters, response schemas, error handling, internal services, and status per module is available in [Frontend/docs/API-INTEGRATION.md](./Frontend/docs/API-INTEGRATION.md).

### Run and Verify

1. Start the Backend from `Backend/` on `http://localhost:8000` following Step 1.
2. Create `Frontend/.env`, install dependencies with `pnpm install --frozen-lockfile`, and run `pnpm typecheck`, `pnpm build`, and `pnpm dev` from `Frontend/`.
3. Open `http://localhost:8443`. In Sky Explorer, query observations for the current coordinates or select a backend-provided region. Temporal Vision requires two queryable observations; Spectral Analysis accepts a FOV between `0.01°` and `0.2°`.
4. Verify **Backend connected** status as well as loading, error, and empty states across each module. External access to NASA/IPAC is required to fetch observations and complete processing.

Jobs are stored in memory and are lost when the Backend restarts. Persisted candidates depend on the configured database and do not represent scientifically validated discoveries.

Local comparison requires compatible DR1/QR3 products, matching band, units, calibration, and compatible PSF, as well as an identical WCS grid. It does not resample the image or variance arrays; instead, it generates a 150-pixel cutout. The `fov_deg` and `band_index` parameters are not applied in this local operation. Local spectral extraction returns a sample without interpolation and preserves the original `BUNIT`; only current spectral endpoints—whose contract specifies `MJy/sr`—convert to that unit after validating the variance unit.

To run isolated synthetic FITS tests, install `pip install -r requirements-test.txt` with Python 3.11 from `Backend/` and run `python -m pytest`. There are currently no real FITS files in the workspace; these tests do not validate flight products or a scientific release.
