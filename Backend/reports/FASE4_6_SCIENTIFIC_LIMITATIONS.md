# FASE 4.6 — Limitaciones científicas y de integración

Este documento separa lo observado, calculado y simulado de lo que permanece sin validar. Los estados de módulos y las pruebas fuente están en [`FASE4_6_MODULE_STATUS.json`](./FASE4_6_MODULE_STATUS.json) y [`FASE4_6_INTEGRATION_MATRIX.md`](./FASE4_6_INTEGRATION_MATRIX.md).

## Limitaciones que bloquean afirmaciones científicas

### Astrometría

- Los WCS se transforman de forma internamente consistente, pero los nueve MEF y el cubo mantienen `ASTROMETRY_UNVALIDATED`.
- `FINAST=0` es una bandera favorable del pipeline, no validación independiente.
- El sondeo CatWISE/2MASS previo tuvo límite de 2.000 filas; los 21 pares candidatos se excluyeron, y no hay residuales aceptados ni RMS/MAD astrométricos.

### Temporalidad

- No existe una pareja FITS local elegible en el inventario actual; el cubo no tiene `VARIANCE` ni `DATE-OBS`.
- La ruta remota IRSA falló por 502/timeout en la prueba anterior.
- El pipeline local requiere `IMAGE`, `VARIANCE`, `FLAGS`, WCS coincidente, fechas distintas, mismo BUNIT, banda, nivel/versión de calibración y PSF compatible. No se remuestrean grillas ni se iguala PSF.
- El Z implementado supone errores independientes; no modela covarianza. Aun con datos compatibles, una diferencia no sería una detección astrofísica validada sin evaluación de artefactos y falsos positivos.
- Temporal Vision debe seguir `PENDING — NOT SCIENTIFICALLY VALIDATED`; esta fase no lo inició ni ejecutó.

### Espectros y calibración

- El cubo produce muestras de sus 102 canales tabulados; no tiene varianza, por lo que incertidumbres y significancia no están disponibles.
- Los MEF se extraen como muestra de un píxel. CWAVE/CBAND D1/D2 pueden asociarse por detector y coincidencia de grilla; esto no comprueba release ni calibración fotométrica absoluta.
- WCS-W embebido se conserva como ruta preliminar/de visualización cuando no hay calibración asociada. No se inventan longitudes de onda.
- No se reaplican correcciones de ganancia ni otras calibraciones upstream a Level 2.

### Detección y descubrimientos

- DAOStarFinder usa `FWHM=2.5 px` y umbral relativo a dispersión global sigma-clipped. La varianza solo participa en la máscara de píxeles válidos; no constituye un modelo de ruido calibrado.
- ePSF está embebido en los MEF, pero el detector no lo consume ni hace ajuste PSF/fotometría.
- No existen métricas de precision/recall, tasa de falsos positivos, centroides con incertidumbre validada ni injection/recovery.
- Las salidas son fuentes experimentales. El `confidence_score_c` de candidatos temporales es una puntuación interna, no una probabilidad calibrada.
- El modelo/endpoint del catálogo recibe candidatos del pipeline temporal; no ingiere los objetos de `scientific_detections`. No se deben promocionar esos resultados como descubrimientos.

## Limitaciones operativas y de reproducibilidad

- PostgreSQL y Redis no se demostraron disponibles; se usaron SQLite y caché en memoria. Redis en memoria es volátil.
- El E2E de navegador registrado en Fase 4.4 fue manual. No hay comando automatizado de Playwright en los manifests.
- El modo demo contiene imágenes, fuentes, tracks, valores y puntuaciones ilustrativos; permanece separado del modo Observatorio y rotulado. No son datos SPHEREx.
- La suite central pasa pruebas backend e integridad; el typecheck/build se verificaron por comandos manuales Windows y, tras la corrección del orquestador, se vuelven a registrar desde el mismo runner.
- La release no se infiere de los nombres `v27` o fechas del archivo. Los productos locales carecen de evidencia suficiente de release/calibración homogénea.
- El README contiene instrucciones y mapas de endpoints que no están sincronizados con la ruta local-first; queda pendiente de la fase documental, pero no se modifica en esta fase.

## Interpretación de resultados temporales (no habilitación)

El código usa \(D=I(t_2)-I(t_1)\) y \(Z=D/\sqrt{V_1+V_2}\). La segunda expresión supone varianzas compatibles e independientes; con errores correlacionados se necesitaría incluir covarianza. Estas ecuaciones no habilitan análisis con productos no alineados, PSF distinta, calibración incompatible o máscaras/incertidumbres incompletas.

## Políticas conservadas

- Originales, headers y manifiesto FITS no se escribieron.
- No se cambiaron umbrales, modelos de detector, WCS, calibraciones ni estados científicos.
- Los bloqueos se conservaron; la corrección de esta fase se limita a la invocación Windows de pruebas del frontend.
