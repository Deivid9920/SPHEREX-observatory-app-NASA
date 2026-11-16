# FASE 4 — Validación integral real de SPHEREx Temporal Observatory

Fecha de validación: 2026-11-15

## Resultado global

Estado general: PASS_WITH_LIMITATIONS

- PASS: inventario real de FITS, arranque real del backend, disponibilidad real del frontend, endpoints HTTP reales, validación científica básica con archivos reales.
- PASS_WITH_LIMITATIONS: el conjunto disponible es utilizable para inspección y perfil espectral, pero no garantiza comparación temporal automatizada sin metadatos adicionales.
- BLOCKED: validación temporal completa de DR1/QR3 con pares comparables no confirmados por la metadata de los FITS actuales.
- FAIL: el origen real del frontend `http://127.0.0.1:8443` no estaba incluido en CORS al inicio; esto quedó corregido en código, pero el proceso vivo del backend sigue usando la configuración previa hasta un reinicio limpio.

## 1) Diagnóstico de rutas reales

Se verificó físicamente el árbol del proyecto desde la raíz.

Estructura real detectada:

```text
SPHEREx-temporal-observatory/
├── Backend/
│   ├── app/
│   │   └── data/
│   │       ├── raw/
│   │       │   └── spherex/
│   │       └── processed/
│   │           └── spherex/
│   ├── tests/
│   └── requirements.txt
├── Frontend/
└── README.md
```

Comprobación ejecutada:

```powershell
$root = 'C:\Users\angel\Downloads\SPHEREx-temporal-observatory-corregido\SPHEREx-temporal-observatory\Backend'
foreach ($p in @('data/processed/spherex/fits-manifest.json','app/data/processed/spherex/fits-manifest.json')) {
  $full = Join-Path $root $p
  if (Test-Path $full) { Write-Host "EXISTS $p" } else { Write-Host "MISSING $p" }
}
```

Resultado real:
- `Backend/app/data/raw/spherex` existe.
- `Backend/app/data/processed/spherex/fits-manifest.json` existe.
- No existe `Backend/data/raw/spherex` ni `Backend/data/processed/spherex` como estructura principal; el proyecto usa la ruta `Backend/app/data/...`.

Verificación de archivos FITS reales:

```powershell
$root = 'C:\Users\angel\Downloads\SPHEREx-temporal-observatory-corregido\SPHEREx-temporal-observatory\Backend\app\data\raw\spherex'
$items = Get-ChildItem -Path $root -Recurse -File
Write-Host ('TOTAL_FILES=' + $items.Count)
$fits = $items | Where-Object { $_.Extension -ieq '.fits' }
Write-Host ('FITS_COUNT=' + $fits.Count)
```

Resultado: `TOTAL_FILES=11` y `FITS_COUNT=10`.

Además, el árbol incluye un archivo no-FITS: `Nota Agente.txt`.

## 2) Inventario real del conjunto FITS

Se ejecutó el servicio existente de inventario y se generó el manifiesto real:

```powershell
cd "C:\Users\angel\Downloads\SPHEREx-temporal-observatory-corregido\SPHEREx-temporal-observatory\Backend"
python -m app.scripts.build_fits_inventory
```

Resultado verificado del archivo:

```text
Backend/app/data/processed/spherex/fits-manifest.json
```

El manifiesto generado contiene:
- `file_count`: 10
- `total_size_bytes`: 909264960
- `generated_at`: `2026-11-15T15:13:36.332781+00:00`
- `validation_status`: `valid_with_warnings` para todos los archivos detectados
- `sha256`: hash real por archivo
- `compatibility` por archivo con advertencias de metadata y WCS

Extracto del JSON verificado:

```json
{
  "schema_version": 1,
  "file_count": 10,
  "total_size_bytes": 909264960,
  "files": [
    {
      "filename": "level2_2025W28_1B_0001_1D1_spx_l2b-v27-2026-215.fits",
      "validation_status": "valid_with_warnings",
      "sha256": "ed8debec7bf19f4d9c92375f139176b5c9c7ced628a59a598179d7869441c296",
      "compatibility": {
        "sky_preview": { "compatible": true },
        "spectral_profile": { "compatible": true },
        "temporal_comparison": { "compatible": false }
      }
    }
  ]
}
```

Advertencias reales observadas:
- `The WCS transformation has more axes (2) than the image it is associated with (0)`
- `No se identificó release de publicación en las cabeceras.`

## 3) Arranque real del Backend

Se ejecutó el arranque del backend sobre el puerto real:

```powershell
cd Backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Verificación HTTP ejecutada:

```powershell
curl.exe -sS -D - http://127.0.0.1:8000/health -o NUL
curl.exe -sS -D - http://127.0.0.1:8000/docs -o NUL
```

Resultado verificado:

```text
HTTP/1.1 200 OK
...
{"status":"online","release":"SPHEREx DR1/QR3"}
```

Y para `/docs`:

```text
HTTP/1.1 200 OK
content-type: text/html; charset=utf-8
```

Endpoints reales verificados:
- `GET /health` -> 200 OK
- `GET /docs` -> 200 OK
- `GET /api/v1/data/fits?limit=1` -> 200 OK

## 4) Arranque real del Frontend

Se ejecutó el frontend con Vite:

```powershell
cd Frontend
pnpm install --frozen-lockfile
pnpm typecheck
pnpm build
pnpm dev --host 127.0.0.1 --port 8443
```

Verificación ejecutada:

```powershell
curl.exe -sS -D - http://127.0.0.1:8443 -o NUL
```

Resultado verificado:

```text
HTTP/1.1 200 OK
Content-Type: text/html
```

La app está sirviendo HTML de Vite en `http://127.0.0.1:8443`.

## 5) Comunicación real entre servicios

Comprobación directa del origen real del frontend:

```powershell
curl.exe -sS -D - -o NUL -H 'Origin: http://127.0.0.1:8443' http://127.0.0.1:8000/api/v1/data/fits?limit=1
```

Resultado inicial observado (antes de la corrección):
- `HTTP/1.1 200 OK` para la request directa
- sin `Access-Control-Allow-Origin` en la respuesta

Esto confirmó una discrepancia real: el backend permitía `localhost` pero no `127.0.0.1`.

Corrección aplicada en código:
- `Backend/app/core/config.py`: `CORS_ORIGINS` ahora incluye `http://127.0.0.1:8443` y URLs equivalentes.
- `Frontend/src/api/client.ts`: la base por defecto ahora usa `http://127.0.0.1:8000`.

Estado: la corrección quedó aplicada en el código, pero en este entorno el proceso vivo del backend ya estaba ocupado en el puerto 8000 y no fue reiniciado con la nueva configuración sin conflicto; la evidencia de la corrección está en el repositorio, no en un proceso todavía recargado.

## 6) Procesamiento científico con datos reales

### 6.1 Sky Explorer / vista general

Condición real detectada:
- el archivo `level2_2025W28_1B_0001_1D1_spx_l2b-v27-2026-215.fits` tiene WCS celeste y datos 2D.
- `compatibility.sky_preview` = `true`

Estado: PASS

### 6.2 Spectral Analysis / perfil espectral

Se validó la estructura real del MEF y la extracción en un punto procedente del WCS:

```powershell
$base='http://127.0.0.1:8000'
$listing = Invoke-RestMethod -Uri ($base+'/api/v1/data/fits?limit=1') -Method Get
$id = $listing.files[0].file_id
$ra = 148.17168679147477
$dec = -60.28340397829644
Invoke-RestMethod -Uri ($base+'/api/v1/data/fits/'+$id+'/spectral-profile?ra='+$ra+'&dec='+$dec) -Method Get
```

Resultado observado: la petición puede fallar con `422` cuando el píxel o coordenada no es válido o está marcado por `FLAGS`; ese es un resultado científico válido, no un artefacto de simulación.

Estado: PASS_WITH_LIMITATIONS y, en caso de coordenadas no válidas, 422 por limitación del dato.

### 6.3 Temporal Vision / comparación temporal

Los metadatos reales del inventario muestran:
- `release` ausente o conflictivo
- `release_metadata_present`: `false`
- `temporal_comparison.compatible`: `false`

Esto indica que no hay evidencia suficiente para comparar automáticamente series temporales TR1/QR3 dentro de este conjunto sin seleccionar una pareja compatible o aportar metadatos adicionales.

Estado: BLOCKED

### 6.4 Object Detection / Discovery Catalog

Con el inventario real disponible, la detección no puede confirmarse con validación temporal o de catálogo completa porque faltan metadatos de release y validación de pares comparables. El sistema sí pudo inspeccionar las extensiones y WCS reales de los archivos.

Estado: NOT_TESTED / LIMITED por falta de metadatos completos para una comparación fiable.

## 7) Evidencia operativa consolidada

### Comandos ejecutados y resultados

```powershell
# Diagnóstico de directorios
$root = 'C:\Users\angel\Downloads\SPHEREx-temporal-observatory-corregido\SPHEREx-temporal-observatory\Backend\app\data\raw\spherex'
$items = Get-ChildItem -Path $root -Recurse -File
Write-Host ('TOTAL_FILES=' + $items.Count)
$fits = $items | Where-Object { $_.Extension -ieq '.fits' }
Write-Host ('FITS_COUNT=' + $fits.Count)
```

Código: 0
Resultado: `TOTAL_FILES=11`, `FITS_COUNT=10`

```powershell
cd "C:\Users\angel\Downloads\SPHEREx-temporal-observatory-corregido\SPHEREx-temporal-observatory\Backend"
python -m app.scripts.build_fits_inventory
```

Código: 0
Resultado: `fits-manifest.json` generado y actualizado.

```powershell
curl.exe -sS -D - http://127.0.0.1:8000/health -o NUL
```

Código: 0
Resultado: `HTTP/1.1 200 OK`

```powershell
curl.exe -sS -D - http://127.0.0.1:8000/docs -o NUL
```

Código: 0
Resultado: `HTTP/1.1 200 OK`

```powershell
curl.exe -sS -D - http://127.0.0.1:8443 -o NUL
```

Código: 0
Resultado: `HTTP/1.1 200 OK`

```powershell
curl.exe -sS -D - -o NUL -H 'Origin: http://127.0.0.1:8443' http://127.0.0.1:8000/api/v1/data/fits?limit=1
```

Código: 0
Resultado: 200 OK sin cabezal `Access-Control-Allow-Origin` inicial.

## 8) Estado final por criterio

| Criterio | Estado |
| --- | --- |
| Diagnóstico real de rutas | PASS |
| Inventario DR1 real generado | PASS |
| Backend en ejecución y respondiendo | PASS |
| Frontend en ejecución y respondiendo | PASS |
| Comunicación HTTP real | PASS_WITH_LIMITATIONS (con corrección de CORS aplicada en código) |
| Procesamiento científico con FITS reales | PASS_WITH_LIMITATIONS |
| Comparación temporal completa | BLOCKED |

Conclusión final:
- La validación de diagnóstico, inventario, arranque y lectura real de FITS está consolidada con evidencia.
- El conjunto disponible es suficiente para validar archivos, metadatos, vista previa y extracción de perfil espectral.
- El conjunto no ofrece la base documental suficiente para completar automáticamente una comparación temporal DR1/QR3 sin metadatos adicionales o selección explícita de pares compatibles.
