# Fase 4.5 — Sistema central de calibración científica

## Resumen ejecutivo

**Estado global: PASS_WITH_LIMITATIONS.** Se implementó el catálogo y diagnóstico central de calibraciones, se contrastaron los resultados con los FITS locales y se mantuvo la asociación estricta por evidencia. Los 10 FITS originales siguen coincidiendo con sus SHA-256 del manifiesto. No se encontraron calibraciones auxiliares independientes en el directorio local.

La estructura de los ePSF embebidos y la tabla espectral del cubo se validan parcialmente. No se declara validado el análisis espectral científico integral de los MEF: falta asociar los mapas oficiales independientes `CWAVE`/`CBAND` Spectral WCS con detector, versión, procesamiento e integridad compatibles. Tampoco se verificaron en navegador los nuevos estados de la interfaz.

## Cambios realizados

- `Backend/app/services/calibration_manager.py`
  - Registro de 13 clases oficiales de productos de calibración.
  - Búsqueda local de auxiliares por patrones de nombre conocidos; los productos encontrados se mantienen como no verificados hasta validar su contenido.
  - Diagnóstico de WCS espacial, SIP, unidades fotométricas, ePSF y canales espectrales del cubo.
  - Asociación de Spectral WCS condicionada a coincidencia de detector, versión, fecha de procesamiento, dimensiones, unidades e integridad. No se elige una asociación ambigua.
  - Autorizaciones explícitas para operaciones científicas. No se aplica dos veces una corrección upstream ni se usa `WCS-WAVE` del MEF como sustituto de `CWAVE`/`CBAND`.
  - Cálculo SHA-256 por bloques para registrar productos auxiliares descubiertos fuera del manifiesto.
  - Comprobación estructural de ePSF: rejilla por detector, pares de índices de zona, centros finitos, únicos y dentro de la imagen, y arrays oversampled de 33×33.
  - Comprobación de longitudes de onda del cubo contra su WCS y validación independiente de `WL_MIN`, `WL_MAX` y `BANDWIDTH`. No se presupone que `BANDWIDTH = WL_MAX - WL_MIN`.
- `Backend/app/api/v1/endpoints/data.py`
  - Endpoints `GET /data/calibrations` y `GET /data/fits/{file_id}/calibration`.
  - Diagnóstico adjunto a las respuestas de extracción y detección locales.
- `Backend/app/services/fits_processor.py`
  - Propaga el ancho de banda tabulado del cubo únicamente si está presente y tiene una unidad de longitud válida; no lo interpola.
- `Backend/app/services/scientific_results.py`
  - Conserva los IDs de calibración asociados en la persistencia y serialización de ejecuciones.
- `Frontend/src/api/fits.ts` y `Frontend/src/App.tsx`
  - Tipos y presentación del diagnóstico, autorizaciones, advertencias y ancho de banda disponible.
- `Backend/tests/test_calibration_manager.py` y `Backend/tests/test_fits_data_api.py`
  - Fixtures estructurales de ePSF, asociaciones válidas/incompatibles/ambiguas y verificación de extracción del cubo y persistencia de IDs.

## Evidencia con datos locales

Raíz de datos utilizada: `Backend/app/data/raw/spherex/`. El manifiesto consultado fue `Backend/app/data/processed/spherex/fits-manifest.json`.

| Comprobación | Resultado |
|---|---|
| Entradas del manifiesto | 10 |
| FITS legibles y SHA-256 coincidente con manifiesto | 10/10 |
| Spectral Image MEF | 9 |
| All-Sky Spectral Cube | 1 |
| Productos auxiliares independientes de calibración | 0 |
| Componentes embebidos registrados | 20: 9 `EPSF`, 10 `WCS-WAVE`, 1 `SPECTRAL_CHANNELS` |

La llamada de verificación fue `FitsInventory.get_path(entry)` para cada entrada; no se escribió ni modificó ningún archivo bajo `raw`. Los hashes canónicos permanecen en el manifiesto.

### ePSF de los MEF

La inspección directa de las extensiones `EPSF` confirmó en los MEF:

- 441 filas por archivo, correspondientes a una rejilla 21×21 para los detectores identificados localmente.
- Array por zona de 33×33 valores.
- Pares `BINX`/`BINY` completos y únicos; centros finitos, únicos y dentro de la imagen.
- `CWAVE` y `CBAND` llevan unidad `um`; los arrays ePSF no contienen valores no finitos.

**Estado: PASS_WITH_LIMITATIONS.** La estructura es compatible, pero su release/procedencia no queda demostrada por esa inspección. `CWAVE`/`CBAND` de esta tabla son valores por zona de ePSF; no son los mapas espectrales científicos de resolución de imagen.

### Canales del cubo

El producto `Npix0_cube.fits` contiene 102 canales en su tabla nativa. Sus longitudes de onda centrales concuerdan con el eje espectral WCS y quedan dentro de los límites ordenados `WL_MIN`/`WL_MAX`. `BANDWIDTH` tiene valores positivos y unidad declarada.

La comprobación inicial detectó que `BANDWIDTH` no es idéntico al ancho calculado como `WL_MAX-WL_MIN`: en este archivo las anchuras de borde varían aproximadamente de 0.019 a 0.120 µm y `BANDWIDTH` de 0.018 a 0.103 µm. Por ello se eliminó esa igualdad asumida. El código valida cada campo independientemente y no deriva ni sustituye un valor con otro. La documentación oficial consultada describe la tabla del cubo como portadora de longitudes de onda centrales y de borde; no se encontró base para imponer esa igualdad.

**Estado: PASS_WITH_LIMITATIONS.** Se verificó coherencia con el WCS y estructura/unidades, pero release, procedencia y calibración absoluta siguen sin verificación independiente. El cubo no tiene extensión `VARIANCE`, por lo que no se autoriza significancia estadística.

### Productos MEF y autorizaciones

Los 9 MEF tienen una tabla `WCS-WAVE` embebida, destinada a visualización según la documentación oficial. No se encontraron productos Spectral WCS independientes para asociar los mapas científicos `CWAVE`/`CBAND`. La etiqueta del release no se infirió solo de la versión del backend ni de un nombre fijo.

**Estado del análisis espectral científico MEF: BLOCKED.** Se conserva únicamente la muestra técnica limitada basada en el WCS disponible, con advertencias y sin afirmar calibración espectral integral.

No se reaplican Absolute Gain, correcciones fotométricas, SIP ni conversión de brillo superficial a flujo por píxel. Fotometría PSF y significancia estadística no quedan autorizadas por este sistema.

## Validación ejecutada

| Comando | Resultado |
|---|---|
| `python -m pytest tests/test_calibration_manager.py -q` | 5 passed |
| `python -m pytest tests/test_fits_data_api.py -q` | 6 passed |
| `python -m pytest tests/test_calibration_manager.py tests/test_fits_data_api.py -q` | 11 passed |
| `python -m pytest tests/test_fits_data_api.py::test_spectral_cube_preview_extraction_and_invalid_position -q` | 1 passed tras incorporar bordes no equivalentes al ancho tabulado |
| `python -m pytest -q` | 33 passed, 21 advertencias de dependencias/WCS |
| Pylance `pylanceFileSyntaxErrors` en `calibration_manager.py` y pruebas | Sin errores de sintaxis |
| `pnpm typecheck` | Exit code 0 |
| `pnpm build` | Exit code 0; build Vite completado |
| Diagnóstico real con `FitsInventory` y `CalibrationManager` | 10 archivos verificados; 9 MEF y 1 cubo diagnosticados |

Las advertencias de pruebas incluyen deprecaciones de Starlette/HTTPX/Matplotlib y advertencias WCS del caso de regresión; no se ocultaron.

## Estado por capacidad

| Capacidad | Estado | Evidencia y límite |
|---|---|---|
| Catálogo local de calibración | PASS_WITH_LIMITATIONS | 13 tipos conocidos y 20 componentes embebidos catalogados; cero auxiliares independientes locales. |
| SHA-256 de los FITS fuente | PASS | Los diez `get_path` validaron el hash frente al manifiesto. |
| Diagnóstico estructural ePSF | PASS_WITH_LIMITATIONS | Rejilla y arrays verificados; procedencia/release no independientes. |
| WCS-WAVE de MEF | PASS_WITH_LIMITATIONS | Identificada para visualización; no reemplaza los mapas Spectral WCS científicos. |
| Asociación de CWAVE/CBAND externa a MEF | BLOCKED | No existe producto auxiliar local compatible que pueda asociarse. |
| Tabla de canales del cubo | PASS_WITH_LIMITATIONS | 102 centros concuerdan con WCS; bordes y ancho tabulado se validan por separado; procedencia/calibración absoluta incompletas. |
| Autorización de fotometría/calibración absoluta/significancia | BLOCKED | Faltan calibraciones/modelos validados para esas operaciones. |
| Persistencia de IDs de calibración | PASS_WITH_LIMITATIONS | La prueba API recupera una ejecución del cubo con el ID de tabla espectral asociado; la validación de persistencia en producción no se ejecutó. |
| Integración Frontend compilable | PASS_WITH_LIMITATIONS | Typecheck y build pasan; no se comprobó la representación en navegador. |
| Backend/frontend en ejecución y prueba E2E en navegador | NOT_TESTED | Fuera de la validación ejecutada para este sistema; no se afirma integración visual E2E. |
| Consulta real a IRSA/descarga de auxiliares | NOT_TESTED | No se simuló disponibilidad remota ni se descargaron productos. |

## Referencias científicas consultadas

- [SPHEREx Data Products — documentación oficial IRSA](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-products/): describe `IMAGE` Level 2 en MJy/sr, `WCS-WAVE` de MEF para visualización, uso de Spectral WCS `CWAVE`/`CBAND` para análisis científico y estructura de ePSF/cubos.
- [SPHEREx Data Access — documentación oficial IRSA](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-access/).
- [SPHEREx Spectral Calibrations](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/spherex_spectral_calibrations.html).

## Pendientes para cerrar la fase

1. Obtener y verificar los productos auxiliares Spectral WCS oficiales; confirmar su estructura, granularidad efectiva, versiones y asociación con los MEF reales. La diferencia de granularidad descrita en documentación auxiliar debe resolverse mediante los propios productos y sus metadatos.
2. Ejecutar integración navegador/API después de obtener calibraciones disponibles y registrar capturas/red de solicitudes si se exige validar la interfaz interactiva.
3. Implementar y validar fotometría PSF, conversión MJy/sr a flujo por píxel o significancia únicamente con productos/modelos de calibración apropiados.
4. Mantener el estado parcial del cubo y de los ePSF hasta verificar release y procedencia independientes.

La Fase 4.5 deja el catálogo y las autorizaciones implementados, pero no declara científicamente operativo todo análisis: las limitaciones señaladas permanecen explícitas.
