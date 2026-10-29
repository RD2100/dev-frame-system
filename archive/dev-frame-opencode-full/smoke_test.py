#!/usr/bin/env python3
"""Cross-project smoke test for D:\\dev-frame-opencode governance chain.

Verifies the minimal governance loop across all three projects (OpenCode-only):
  codegraph MCP readiness -> core workflow state machine -> E2E evidence integrity -> governance review.

Usage:
  python D:\\dev-frame-opencode\\smoke_test.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FRAME_ROOT = Path(r"D:\dev-frame-opencode")

def _npx_cmd() -> list[str]:
    """Return the correct npx invocation for the current platform."""
    if sys.platform == "win32":
        return ["npx.cmd"]
    return ["npx"]


SMOKE_COMMANDS: list[dict] = [
    {
        "id": 0,
        "label": "Documentation staleness check",
        "cwd": str(FRAME_ROOT),
        "cmd": [
            "python", "-c",
            "import subprocess, sys; "
            "stale = ['172/172', '172 tests', '172 passed', '~900 tests', '77 core tests', '175 evidence tests', '31 core + 168 e2e']; "
            "docs = ['AGENTS.md', 'CLAUDE.md', 'PROJECT_STATE.md', 'HEALTH_REPORT.md', 'RUNBOOK.md', "
            "'PRODUCTION_READINESS_SUMMARY.md', 'RELEASE_CRITERIA.md', 'PRODUCTION_READINESS_CHECKLIST.md', "
            "'PRODUCTION_READINESS_GAPS.md']; "
            "found = []; "
            "[found.append(f'{d}:{p}') for d in docs for p in stale "
            " if __import__('pathlib').Path(d).exists() and p in __import__('pathlib').Path(d).read_text(encoding='utf-8', errors='replace')]; "
            "print(f'STALE: {\", \".join(found)}' if found else 'CLEAN: 0 stale patterns'); "
            "sys.exit(1 if found else 0)",
        ],
        "known_issues": [],
    },
    {
        "id": 1,
        "label": "Readiness score diagnostic",
        "cwd": str(FRAME_ROOT),
        "cmd": ["python", "tools/readiness_score.py"],
        "known_issues": [],
    },
    {
        "id": 2,
        "label": "CodeGraph type-check",
        "cwd": str(FRAME_ROOT / "codegraph"),
        "cmd": _npx_cmd() + ["tsc", "--noEmit"],
        "known_issues": [],
    },
    {
        "id": 3,
        "label": "ai-workflow-hub core state tests (OpenCode)",
        "cwd": str(FRAME_ROOT / "ai-workflow-hub"),
        "cmd": ["python", "-m", "pytest", "tests/",
                "--ignore=tests/test_e2e_pipeline.py", "-v", "--tb=line"],
        "known_issues": [],
    },
    {
        "id": 4,
        "label": "ai-workflow-hub-e2e evidence + gate tests",
        "cwd": str(FRAME_ROOT / "ai-workflow-hub-e2e"),
        "cmd": ["python", "-m", "pytest", "tests/fittrack/", "tests/test_gate.py", "tests/test_sha256.py", "-v", "--tb=line"],
        "known_issues": [],
    },
]

TIMEOUT_SEC = 120

# ANSI color codes
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class CommandResult:
    cmd_id: int
    label: str
    cwd: str
    cmd: list[str]
    exit_code: int
    stdout_last: str  # last 10 lines of stdout
    stderr_last: str  # last 10 lines of stderr
    duration_ms: float
    status: str = ""  # PASS / KNOWN_ISSUE / FAIL
    key_metrics: str = ""


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _last_n_lines(text: str, n: int = 10) -> str:
    """Return the last n lines of text, stripping trailing blank lines."""
    lines = [l for l in text.splitlines() if l.strip() != ""]
    return "\n".join(lines[-n:])


def _extract_pytest_metrics(stdout: str) -> str:
    """Extract the pytest summary line (passed/failed/skipped)."""
    lines = stdout.splitlines()
    # Look for the summary line from the end: "===== N failed, M passed ... ====="
    # or "===== N passed ... ====="
    for line in reversed(lines):
        stripped = line.strip()
        if stripped.startswith("==") and ("passed" in stripped or "failed" in stripped):
            return stripped.strip("= ")
    return ""


def run_one(cfg: dict) -> CommandResult:
    """Execute one smoke command and return the result."""
    start = time.time()
    try:
        proc = subprocess.run(
            cfg["cmd"],
            cwd=cfg["cwd"],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SEC,
        )
        exit_code = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
    except subprocess.TimeoutExpired:
        exit_code = -1
        stdout = ""
        stderr = f"TIMEOUT after {TIMEOUT_SEC}s"
    elapsed = (time.time() - start) * 1000

    result = CommandResult(
        cmd_id=cfg["id"],
        label=cfg["label"],
        cwd=cfg["cwd"],
        cmd=cfg["cmd"],
        exit_code=exit_code,
        stdout_last=_last_n_lines(stdout),
        stderr_last=_last_n_lines(stderr),
        duration_ms=elapsed,
    )

    # Determine status
    if exit_code == 0:
        result.status = "PASS"
        pytest_metrics = _extract_pytest_metrics(stdout)
        result.key_metrics = pytest_metrics if pytest_metrics else "0 errors"
    elif exit_code == 1:
        # Could be known issue or real failure
        known = cfg.get("known_issues", [])
        # Check if all FAILED lines are from known issues only
        failed_lines = [line for line in stdout.splitlines() if "FAILED" in line]
        known_failed = sum(1 for line in failed_lines for k in known if k in line)
        if known and known_failed == len(failed_lines) and known_failed > 0:
            result.status = "KNOWN_ISSUE"
            result.key_metrics = _extract_pytest_metrics(stdout)
        else:
            result.status = "FAIL"
            result.key_metrics = f"exit_code={exit_code}"
    else:
        result.status = "FAIL"
        result.key_metrics = f"exit_code={exit_code}"

    return result


def color_status(status: str) -> str:
    if status == "PASS":
        return f"{GREEN}{status}{RESET}"
    elif status == "KNOWN_ISSUE":
        return f"{YELLOW}{status}{RESET}"
    elif status == "FAIL":
        return f"{RED}{status}{RESET}"
    return status


def print_summary(results: list[CommandResult]):
    """Print a unified summary table."""
    print()
    print(f"{BOLD}{'='*80}{RESET}")
    print(f"{BOLD}  CROSS-PROJECT SMOKE TEST RESULTS{RESET}")
    print(f"{BOLD}{'='*80}{RESET}")
    print()
    print(f"  {'#':<4} {'Command':<40} {'Exit':<6} {'Status':<16} {'Key Output'}")
    print(f"  {'-'*4} {'-'*40} {'-'*6} {'-'*16} {'-'*30}")

    for r in results:
        status_colored = color_status(r.status)
        key_out = r.key_metrics[:60] if r.key_metrics else "-"
        print(f"  {r.cmd_id:<4} {r.label:<40} {r.exit_code:<6} {status_colored:<38} {key_out}")

    print()

    passed = sum(1 for r in results if r.status == "PASS")
    known = sum(1 for r in results if r.status == "KNOWN_ISSUE")
    failed = sum(1 for r in results if r.status == "FAIL")

    if failed == 0:
        verdict_color = GREEN if known == 0 else YELLOW
        verdict = "PASS" if known == 0 else "PASS (with known issues)"
    else:
        verdict_color = RED
        verdict = "FAIL"

    print(f"  Summary: {GREEN}{passed} passed{RESET}, {YELLOW}{known} known issues{RESET}, {RED}{failed} failed{RESET}")
    print(f"  Verdict: {verdict_color}{verdict}{RESET}")
    print(f"{BOLD}{'='*80}{RESET}")


def write_report(results: list[CommandResult], report_path: Path):
    """Write smoke_report.txt."""
    import platform

    lines = []
    lines.append("=" * 80)
    lines.append("  SMOKE TEST REPORT")
    lines.append("=" * 80)
    lines.append(f"  Timestamp : {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    lines.append(f"  Host      : {platform.node()}")
    lines.append(f"  OS        : {platform.system()} {platform.release()} ({platform.version()})")
    lines.append(f"  Python    : {sys.version.split()[0]}")
    try:
        node_ver = subprocess.run(
            ["node", "--version"], capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except Exception:
        node_ver = "unknown"
    lines.append(f"  Node      : {node_ver}")
    lines.append("-" * 80)
    lines.append(f"  {'#':<4} {'Command':<40} {'Exit':<6} {'Status':<16} {'Duration':<12} {'Key Output'}")
    lines.append(f"  {'-'*4} {'-'*40} {'-'*6} {'-'*16} {'-'*12} {'-'*30}")

    for r in results:
        dur_str = f"{r.duration_ms:.0f}ms"
        key_out = r.key_metrics[:60] if r.key_metrics else "-"
        lines.append(f"  {r.cmd_id:<4} {r.label:<40} {r.exit_code:<6} {r.status:<16} {dur_str:<12} {key_out}")

    lines.append("-" * 80)
    passed = sum(1 for r in results if r.status == "PASS")
    known = sum(1 for r in results if r.status == "KNOWN_ISSUE")
    failed = sum(1 for r in results if r.status == "FAIL")
    lines.append(f"  Summary : {passed} passed, {known} known issues, {failed} failed")
    verdict = "PASS" if failed == 0 else "FAIL"
    lines.append(f"  Verdict : {verdict}")
    lines.append("=" * 80)

    # Per-command detail
    for r in results:
        lines.append("")
        lines.append(f"--- Command {r.cmd_id}: {r.label} ---")
        lines.append(f"  CWD       : {r.cwd}")
        lines.append(f"  CMD       : {' '.join(r.cmd)}")
        lines.append(f"  Exit Code : {r.exit_code}")
        lines.append(f"  Duration  : {r.duration_ms:.0f}ms")
        lines.append(f"  Status    : {r.status}")
        if r.stdout_last:
            lines.append(f"  stdout (last 10):")
            for line in r.stdout_last.splitlines():
                lines.append(f"    | {line}")
        if r.stderr_last:
            lines.append(f"  stderr (last 10):")
            for line in r.stderr_last.splitlines():
                lines.append(f"    E {line}")

    lines.append("")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n  Report written: {report_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print(f"{CYAN}Cross-Project Smoke Test{RESET}")
    print(f"  Projects: codegraph | ai-workflow-hub | ai-workflow-hub-e2e")
    print()

    results: list[CommandResult] = []
    for cfg in SMOKE_COMMANDS:
        label = cfg["label"]
        print(f"  [{cfg['id']}/{len(SMOKE_COMMANDS)}] Running: {label} ... ", end="", flush=True)
        result = run_one(cfg)
        status_colored = color_status(result.status)
        print(f"{status_colored} ({result.duration_ms:.0f}ms)")
        results.append(result)

    print_summary(results)

    report_path = FRAME_ROOT / "smoke_report.txt"
    write_report(results, report_path)

    # Exit 0 only if ALL pass (known issues are not blockers)
    failed_count = sum(1 for r in results if r.status == "FAIL")
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
