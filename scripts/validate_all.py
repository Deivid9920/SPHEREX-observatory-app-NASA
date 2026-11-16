#!/usr/bin/env python3
"""Run repository validation groups and preserve structured, reproducible logs."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"
FRONTEND = ROOT / "Frontend"
DEFAULT_REPORT_ROOT = ROOT / "reports"
MANIFEST = BACKEND / "app" / "data" / "processed" / "spherex" / "fits-manifest.json"
RAW_ROOT = BACKEND / "app" / "data" / "raw" / "spherex"

PYTEST_GROUPS: dict[str, list[str]] = {
    "backend": ["-q"],
    "wcs": ["-q", "tests/test_astrometry.py", "tests/test_real_spherex_wcs.py"],
    "api": ["-q", "tests/test_fits_data_api.py"],
    "persistence": ["-q", "tests/test_scientific_results.py"],
    "scientific": ["-q", "tests/test_calibration_manager.py", "tests/test_fits_inventory.py"],
}

CATEGORY_GROUPS: dict[str, list[str]] = {
    "all": ["backend", "frontend", "fits-integrity", "e2e"],
    "astrometry": ["wcs", "astrometry-audit", "fits-integrity"],
    "backend": ["backend"],
    "wcs": ["wcs"],
    "api": ["api"],
    "persistence": ["persistence"],
    "scientific": ["scientific"],
    "frontend": ["frontend"],
    "fits-integrity": ["fits-integrity"],
    "e2e": ["e2e"],
}

PYTEST_SUMMARY = re.compile(
    r"(?:(?P<passed>\d+) passed)?"
    r"(?:,\s*)?(?:(?P<failed>\d+) failed)?"
    r"(?:,\s*)?(?:(?P<skipped>\d+) skipped)?"
    r"(?:,\s*)?(?:(?P<errors>\d+) errors?)?"
    r"(?:,\s*)?(?:(?P<xfailed>\d+) xfailed)?"
    r"(?:,\s*)?(?:(?P<xpassed>\d+) xpassed)?",
    re.IGNORECASE,
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _run_id() -> str:
    return _utc_now().strftime("%Y%m%dT%H%M%S.%fZ")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fits_integrity() -> dict[str, Any]:
    if not MANIFEST.is_file():
        return {
            "status": "blocked",
            "failure_kind": "infrastructure",
            "reason": f"FITS manifest is missing: {MANIFEST}",
            "checked_files": 0,
            "mismatches": [],
        }

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entries = manifest.get("files")
    if not isinstance(entries, list):
        return {
            "status": "failed",
            "failure_kind": "software",
            "reason": "Manifest does not contain a files list.",
            "checked_files": 0,
            "mismatches": [],
        }

    mismatches: list[dict[str, str]] = []
    checked = 0
    for entry in entries:
        relative_path = entry.get("relative_path")
        expected = entry.get("sha256")
        if not relative_path or not expected:
            mismatches.append({
                "path": str(relative_path or "<missing>"),
                "reason": "Manifest entry lacks relative_path or sha256.",
            })
            continue
        path = RAW_ROOT / Path(relative_path)
        if not path.is_file():
            mismatches.append({"path": relative_path, "reason": "Original file is missing."})
            continue
        actual = _hash_file(path)
        checked += 1
        if actual.lower() != str(expected).lower():
            mismatches.append({
                "path": relative_path,
                "expected_sha256": str(expected),
                "actual_sha256": actual,
            })

    return {
        "status": "passed" if not mismatches else "failed",
        "failure_kind": None if not mismatches else "data_integrity",
        "manifest": str(MANIFEST.relative_to(ROOT)),
        "manifest_sha256": _hash_file(MANIFEST),
        "manifest_entries": len(entries),
        "checked_files": checked,
        "mismatches": mismatches,
    }


def _pytest_counts(output: str) -> dict[str, int]:
    for line in reversed(output.splitlines()):
        if " in " not in line or "pytest" in line.lower():
            continue
        match = PYTEST_SUMMARY.search(line.strip())
        if match and any(value is not None for value in match.groupdict().values()):
            return {key: int(value or 0) for key, value in match.groupdict().items()}
    return {
        "passed": 0, "failed": 0, "skipped": 0, "errors": 0,
        "xfailed": 0, "xpassed": 0,
    }


def _failure_kind(stdout: str, stderr: str) -> str:
    text = f"{stdout}\n{stderr}".lower()
    if any(token in text for token in (
        "modulenotfounderror", "no module named", "command not found",
        "is not recognized as the name of a cmdlet",
    )):
        return "missing_dependency"
    if any(token in text for token in (
        "connection refused", "connectionerror", "timed out",
        "could not connect", "service unavailable",
    )):
        return "infrastructure"
    return "software"


def _execute(
    *,
    name: str,
    command: list[str],
    cwd: Path,
    log_dir: Path,
    env: dict[str, str],
) -> dict[str, Any]:
    started_at = _utc_now()
    start = time.monotonic()
    stdout_path = log_dir / f"{name}.stdout.log"
    stderr_path = log_dir / f"{name}.stderr.log"
    try:
        process = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        stdout, stderr = process.stdout, process.stderr
        exit_code = process.returncode
        status = "passed" if exit_code == 0 else "failed"
        failure_kind = None if exit_code == 0 else _failure_kind(stdout, stderr)
    except OSError as exc:
        stdout, stderr, exit_code = "", str(exc), None
        status, failure_kind = "blocked", "infrastructure"

    duration = time.monotonic() - start
    stdout_path.write_text(stdout, encoding="utf-8", errors="replace")
    stderr_path.write_text(stderr, encoding="utf-8", errors="replace")
    combined = stdout + ("\n" if stdout and stderr else "") + stderr
    counts = _pytest_counts(combined) if "pytest" in name else {
        "passed": 0, "failed": 0, "skipped": 0, "errors": 0,
        "xfailed": 0, "xpassed": 0,
    }
    return {
        "name": name,
        "command": command,
        "cwd": str(cwd),
        "started_at": started_at.isoformat(),
        "duration_seconds": round(duration, 3),
        "exit_code": exit_code,
        "status": status,
        "failure_kind": failure_kind,
        "pytest_counts": counts,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "warnings": [
            line.strip()
            for line in combined.splitlines()
            if "warning" in line.lower()
        ][:100],
    }


def _skip(name: str, reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "not_run",
        "failure_kind": None,
        "reason": reason,
        "pytest_counts": {
            "passed": 0, "failed": 0, "skipped": 0, "errors": 0,
            "xfailed": 0, "xpassed": 0,
        },
    }


def _pytest_step(
    group: str, log_dir: Path, env: dict[str, str]
) -> dict[str, Any]:
    if importlib.util.find_spec("pytest") is None:
        return _skip(
            f"pytest-{group}",
            "The active Python environment does not have pytest installed.",
        ) | {"status": "blocked", "failure_kind": "missing_dependency"}
    return _execute(
        name=f"pytest-{group}",
        command=[sys.executable, "-m", "pytest", *PYTEST_GROUPS[group]],
        cwd=BACKEND,
        log_dir=log_dir,
        env=env,
    )


def _run_group(
    group: str,
    log_dir: Path,
    env: dict[str, str],
    *,
    catalog_probe: bool = False,
    run_id: str,
) -> list[dict[str, Any]]:
    if group in PYTEST_GROUPS:
        return [_pytest_step(group, log_dir, env)]
    if group == "astrometry-audit":
        command = [
            sys.executable,
            str(BACKEND / "scripts" / "validate_astrometry_complementary.py"),
            "--output",
            str(
                BACKEND
                / "reports"
                / "evidence"
                / f"phase454-astrometry-audit-{run_id}.json"
            ),
        ]
        if catalog_probe:
            command.append("--catalog-probe")
        result = _execute(
            name="astrometry-audit",
            command=command,
            cwd=BACKEND,
            log_dir=log_dir,
            env=env,
        )
        evidence_dir = log_dir.parent / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        source = (
            BACKEND / "reports" / "evidence"
            / f"phase454-astrometry-audit-{run_id}.json"
        )
        if source.is_file():
            shutil.copy2(source, evidence_dir / source.name)
        return [result]
    if group == "fits-integrity":
        started = time.monotonic()
        result = _fits_integrity()
        result.update({
            "name": "fits-integrity",
            "duration_seconds": round(time.monotonic() - started, 3),
        })
        return [result]
    if group == "frontend":
        pnpm_command = "pnpm.cmd" if os.name == "nt" else "pnpm"
        if shutil.which(pnpm_command) is None:
            return [_skip("frontend", "pnpm is not available on PATH.") | {
                "status": "blocked",
                "failure_kind": "missing_dependency",
            }]
        if not (FRONTEND / "node_modules").is_dir():
            return [_skip("frontend", "Frontend dependencies are not installed.") | {
                "status": "blocked",
                "failure_kind": "missing_dependency",
            }]
        return [
            _execute(
                name=f"frontend-{script}",
                command=[pnpm_command, "run", script],
                cwd=FRONTEND,
                log_dir=log_dir,
                env=env,
            )
            for script in ("typecheck", "build")
        ]
    if group == "e2e":
        return [_skip(
            "browser-e2e",
            "No automated browser E2E command is configured in the project manifests.",
        )]
    raise ValueError(f"Unknown validation group: {group}")


def _status(results: list[dict[str, Any]]) -> str:
    statuses = {result["status"] for result in results}
    if "failed" in statuses:
        return "failed"
    if "blocked" in statuses:
        return "blocked"
    if "not_run" in statuses:
        return "partial"
    return "passed"


def _markdown_report(payload: dict[str, Any]) -> str:
    totals = payload["totals"]
    lines = [
        "# Central validation report",
        "",
        f"- Run ID: `{payload['run_id']}`",
        f"- Started: `{payload['started_at']}`",
        f"- Finished: `{payload['finished_at']}`",
        f"- Category: `{payload['category']}`",
        f"- Overall: **{payload['status'].upper()}**",
        f"- Duration: {payload['duration_seconds']:.2f} s",
        "",
        "## Totals",
        "",
        f"- Tests: {totals['tests']}",
        f"- Passed: {totals['passed']}",
        f"- Failed: {totals['failed']}",
        f"- Skipped by pytest: {totals['skipped']}",
        f"- Errors: {totals['errors']}",
        f"- Unstable (unexpected passes): {totals['unstable']}",
        f"- Blocked groups: {totals['blocked_groups']}",
        f"- Not-run groups: {totals['not_run_groups']}",
        "",
        "## Validation groups",
        "",
        "| Group | Status | Duration (s) | Exit code | Failure kind |",
        "|---|---|---:|---:|---|",
    ]
    for result in payload["results"]:
        lines.append(
            "| {name} | {status} | {duration} | {exit_code} | {failure} |".format(
                name=result["name"],
                status=result["status"],
                duration=result.get("duration_seconds", "—"),
                exit_code=result.get("exit_code", "—"),
                failure=result.get("failure_kind") or "—",
            )
        )
    warnings = [
        (result["name"], warning)
        for result in payload["results"]
        for warning in result.get("warnings", [])
    ]
    lines.extend(["", "## Warnings", ""])
    if warnings:
        lines.extend(f"- `{name}`: {warning}" for name, warning in warnings)
    else:
        lines.append("No warning lines were captured.")
    lines.extend([
        "",
        "## Evidence and logs",
        "",
        f"- JSON: `{payload['paths']['json']}`",
        f"- Test logs: `{payload['paths']['logs']}`",
        f"- Evidence directory: `{payload['paths']['evidence']}`",
        f"- History copy: `{payload['paths']['history']}`",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--category",
        choices=sorted(CATEGORY_GROUPS),
        default="all",
        help="Validation category to execute (default: all).",
    )
    parser.add_argument(
        "--report-root",
        type=Path,
        default=DEFAULT_REPORT_ROOT,
        help="Root directory for latest and timestamped history reports.",
    )
    parser.add_argument(
        "--catalog-probe",
        action="store_true",
        help="Include the bounded public IRSA catalog probe in astrometry validation.",
    )
    args = parser.parse_args()

    run_id = _run_id()
    latest_dir = args.report_root / "latest"
    history_dir = args.report_root / "history" / run_id
    logs_dir = latest_dir / "test_logs" / run_id
    evidence_dir = latest_dir / "evidence" / run_id
    for directory in (logs_dir, evidence_dir, history_dir / "test_logs"):
        directory.mkdir(parents=True, exist_ok=True)

    started_at = _utc_now()
    start = time.monotonic()
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    results: list[dict[str, Any]] = []
    groups = CATEGORY_GROUPS[args.category]
    for group in groups:
        group_results = _run_group(
            group,
            logs_dir,
            env,
            catalog_probe=args.catalog_probe and group == "astrometry-audit",
            run_id=run_id,
        )
        results.extend(group_results)

    elapsed = time.monotonic() - start
    pytest_totals = {
        key: sum(result.get("pytest_counts", {}).get(key, 0) for result in results)
        for key in ("passed", "failed", "skipped", "errors", "xfailed", "xpassed")
    }
    test_total = sum(pytest_totals.values())
    failed_groups = sum(result["status"] == "failed" for result in results)
    blocked_groups = sum(result["status"] == "blocked" for result in results)
    not_run_groups = sum(result["status"] == "not_run" for result in results)
    overall_status = _status(results)

    payload: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "category": args.category,
        "status": overall_status,
        "started_at": started_at.isoformat(),
        "finished_at": _utc_now().isoformat(),
        "duration_seconds": round(elapsed, 3),
        "totals": {
            "tests": test_total,
            **pytest_totals,
            "unstable": pytest_totals["xpassed"],
            "failed_groups": failed_groups,
            "blocked_groups": blocked_groups,
            "not_run_groups": not_run_groups,
        },
        "results": results,
        "paths": {
            "json": str((latest_dir / "validation_results.json").relative_to(ROOT)),
            "logs": str(logs_dir.relative_to(ROOT)),
            "evidence": str(evidence_dir.relative_to(ROOT)),
            "history": str(history_dir.relative_to(ROOT)),
        },
        "notes": [
            "No retry is performed; an initial failure remains visible.",
            "The FITS integrity check reads and hashes originals but never writes to them.",
            "A missing browser E2E command is recorded as not run, not passed.",
        ],
    }

    latest_json = latest_dir / "validation_results.json"
    latest_markdown = latest_dir / "validation_report.md"
    _write_json(latest_json, payload)
    markdown = _markdown_report(payload)
    latest_markdown.write_text(markdown, encoding="utf-8")
    _write_json(history_dir / "validation_results.json", payload)
    (history_dir / "validation_report.md").write_text(markdown, encoding="utf-8")
    for log in logs_dir.iterdir():
        if log.is_file():
            shutil.copy2(log, history_dir / "test_logs" / log.name)
    history_evidence_dir = history_dir / "evidence"
    history_evidence_dir.mkdir(exist_ok=True)
    for evidence in evidence_dir.iterdir():
        if evidence.is_file():
            shutil.copy2(evidence, history_evidence_dir / evidence.name)

    print(markdown)
    return 0 if overall_status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
