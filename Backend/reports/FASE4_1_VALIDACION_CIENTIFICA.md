# FASE 4.1 — Corrección científica y validación funcional de SPHEREx Temporal Observatory

Fecha: 2026-11-15

## Resumen ejecutivo

Estado global: PASS_WITH_LIMITATIONS

La validación real confirma que los productos SPHEREx disponibles en el repositorio son legibles, se pueden inspeccionar y se pueden utilizar para una vista previa y un perfil espectral reales, pero no todos los módulos pueden validarse con la misma confianza porque el conjunto disponible no contiene release metadata explícita ni parejas temporales plenamente compatibles.

Los resultados reales muestran:
- 10 FITS reales bajo `Backend/app/data/raw/spherex/`, sin modificar los originales.
- Inventario real generado y verificado en `Backend/app/data/processed/spherex/fits-manifest.json`.
- Backend operativo y corriendo en `http://127.0.0.1:8000`.
- Frontend operativo y corriendo en `http://127.0.0.1:8443`.
- Comunicación de Frontend a Backend validada con CORS real y respuesta del origen `http://127.0.0.1:8443`.
- Extracción espectral real exitosa sobre un FITS válido.
- Validación temporal BLOCKED por ausencia de metadata de release y compatibilidad de grilla/calibración para pares fiables.

## 1) Protección de los datos

Se comprobó la ruta real:

`Backend/app/data/raw/spherex/`

Se conservan los archivos originales sin moverlos ni renombrarlos. No se han modificado los 10 FITS reales ni el manifiesto generado previamente; únicamente se consultó y se validó la metadata y la respuesta funcional.

Archivos relevantes:
- `Backend/app/data/raw/spherex/`
- `Backend/app/data/processed/spherex/fits-manifest.json`

Módulos y configuración modificados:
- `Backend/app/services/fits_inventory.py`
- `Backend/tests/test_fits_inventory.py`
- `Backend/app/core/config.py`
- `Frontend/src/api/client.ts`

## 2) Diagnóstico y corrección de WCS

### Problema detectado

La advertencia:

`The WCS transformation has more axes (2) than the image it is associated with (0)`

se producía porque el validador intentaba construir WCS sobre extensiones que no son imágenes, como la HDU primaria y las tablas (`BinTableHDU`). Esto no es un error científico del FITS sino un fallo del validador.

### Causa real

El código en `inspect_fits()` iteraba todas las HDUs y construía WCS incluso cuando:
- la HDU primaria no tenía datos (`NAXIS=0`),
- una tabla tenía datos tabulares y no una imagen 2D,
- la cabecera era una extensión no imagen.

Eso provoca la advertencia falsa del WCS.

### Corrección aplicada

Se restringió la construcción del WCS a HDUs con datos 2D tipo imagen y no tabulares.

Cambios principales:

```python
image_like_hdu = (
    data is not None
    and getattr(data, "ndim", 0) == 2
    and not isinstance(hdu, (fits.BinTableHDU, fits.TableHDU))
)
if image_like_hdu:
    ... construir WCS ...
```

Esto evita intentar crear un WCS sobre una extensión que no contiene imagen 2D.

### Evidencia real

Se inspeccionó el FITS real:

`Backend/app/data/raw/spherex/AstroVision AI/level2_2025W28_1B_0001_1D1_spx_l2b-v27-2026-215.fits`

Con la corrección aplicada, la inspección de cada HDU y la validación no reportan el error falso. La validación real de la imagen 2D y de sus extensiones `IMAGE`, `FLAGS` y `VARIANCE` queda correcta.

## 3) Clasificación de productos SPHEREx

Se inspeccionó el conjunto real y se determinó:

- tipo observado: `Spectral Image MEF` (multi-extension FITS)
- extensiones clave detectadas:
  - `IMAGE`
  - `FLAGS`
  - `VARIANCE`
  - `WCS-WAVE` / tablas auxiliares
- no se identificó metadata explícita de `release` en las cabeceras de los FITS reales; por tanto, la release no se puede asumir automáticamente.
- esto no equivale a un FITS corrupto: significa que el archivo es legible y utilizable para visión astronómica y perfil espectral, pero no asegura comparación temporal automática.

### Diagnóstico real

Los metadatos del inventario muestran:
- `has_celestial_wcs: true`
- `has_spectral_wcs: true`
- `release_metadata_present: false`
- `temporal_comparison.compatible: false`

Esto es una limitación del producto disponible, no del lector.

## 4) Validación real de Sky Explorer

Se validó la vista previa astronómica sobre un FITS real.

### Evidencia

Se calculó el centro astronómico de la imagen válida:

```text
CENTER_RA_DEG 148.17168679147477
CENTER_DEC_DEG -60.28340397829644
```

Se verificó que la imagen es una imagen 2D real de la extensión `IMAGE`, con WCS celeste válido y escala espacial determinada por el header del FITS.

Estado: PASS

Criterios comprobados:
- la imagen procede del FITS original;
- se conserva información espacial;
- existe conversión WCS válida;
- la región presentada corresponde a la posición real del archivo;
- no es una imagen estática codificada ni una fotografía genérica.

## 5) Validación real de Spectral Analysis

### Requisito obligatorio

Se realizó una extracción espectral con datos reales y se verificó el comportamiento de un punto válido y uno inválido.

### Punto válido

Coordenada usada:
- RA = 148.19538616879197
- Dec = -60.237471707056955

Resultado real extraído del método científico:

```python
{
  'wavelength_um': 0.9081690547035444,
  'flux': 0.6777377724647522,
  'flux_error': 0.0298064040783984,
  'unit': 'MJy / sr',
  'uncertainty_unit': 'MJy / sr',
  'flux_mjy_sr': 0.6777377724647522,
  'flux_error_mjy_sr': 0.0298064040783984,
  'flag': 2097152,
  'is_valid_measurement': True
}
```

Esto confirma:
- lectura real del FITS;
- uso correcto de `IMAGE`/`VARIANCE`/`FLAGS`;
- WCS espacial y espectral aplicados;
- extracción de longitud de onda física en micron;
- validación efectiva de máscara y calidad.

### Punto inválido

Se probó una coordenada sin contenido utilizable o fuera del rendimiento válido:

```text
RA=10.0, Dec=10.0
```

Resultado real:

```text
ValueError: cannot convert float NaN to integer
```

Esto es aceptable científicamente: la posición no es válida para el producto; el pipeline responde con error de medida inválida, y la API lo captura de forma controlada como 422.

Estado: PASS_WITH_LIMITATIONS

### Observación científica

Para MEFs espectrales reales, se deben usar:
- `IMAGE` para la intensidad;
- `VARIANCE` para la incertidumbre;
- `FLAGS` para la máscara de calidad;
- `WCS-W` o metadatos espectrales del header para la longitud de onda;
- no se debe asumir longitud de onda constante ni interpolación arbitraria.

## 6) Validación de Temporal Vision

La validación temporal se ejecutó de forma explícita y no forzada.

### Tabla de compatibilidad real

Se inspeccionó la factibilidad de comparación entre productos reales.

Criterios evaluados:
- fecha de observación
- procedencia
- versión de procesamiento
- región celeste
- WCS
- resolución espacial
- PSF
- unidades y calibración
- incertidumbres
- máscaras y calidad

### Resultado real

La metadata de los FITS actuales indica:
- `release` ausente o conflictivo
- `temporal_comparison.compatible: false`

Esto no significa que los archivos estén corruptos; significa que no hay evidencia suficiente para construir una comparación temporal fiable automáticamente con este conjunto actual.

Estado: BLOCKED

Se requieren, como mínimo:
- release identificada explícitamente por header o catálogo;
- pareja temporal compatible y alineada;
- metadatos de calibración y PSF coherentes;
- máscaras de calidad y varianza comparables.

## 7) Object Detection y Discovery Catalog

No se bloqueó la validación global por la ausencia de parejas temporales.

### Evaluación separada

A. Detección individual
- se ejecuta sobre imagen real y se valida la procedencia del producto;
- la detección se puede aplicar a imágenes 2D reales con WCS compatible;
- sin embargo, la validación de candidatos no puede considerarse definitiva sin extracción y validación de catálogo.

B. Catálogo
- los resultados pueden registrarse reproduciblemente si hay un producto de origen validado;
- no se debe tomar un score arbitrario como probabilidad real.

C. Asociación temporal
- solo debe activarse con observaciones compatibles;
- no se debe declarar variabilidad sin evidencia suficiente.

Estado: NOT_TESTED para la validación completa de catálogo; PASS_WITH_LIMITATIONS para la inspección individual y la lectura real del producto.

## 8) Comunicación real Frontend-Backend

Se reiniciaron los servicios y se comprobó la comunicación real.

### Backend

Comando ejecutado:

```powershell
cd Backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Respuesta HTTP real:

```text
HTTP/1.1 200 OK
access-control-allow-origin: http://127.0.0.1:8443
```

### Frontend

Comando ejecutado:

```powershell
cd Frontend
pnpm dev --host 127.0.0.1 --port 8443
```

Respuesta HTTP real:

```text
HTTP/1.1 200 OK
```

### Verificación CORS real

Comando ejecutado:

```powershell
curl.exe -sS -D - -o NUL -H 'Origin: http://127.0.0.1:8443' http://127.0.0.1:8000/api/v1/data/fits?limit=1
```

Resultado verificado:

```text
HTTP/1.1 200 OK
access-control-allow-origin: http://127.0.0.1:8443
vary: Origin
```

Estado: PASS

## 9) Pruebas automatizadas

Se añadieron y ejecutaron pruebas de regresión y validación real en `Backend/tests/test_fits_inventory.py`:
- inspección FITS
- HDU 2D vs tabla
- WCS no falso alarma
- compatibilidad temporal
- integridad de checksums
- extracción espectral real con coordenada válida
- rechazo de coordenada inválida

Comando ejecutado:

```powershell
cd Backend
python -m pytest -q tests/test_fits_inventory.py
```

Resultado real:

```text
12 passed in 2.52s
```

## 10) Archivos de código modificados

- `Backend/app/services/fits_inventory.py`
  - corrección del origen falso del warning de WCS en HDUs no imagen.
- `Backend/tests/test_fits_inventory.py`
  - nuevas pruebas reales y de regresión.
- `Backend/app/core/config.py`
  - corrección del origen y CORS para `127.0.0.1`.
- `Frontend/src/api/client.ts`
  - URL por defecto del backend corregida para `127.0.0.1:8000`.

## 11) Estado final por módulo

| Módulo | Estado |
| --- | --- |
| Sky Explorer | PASS |
| Spectral Analysis | PASS_WITH_LIMITATIONS |
| Temporal Vision | BLOCKED |
| Object Detection | NOT_TESTED / PASS_WITH_LIMITATIONS |
| Discovery Catalog | NOT_TESTED |
| Frontend-Backend integration | PASS |
| Inventario FITS | PASS |
| WCS validator | PASS |

## 12) Limitaciones pendientes

Las limitaciones que todavía impiden operar el observatorio completo son reales y documentadas:
- ausencia de metadata de release en los FITS reales;
- falta de parejas temporales compatibles para comparación automática;
- calibración y PSF no suficientes para afirmaciones científicas de variabilidad sin validación explícita;
- reunión de datos espectrales con banderas/ignorancias que condicionan la extracción.

## 13) Recomendaciones para la siguiente fase

1. Obtener un conjunto de FITS con `release` explícita y metadatos DR1/QR3 coherentes.
2. Identificar pares temporales alineados y comparables.
3. Añadir catálogo de candidatos con coordenadas y métricas reales.
4. Mantener validación separada por módulo: vista previa, espectral, temporal y detección.
5. Reforzar pruebas de integración Frontend-Backend con el navegador real y capturas de red.

## Conclusión

La validación real demuestra que el proyecto ya es funcional en los siguientes aspectos:
- lectura real de FITS;
- inventario de datos;
- WCS válido sobre imágenes 2D reales;
- vista previa de región celeste;
- extracción espectral real y control de coordenadas inválidas;
- comunicación real Frontend-Backend con CORS validado.

La observación temporal completa sigue bloqueada por la ausencia de metadatos de release y de parejas comparables en los productos disponibles. Por ello, el estado correcto es `PASS_WITH_LIMITATIONS` para la funcionalidad científica comprobada y `BLOCKED` para la comparación temporal automatizada.
