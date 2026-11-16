# Central validation report

- Run ID: `20261116T013925.498214Z`
- Started: `2026-11-16T01:39:25.499222+00:00`
- Finished: `2026-11-16T01:39:39.003233+00:00`
- Category: `all`
- Overall: **BLOCKED**
- Duration: 13.50 s

## Totals

- Tests: 45
- Passed: 45
- Failed: 0
- Skipped by pytest: 0
- Errors: 0
- Unstable (unexpected passes): 0
- Blocked groups: 2
- Not-run groups: 1

## Validation groups

| Group | Status | Duration (s) | Exit code | Failure kind |
|---|---|---:|---:|---|
| pytest-backend | passed | 12.718 | 0 | — |
| frontend-typecheck | blocked | 0.0 | None | infrastructure |
| frontend-build | blocked | 0.0 | None | infrastructure |
| fits-integrity | passed | 0.766 | — | — |
| browser-e2e | not_run | — | — | — |

## Warnings

- `pytest-backend`: ============================== warnings summary ===============================
- `pytest-backend`: C:\Users\walke\.copilot\session-state\6678e58f-0f41-4a6a-8d18-0e0257bfe143\files\venv\Lib\site-packages\starlette\testclient.py:41: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
- `pytest-backend`: C:\Users\walke\.copilot\session-state\6678e58f-0f41-4a6a-8d18-0e0257bfe143\files\venv\Lib\site-packages\matplotlib\_fontconfig_pattern.py:88: PyparsingDeprecationWarning: 'parseString' deprecated - use 'parse_string'
- `pytest-backend`: C:\Users\walke\.copilot\session-state\6678e58f-0f41-4a6a-8d18-0e0257bfe143\files\venv\Lib\site-packages\matplotlib\_fontconfig_pattern.py:92: PyparsingDeprecationWarning: 'resetCache' deprecated - use 'reset_cache'
- `pytest-backend`: C:\Users\walke\.copilot\session-state\6678e58f-0f41-4a6a-8d18-0e0257bfe143\files\venv\Lib\site-packages\matplotlib\_mathtext.py:45: PyparsingDeprecationWarning: 'enablePackrat' deprecated - use 'enable_packrat'
- `pytest-backend`: C:\Users\walke\.copilot\session-state\6678e58f-0f41-4a6a-8d18-0e0257bfe143\files\venv\Lib\site-packages\httpx\_client.py:690: DeprecationWarning: The 'app' shortcut is now deprecated. Use the explicit style 'transport=WSGITransport(app=...)' instead.
- `pytest-backend`: warnings.warn(message, DeprecationWarning)
- `pytest-backend`: -- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
- `pytest-backend`: 45 passed, 20 warnings in 11.56s

## Evidence and logs

- JSON: `reports\latest\validation_results.json`
- Test logs: `reports\latest\test_logs\20261116T013925.498214Z`
- Evidence directory: `reports\latest\evidence\20261116T013925.498214Z`
- History copy: `reports\history\20261116T013925.498214Z`
