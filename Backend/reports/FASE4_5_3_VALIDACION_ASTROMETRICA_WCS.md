# FASE 4.5.3 — Validación astrométrica, corrección documentada de WCS y trazabilidad de coordenadas

## 1. Resumen ejecutivo

La validación de la astrometría de los productos SPHEREx usados por la plataforma se resolvió con una conclusión científica conservadora: la geometría WCS del espacio celestial de los MEF es estructuralmente válida, los coeficientes SIP están presentes y Astropy los aplica en la transformación celestial, pero la precisión absoluta del alineamiento con el cielo real no está demostrada por una referencia astrométrica independiente.

La evidencia disponible sugiere lo siguiente:

- Los nueve MEF son productos `spectral_image_mef` de 2040 × 2040 píxeles y cada uno contiene una solución celestial con `CTYPE1 = RA---TAN-SIP` y `CTYPE2 = DEC--TAN-SIP`.
- La advertencia de Astropy no está asociada a una corrupción del FITS ni a una modificación de los encabezados originales; refleja la incompatibilidad habitual entre la presencia de coeficientes SIP y la ausencia de `-SIP` en un WCS alternativo `WAVE-TAB` del eje espectral.
- La solución espacial primaria usa SIP y por tanto debe considerarse `SIP_CONFIRMED_ACTIVE` para el WCS celestial efectivo utilizado por Astropy.
- La validación astrométrica absoluta sigue en `ASTROMETRY_UNVALIDATED` porque no se completó una comparación con Gaia DR3 ni otra referencia independiente suficiente.
- El cubo `Npix0_cube.fits` tiene una WCS celeste estructuralmente válida, sin SIP y sin `FINAST`, pero tampoco queda validado astronómicamente con una referencia externa.
- El código del proyecto fue reforzado para conservar trazabilidad de coordenadas, estados WCS, advertencias y variantes utilizadas, sin editar FITS originales ni ocultar la advertencia.

Resultado final científico: `PASS_WITH_LIMITATIONS`.

## 2. Estado inicial

Antes de la validación final se confirmó que:

- Los diez FITS originales del inventario siguen presentes en `Backend/app/data/raw/spherex/`.
- El manifiesto `Backend/app/data/processed/spherex/fits-manifest.json` sigue coincidiendo con todos los SHA-256 originales.
- No se modificó ningún FITS ni el manifiesto.
- La auditoría anterior (fase 4.5.2) ya había identificado la advertencia SIP/CTYPE como un problema de interpretación WCS y no como un fallo de integridad.
- El flujo de extracción local de SPHEREx funciona con productos reales y conserva la procedencia del origen, las advertencias y los estados de validación.

## 3. Archivos inspeccionados

### 3.1 MEF

Los nueve MEF inspeccionados fueron:

1. `level2_2025W28_1B_0001_1D1_spx_l2b-v27-2026-215.fits`
2. `level2_2025W28_1B_0002_1D1_spx_l2b-v27-2026-215.fits`
3. `level2_2025W28_1B_0003_1D1_spx_l2b-v27-2026-215.fits`
4. `level2_2025W25_1B_0429_1D1_spx_l2b-v27-2026-213.fits`
5. `level2_2025W17_4B_0001_1D1_spx_l2b-v27-2026-196.fits`
6. `level2_2025W17_4B_0001_1D2_spx_l2b-v27-2026-196.fits`
7. `level2_2025W18_1B_0001_1D1_spx_l2b-v27-2026-196.fits`
8. `level2_2025W30_1B_0001_1D1_spx_l2b-v27-2026-220.fits`
9. `level2_2025W42_1A_0001_1D1_spx_l2b-v27-2026-243.fits`

### 3.2 Cubo

- `Npix0_cube.fits`

## 4. Auditoría de encabezados WCS

### 4.1 Propiedades comunes observadas

Los nueve MEF comparten una estructura compatible con la misión:

- `NAXIS = 2`
- `NAXIS1 = 2040`
- `NAXIS2 = 2040`
- `WCSAXES = 2`
- `CTYPE1 = RA---TAN-SIP`
- `CTYPE2 = DEC--TAN-SIP`
- `CUNIT1 = deg`
- `CUNIT2 = deg`
- `RADESYS = ICRS`
- `LONPOLE = 180.0`
- `LATPOLE = CRVAL2`
- `CRPIX1 = 1020.5`
- `CRPIX2 = 1020.5`
- `CDELT1 = 1.0`
- `CDELT2 = 1.0`
- `PC` matrix present
- `FINAST = 0`

Todos los encabezados tienen SIP completo en las familias `A`, `B`, `AP` y `BP` con orden 3 y 10 coeficientes cada familia, sin valores nulos ni no finitos. El número total de coeficientes SIP es 40 por MEF.

### 4.2 Tabla comparativa resumida

| Archivo | Detector | Fecha | CTYPE1 / CTYPE2 | FINAST | SIP | Clasificación WCS | Estado astrométrico |
|---|---:|---|---|---:|---|---|---|
| level2_2025W28_1B_0001_1D1...fits | 1 | 2026-08-04T03:16:52.560 | `RA---TAN-SIP` / `DEC--TAN-SIP` | 0 | activo | `WCS_STRUCTURALLY_VALID` | `ASTROMETRY_UNVALIDATED` |
| level2_2025W28_1B_0002_1D1...fits | 1 | 2026-08-04T02:00:42.631 | `RA---TAN-SIP` / `DEC--TAN-SIP` | 0 | activo | `WCS_STRUCTURALLY_VALID` | `ASTROMETRY_UNVALIDATED` |
| level2_2025W28_1B_0003_1D1...fits | 1 | 2026-08-04T00:53:06.211 | `RA---TAN-SIP` / `DEC--TAN-SIP` | 0 | activo | `WCS_STRUCTURALLY_VALID` | `ASTROMETRY_UNVALIDATED` |
| level2_2025W25_1B_0429_1D1...fits | 1 | 2026-08-01T10:39:02.824 | `RA---TAN-SIP` / `DEC--TAN-SIP` | 0 | activo | `WCS_STRUCTURALLY_VALID` | `ASTROMETRY_UNVALIDATED` |
| level2_2025W17_4B_0001_1D1...fits | 1 | 2026-07-15T18:20:15.775 | `RA---TAN-SIP` / `DEC--TAN-SIP` | 0 | activo | `WCS_STRUCTURALLY_VALID` | `ASTROMETRY_UNVALIDATED` |
| level2_2025W17_4B_0001_1D2...fits | 2 | 2026-07-15T21:21:27.825 | `RA---TAN-SIP` / `DEC--TAN-SIP` | 0 | activo | `WCS_STRUCTURALLY_VALID` | `ASTROMETRY_UNVALIDATED` |
| level2_2025W18_1B_0001_1D1...fits | 1 | 2026-07-16T00:44:42.294 | `RA---TAN-SIP` / `DEC--TAN-SIP` | 0 | activo | `WCS_STRUCTURALLY_VALID` | `ASTROMETRY_UNVALIDATED` |
| level2_2025W30_1B_0001_1D1...fits | 1 | 2026-08-08T19:40:54.506 | `RA---TAN-SIP` / `DEC--TAN-SIP` | 0 | activo | `WCS_STRUCTURALLY_VALID` | `ASTROMETRY_UNVALIDATED` |
| level2_2025W42_1A_0001_1D1...fits | 1 | 2026-08-31T19:36:38.287 | `RA---TAN-SIP` / `DEC--TAN-SIP` | 0 | activo | `WCS_STRUCTURALLY_VALID` | `ASTROMETRY_UNVALIDATED` |

Los hashes reales corroborados fueron:

| Archivo | SHA-256 |
|---|---|
| level2_2025W28_1B_0001_1D1...fits | `ed8debec7bf19f4d9c92375f139176b5c9c7ced628a59a598179d7869441c296` |
| level2_2025W28_1B_0002_1D1...fits | `9bbf5ff345c36c0f95689a856f788562e48bc56fe792a558c1cbc4a16b195bde` |
| level2_2025W28_1B_0003_1D1...fits | `1e7318b504635f0de620de975e5109a5b83aca560fd07096a4ec881d32a733a2` |
| level2_2025W25_1B_0429_1D1...fits | `921b24805a3213467ef6a8502bb4af4231be78f4bd1b99802b52609c7d83d28c` |
| level2_2025W17_4B_0001_1D1...fits | `b2b78466058203dbabcf841b6223697e7e69b08b18a00882c764c6f8fd0acd59` |
| level2_2025W17_4B_0001_1D2...fits | `3d51d09b5a8653b21ec0bbdaffa923545af8bdb5af4b4a2b42fe260b4f5a3b9a` |
| level2_2025W18_1B_0001_1D1...fits | `64113e82f4357303d9a595e384a51cd1e021e74c3ce81443d31ee74d42f8619a` |
| level2_2025W30_1B_0001_1D1...fits | `6b0061a1bea9539b4fe4ae288911c770d08b058ac900a068ddb28490192cc3a6` |
| level2_2025W42_1A_0001_1D1...fits | `bfcd10b34d3222855ea9cd92b6e103e56b90949d92c399f8a5d36a608c0d970e` |

## 5. Análisis SIP/CTYPE

La evidencia astronómica real en los header confirma que:

- Hay coeficientes SIP en las familias `A`, `B`, `AP` y `BP`.
- El orden es 3 para todas las familias y para todos los MEF.
- Hay 10 coeficientes por familia, todos finitos.
- El WCS celeste espacial principal usa `RA---TAN-SIP`, `DEC--TAN-SIP` y Astropy utiliza esos coeficientes.
- La advertencia aparece cuando Astropy construye la WCS alternativa `W` para la extensión `WAVE-TAB`, donde no hay `-SIP` en `CTYPE`. La advertencia es real, pero es de una WCS espectral alternativa, no de la WCS celeste primaria.

La conclusión defendible es:

- `SIP_CONFIRMED_ACTIVE` para el WCS celestial efectivo del espacio en la imagen `IMAGE`.
- La advertencia no se silencia ni se elimina.
- No se eliminan coeficientes SIP del FITS original.

La diferencia entre las variantes `A` (con SIP) y `B` (sin SIP) sobre una grilla 5 × 5 por MEF fue consistente y de magnitud angular significativa:

| MEF | Diferencia mediana | p95 | Máximo |
|---|---:|---:|---:|
| D1 #1 | 18.49 arcsec | 56.28 arcsec | 80.71 arcsec |
| D1 #2 | 18.44 arcsec | 55.74 arcsec | 85.24 arcsec |
| D1 #3 | 17.37 arcsec | 56.59 arcsec | 79.41 arcsec |
| D1 #4 | 15.61 arcsec | 55.57 arcsec | 78.54 arcsec |
| D1 #5 | 18.51 arcsec | 57.25 arcsec | 80.57 arcsec |
| D2 #1 | 16.74 arcsec | 63.91 arcsec | 69.25 arcsec |
| D1 #6 | 18.91 arcsec | 60.09 arcsec | 77.77 arcsec |
| D1 #7 | 19.18 arcsec | 56.40 arcsec | 81.28 arcsec |
| D1 #8 | 17.85 arcsec | 57.21 arcsec | 82.09 arcsec |

Estas diferencias no validan ninguna de las dos variantes; solo indican que la elección de SIP/no-SIP impacta la geometría relativa entre 15 y 85 arcsec en la grilla de prueba. La comparación tampoco sustituye una validación astrométrica con referencia real.

## 6. Análisis de FINAST

La documentación oficial y la auditoría de los headers muestran que:

- `FINAST = 0` en los nueve MEF.
- El cubo no incluye `FINAST`.

La interpretación correcta es:

- `FINAST = 0` se interpreta como “solución astrométrica buena” según el pipeline.
- Eso no equivale a una validación astrométrica absoluta con Gaia u otra referencia independiente.
- La ausencia de `FINAST` no debe interpretarse como un signo de validación. Se registra como advertencia y se mantiene `ASTROMETRY_UNVALIDATED`.

## 7. Documentación oficial consultada

Las referencias oficiales y técnicas consultadas incluyeron:

- SPHEREx Explanatory Supplement, v2.1, IRSA.
- IRSA SPHEREx Data Products documentation.
- IRSA SPHEREx Data Access documentation.
- Astropy SIP note: `https://docs.astropy.org/en/stable/wcs/note_sip.html`
- Documentación del pipeline de SPHEREx y de sus WCS de calibración.

La conclusión clave de la documentación es que la convención SIP exige una `-SIP` en `CTYPE` para que la WCS sea internalmente consistente. Astropy, sin embargo, aplica los coeficientes SIP aunque el encabezado sea inconsistente, exactamente como documenta `note_sip.html`, por lo que la advertencia debe conservarse y no silenciarse.

## 8. Variantes WCS comparadas

Se compararon las siguientes variantes diagnosticas sin tocar los FITS originales:

### Variante A — WCS interpretado con SIP

- Matriz celestial efectiva construida por Astropy desde la WCS del MEF.
- Se usa para las transformaciones reales del backend.
- Resultado: `SIP_CONFIRMED_ACTIVE`.

### Variante B — WCS sin SIP

- Se construye una copia del WCS con `wcs.sip = None` para diagnosticar el efecto comparativo.
- Resultado: diferencias angulares de 15–85 arcsec en muestras de prueba; no se usa como solución validada.

### Variante C — WCS alternativo documentado

- El cubo usa un WCS espacial HEALPix y el eje espectral `WAVE-TAB`; no hay conflicto SIP comparativo en el eje celestial.
- No se encontró una alternativa documentada que sustituya la WCS del MEF con evidencia superior.

Conclusión: la variante A es la que corresponde a la convención en uso por Astropy, y la variante B solo sirve como diagnóstico. Ninguna de las dos constituye una validación absoluta.

## 9. Catálogo astronómico utilizado

No se obtuvo una validación astronómica independiente con Gaia DR3 ni otro catálogo de referencia en este ciclo. El intento de acceso a Gaia DR3 a través de TAP no completó la consulta en el tiempo disponible, por lo que:

- no hay residuos astrométricos publicados en este informe,
- no hay RMS, MAD, percentiles ni cobertura espacial de Gaia,
- no se afirmará que la astrometría final está validada.

La estrategia correcta fue evitar inventar o simular referencias astronómicas.

## 10. Método de asociación de fuentes

No se realizaron asociaciones científicas reales con Gaia debido a la ausencia de catálogo ejecutado. La prueba de validación independiente quedó bloqueada.

## 11. Número de fuentes de referencia

No se obtuvieron fuentes de referencia reales en la fase efectiva. El valor real es 0 en la validación analítica, con bloqueo explícito del procedimiento de asociación y cálculo de residuos.

## 12. Cobertura espacial

No hubo cobertura astrométrica independiente; no se generaron mapas espaciales de residuos ni se evaluó la distribución de fuentes en centro, bordes y esquinas.

## 13. Residuales astrométricos

No se obtuvieron residuales astrométricos reales. La razón es la ausencia de referencia fiable; la plataforma conserva el estado `ASTROMETRY_UNVALIDATED` para no validar una precisión que no se ha demostrado.

## 14. Métricas de precisión

Se calculó únicamente la consistencia interna de la proyección WCS y el round-trip. Los resultados observados fueron:

- Max round-trip para los MEF: entre `4.4e-08` y `1.75e-06` píxeles sobre la grilla de prueba.
- Esto verifica consistencia interna, no precisión astrométrica absoluta.

## 15. Resultados de transformaciones round-trip

La transformación en ambos sentidos fue estable y continua. En la grilla de prueba se comprobó que:

- la conversión `pixel -> sky -> pixel` es interna y matemáticamente reversible,
- los valores no degeneran ni generan `NaN`/`Inf` en los puntos de prueba,
- la diferencia de vuelta es extremadamente pequeña en píxeles,
- no hay evidencia de un desplazamiento constante de un píxel.

Esto no demuestra que la WCS represente correctamente el cielo real.

## 16. Validación del cubo

El cubo `Npix0_cube.fits` tiene:

- forma `102 × 512 × 512`,
- `CTYPE1 = RA---HPX`, `CTYPE2 = DEC--HPX`, `CTYPE3 = WAVE-TAB`,
- `RADESYS = ICRS`,
- `CUNIT1/2 = deg`, `CUNIT3 = um`,
- sin `FINAST`,
- sin `VARIANCE`,
- WCS espacial validada longitudinalmente con estabilidad constante en los canales 0, 51 y 101.

Se evaluó una prueba de consistencia espacial y de canal: el cielo calculado para los ejes espaciales fue idéntico en los canales comparados. La solución espacial del cubo se clasifica como `WCS_STRUCTURALLY_VALID` y `SIP_CONFIRMED_INACTIVE` con `ASTROMETRY_UNVALIDATED`.

## 17. Correcciones implementadas

Se implementó una capa centralizada y segura de gestión WCS, sin editar los FITS ni ocultar advertencias.

Archivos principales:

- `Backend/app/services/astrometry.py`
- `Backend/app/services/fits_processor.py`
- `Backend/app/services/fits_inventory.py`
- `Backend/app/api/v1/endpoints/data.py`
- `Backend/app/services/scientific_results.py`
- `Frontend/src/api/fits.ts`
- `Frontend/src/App.tsx`

La corrección incluye:

- construcción explícita de WCS espacial por producto,
- diferenciación de estados de WCS (`WCS_STRUCTURALLY_VALID`, `WCS_WITH_SIP_INCONSISTENCY`, etc.),
- estados de SIP (`SIP_CONFIRMED_ACTIVE`, `SIP_CONFIRMED_INACTIVE`, `SIP_CONVENTION_INCONSISTENT`, `SIP_UNRESOLVED`),
- rechazo de coordenadas inválidas y fuera de imagen,
- tratamiento controlado de `NaN`, `Inf` y no convergencia,
- trazabilidad de origen, SHA-256, detector, HDU y variante WCS,
- persistencia de resultados científicos con procedencia y advertencias.

## 18. Archivos modificados

- `Backend/app/services/astrometry.py`
- `Backend/app/services/fits_processor.py`
- `Backend/app/services/fits_inventory.py`
- `Backend/app/api/v1/endpoints/data.py`
- `Backend/app/services/scientific_results.py`
- `Frontend/src/api/fits.ts`
- `Frontend/src/App.tsx`
- `Backend/tests/test_astrometry.py`
- `Backend/tests/test_fits_data_api.py`
- `Backend/tests/test_fits_inventory.py`

## 19. Pruebas ejecutadas

Lista de validaciones reales ejecutadas:

- `python -m pytest -q` desde `Backend/` → 45 pruebas pasadas.
- `pytest -q tests/test_astrometry.py tests/test_fits_data_api.py` → 16 pruebas pasadas.
- `pnpm typecheck` desde `Frontend/` → OK.
- `pnpm build` desde `Frontend/` → OK.
- Comprobaciones HTTP en `http://127.0.0.1:8000` para validación de coordenadas: válidas/fuera de imagen/inválidas → respuestas 200/404/422 controladas.
- Verificación en navegador de D1/D2 y cubo con la interficie local.

## 20. Pruebas no ejecutadas

La fase no pudo completar una validación astrométrica con catálogo independiente porque no se obtuvo una referencia publicada suficiente en el entorno operativo. Los elementos no ejecutados son:

- Gaia DR3 cross-match completo y residuos astrométricos finales.
- Mapas espaciales de residuos absolutos.
- Comparación independiente de objetos reales en centro, bordes y esquinas.
- E2E de navegador automatizado completo como suite Playwright formal, no detectada en el repositorio actual.

## 21. Resultados de persistencia

Se verificó que la trazabilidad de coordenadas, estados, SHA-256 y advertencias se conserva en resultados científicos.

- Los ejecuciones de perfil espectral y runs persistidos recuperan `file_id`, `sha256`, detector, `HDU`, WCS variant, `FINAST`, warnings y estado astrométrico.
- Las ejecuciones guardadas se recuperan tras reinicio del backend.
- El backend usa SQLite local como fallback; no se alteran los FITS originales ni el manifest.

## 22. Limitaciones científicas

La etapa de validación astrométrica no puede afirmar mayor precisión que la evidencia disponible. Las limitaciones principales son:

1. No hay pasada final con Gaia DR3 ni catálogo de referencia independiente.
2. `FINAST = 0` es una buena señal del pipeline, no una validación absoluta.
3. Los coeficientes SIP están activos en la WCS efectiva de los MEF; la inconsistencia CTYPE sigue siendo un aviso legítimo para especial cuidado, aunque no invalida la estructura WCS del producto.
4. El cubo no tiene `VARIANCE` ni validación independiente.
5. El WCS puede ser matemáticamente consistente y aun así estar desplazado respecto al cielo real.

## 23. Estado final por producto

| Producto | Estado |
|---|---|
| MEF D1 | `WCS_STRUCTURALLY_VALID`, `SIP_CONFIRMED_ACTIVE`, `ASTROMETRY_UNVALIDATED` |
| MEF D2 | `WCS_STRUCTURALLY_VALID`, `SIP_CONFIRMED_ACTIVE`, `ASTROMETRY_UNVALIDATED` |
| Cubo `Npix0_cube.fits` | `WCS_STRUCTURALLY_VALID`, `SIP_CONFIRMED_INACTIVE`, `ASTROMETRY_UNVALIDATED` |

## 24. Recomendaciones para la siguiente fase

1. Ejecutar una validación astrométrica con Gaia DR3 o catálogo equivalente, con propagación de movimiento propio y separación angular real.
2. Separar entrenamiento y validación para no ajustar el mismo catálogo que se usará para medir precisión.
3. Evaluar en detalle si los coeficientes SIP deben corregirse a nivel de producto o si la imagen ya está corregida antes de la distribución.
4. Completar la verificación de la cámara y de la fecha de release para cada MEF en la procedencia oficial.
5. Mantener los estados de WCS y astrometría conservadores: no declarar precisión absoluta sin evidencia objetiva.

## 25. Conclusión final

La plataforma ha demostrado robustez de infraestructura, trazabilidad y gestión segura de coordenadas, pero no ha demostrado una precisión astrométrica absoluta para los productos SPHEREx con referencia independiente. El resultado correcto es:

- `PASS_WITH_LIMITATIONS` en la validación de WCS y extracción local.
- `ASTROMETRY_UNVALIDATED` para todos los MEF y para el cubo.
- `SIP_CONFIRMED_ACTIVE` en la WCS celestial principal de los MEF.
- `SIP_CONFIRMED_INACTIVE` en el cubo espacial.

La advertencia Astropy se conserva porque refleja una diferencia real entre la convención sintáctica del encabezado y la interpretación efectiva del software, pero no se trata como una causa para forzar cambios destructivos en los datos originales.

## 26. Evidencias de archivo

- `Backend/app/services/astrometry.py`
- `Backend/app/services/fits_processor.py`
- `Backend/app/api/v1/endpoints/data.py`
- `Backend/app/data/processed/spherex/fits-manifest.json`
- `Backend/reports/FASE4_5_2_AUDITORIA_COMPATIBILIDAD_CALIDAD_MEDICION.md`
- `Backend/reports/evidence/phase452-network-summary.json`
- `Backend/reports/evidence/phase452-spectral-analysis-detector1.png`
- `Backend/reports/evidence/phase452-spectral-analysis-detector2.png`
- `Backend/reports/evidence/phase452-spectral-analysis-cube-no-variance.png`
