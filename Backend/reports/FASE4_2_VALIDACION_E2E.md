# FASE 4.2 — Validación End-to-End de SPHEREx Temporal Observatory

Fecha de ejecución: 2026-11-15 (UTC; logs de los servicios)

## Resumen ejecutivo

**Estado global: PASS_WITH_LIMITATIONS**

Los servidores reales se reiniciaron y el navegador cargó la aplicación. La API respondió con datos del inventario real, CORS quedó comprobado desde el origen del frontend, y las rutas de backend generaron una imagen PNG desde un FITS real y una extracción espectral válida.

La aplicación de usuario no completa los flujos científicos con esos archivos: las vistas filtradas por módulo devuelven cero FITS porque el manifiesto no asigna consumidores; Sky/Spectral consultan IRSA y fallan con HTTP 502/500; las pantallas temporales y de detección muestran visualizaciones ilustrativas identificadas como demo. Por tanto, que ambos servidores respondan HTTP 200 **no** equivale a integración funcional ni a validación científica E2E.

El observatorio completo no se considera operativo. Se requiere corregir la integración del frontend con el inventario real, reparar el cliente TAP de IRSA y dejar explícitamente experimentales las visualizaciones no basadas en observaciones reales.

## 1. Arranque limpio y procesos

Antes del arranque se identificó y detuvo el proceso anterior de backend (PID 27984). No había proceso escuchando en el puerto 8443 al detener las sesiones. Se reiniciaron ambos servicios desde sus respectivos directorios:

```powershell
# Backend/
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Frontend/
pnpm dev --host 127.0.0.1 --port 8443
```

Logs de arranque:

```text
Backend: Started server process [13864]
Application startup complete.
Uvicorn running on http://127.0.0.1:8000

Frontend: VITE v8.0.5 ready in 986 ms
Local: http://127.0.0.1:8443/
```

Procesos verificados al final:

| Servicio | PID | Proceso | Puerto |
|---|---:|---|---:|
| Backend | 13864 | python3.11.exe / uvicorn | 8000 |
| Frontend | 18716 | node.exe / vite | 8443 |

No hubo conflicto de puerto durante el arranque limpio.

Comprobaciones HTTP:

| Solicitud | Resultado |
|---|---|
| `GET http://127.0.0.1:8000/health` | 200; `{"status":"online","release":"SPHEREx DR1/QR3"}` |
| `GET http://127.0.0.1:8000/docs` | 200; FastAPI Swagger HTML |
| `GET http://127.0.0.1:8443/` | 200; documento HTML de Vite |
| `GET /api/v1/data/fits?limit=1` | 200; 10 FITS en inventario real |

Los endpoints de IRSA fallidos se registran más adelante y no se consideran respuestas funcionales.

## 2. Datos reales y trazabilidad

Ruta original confirmada:

`Backend/app/data/raw/spherex/`

Se detectaron 10 FITS reales y el manifiesto preexistente. No se movieron, renombraron ni modificaron los FITS originales ni se regeneró el manifiesto en esta fase.

Archivo usado para las pruebas de preview y perfil:

```text
AstroVision AI/level2_2025W28_1B_0001_1D1_spx_l2b-v27-2026-215.fits
file_id: fa0be417-a929-52b0-bd99-8e02be2ef385
size: 61,511,040 bytes
SHA-256: ed8debec7bf19f4d9c92375f139176b5c9c7ced628a59a598179d7869441c296
```

El backend devuelve el ID y ruta del FITS en el perfil; el endpoint de descarga expone el SHA-256. El perfil actual no devuelve SHA-256, versión de software ni fecha de ejecución como campos propios. No se encontró un registro persistente ligado a este cálculo. La respuesta, por tanto, no constituye una trazabilidad de resultado completa.

## 3. Navegador real, carga, Network y consola

Se abrió `http://127.0.0.1:8443/` en el navegador integrado, se inspeccionó la pantalla y se navegaron las secciones Cosmic Sky, Temporal Universe, Spectral Cube, Object Discovery y Discovery Catalog. El título y la interfaz cargaron.

Se capturaron las respuestas de red y errores del navegador durante una recarga. Requests relevantes:

| Endpoint | Estado visto en navegador | Resultado |
|---|---:|---|
| `GET /api/v1/sky/regions/featured` | 200 | Respuesta real con 2 regiones recomendadas |
| `GET /api/v1/data/fits?module=sky_explorer` | 200 | Lista vacía; `total: 0` |
| `GET /api/v1/data/fits?module=spectral_analysis` | 200 | Lista vacía; `total: 0` |
| `GET /api/v1/data/fits?module=temporal_vision` | 200 | Lista vacía |
| `GET /api/v1/data/fits?module=object_detection` | 200 | Lista vacía |
| `GET /api/v1/sky/observations?ra=83.8221&dec=-5.3911&fov_deg=0.5` | 502 | Error de cliente TAP IRSA |
| `GET /api/v1/spectral/profile?ra=83.8221&dec=-5.3911&fov_deg=0.05` | 500 | Error de cliente TAP IRSA |
| `GET /api/v1/detection/discoveries?limit=50` | 200 | Catálogo backend vacío |

Consola del navegador:

```text
Failed to load resource: the server responded with a status of 502 (Bad Gateway)
Failed to load resource: the server responded with a status of 500 (Internal Server Error)
```

No se observó un error CORS tras el reinicio. Una llamada con `Origin: http://127.0.0.1:8443` devolvió:

```text
HTTP/1.1 200 OK
access-control-allow-origin: http://127.0.0.1:8443
vary: Origin
```

Esto confirma CORS y comunicación de red, pero no la ejecución exitosa de los flujos de UI.

### Causa de los errores IRSA

Los logs del backend registran:

```text
AttributeError: 'IrsaClass' object has no attribute 'query_tap'
GET /api/v1/sky/observations?... 502 Bad Gateway
GET /api/v1/spectral/profile?... 500 Internal Server Error
```

La API devuelve los errores al frontend, que los muestra como estado de error. Causa: la implementación llama a un método `query_tap` inexistente en la clase `Irsa` instalada. No se enmascaró como una consulta exitosa.

## 4. Sky Explorer

### Flujo desde la interfaz

El navegador abrió Sky Explorer y la interfaz mostró:

- inventario local FITS: 0;
- mensaje para añadir FITS a una ruta `Backend/data/raw/spherex` y asignarlos a `fits-consumers.json`;
- datos de regiones y marcadores que la propia interfaz identifica como ilustrativos;
- error al consultar observaciones IRSA (HTTP 502).

La ruta indicada por la UI no coincide con la ruta real de los datos (`Backend/app/data/raw/spherex`). La pantalla tampoco ofrece el FITS real para selección. Por ello, no se pudo completar desde la interfaz el flujo seleccionar FITS → preview → cambiar FITS.

Estado del flujo UI: **BLOCKED**.

### Endpoint real de imagen

Se llamó directamente al endpoint de preview del archivo real:

```powershell
curl.exe -sS -D - `
  "http://127.0.0.1:8000/api/v1/data/fits/fa0be417-a929-52b0-bd99-8e02be2ef385/preview?hdu=1" `
  -o "Backend/reports/e2e-sky-preview.png"
```

Respuesta:

```text
HTTP/1.1 200 OK
content-type: image/png
x-fits-file-id: fa0be417-a929-52b0-bd99-8e02be2ef385
x-fits-hdu: 1
content-length: 6469957
```

Evidencia persistida: [e2e-sky-preview.png](./e2e-sky-preview.png)

Propiedades del resultado:

| Campo | Resultado |
|---|---|
| Origen | FITS real indicado arriba, HDU 1 `IMAGE` |
| Dimensiones del FITS | 2040 × 2040; float32 |
| Dimensiones PNG | 2040 × 2040; RGBA |
| Tamaño PNG | 6,469,957 bytes |
| SHA-256 PNG | `ac25bcabb565f6fac992dfc6f126f3cfce25e163da64fe2120fde41f7ce25af3` |
| Centro WCS en pixel (1000,1000) | RA 148.1953861688°, Dec −60.2374717071° |
| Roundtrip pixel → cielo → pixel | (1000.000000003, 999.999999986) |

La imagen resultante se abrió en el navegador y se observó el campo astronómico real. El endpoint identifica el FITS/HDU mediante headers HTTP. El PNG por sí solo no contiene WCS embebido; las coordenadas se obtienen del header WCS del FITS fuente.

Estado: preview de backend **PASS**; flujo completo de Sky Explorer en la UI **BLOCKED** por inventario filtrado vacío.

## 5. Spectral Analysis

### Flujo desde la interfaz

La pantalla Spectral Cube describe una ruta `GET /api/v1/spectral/profile` y muestra “calibrated wavelengths and measured signals are not connected in this demo”. La petición desde UI terminó en HTTP 500 con `query_tap` inexistente. No ofrece el perfil del FITS local ni un selector de archivo real. La longitud de onda se marca como calibración no disponible.

Estado E2E de Spectral Analysis en UI: **FAIL**.

### Inspección científica del producto y extracción por API local

El FITS es un **Spectral Image MEF** con:

| HDU | Nombre | Tipo | Shape |
|---:|---|---|---|
| 0 | PRIMARY | PrimaryHDU | sin datos; NAXIS=0 |
| 1 | IMAGE | ImageHDU | (2040, 2040) |
| 2 | FLAGS | CompImageHDU | (2040, 2040) |
| 3 | VARIANCE | ImageHDU | (2040, 2040) |
| 4 | ZODI | ImageHDU | (2040, 2040) |
| 5 | EPSF | BinTableHDU | 441 filas |
| 6 | WCS-WAVE | BinTableHDU | 1 fila |

La tabla `WCS-WAVE` tiene columnas `X`, `Y`, `VALUES` (162 floats). No se hallaron claves `CWAVE*` ni `CBAND*` en el header IMAGE. `BUNIT` de IMAGE es `MJy / sr`; no se hallaron `CALLEVEL`, `CAL_VER` ni `CALVERS`. `DATE` es fecha de creación de HDU, y `DATE-OBS`/`MJD-OBS` son fecha de observación; no son equivalentes a release.

El endpoint local:

```text
GET /api/v1/data/fits/fa0be417-a929-52b0-bd99-8e02be2ef385/spectral-profile
    ?ra=148.19538616879197&dec=-60.237471707056955
```

devolvió HTTP 200 con:

```json
{
  "file_id": "fa0be417-a929-52b0-bd99-8e02be2ef385",
  "filename": "level2_2025W28_1B_0001_1D1_spx_l2b-v27-2026-215.fits",
  "release": null,
  "ra": 148.19538616879197,
  "dec": -60.237471707056955,
  "measurement_type": "Direct MEF WCS-W Extraction (Non-interpolated)",
  "wavelength_um": 0.9081690547035444,
  "flux": 0.6777377724647522,
  "flux_error": 0.0298064040783984,
  "unit": "MJy / sr",
  "uncertainty_unit": "MJy / sr",
  "flag": 2097152,
  "is_valid_measurement": true
}
```

Esta ruta calcula el valor espectral desde el WCS alternativo `W` con FITS `fobj`, no usa `CWAVE`/`CBAND` (ausentes), y no consulta la UI. `WCS-WAVE` está presente con 162 valores; no se ha demostrado que las salidas cubran de forma calibrada el modelo completo de wavelength/band, ni se ha validado científicamente la correspondencia pixel-canal de toda la imagen. El resultado demuestra una extracción técnica real y valores/unidades/varianza/máscara para un pixel, **no** una calibración espectral completa. Las advertencias SIP de Astropy durante la conversión inversa de una coordenada muestran que hay que resolver la consistencia de la distorsión antes de elevar la interpretación a ciencia calibrada.

Prueba negativa:

```text
GET .../spectral-profile?ra=10&dec=10
HTTP/1.1 422 Unprocessable Entity
{"detail":"No se pudo extraer un perfil válido: cannot convert float NaN to integer"}
```

El caso inválido no devolvió una medición aparente; no obstante, el mensaje interno por NaN debería transformarse en un error de dominio claro.

Estado: extracción local backend **PASS_WITH_LIMITATIONS**; flujo de UI **FAIL**; análisis espectral calibrado integral **NOT_TESTED**.

## 6. Temporal Vision

En la interfaz:
- el inventario local para `temporal_vision` está vacío;
- se informa que hacen falta dos observaciones reales;
- la solicitud de observaciones IRSA falla;
- las trayectorias, fechas, mapas de fondo y candidatos se identifican como ilustrativos/demo.

No se ejecutó ni se representó un cálculo real `D = I2 - I1`, `sigma_D` o `Z`. No se construyó una diferencia sintética como si fuera observación.

Estado: **BLOCKED** para la comparación real por falta de pareja elegible y fallo IRSA. La vista demostrativa se clasifica como experimental, no como resultado científico.

## 7. Object Detection y Discovery Catalog

### Object Detection

El endpoint de lista del módulo FITS devolvió 0 archivos asignados. No se encontró una detección individual real ejecutada desde la UI ni desde un endpoint de detección aislada en esta prueba. La interfaz muestra cinco candidatos, puntuaciones/confianzas y desplazamientos, pero los etiqueta explícitamente como ilustrativos/simulados y dice que requieren revisión.

Estado de detección real: **NOT_TESTED**. UI demo: **PASS_WITH_LIMITATIONS** por la advertencia explícita, pero no es ciencia observacional.

### Discovery Catalog

`GET /api/v1/detection/discoveries?limit=50` respondió HTTP 200 con `[]`. La interfaz indica “backend no ha devuelto candidatos persistidos” y a su vez muestra candidatos de demo/locales identificados como demo y sesión de prototipo.

No hay registro persistido de detecciones reales ni asociación a hash FITS, coordenadas de cálculo y parámetros reproducibles.

Estado: catálogo real persistente **BLOCKED**; interfaz de catálogo ilustrativo **PASS_WITH_LIMITATIONS**.

## 8. Persistencia y auditoría

Resultado científico persistible evaluado: perfil espectral de un pixel.

| Requisito | Estado observado |
|---|---|
| `file_id` | Presente en la respuesta del perfil |
| Ruta/nombre del FITS | Presente |
| SHA-256 | Disponible en el manifest/endpoint de descarga, no incluido en el perfil |
| Coordenadas RA/Dec | Presentes |
| Parámetros de procesamiento | Método indicado parcialmente (`Direct MEF WCS-W Extraction`) |
| Fecha/hora de ejecución | No devuelta ni guardada junto al resultado |
| Versión de software | No devuelta |
| Máscara/calidad | Valor `flag` presente |
| Incertidumbre/unidad | Presentes |
| Registro persistente reproducible | No observado |

Estado: **BLOCKED** para trazabilidad científica completa.

## 9. Pruebas ejecutadas

### Backend

```powershell
cd Backend
python -m pytest -q tests/test_fits_inventory.py tests/test_fits_data_api.py
```

Resultado: `15 passed, 18 warnings in 3.73s`, código 0. Incluye warnings deprecados de dependencias y warnings Astropy WCS en la prueba de coordenada inválida.

### Frontend

```powershell
cd Frontend
pnpm typecheck
```

Resultado: `tsc --noEmit`, código 0.

### Validación en navegador

Aplicación abierta en el navegador real en `http://127.0.0.1:8443/`; requests de red y consola observados durante carga y navegación. Resumen de errores reproducidos:

- IRSA observations: HTTP 502 por atributo `IrsaClass.query_tap` no disponible.
- `GET /api/v1/spectral/profile`: HTTP 500 por el mismo error.
- Las listas de FITS con `module=` devuelven 200 pero `total: 0`.
- El catálogo persistido devuelve `[]`.

### Evidencia visual

- Captura/preview astronómico generado desde HDU 1 persistido en [e2e-sky-preview.png](./e2e-sky-preview.png) y servido por `/static/spherex/fa0be417-a929-52b0-bd99-8e02be2ef385_hdu1.png`.
- La interfaz fue inspeccionada en las cinco secciones y las pantallas de Spectral, Temporal y Object Discovery mostraron los errores/etiquetas descritos.
- El navegador integrado entrega capturas en la sesión, pero no ofrece una ruta de exportación local para guardar capturas independientes de cada módulo. No se afirman archivos de captura que no hayan sido realmente guardados.

## 10. Estado por capa y capacidad

| Capa / capacidad | Estado | Motivo |
|---|---|---|
| Backend operativo | PASS | Uvicorn reiniciado; health/docs y API reales responden |
| Frontend operativo | PASS | Vite reiniciado; página carga en navegador |
| CORS browser → backend | PASS | `Access-Control-Allow-Origin` correcto para `127.0.0.1:8443` |
| Integración frontend-backend | PASS_WITH_LIMITATIONS | Se observaron requests reales, pero varios flujos terminan en 0/500/502 |
| Sky Explorer UI con FITS real | BLOCKED | No hay consumidores asignados; lista filtrada vacía; UI muestra ruta errónea |
| Preview FITS backend | PASS | PNG real producido; source ID/HDU, dimensiones, SHA y WCS documentados |
| Spectral Analysis UI | FAIL | UI llama a ruta IRSA que responde 500; no usa FITS local |
| Extracción espectral MEF local | PASS_WITH_LIMITATIONS | Perfil real recuperado; calibration metadata CWAVE/CBAND ausente y validez integral no demostrada |
| Temporal Vision real | BLOCKED | Sin pares asignados/comparables; IRSA falla; no se ejecutó diferencia |
| Object Detection real | NOT_TESTED | No hubo detector individual real probado; candidatos de UI son demo |
| Discovery Catalog persistente | BLOCKED | API devuelve lista vacía; la UI tiene datos de demo/locales |
| Persistencia/linaje | BLOCKED | Resultado no persiste con SHA, software y timestamp completos |
| Typecheck y tests focalizados | PASS | Typecheck correcto; 15 tests backend pasan |

## 11. Cambios realizados durante Fase 4.2

No se modificaron fuentes ni FITS originales durante esta fase. Se generaron solamente:

- este informe;
- `Backend/reports/e2e-sky-preview.png`, un artefacto PNG de la ruta API de preview.

Configuración y código que ya estaban modificados desde la fase anterior:

- `Backend/app/core/config.py`: configuración de orígenes CORS para `127.0.0.1`.
- `Frontend/src/api/client.ts`: URL backend por defecto `http://127.0.0.1:8000`.
- `Backend/app/services/fits_inventory.py`: evitar WCS sobre HDUs sin imagen 2D.
- `Backend/tests/test_fits_inventory.py`: regresiones y extracción con FITS real.

El manifest que se conserva fue generado antes de la corrección del validador WCS y sigue conteniendo el warning anterior. No se regeneró para respetar la conservación solicitada; una regeneración posterior debe preservar/volver a verificar los hashes originales.

## 12. Problemas pendientes priorizados

1. **P0 — Conectar UI al inventario real.** Corregir la ruta explicada por la UI, configurar explícitamente `fits-consumers.json` para productos existentes y permitir selección de `file_id`, preview y perfil local. No asignar módulos por suposición: documentar el criterio producto/módulo.
2. **P0 — Reparar IRSA TAP.** Sustituir `Irsa.query_tap` por el cliente TAP compatible con la versión instalada, añadir prueba de contrato y convertir errores externos en estado visible sin 500 inesperado.
3. **P0 — Evitar demos ambiguas en modos científicos.** En modo de observatorio operativo, no mostrar fechas, estrellas, detecciones ni scores de demo como resultados; mantener demos aisladas y rotuladas.
4. **P1 — Validación espectral calibrada.** Determinar la semántica y aplicación de `WCS-WAVE`/162 valores, disponibilidad de CWAVE/CBAND por los productos oficiales, unidades/calibración y tratamiento de SIP. No declarar calibración por un único pixel positivo.
5. **P1 — Parejas para Temporal Vision.** Obtener productos compatibles, comprobar WCS/resolución/PSF, bandas, calibraciones, máscaras y varianzas; recién entonces calcular D, sigma_D y Z con propagación.
6. **P1 — Detección/catálogo reales.** Probar detector individual real, guardar resultados con identificador estable, hash, región/coordenadas, parámetros, fecha y versión; separar candidatos observacionales de demo.
7. **P2 — Integración automatizada E2E.** Añadir pruebas navegador que verifiquen requests, estado vacío, errores IRSA, binarios, selección FITS, perfil válido/inválido y ausencia de demos en resultados científicos.
8. **P2 — Evidencia auditable.** Automatizar export de screenshots por módulo y registro de red/logs a archivos dentro de `Backend/reports/`.

## 13. Requisitos de entrada para Fase 5

- El inventario debe permitir seleccionar al menos un FITS real desde la UI y exponer su SHA/ID.
- Sky Explorer debe renderizar la imagen de origen y coordenadas WCS sin usar assets de demostración.
- Spectral Analysis debe conectarse al endpoint local MEF, documentar el modelo CWAVE/CBAND/WCS-WAVE y mostrar máscara/incertidumbre/calibración.
- Temporal Vision debe bloquear claramente si no existe pareja elegible; si existe, debe validar compatibilidad antes del cálculo y registrar D, sigma_D y Z.
- Object Detection/Discovery Catalog deben indicar claramente que son experimentales hasta demostrar detección real y linaje persistente.
- Las pruebas de navegador deben pasar con requests y respuestas reales; no basta con HTTP 200 de la página.
- No debe haber errores 500/502 inesperados ni errores CORS.

**Conclusión:** los servidores están operativos, pero la interfaz científica E2E no está operativa. El estado global permanece `PASS_WITH_LIMITATIONS`; no se declara el observatorio completamente operativo.
