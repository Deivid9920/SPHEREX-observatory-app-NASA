# FASE 4.6 — Matriz de integración y endpoints

Estados: `PASS`, `PASS_WITH_LIMITATIONS`, `BLOCKED`, `NOT_TESTED`, `DEMO_ONLY`.

## Flujos integrados

| Flujo | Ruta efectiva | Prueba/evidencia | Estado | Limitaciones/criterio |
|---|---|---|---|---|
| Inventario e ingesta | FITS local → manifiesto SHA-256 → `GET /api/v1/data/fits` → filtro por consumidor en React | 45 pruebas backend pasan; manifiesto confirma 10 productos/10 hashes. Fase 4.4 verificó inventario desde navegador. | `PASS_WITH_LIMITATIONS` | No descarga ni clasifica release de forma autónoma; release ausente queda desconocida. |
| Preview astronómico | selector local → `GET /api/v1/data/fits/{id}/preview` → HDU IMAGE → renderer → PNG | Fase 4.4 verificó previews reales con IDs/hash de producto. | `PASS_WITH_LIMITATIONS` | Render PNG y WCS estructural no demuestran precisión astrométrica absoluta (`ASTROMETRY_UNVALIDATED`). |
| Diagnóstico de producto | `GET /api/v1/data/fits/{id}` y `/calibration` → `FitsInventory`/`CalibrationManager` | Tests de inventario y calibración; integración visible en panel de backend. | `PASS_WITH_LIMITATIONS` | Provenance de release no comprobada; calibración global queda parcial. |
| Espectro del cubo | `POST /api/v1/data/fits/{id}/spectral-runs` → `FITSProcessor` → `SPECTRAL_CHANNELS` y WCS 3D → persistencia | Fase 4.4: 102 canales, 91 válidos; GET/replay con digest idéntico. Suite backend actual: PASS. | `PASS_WITH_LIMITATIONS` | No hay VARIANCE; incertidumbres/significancia no disponibles. |
| Muestra espectral MEF | selección MEF → asociación WCS D1/D2 por detector/grilla → CWAVE/CBAND (o fallback WCS-W explicitado) → run persistido | Tests FITS/calibración; código valida unidad, flags, grilla y producto de calibración. | `PASS_WITH_LIMITATIONS` | Una muestra/píxel, no espectro integrado ni fotometría absoluta; release sigue sin verificar. |
| Detección local | `POST /api/v1/data/fits/{id}/detection-runs` → `IMAGE` + FLAGS/VARIANCE máscara → DAOStarFinder → `ScientificRun` y detecciones | Fase 4.4 ejecutó detección real, replay persistente; endpoint declara método y limitaciones. | `PASS_WITH_LIMITATIONS` | VARIANCE solo enmascara valores inválidos; umbral es dispersión global. No hay FPR/recall, injection/recovery ni ePSF aplicado. |
| Persistencia de ejecuciones locales | `scientific_runs`, `scientific_detections`; GET y replay verifican hash de entrada | 45 pruebas backend incluyen persistencia; Fase 4.4 verificó replay tras reinicio. | `PASS_WITH_LIMITATIONS` | Probado en SQLite local, no en PostgreSQL de producción. |
| Comparación remota de épocas | búsqueda `/api/v1/sky/observations` → `POST /api/v1/jobs/temporal` → IRSA, reproyección/diferencia | Fase 4.4 registró IRSA 502/timeout. | `BLOCKED` | No existe resultado real de comparación; datos demo no participan en el camino científico. |
| Comparación FITS local | selector de dos FITS compatibles → `POST /api/v1/jobs/temporal/local` → guardas WCS/PSF/unidad/release/varianza | Inventario filtró 0 productos locales temporalmente elegibles; UI muestra bloqueo y no ejecuta diferencia. | `BLOCKED` | No iniciar comparación hasta obtener un par realmente comparable y validado. |
| Catálogo de descubrimientos | `DetectionCandidateModel` → `GET /api/v1/detection/discoveries` y `/{candidate_code}` | Endpoints probados en API; evidencia Fase 4.4: catálogo bloqueado en modo Observatorio. | `BLOCKED` | Solo el pipeline temporal escribe ese modelo; las detecciones `ScientificDetectionModel` no se conectan. Falta evidencia/procedencia para promoción. |
| Interfaz Observatorio (datos reales) | React/Vite → cliente API tipado/validado → endpoints locales/IRSA → estados de error/vacío | Fase 4.4: navegador real, inventario, previews, análisis, persistencia y bloqueos visibles. | `PASS_WITH_LIMITATIONS` | E2E reproducible automatizado no está definido; consulta IRSA falla externamente. |
| Interfaz conceptual demo | `dataMode="demo"` → arrays/valores ilustrativos en `App.tsx` | Código rotula modo, banner, candidatos y valores como simulados/ilustrativos; no son respuestas científicas. | `DEMO_ONLY` | No usar los valores ni scores como observaciones SPHEREx. |
| Pruebas automáticas de navegador | no hay `test`, `e2e` ni Playwright script en `Frontend/package.json` | Orquestador registra `browser-e2e` como `not_run`; pruebas manuales anteriores están citadas por separado. | `NOT_TESTED` | Requiere harness automatizado antes de poder reclamar E2E repetible. |

## Matriz de endpoints y consumidores

| Endpoint | Responsable | Consumidor actual | Resultado en este corte | Estado |
|---|---|---|---|---|
| `GET /api/v1/data/fits` | `endpoints/data.py`, `FitsInventory` | `Frontend/src/api/fits.ts`, panel de inventario | 10 FITS; integridad 10/10 | `PASS_WITH_LIMITATIONS` |
| `GET /api/v1/data/fits/{id}` | `data.py`, `FitsInventory` | `getFitsMetadata` en UI local | Metadatos/HDU/WCS/calidad | `PASS_WITH_LIMITATIONS` |
| `GET /api/v1/data/fits/{id}/preview` | `data.py`, `ImageRenderer` | preview local | PNG basado en el HDU elegido | `PASS_WITH_LIMITATIONS` |
| `GET /api/v1/data/fits/{id}/download` | `data.py` | vínculo de descarga en panel local | FITS fuente servido con encabezado de SHA | `PASS_WITH_LIMITATIONS` |
| `GET /api/v1/data/fits/{id}/detections` | `data.py` | No se identificó un consumidor frontend; el UI usa `POST .../detection-runs` | Ruta GET no probada E2E | `NOT_TESTED` |
| `GET /api/v1/data/fits/{id}/calibration` | `data.py`, `CalibrationManager` | diagnóstico por producto desde el panel local | Perfil parcial y avisos | `PASS_WITH_LIMITATIONS` |
| `GET /api/v1/data/calibrations` | `data.py`, `CalibrationManager` | No se identificó un consumidor frontend | Catálogo backend disponible, no probado E2E | `NOT_TESTED` |
| `POST /api/v1/data/fits/{id}/spectral-runs` | `data.py`, `FITSProcessor`, `ScientificRun` | muestra espectral local | Cubo/MEF con provenance y persistencia | `PASS_WITH_LIMITATIONS` |
| `GET /api/v1/data/fits/{id}/spectral-profile` | `data.py` | No se identificó llamada UI en las rutas locales actuales (usan `spectral-runs`) | Ruta legacy redundante/no verificada como consumida | `NOT_TESTED` |
| `POST /api/v1/data/fits/{id}/detection-runs` | `data.py`, `TemporalEngine` | AstroVision local | Detección experimental sobre imagen real | `PASS_WITH_LIMITATIONS` |
| `GET /api/v1/data/scientific-runs/{id}`, `POST .../{id}/replay` | `data.py`, `scientific_results` | controles recuperar ejecución/replay | Persistencia local demostrada | `PASS_WITH_LIMITATIONS` |
| `GET /api/v1/sky/regions/featured` | `sky.py` | llamada de arranque UI | API conecta; regiones solo alimentan contexto demo | `PASS_WITH_LIMITATIONS` |
| `GET /api/v1/sky/observations` | `sky.py`, `IRSAClient` | botón de búsqueda remota | IRSA 502/timeout en prueba previa | `BLOCKED` |
| `GET /api/v1/spectral/profile` | `spectral.py`, `IRSAClient` | modo remoto/demo; modo Observatorio usa runs FITS locales | Dependencia externa no validada por el flujo local | `BLOCKED` |
| `POST /api/v1/temporal/compare` | `temporal.py` | no se identificó consumidor frontend directo; el UI usa `/jobs/temporal` | Ruta síncrona no probada E2E en este corte | `NOT_TESTED` |
| `POST /api/v1/jobs/temporal` y `GET /jobs/{job_id}` | `jobs.py`, `temporal.py` | comparación IRSA en UI | No hay dos observaciones accesibles; proceso de jobs en memoria | `BLOCKED` |
| `POST /api/v1/jobs/temporal/local` | `jobs.py`, `execute_local_temporal_pipeline` | comparación local en UI | El inventario tiene 0 elegibles; no se ejecutó | `BLOCKED` |
| `GET /api/v1/detection/discoveries[/{code}]` | `detection.py`, `DetectionCandidateModel` | UI al recuperar candidatos tras análisis; lista en modo demo | Sin catálogo científico local elegible; detecciones no conectadas | `BLOCKED` |

## Matriz de persistencia

| Dato | Repositorio/tabla | Persistencia verificada | Observación |
|---|---|---|---|
| Originales FITS | `app/data/raw/spherex/` | Hashes comparados con manifiesto | Inmutables durante esta fase. |
| Inventario/metadatos | `fits-manifest.json` | Leído, no regenerado | 10 entradas; hash del manifiesto se registra en JSON de estado. |
| Resultados espectrales y detección individual | `scientific_runs`; `scientific_detections` | GET/replay probados en Fase 4.4; 45 tests pasan | SQLite local; incluye SHA de fuente/resultado, parámetros, warnings y calibraciones. |
| Candidatos temporales | `detection_candidates` | Endpoints y modelo existen | No es una persistencia de detecciones individuales ni de holdout astrométrico; sin promoción actual. |
| PNG derivados | `data/processed`/`/static` | Se generaron en la Fase 4.4 | Son visualizaciones derivadas, no reemplazan FITS fuente. |
| Caché | Redis o memoria | Redis no disponible; fallback documentado | Fallback volátil. |
| Base de datos | PostgreSQL o SQLite | PostgreSQL no validado, SQLite sí | No declarar equivalencia entre modos. |

## Capturas y logs

- Pruebas actuales: [`validation_report.md`](../../reports/latest/validation_report.md), [`validation_results.json`](../../reports/latest/validation_results.json), logs por ejecución en `../../reports/latest/test_logs/`.
- E2E manual anterior: capturas referenciadas desde [`FASE4_4_VALIDACION_CIENTIFICA.md`](./FASE4_4_VALIDACION_CIENTIFICA.md).
- Estado estructurado de las capacidades: [`FASE4_6_MODULE_STATUS.json`](./FASE4_6_MODULE_STATUS.json).
