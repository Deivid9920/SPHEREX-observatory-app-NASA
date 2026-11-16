# Fase 4.5.2 — Auditoría de compatibilidad, calidad y medición

**Fecha de validación:** 2026-11-15  
**Estado global:** `PASS_WITH_LIMITATIONS`

## Conclusión

La extracción espectral se ejecutó desde la interfaz con FITS locales reales. El backend interpreta `FLAGS` como bitmap, excluye píxeles según la política documentada, conserva advertencias, no inventa incertidumbres y persiste tanto resultados utilizables como intentos bloqueados. Se recuperaron ejecuciones guardadas tras reiniciar el backend y los diez hashes de los FITS originales siguen coincidiendo con el manifiesto.

Esto **no** demuestra una calibración absoluta ni una validación astrométrica completa. Los nueve MEF no identifican explícitamente su release; los productos Spectral WCS y sus asociaciones siguen `partially_verified`. Además, Astropy advirtió que algunos headers contienen coeficientes SIP con una declaración `CTYPE` inconsistente. El cubo carece de `VARIANCE`, por lo que su significancia estadística no está disponible.

## 1. Datos reales y preservación

El inventario usado fue [`fits-manifest.json`](../app/data/processed/spherex/fits-manifest.json), generado sobre `Backend/app/data/raw/spherex/`.

| Comprobación | Resultado |
|---|---|
| Archivos inventariados | 10, total 909,264,960 bytes |
| Imágenes espectrales MEF | 9, cada una de 2040 × 2040 píxeles |
| Cubo espectral | 1, `Npix0_cube.fits`, 102 × 512 × 512 |
| Hashes de originales | 10/10 SHA-256 coinciden con el manifiesto; ningún original fue modificado |
| Extensiones `VARIANCE` de MEF | 37,454,400 muestras; 1,642 NaN, 0 infinitos y 0 valores finitos no positivos |
| `VARIANCE` del cubo | No existe |
| Valores no finitos en `IMAGE` del cubo | 526,979 |

El inventario y los hashes completos están en el manifiesto enlazado; los SHA-256 usados por las ejecuciones visibles se incluyen abajo.

## 2. Calidad y tratamiento de incertidumbre

Se contrastó la decodificación con la Tabla 16 del [SPHEREx Explanatory Supplement](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp.pdf), versión 2.1 (2026-11-10), y con las recomendaciones de máscara para fotometría. `FLAGS` se trata como bitmap: los bits pueden coexistir y no son categorías mutuamente excluyentes. Los bits no documentados quedan como `unknown` y no se consideran válidos.

Bits excluidos por la política aplicada, numerados desde cero: `SUR_ERROR` (2), `NONFUNC` (6), `DICHROIC` (7), `MISSING_DATA` (9), `HOT` (10), `COLD` (11), `NONLINEAR` (15), `PERSIST` (17), `BLOOM` (26), `SNOWBALL` (27), `HALO` (28) y `SATELLITE_HALO` (29). Otros bits reconocidos —por ejemplo `SOURCE`, `OUTLIER` y `OVERFLOW`— se decodifican y reportan como advertencias cuando corresponde. No se encontraron bits desconocidos en los diez archivos.

- Una muestra de D1 con `SOURCE` (bit 21) se conservó como medición con advertencia; la incertidumbre se calculó desde `VARIANCE`.
- Una posición D1 con `TRANSIENT | SOURCE | HALO` (valor bitmap `270532609`) se excluyó por `HALO`. La respuesta conserva banderas y coordenadas, deja flujo e incertidumbre en `null`, e informa `0/1` canales utilizables. La ejecución se persistió con estado `BLOCKED`.
- En MEF, una incertidumbre solo se ofrece cuando la varianza es finita, positiva y tiene unidades compatibles. El conteo agregado incluye 1,642 valores NaN, pero no infinitos ni valores finitos no positivos.
- El cubo no tiene `VARIANCE`: la UI informa incertidumbre `missing` y no calcula significancia estadística. La muestra probada contiene 100/102 canales utilizables; los otros dos no se convirtieron en mediciones válidas.

## 3. Spectral WCS y alcance científico

Están disponibles los auxiliares oficiales D1 y D2:

| Detector | Producto | SHA-256 local | `CWAVE` / `CBAND` |
|---|---|---|---|
| D1 | `spectral_wcs_D1_spx_cal-swcs-v5-2026-191.fits` | `44fb48b236e25a99d42c8986da0064cc58359527e1fc76e182eda52371a1ae23` | 2040 × 2040; `um`; 4,161,600/4,161,600 valores finitos y positivos en cada mapa |
| D2 | `spectral_wcs_D2_spx_cal-swcs-v5-2026-191.fits` | `0eb4e27f351e6161e21372818f9e811480a7ab8bab9295722f180791e151a463` | 2040 × 2040; `um`; 4,161,600/4,161,600 valores finitos y positivos en cada mapa |

El CalibrationManager asocia los nueve MEF a los mapas del detector correspondiente. La comparación con los puntos `WCS-WAVE` embebidos cubre 81 controles D1 y 121 controles D2; la diferencia máxima observada para `CWAVE` y `CBAND` es 0.0 µm. Los mapas se consultan directamente por píxel, sin interpolación ni ajuste artificial de dimensiones.

La asociación permanece `partially_verified`: falta un release explícito en los headers de los MEF, por lo que no se afirma correspondencia completa de procedencia. La comparación de puntos de control tampoco equivale a una comparación independiente píxel a píxel de la semántica completa de los mapas. `CWAVE`/`CBAND` proporcionan información de longitud de onda/ancho de banda, pero **no** demuestran calibración fotométrica absoluta.

Durante extracción, Astropy advirtió que había coeficientes SIP con `CTYPE` sin el sufijo `-SIP`; Astropy aplica los coeficientes y advierte que las coordenadas resultantes podrían ser incorrectas. No se editaron los FITS originales ni se aplicó una corrección no documentada. La localización celeste requiere una validación astrométrica independiente antes de elevar su estado.

## 4. Prueba real desde la interfaz

Se usó el navegador en `http://127.0.0.1:8443/`, en modo **Observatorio**, con productos del inventario local. Se capturaron las respuestas de red relevantes y se guardaron las capturas:

| Flujo | Producto / entrada | Respuesta y resultado |
|---|---|---|
| D1 válido | `level2_2025W28_1B_0001_1D1_spx_l2b-v27-2026-215.fits`, ID `fa0be417-a929-52b0-bd99-8e02be2ef385`, SHA-256 `ed8debec7bf19f4d9c92375f139176b5c9c7ced628a59a598179d7869441c296`, píxel (1000, 1000) | `POST /spectral-runs` 201; `CWAVE=0.9081966281 µm`, `CBAND=0.0230476782 µm`, flujo `0.6777377725 MJy/sr`, error estadístico `0.0298064041 MJy/sr`, `SOURCE`, `valid_with_warnings`. Calibración `cal-2bd2033d8dbb41db68e62577`. Run `093bb14d-f66a-4921-81c9-5b723fda07a8`; resultado SHA-256 `3036e2ce42eb8ca234e6e27fac6f9d5ee07bae5774019aaeb52d2937a226fd14`. |
| D2 válido | `level2_2025W17_4B_0001_1D2_spx_l2b-v27-2026-196.fits`, ID `075c2cab-8372-599a-823c-9df2fd606530`, SHA-256 `3d51d09b5a8653b21ec0bbdaffa923545af8bdb5af4b4a2b42fe260b4f5a3b9a`, píxel (1019, 1019) | `POST /spectral-runs` 201; `CWAVE=1.3376700878 µm`, `CBAND=0.0321996361 µm`, flujo `0.2325007468 MJy/sr`, error estadístico `0.0172795790 MJy/sr`, `SOURCE`, `valid_with_warnings`. Calibración `cal-6747e7384946891cca8b541a`. Run `f8fc0494-385b-4dee-8c8e-9e4cc1d22b9d`; resultado SHA-256 `e4f8bacb8d9a7c09c7f36352b8be45ce7b30955faaccd51eb6916d013309b827`. |
| D1 inválido | Mismo MEF e ID, píxel (1019, 1019), `TRANSIENT | SOURCE | HALO` | `POST /spectral-runs` 201 para registrar el intento; flujo/error no disponibles, `0/1` canales, estado persistido `BLOCKED`. Calibración asociada `cal-2bd2033d8dbb41db68e62577`. Run `4a5d383f-8e4d-483a-98f0-1a9f94f80df7`; resultado SHA-256 `6ae3dfce1e1d9f107d4eb098417708b658c7db01d3d5211863b2564f9678aa33`. |
| Cubo | `Npix0_cube.fits`, ID `60a077eb-47e2-504c-9f69-1573d0ef83f9`, SHA-256 `a595a4511dc0b63e0a4c1fb3d0a7735317f17ebf1d11d774888b2566bdb870bc`, píxel (255, 255), 102 canales nativos | `POST /spectral-runs` 201; `SPECTRAL_CHANNELS.WAVELENGTH` contrastado con WCS 3D; 100/102 utilizables; unidad `MJy/sr`; incertidumbre `missing` por ausencia de `VARIANCE`; advertencias visibles. Calibración registrada `cal-bf15da33fcaf2db5f7d90cc6`. Run `21327477-86f1-486b-adfa-02076059eb9e`; resultado SHA-256 `2a8c4e8c953f2717bbf51f035e68420c7bff3ee2e9a08fc9fbc314d926d54a6`. |

En cada flujo se observó la selección del archivo local y se mantuvo el modo Observatorio. Los previews reales devolvieron 200; las consultas de inventario, metadatos y calibración devolvieron 200. No se capturaron errores de consola durante las extracciones de navegador incluidas en esta evidencia. Las solicitudes CORS del origen `http://127.0.0.1:8443` recibieron `OPTIONS 200` y `Access-Control-Allow-Origin` con el mismo origen.

Capturas:

- [D1 — extracción válida y preview](./evidence/phase452-spectral-analysis-detector1.png)
- [D2 — extracción válida y preview](./evidence/phase452-spectral-analysis-detector2.png)
- [D1 — píxel excluido por FLAGS](./evidence/phase452-spectral-analysis-invalid-flags.png)
- [Cubo — sin varianza](./evidence/phase452-spectral-analysis-cube-no-variance.png)
- [Resumen de peticiones, códigos HTTP y respuestas](./evidence/phase452-network-summary.json)

## 5. Servidores, persistencia y comandos

El Backend se inició desde `Backend/` con:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

El Frontend se sirvió desde `Frontend/` en `http://127.0.0.1:8443/`. Durante las comprobaciones finales, los procesos fueron Backend PID `18640` y Frontend PID `2380`. Respondieron `GET /health` (200, `{"status":"online","version":"1.0.0"}`), `/docs` (200), `/openapi.json` (200), el inventario real (200), los previews (200), los perfiles/runs (201), y `GET /api/v1/data/scientific-runs/{run_id}` (200). El HTML del frontend respondió 200.

Los runs D1 y D2 creados antes del reinicio se recuperaron con HTTP 200 después de iniciar el Backend de nuevo. El run inválido y el del cubo también se recuperaron mediante el endpoint de runs; el primero se mantuvo `BLOCKED` y los válidos `PASS_WITH_LIMITATIONS`. Durante el arranque, PostgreSQL no estuvo disponible por un error de decodificación UTF-8 y la aplicación usó SQLite local; Redis tampoco estaba disponible y se usó la caché en memoria. Estos fallbacks se registran como limitaciones del entorno.

| Comando / comprobación | Resultado |
|---|---|
| `python -m pytest -q` desde `Backend/` | Exit 0; **36 passed**, 22 warnings |
| `pnpm typecheck` desde `Frontend/` | Exit 0 |
| `pnpm build` desde `Frontend/` | Exit 0 |
| Recalcular y comparar SHA-256 de originales con el manifiesto | Exit 0; 10 verificados, 0 faltantes o discrepantes |
| `GET /health`, frontend y preflight CORS con `curl.exe` | HTTP 200 en los tres casos |

El mensaje de herramienta sobre el shell de arranque con exit `-1` corresponde al ciclo de vida del servidor: Uvicorn había registrado `Application startup complete`, estaba escuchando en `127.0.0.1:8000` y atendió solicitudes HTTP 200; el proceso se detuvo después para reiniciar y comprobar persistencia. No fue un fallo de inicialización. Una comprobación auxiliar con `Invoke-WebRequest` terminó con exit 1 porque esa versión de PowerShell no permite sus funciones de lectura en modo no interactivo; se repitió con `curl.exe`, que obtuvo los códigos indicados arriba.

Los 22 avisos de pytest incluyen advertencias de dependencias y de Astropy/WCS (incluidos problemas de convergencia para un punto de prueba). Las pruebas aprobaron, pero esos avisos no se interpretan como evidencia de precisión astrométrica.

## 6. Cambios y regresión

La implementación auditada:

- decodifica `FLAGS` por bits según la tabla oficial, conserva bits reconocidos, excluye los definidos por la política y trata bits desconocidos como no válidos;
- propaga coordenadas de píxel, bits/nombres, estado de calidad e incertidumbre al perfil y al resultado persistido;
- evita devolver flujo o error estadístico de píxeles excluidos y no inventa varianza para el cubo;
- incluye parámetros y procedencia normalizados en el digest reproducible; resultados inválidos o con calidad desconocida quedan `BLOCKED`;
- presenta estos estados, unidades y advertencias en Spectral Analysis.

Los cambios y regresiones están en [`fits_processor.py`](../app/services/fits_processor.py), [`data.py`](../app/api/v1/endpoints/data.py), [`scientific_results.py`](../app/services/scientific_results.py), [`fits.ts`](../../Frontend/src/api/fits.ts), [`App.tsx`](../../Frontend/src/App.tsx), [`test_fits_inventory.py`](../tests/test_fits_inventory.py) y [`test_fits_data_api.py`](../tests/test_fits_data_api.py).

## 7. Estado por capacidad

| Capacidad | Estado | Motivo |
|---|---|---|
| Integridad de los diez FITS originales | `PASS` | 10/10 SHA-256 coinciden con el manifiesto. |
| Decodificación y política de `FLAGS` | `PASS_WITH_LIMITATIONS` | Bitmap, máscaras y bits desconocidos probados; la política de exclusión no sustituye validación de cada producto científico derivado. |
| Incertidumbre estadística MEF | `PASS_WITH_LIMITATIONS` | Varianza disponible y positiva en valores finitos; existen 1,642 NaN que no producen error estadístico válido. |
| Incertidumbre del cubo | `BLOCKED` | No existe extensión `VARIANCE`; no se puede evaluar significancia. |
| Extracción espectral D1/D2 en UI | `PASS_WITH_LIMITATIONS` | Flujo local real, CWAVE/CBAND, unidad, error estadístico, FLAGS, procedencia y estado visibles; release del MEF no identificado. |
| Rechazo de píxel enmascarado | `PASS` | HALO excluido, flujo/error ausentes, ejecución trazable `BLOCKED`. |
| Asociación Spectral WCS | `PASS_WITH_LIMITATIONS` | Mapas oficiales, detector y controles WCS-WAVE comprobados; la procedencia de release del MEF sigue parcial. |
| WCS celeste / correspondencia RA-Dec a píxel | `BLOCKED` para validación completa | Advertencia SIP/CTYPE y falta de comparación astrométrica independiente. |
| Persistencia y recuperación de resultados | `PASS_WITH_LIMITATIONS` | GET tras reinicio; almacenamiento local SQLite por indisponibilidad de PostgreSQL. |
| Calibración fotométrica absoluta/integrada | `NOT_TESTED` | CWAVE/CBAND no bastan para afirmar calibración fotométrica absoluta ni espectro integrado. |
| Temporal Vision y descubrimientos | `NOT_TESTED` | Fuera del alcance de esta auditoría. |

## 8. Pendientes priorizados

1. **Validar la astrometría**: resolver, con documentación oficial del producto y sin modificar los originales, la inconsistencia SIP/CTYPE; contrastar RA/Dec contra puntos de referencia independientes.
2. **Completar procedencia de release**: obtener metadatos autoritativos para cada MEF o conservar el estado `partially_verified`; no inferirlo del nombre del archivo.
3. **Mantener la limitación del cubo**: no publicar incertidumbre ni significancia estadística hasta disponer de una varianza/covarianza científicamente compatible.
4. **No elevar calibración fotométrica**: se requiere evidencia adicional de calibración y validación para flujos integrados o absolutos.
5. **Infraestructura**: revisar la configuración de PostgreSQL que produjo el error UTF-8 si se requiere persistencia fuera del fallback SQLite; Redis es opcional para esta validación.

La Fase 4.5.2 queda **validada con limitaciones**, no como calibración espectrofotométrica integral ni como validación astrométrica completa.
