# FASE 4.5.4 — Validación astrométrica complementaria

**Estado:** `PASS_WITH_LIMITATIONS` para auditoría, integridad y pruebas internas.  
**Estado científico:** `ASTROMETRY_UNVALIDATED` para los nueve MEF y el cubo.  
**Ejecución:** `2026-11-16T01:24:19Z`–`2026-11-16T01:24:52Z` (UTC).

## 1. Resumen ejecutivo

Se volvió a inspeccionar, en solo lectura, el conjunto local: nueve MEF y `Npix0_cube.fits`. Los diez SHA-256 coinciden con el manifiesto y las diez pruebas de WCS existentes pasaron. También se consultaron 2MASS PSC y CatWISE2020 a través de IRSA para un piloto acotado.

La consulta externa no proporciona una validación astrométrica: ambos resultados alcanzaron el límite de 2.000 filas; el piloto CatWISE cubrió solo un cono central de 0,1° de un MEF y produjo 21 pares candidatos, todos excluidos de cualquier métrica. No se calcularon residuos aceptados, RMS, MAD ni percentiles astrométricos. **El pase del orquestador demuestra que los controles ejecutados terminaron correctamente, no que la precisión absoluta de la WCS esté demostrada.**

No se modificaron los FITS originales, sus headers ni el manifiesto; tampoco se ajustó ninguna WCS.

## 2. Alcance, entradas y evidencia

Los productos fueron leídos desde `Backend/app/data/raw/spherex/` y contrastados con `Backend/app/data/processed/spherex/fits-manifest.json`.

| Evidencia | Resultado |
|---|---|
| Productos inspeccionados | 10: 9 MEF y 1 cubo |
| Diferencias SHA-256 respecto al manifiesto | 0 |
| SHA-256 del manifiesto | `899881dfbca6ba5f035f30e346af93f4af457c8ec22d3db667ce6c860e64874c` |
| Pruebas WCS | 10 aprobadas; 0 fallidas, omitidas o inestables |
| Sondeo de catálogos | Ejecutado; filas truncadas por límite en ambos catálogos |
| Asociaciones aceptadas para métricas | 0 |
| Informe central | [`validation_report.md`](../../reports/latest/validation_report.md) |
| Resultados JSON del orquestador | [`validation_results.json`](../../reports/latest/validation_results.json) |
| Evidencia JSON de esta fase | [`phase454-astrometry-audit-20261116T012419.458875Z.json`](./evidence/phase454-astrometry-audit-20261116T012419.458875Z.json) |
| Logs de la consulta/auditoría | [`astrometry-audit.stderr.log`](../../reports/latest/test_logs/20261116T012419.458875Z/astrometry-audit.stderr.log) |
| Auditoría previa de encabezados y diagnóstico SIP | [`FASE4_5_3_VALIDACION_ASTROMETRICA_WCS.md`](./FASE4_5_3_VALIDACION_ASTROMETRICA_WCS.md) |

El inventario no contiene palabras clave de release reconocidas en los headers inspeccionados. La versión `v27` y la fecha `2026-xxx` que aparecen en los nombres se registran como metadatos del nombre del producto, **no** como prueba suficiente de que el producto pertenezca a DR1 o QR3.

## 3. WCS local: estado y trazabilidad por producto

En los nueve MEF, la extensión seleccionada es `IMAGE` (HDU 1), de 2040 × 2040 píxeles, `WCSAXES=2`, `CTYPE=(RA---TAN-SIP, DEC--TAN-SIP)`, `CUNIT=(deg, deg)`, `CRPIX=(1020.5, 1020.5)`, `CDELT=(1, 1)`, matriz `PC` propia por producto, sin matriz `CD`, y `RADESYS=ICRS`. `EQUINOX` no está definido; `LONPOLE=180°` y `LATPOLE=CRVAL2`. Las matrices `PC` y `CRVAL` no se asumen iguales entre archivos; están preservadas por producto en la evidencia JSON.

| Producto MEF | Detector | OBSID | DATE-OBS (UTC) | DATE del header | FINAST | SHA-256 |
|---|---:|---|---|---|---:|---|
| `level2_2025W28_1B_0001_1D1_spx_l2b-v27-2026-215.fits` | 1 | `2025W28_1B_0001_1` | 2025-07-07T00:07:23.351 | 2026-08-04T03:16:52.560 | 0 | `ed8debec7bf19f4d9c92375f139176b5c9c7ced628a59a598179d7869441c296` |
| `level2_2025W28_1B_0002_1D1_spx_l2b-v27-2026-215.fits` | 1 | `2025W28_1B_0002_1` | 2025-07-07T00:10:13.724 | 2026-08-04T02:00:42.631 | 0 | `9bbf5ff345c36c0f95689a856f788562e48bc56fe792a558c1cbc4a16b195bde` |
| `level2_2025W28_1B_0003_1D1_spx_l2b-v27-2026-215.fits` | 1 | `2025W28_1B_0003_1` | 2025-07-07T00:13:13.307 | 2026-08-04T00:53:06.211 | 0 | `1e7318b504635f0de620de975e5109a5b83aca560fd07096a4ec881d32a733a2` |
| `level2_2025W25_1B_0429_1D1_spx_l2b-v27-2026-213.fits` | 1 | `2025W25_1B_0429_1` | 2025-06-18T02:23:01.543 | 2026-08-01T10:39:02.824 | 0 | `921b24805a3213467ef6a8502bb4af4231be78f4bd1b99802b52609c7d83d28c` |
| `level2_2025W17_4B_0001_1D1_spx_l2b-v27-2026-196.fits` | 1 | `2025W17_4B_0001_1` | 2025-04-24T18:01:05.843 | 2026-07-15T18:20:15.775 | 0 | `b2b78466058203dbabcf841b6223697e7e69b08b18a00882c764c6f8fd0acd59` |
| `level2_2025W17_4B_0001_1D2_spx_l2b-v27-2026-196.fits` | 2 | `2025W17_4B_0001_1` | 2025-04-24T18:01:05.843 | 2026-07-15T21:21:27.825 | 0 | `3d51d09b5a8653b21ec0bbdaffa923545af8bdb5af4b4a2b42fe260b4f5a3b9a` |
| `level2_2025W18_1B_0001_1D1_spx_l2b-v27-2026-196.fits` | 1 | `2025W18_1B_0001_1` | 2025-04-28T13:00:15.755 | 2026-07-16T00:44:42.294 | 0 | `64113e82f4357303d9a595e384a51cd1e021e74c3ce81443d31ee74d42f8619a` |
| `level2_2025W30_1B_0001_1D1_spx_l2b-v27-2026-220.fits` | 1 | `2025W30_1B_0001_1` | 2025-07-21T00:02:39.204 | 2026-08-08T19:40:54.506 | 0 | `6b0061a1bea9539b4fe4ae288911c770d08b058ac900a068ddb28490192cc3a6` |
| `level2_2025W42_1A_0001_1D1_spx_l2b-v27-2026-243.fits` | 1 | `2025W42_1A_0001_1` | 2025-10-13T00:09:07.399 | 2026-08-31T19:36:38.287 | 0 | `bfcd10b34d3222855ea9cd92b6e103e56b90949d92c399f8a5d36a608c0d970e` |

Los 40 coeficientes SIP de cada MEF (10 cada uno en A, B, AP y BP) son finitos, completos y de orden 3; la clasificación estructural es `WCS_STRUCTURALLY_VALID` para cada WCS celeste primario. `FINAST=0` en los nueve productos indica una solución buena según el pipeline, pero no es validación absoluta independiente.

El cubo `Npix0_cube.fits` tiene forma de datos 102 × 512 × 512 (NAXIS1=512, NAXIS2=512, NAXIS3=102), HDU `IMAGE` (1) y WCS de tres ejes con espacio `RA---HPX` / `DEC--HPX` y eje espectral `WAVE-TAB`. Su WCS espacial no tiene SIP; no existe `FINAST`. Su solución tampoco queda validada externamente.

| Producto | Consistencia interna observada | Clasificación | Estado astrométrico |
|---|---|---|---|
| Nueve MEF, cada uno | Round-trip cielo↔píxel máximo entre `4.4e-08` y `1.75e-06` píxeles en la grilla de prueba | `WCS_STRUCTURALLY_VALID` | `ASTROMETRY_UNVALIDATED` |
| `Npix0_cube.fits` | Round-trip 0 píxeles en los tres puntos muestreados | WCS espacial estructuralmente interpretable; sin SIP | `ASTROMETRY_UNVALIDATED` |

Estos round-trips verifican reversibilidad numérica en puntos internos, no acuerdo con el cielo real. No se usó la WCS espectral `WAVE-TAB` para la validación celestial.

## 4. Diagnóstico de SIP/CTYPE y warnings

Los `CTYPE` del WCS celestial primario de los MEF sí contienen el sufijo `-SIP`; la auditoría confirma que Astropy aplica los coeficientes SIP a esa transformación espacial. El warning previamente observado pertenece al WCS alternativo `W`: se construye con ejes `WAVE-TAB`, pero Astropy detecta coeficientes SIP espaciales presentes en el header, cuyos `CTYPE` alternativos no declaran `-SIP`. Esta condición se conserva como advertencia y no se interpreta como una prueba para aplicar SIP al eje espectral ni para eliminar SIP del WCS celestial.

La diferencia diagnóstica entre WCS con SIP y una copia temporal sin SIP (no escrita al FITS) fue de aproximadamente 15–19″ en mediana, 55.57–63.91″ en p95 y 69.25–85.24″ en máximo, según producto. **No son residuos astrométricos ni permiten elegir cuál transformación coincide mejor con el cielo.**

El log de la consulta registra además un `ErfaWarning`: `pmsafe` indica que se sobrescribió la distancia para 78 fuentes porque el catálogo no proporciona distancia. No se suprimió. La propagación aplicó movimiento propio angular, sin distancia ni velocidad radial; por tanto, ese aviso forma parte de las limitaciones del piloto.

## 5. Consulta externa y método del piloto

**Consulta:** IRSA TAP, ejecutada el `2026-11-16T01:24:23Z`, centrada en el MEF `level2_2025W28_1B_0001_1D1_spx_l2b-v27-2026-215.fits` (centro ICRS `[148.167829013°, -60.282634698°]`, `MJD-OBS=60863.005131377`).

| Catálogo | Tabla | Radio consultado | Filas recibidas | Límite | Límite alcanzado | Movimiento propio |
|---|---|---:|---:|---:|---|---|
| 2MASS PSC | `fp_psc` | 0.25° | 2.000 | 2.000 | Sí | No había campos PM/época utilizables en la respuesta |
| CatWISE2020 | `catwise_2020` | 0.1° | 2.000 | 2.000 | Sí | `pmra`, `pmdec` disponibles |

El límite de filas implica que estas respuestas no son un inventario completo del área. 2MASS no se utilizó para residuos. Para CatWISE2020, se seleccionaron fuentes con `cc_flags=0000`, `sigra<1″`, `sigdec<1″`, `sigpmra<0.1″/año`, `sigpmdec<0.1″/año`, `rchi2_pm<5`, `w1snr>10` y `w2snr>5`.

Las coordenadas CatWISE2020 se propagaron desde la época de posición MJD 57170 a `MJD-OBS=60863.005131377`. La época se tomó de Marocco et al. (2021), no del campo `meanobsmjd`. Se interpretó `pmra` como componente \(\mu_\alpha^*=\mu_\alpha\cos\delta\). No se aplicaron correcciones de offsets por mosaico descritas en el artículo, ya que están derivadas de Gaia DR2 y su aplicación introduciría una corrección basada en Gaia en este piloto.

### Resultado y exclusiones

- 78 referencias CatWISE pasaron los filtros de calidad y fueron proyectadas dentro de la imagen.
- El detector exploratorio de la imagen produjo 28.727 picos a partir de un umbral global y máscaras existentes.
- Se hallaron 21 pares mutuos candidatos dentro de 8 píxeles.
- Pares aceptados como asociaciones astrométricas: **0**.
- Pares excluidos de toda métrica: **21**.

La asociación se excluyó porque el sondeo cubrió solo el cono central, sin bordes ni esquinas; además, el detector empleado no tiene una tasa de falsos positivos demostrada, incertidumbre de centroide validada ni calibración por inyección/recuperación. Por tanto, los 21 pares son candidatos de un piloto, no identificaciones confiables.

## 6. Independencia y métricas

El material de referencia no se trató como validación independiente solo por provenir de un catálogo distinto. El pipeline SPHEREx usa Gaia DR3 para su solución astrométrica; CatWISE2020 es un catálogo distinto, pero el artículo documenta correcciones por mosaico derivadas de Gaia DR2. Esas correcciones no se aplicaron. En cualquier caso, al no haber asociaciones aceptadas y estar la consulta truncada, no existe aquí una muestra de holdout adecuada para evaluar precisión absoluta.

| Dimensión de validación | Resultado |
|---|---|
| Consistencia estructural del WCS | Aprobada para los WCS celestes inspeccionados |
| Round-trip numérico interno | Aprobado en los puntos de prueba; no mide exactitud |
| Consulta de catálogo externo | Completa a nivel de conexión/consulta, pero truncada por límite |
| Concordancia de candidatos | 21 pares exploratorios; ninguno aceptado |
| Validación independiente holdout | No demostrada |
| Precisión absoluta | No demostrada |
| Residuos RA/Dec, plano tangencial, RMS, MAD, p95, máximo astrométrico | No calculados: no hay asociaciones válidas |
| Cobertura espacial de residuos | No evaluable; solo se sondeó un cono central |

En consecuencia, se conserva `ASTROMETRY_UNVALIDATED` para todos los productos. No se alteró la WCS para mejorar el resultado y no se publican métricas de precisión obtenidas de asociaciones no validadas.

## 7. Limitaciones y trabajo necesario

1. Repetir consultas con particionado o paginación que evite truncamiento y cubra el campo completo.
2. Construir un detector/centroide con control de calidad cuantificado mediante inyección y recuperación, y estimaciones de incertidumbre.
3. Definir antes del análisis criterios de asociación única, radios motivados por incertidumbres y exclusión de fuentes ambiguas.
4. Obtener un holdout espacial de referencias no usado por el ajuste astrométrico original, con procedencia y época verificadas; propagar movimientos propios cuando proceda.
5. Si se usa Gaia como marco de referencia, declarar su relación con el ajuste SPHEREx y no presentar la comparación como completamente independiente.
6. Solo con muestra suficiente y cobertura del campo calcular residuos en RA/Dec y plano tangencial, estadísticas robustas y métricas por detector/producto.
7. Mantener el warning SIP/CTYPE de la WCS alternativa visible y diagnosticado; no modificar encabezados originales para ocultarlo.

## 8. Fuentes

Consultadas para interpretar los productos, el comportamiento de Astropy y la época de CatWISE2020:

- [IRSA SPHEREx Data Products](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-products/) — estructura y semántica de los productos SPHEREx.
- [IRSA SPHEREx DR1 overview](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/overview_dr1.html) — contexto de release. La release de estos archivos locales no se infiere solo por el nombre.
- [Astropy WCS: SIP conventions](https://docs.astropy.org/en/stable/wcs/note_sip.html) — convención SIP y advertencia cuando `CTYPE` no declara `-SIP`.
- [Marocco et al. 2021, CatWISE2020](https://arxiv.org/abs/2012.13084) — época de las posiciones y propiedades astrométricas del catálogo.

## 9. Estado final de la fase

**Fase 4.5.4: `PASS_WITH_LIMITATIONS`.** Se ejecutaron las pruebas WCS, se auditó el conjunto local, se verificó la integridad y se realizó un sondeo externo con época CatWISE corregida. Los datos no respaldan una conclusión de precisión astrométrica absoluta ni independiente. Estado que debe exponerse a consumidores y usuarios: **`ASTROMETRY_UNVALIDATED`**.
