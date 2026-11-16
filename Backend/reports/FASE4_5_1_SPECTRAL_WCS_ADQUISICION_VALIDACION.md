# Fase 4.5.1 — Adquisición y validación de Spectral WCS

**Estado global: PASS_WITH_LIMITATIONS**

Se localizaron y descargaron los productos oficiales de Spectral WCS para los dos detectores presentes en los nueve MEF locales. El CalibrationManager valida su integridad y la correspondencia de todos los puntos de control declarados en WCS-WAVE con las posiciones homólogas de CWAVE/CBAND. Esto no equivale a una comparación independiente de cada píxel del detector. Spectral Analysis usa CWAVE/CBAND por consulta directa en el índice de píxel seleccionado cuando la comparación de controles pasa. El estado permanece parcial porque los MEF no identifican explícitamente su release y no se puede afirmar una asociación de release completa ni calibración fotométrica absoluta.

## 1. Fuentes oficiales y adquisición

Fuentes consultadas:

- [IRSA SPHEREx Data Access](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-access/)
- [IRSA SPHEREx Data Products](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-products/)
- [SPHEREx Explanatory Supplement](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp.pdf)

Los directorios de calibración on-prem consultados no estaban disponibles (HTTP 404). Se utilizó el acceso S3 oficial documentado por IRSA, no SIA2. El listado de `dr1/spectral_wcs/` ofreció el directorio `cal-swcs-v5-2026-191/`; se obtuvieron únicamente D1 y D2, requeridos por los productos locales. No se descargaron calibraciones para D3–D6.

`HEAD` sobre ambos objetos devolvió HTTP 200 y confirmó tamaño, ETag y fecha de modificación:

| Detector | Producto oficial | Tamaño | ETag S3 | Última modificación | SHA-256 local |
|---|---|---:|---|---|---|
| 1 | `spectral_wcs_D1_spx_cal-swcs-v5-2026-191.fits` | 33,312,960 bytes | `624790eba5fdde40a6cb2187099e415d` | 2026-11-11 14:08:11 GMT | `44fb48b236e25a99d42c8986da0064cc58359527e1fc76e182eda52371a1ae23` |
| 2 | `spectral_wcs_D2_spx_cal-swcs-v5-2026-191.fits` | 33,312,960 bytes | `af87630c33716cd77ae54ab6c63d388d` | 2026-11-11 14:08:11 GMT | `0eb4e27f351e6161e21372818f9e811480a7ab8bab9295722f180791e151a463` |

Los archivos están separados de los originales en `app/data/calibration/spherex/spectral_wcs/`. Su procedencia y hashes se guardan en [`spectral-wcs-manifest.json`](../app/data/calibration/spherex/spectral_wcs/spectral-wcs-manifest.json). Los dos objetos contienen `PRIMARY`, `CWAVE`, `CBAND` y `WCS-WAVE`; los mapas son 2040×2040, `CWAVE` y `CBAND` declaran `um`, y no se encontraron valores no finitos o no positivos. Los FITS oficiales no incluyen CHECKSUM/DATASUM en todos los HDUs; la integridad local se contrasta con SHA-256 del manifiesto de adquisición. El ETag se registra como metadato de origen, no como sustituto del SHA-256.

## 2. Inventario y asociación por MEF

Los nueve productos son imágenes MEF 2040×2040 con detector y fecha extraídos del nombre L2B. La versión `l2b-v27` y la fecha L2B no se equiparan literalmente a `cal-swcs-v5-2026-191`: son identificadores de productos distintos. La asociación usa detector, estructura/unidades, integridad, y la comparación directa de los controles WCS-WAVE del MEF con los mapas oficiales. No se infiere un release que no esté en los headers.

`X` e `Y` de WCS-WAVE están en coordenadas FITS 1-based; los mapas se consultan mediante `[Y-1, X-1]`. Los 81 puntos de control D1 y los 121 puntos de D2 coinciden con `CWAVE` y `CBAND` con diferencia máxima observada **0.0 µm** en ambos campos para los nueve MEF. Se comparó cada control; no se interpolaron mapas ni se ajustaron dimensiones.

| FITS MEF | Detector / proc. | SHA-256 del original | Controles | Δ máx. CWAVE / CBAND (µm) | Calibración asociada |
|---|---|---|---:|---:|---|
| `level2_2025W28_1B_0001_1D1_spx_l2b-v27-2026-215.fits` | D1 / 2026-215 | `ed8debec7bf19f4d9c92375f139176b5c9c7ced628a59a598179d7869441c296` | 81 | 0 / 0 | `cal-2bd2033d8dbb41db68e62577` · D1 |
| `level2_2025W28_1B_0002_1D1_spx_l2b-v27-2026-215.fits` | D1 / 2026-215 | `9bbf5ff345c36c0f95689a856f788562e48bc56fe792a558c1cbc4a16b195bde` | 81 | 0 / 0 | `cal-2bd2033d8dbb41db68e62577` · D1 |
| `level2_2025W28_1B_0003_1D1_spx_l2b-v27-2026-215.fits` | D1 / 2026-215 | `1e7318b504635f0de620de975e5109a5b83aca560fd07096a4ec881d32a733a2` | 81 | 0 / 0 | `cal-2bd2033d8dbb41db68e62577` · D1 |
| `level2_2025W25_1B_0429_1D1_spx_l2b-v27-2026-213.fits` | D1 / 2026-213 | `921b24805a3213467ef6a8502bb4af4231be78f4bd1b99802b52609c7d83d28c` | 81 | 0 / 0 | `cal-2bd2033d8dbb41db68e62577` · D1 |
| `level2_2025W17_4B_0001_1D1_spx_l2b-v27-2026-196.fits` | D1 / 2026-196 | `b2b78466058203dbabcf841b6223697e7e69b08b18a00882c764c6f8fd0acd59` | 81 | 0 / 0 | `cal-2bd2033d8dbb41db68e62577` · D1 |
| `level2_2025W17_4B_0001_1D2_spx_l2b-v27-2026-196.fits` | D2 / 2026-196 | `3d51d09b5a8653b21ec0bbdaffa923545af8bdb5af4b4a2b42fe260b4f5a3b9a` | 121 | 0 / 0 | `cal-6747e7384946891cca8b541a` · D2 |
| `level2_2025W18_1B_0001_1D1_spx_l2b-v27-2026-196.fits` | D1 / 2026-196 | `64113e82f4357303d9a595e384a51cd1e021e74c3ce81443d31ee74d42f8619a` | 81 | 0 / 0 | `cal-2bd2033d8dbb41db68e62577` · D1 |
| `level2_2025W30_1B_0001_1D1_spx_l2b-v27-2026-220.fits` | D1 / 2026-220 | `6b0061a1bea9539b4fe4ae288911c770d08b058ac900a068ddb28490192cc3a6` | 81 | 0 / 0 | `cal-2bd2033d8dbb41db68e62577` · D1 |
| `level2_2025W42_1A_0001_1D1_spx_l2b-v27-2026-243.fits` | D1 / 2026-243 | `bfcd10b34d3222855ea9cd92b6e103e56b90949d92c399f8a5d36a608c0d970e` | 81 | 0 / 0 | `cal-2bd2033d8dbb41db68e62577` · D1 |

**Estado de asociación de los nueve: `partially_verified`.** La identidad de detector y la correspondencia de mapas están comprobadas, pero el release del MEF no está explícito en sus metadatos. El estado no se eleva a `verified` por el solo hecho de descargar el auxiliar. La tolerancia implementada es `1e-5 µm` (0.01 nm), solo para la representación de punto flotante de los valores tabulados; no es una tolerancia de interpolación espacial. Todas las comparaciones de controles dieron cero.

## 3. CalibrationManager y extracción

Cambios:

- `Settings.SPHEREX_CALIBRATION_DIR` resuelve el directorio independiente de calibración.
- CalibrationManager descubre `cal-swcs`, lee el manifiesto de procedencia, calcula SHA-256, valida tamaño, detector, HDUs, unidades, valores finitos/positivos y controles WCS-WAVE.
- La selección rechaza detectores incompatibles, hashes/tamaños incorrectos, controles discordantes y más de un candidato compatible. La asociación queda registrada por identificador estable y conserva su estado parcial.
- `FITSProcessor.extract_spectral_profile_from_mef()` acepta un archivo Spectral WCS asociado y lee CWAVE/CBAND directamente en el píxel seleccionado. Si no hay asociación, mantiene la salida WCS-W preliminar.
- `/api/v1/data/fits/{file_id}/spectral-profile` y `/spectral-runs` devuelven fuente espectral, ancho de banda, hash/ID del original, ID/hash/estado del auxiliar, incertidumbre, banderas y advertencias.
- Spectral Analysis distingue una extracción MEF de un píxel de un espectro integrado y advierte que CWAVE/CBAND no implican calibración fotométrica absoluta. Las ejecuciones mantienen la procedencia y los IDs de calibración para recuperación.

Las pruebas nuevas incluyen asociación externa, discrepancia de detector, ambigüedad, comparación de control-píxel, lookup directo CWAVE/CBAND y persistencia/recuperación del perfil.

## 4. Ejecución y evidencia

### Servidores y HTTP

No había procesos escuchando en 8000/8443 antes del arranque. Se iniciaron:

```powershell
cd Backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

cd Frontend
pnpm dev --host 127.0.0.1 --port 8443
```

Resultados HTTP observados:

| Solicitud | Resultado |
|---|---|
| `GET http://127.0.0.1:8000/health` | 200 JSON |
| `GET http://127.0.0.1:8000/docs` | 200 HTML |
| `GET /api/v1/data/calibrations` | 200; dos auxiliares identificados y parcialmente validados |
| `GET /api/v1/data/fits?module=spectral_analysis` | 200; 10 FITS, incluidos nueve MEF |
| `GET /api/v1/data/fits/{id}/calibration` | 200 para los nueve MEF |
| `POST /api/v1/data/fits/{id}/spectral-runs` | 201 en pruebas de navegador D1 y D2 |
| `GET /api/v1/data/scientific-runs/{run_id}` | 200; recuperó hashes de origen, calibración y resultado |
| CORS con origen `http://127.0.0.1:8443` | 200; `Access-Control-Allow-Origin` coincide con el origen |
| `GET /` | 404; no hay ruta raíz configurada. `/health` y `/docs` sí responden. |

### Navegador real

Se abrió `http://127.0.0.1:8443/` en el navegador, en modo **Observatorio**. La interfaz cargó el inventario real de 10 productos y el preview FITS local. En Spectral Analysis se seleccionó un MEF D1 y luego se cambió a D2; el producto, el ID/hash de calibración y el valor espectral cambiaron junto con la selección. Los dos POST de navegador recibieron 201. En el recorrido de recarga/cambio de módulo no se observaron errores de consola ni errores de página; las solicitudes canceladas por la navegación fueron abortos de solicitudes previas, seguidas de respuestas 200 del inventario.

Resultados visibles de los perfiles:

- D1: archivo `level2_2025W28_1B_0001_1D1_spx_l2b-v27-2026-215.fits`, píxel válido (1018, 1020), CWAVE `0.9042640924 µm`, CBAND `0.0233631600 µm`, flujo `0.5714768171 MJy/sr`, incertidumbre `0.0268891384 MJy/sr`, FLAGS `2097152`, estado `partially_verified`.
- D2: archivo `level2_2025W17_4B_0001_1D2_spx_l2b-v27-2026-196.fits`, píxel válido (1019, 1019), CWAVE `1.3376700878 µm`, CBAND `0.0321996361 µm`, flujo `0.2325007468 MJy/sr`, incertidumbre `0.0172795790 MJy/sr`, FLAGS `2097152`, estado `partially_verified`.

Los perfiles de navegador se guardaron como:

- [Spectral Analysis — detector 1](./evidence/phase451-spectral-wcs-detector1.png)
- [Spectral Analysis — detector 2](./evidence/phase451-spectral-wcs-detector2.png)

Además, se ejecutó el endpoint de perfil en los nueve MEF usando un píxel válido cercano al centro de cada imagen; los nueve devolvieron CWAVE/CBAND del auxiliar correcto. Los intentos iniciales en el centro geométrico de tres MEF dieron HTTP 422 porque FLAGS marcaba ese píxel inválido; al cambiar a píxeles válidos el endpoint respondió correctamente. No se trataron esos píxeles enmascarados como resultados científicos.

### Preservación de los originales y pruebas

El cálculo SHA-256 de los **10 FITS originales** coincide con las entradas del manifiesto local. No se modificaron los originales. Hash del cubo incluido en esa verificación: `a595a4511dc0b63e0a4c1fb3d0a7735317f17ebf1d11d774888b2566bdb870bc`.

| Comando | Resultado |
|---|---|
| `python -m compileall -q app` | PASS, exit code 0 |
| `python -m pytest -q` | PASS, 35 passed, exit code 0 (22 warnings de dependencias/Astropy) |
| `pnpm typecheck` | PASS, exit code 0 |
| `pnpm build` | PASS, exit code 0 |
| Verificación de hashes de los 10 originales | PASS, 10/10 coinciden con el manifiesto |
| Validación de estructura e integridad de los dos auxiliares | PASS_WITH_LIMITATIONS |
| Comparación WCS-WAVE ↔ CWAVE/CBAND de los nueve MEF | PASS, 9/9; delta máximo 0 µm en controles |
| Extracción real de nueve perfiles y E2E visual D1/D2 | PASS_WITH_LIMITATIONS |

## 5. Estado por capacidad y limitaciones

| Capacidad | Estado | Evidencia / limitación |
|---|---|---|
| Adquisición oficial de calibraciones D1/D2 | PASS_WITH_LIMITATIONS | URLs oficiales, HEAD, tamaño, ETag, SHA-256 y estructura FITS comprobados. |
| Asociación de los nueve MEF | PASS_WITH_LIMITATIONS | Detector/grilla y todos los controles coinciden; release local del MEF no identificado. |
| Lectura científica directa CWAVE/CBAND | PASS_WITH_LIMITATIONS | Extracción sin interpolar en los nueve productos; valores, unidades y FLAGS devueltos. |
| Perfil espectral fotométricamente absoluto o integrado | NOT_TESTED | Fuera de lo que demuestran estos mapas; el resultado es una muestra de flujo superficial por píxel. |
| E2E del navegador D1/D2 | PASS_WITH_LIMITATIONS | Selección, POST real, respuesta, cambio de producto, advertencias, persistencia y capturas verificados. |
| Temporal Vision y descubrimientos | NOT_TESTED | Excluidos expresamente del objetivo de esta fase. |

Pendiente para retirar las limitaciones:

1. Identificar con evidencia oficial el release/pipeline de cada MEF local o incorporar metadatos de procedencia autoritativos; no inferirlo del nombre.
2. No declarar calibración fotométrica absoluta: se requieren los demás productos/correcciones y validaciones pertinentes.
3. La ruta raíz `/` del backend responde 404; no afecta a `/health`, `/docs` ni a las rutas de datos usadas aquí.

