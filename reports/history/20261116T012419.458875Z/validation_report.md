# Central validation report

- Run ID: `20261116T012419.458875Z`
- Started: `2026-11-16T01:24:19.460894+00:00`
- Finished: `2026-11-16T01:24:52.005064+00:00`
- Category: `astrometry`
- Overall: **PASSED**
- Duration: 32.55 s

## Totals

- Tests: 10
- Passed: 10
- Failed: 0
- Skipped by pytest: 0
- Errors: 0
- Unstable (unexpected passes): 0
- Blocked groups: 0
- Not-run groups: 0

## Validation groups

| Group | Status | Duration (s) | Exit code | Failure kind |
|---|---|---:|---:|---|
| pytest-wcs | passed | 1.781 | 0 | — |
| astrometry-audit | passed | 30.031 | 0 | — |
| fits-integrity | passed | 0.719 | — | — |

## Warnings

- `astrometry-audit`: C:\Users\walke\.copilot\session-state\6678e58f-0f41-4a6a-8d18-0e0257bfe143\files\venv\Lib\site-packages\erfa\core.py:133: ErfaWarning: ERFA function "pmsafe" yielded 78 of "distance overridden (Note 6)"
- `astrometry-audit`: warn(f'ERFA function "{func_name}" yielded {wmsg}', ErfaWarning)

## Evidence and logs

- JSON: `reports\latest\validation_results.json`
- Test logs: `reports\latest\test_logs\20261116T012419.458875Z`
- Evidence directory: `reports\latest\evidence\20261116T012419.458875Z`
- History copy: `reports\history\20261116T012419.458875Z`
