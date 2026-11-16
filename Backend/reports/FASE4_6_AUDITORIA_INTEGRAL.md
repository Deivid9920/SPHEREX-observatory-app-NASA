# FASE 4.6 — Auditoría integral de integración científica y funcional

**Corte de auditoría:** 2026-11-15 local (UTC-06:00), 2026-11-16 UTC.  
**Evaluación global:** `READY_WITH_LIMITATIONS`.  
**Alcance:** auditoría del estado real y corrección de un defecto del orquestador; sin cambios a algoritmos científicos, FITS, calibraciones ni manifiesto.

## Resumen ejecutivo

El proyecto tiene un camino local real y comprobable para inventariar FITS, mostrar previews, extraer muestras espectrales, ejecutar detección individual experimental y persistir/reproducir ejecuciones. La interfaz integra esos flujos desde los endpoints `/api/v1/data/...`, conserva identificadores y hashes, y rotula las mediciones/detecciones con sus limitaciones.

No es una plataforma temporal científicamente validada ni un sistema de descubrimientos confirmado. Ninguno de los diez productos del inventario es elegible para una comparación local; las consultas remotas a IRSA fallaron en la validación E2E anterior. Astrometría absoluta, fotometría, FPR/recall de detecciones, ePSF en detección y compatibilidad integral de releases/calibración siguen sin demostrar. El módulo de catálogo no recibe los resultados de detección de imagen individual y no hay candidato validado que promover.

La primera suite central informó 45 pruebas backend aprobadas e integridad FITS aprobada (10 archivos, 0 discrepancias), pero marcó typecheck/build como bloqueados. La causa reproducible fue la invocación Windows de `pnpm` por `subprocess` (WinError 2) aun cuando `pnpm.cmd` estaba disponible. Los comandos `pnpm.cmd run typecheck` y `pnpm.cmd run build` pasaron directamente. Se corrigió únicamente el nombre del ejecutable en la rama Windows del orquestador y se repitió la suite. No se instalaron dependencias ni se tocaron los resultados científicos.

## Arquitectura real

El diagrama de componentes, con rutas funcionales y bloqueadas diferenciadas, está en [`FASE4_6_ARCHITECTURE.mmd`](./FASE4_6_ARCHITECTURE.mmd). La matriz detallada de endpoints/consumidores se encuentra en [`FASE4_6_INTEGRATION_MATRIX.md`](./FASE4_6_INTEGRATION_MATRIX.md).

Flujo local demostrado:

`FITS originales → manifiesto/hash/inventario → endpoints locales FastAPI → servicios FITS/WCS/calibración → preview o extracción/detección → scientific_runs → recuperación/replay → interfaz`.

El pipeline remoto de observaciones depende de IRSA. El pipeline temporal local exige dos productos compatibles, y no hay un par elegible en el inventario actual. `DetectionCandidateModel` recibe candidatos del pipeline temporal, no las detecciones individuales almacenadas como `ScientificDetectionModel`; falta ese enlace funcional. PostgreSQL y Redis no son el modo validado en este entorno: se observó SQLite y caché en memoria como fallback.

## Evidencia técnica ejecutada y heredada

### Ejecutada para esta auditoría

La ejecución inicial se conserva en [`validation_results.json`](../../reports/history/20261116T013925.498214Z/validation_results.json), con logs en [`test_logs/`](../../reports/history/20261116T013925.498214Z/test_logs/). La repetición posterior a la corrección está en [`validation_results.json`](../../reports/history/20261116T014454.152783Z/validation_results.json), con logs en [`test_logs/`](../../reports/history/20261116T014454.152783Z/test_logs/):

| Grupo | Resultado |
|---|---|
| Suite backend completa | PASS: 45 aprobadas, 0 fallidas, 20 warnings |
| Integridad FITS | PASS: 10 entradas verificadas, 0 hashes discrepantes |
| Frontend typecheck por orquestador | PASS después del ajuste: exit 0 |
| Frontend build por orquestador | PASS después del ajuste: exit 0; warning Node DEP0205 |
| E2E automatizado | NOT_TESTED: no existe script E2E en `Frontend/package.json` |
| Resultado del orquestador | PARTIAL: 0 grupos bloqueados y 1 grupo E2E no ejecutado |

El orquestador conserva el resultado inicial `BLOCKED` en su historial. Tras el cambio, devuelve `PARTIAL` y exit 1 porque el E2E no está configurado; no se reinterpretó esa omisión como aprobación. La suite final reporta 45/45 tests backend, typecheck/build aprobados e integridad 10/10.

### Evidencia E2E previa, con fecha local coincidente

[`FASE4_4_VALIDACION_CIENTIFICA.md`](./FASE4_4_VALIDACION_CIENTIFICA.md) registra el recorrido real del navegador contra el backend y los FITS: inventario de diez archivos, previews PNG de MEF, extracción del cubo con 91/102 canales válidos, replay de ejecución y detección experimental, y pantallas explícitas de bloqueo temporal/catálogo. También registra IRSA 502, backend SQLite y caché en memoria. Es evidencia de E2E manual, no una prueba automatizada repetible por este repositorio.

La marca de tiempo de la Fase 4.5.4 está en UTC y se reconcilia con la fecha local mediante UTC-06:00; no se considera futura. Su evidencia WCS/integridad sigue referenciada en [`FASE4_5_4_VALIDACION_ASTROMETRICA_COMPLEMENTARIA.md`](./FASE4_5_4_VALIDACION_ASTROMETRICA_COMPLEMENTARIA.md).

## Estado por subsistema

| Subsistema | Estado | Conclusión |
|---|---|---|
| SPHEREx Data Core | `PASS_WITH_LIMITATIONS` | FITS e inventario íntegros, HDUs reconocidos, WCS y provenance local; releases y calibración total no verificadas. |
| Temporal Sky Engine | `BLOCKED` | Algoritmo y guardas existen; ningún par local elegible y consulta IRSA fallida. No se generó diferencia científica en esta fase. |
| Spectral Intelligence | `PASS_WITH_LIMITATIONS` | Cubo real y MEF con calibración Spectral WCS asociada donde la grilla concuerda; extracción MEF es una muestra de un píxel, no espectro integrado/fotometría. |
| AstroVision AI | `PASS_WITH_LIMITATIONS` | Detector de imagen real ejecutado y enmascarado; salidas experimentales sin FPR/recall/centroides calibrados ni ePSF. |
| Discovery Intelligence | `BLOCKED` | Endpoints/modelo existen, pero no reciben las detecciones locales; sin candidatos validados/procedencia completa no hay catálogo científico. |
| Cosmic Observatory | `PASS_WITH_LIMITATIONS` | Consume endpoints y muestra productos FITS/reales; parte de la experiencia histórica es demo separada y etiquetada. E2E automatizado no configurado. |

Cada capacidad, su evidencia, límites y criterios de estado se detalla en [`FASE4_6_MODULE_STATUS.json`](./FASE4_6_MODULE_STATUS.json) y [`FASE4_6_INTEGRATION_MATRIX.md`](./FASE4_6_INTEGRATION_MATRIX.md).

## Hallazgos

### Defecto corregido en esta fase

- **Severidad:** menor, infraestructura de validación.
- **Hecho:** el orquestador resolvía `pnpm` mediante `shutil.which`, pero trataba de ejecutar el nombre `pnpm` en Windows; `subprocess` no pudo iniciar el shim y devolvió WinError 2.
- **Evidencia antes del cambio:** los logs `frontend-typecheck.stderr.log` y `frontend-build.stderr.log` de la ejecución inicial guardan WinError 2; las mismas tareas ejecutadas explícitamente como `pnpm.cmd` pasaron.
- **Cambio acotado:** usar `pnpm.cmd` solo en Windows, conservar `pnpm` en otros sistemas y conservar los controles de disponibilidad existentes.
- **Justificación documentada antes del cambio:** el orquestador impedía que la auditoría informara el estado real del frontend, aunque las dependencias estaban presentes y los comandos pasaban.
- **Verificación posterior:** ejecución `20261116T014454.152783Z`; ambos comandos pasaron desde el orquestador. E2E quedó correctamente como `not_run`.

### Defectos y limitaciones no corregidos

1. No existe automatización E2E de navegador en los manifests; la evidencia de navegador disponible es manual.
2. `README.md` documenta en partes rutas de datos/endpoints y una arquitectura temporal/discovery que no concuerdan con la implementación local-first observada. No se modifica por instrucción de esta fase.
3. La ingesta local de detecciones y el catálogo de candidatos son flujos separados; el esquema de descubrimiento no hereda SHA-256/procedencia de una ejecución local de detección.
4. El endpoint de listado de candidatos ordena por `peak_z_score`; las puntuaciones C son experimentales y no probabilidades. La UI del modo Observatorio evita presentarlas como descubrimientos confirmados.
5. PostgreSQL/Redis no fueron validados como infraestructura operativa; los fallbacks locales no son equivalentes.
6. La compatibilidad de release/calibración y la precisión astrométrica absoluta siguen sin validar. No se recalibró ni se alteró ningún dato.

## Riesgos críticos y aceptables

**Bloqueos para afirmar capacidad científica completa:** Temporal Vision real, descubrimientos validados, astrometría absoluta, fotometría/PSF y métricas de precisión/recall de detección.

**Limitaciones aceptables para una entrega experimental local:** catálogo IRSA no disponible durante E2E, operación SQLite/memoria local, incertidumbres ausentes en el cubo y modo demo aislado y rotulado.

**Recomendación de cierre:** preparar documentación y release como herramienta experimental local-first con límites explícitos; no afirmar detección validada de transitorios, catálogo científico ni validación astrométrica absoluta. No iniciar Temporal Vision ni cambiar estados bloqueados.

## Resultado

**`READY_WITH_LIMITATIONS`** para pasar a las fases de documentación/release, conservando los bloqueos científicos visibles y la ausencia de E2E automatizado. No equivale a aprobación científica de todos los subsistemas.
