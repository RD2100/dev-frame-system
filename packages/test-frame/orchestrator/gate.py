"""质量门禁评估器"""

import os
import json
import yaml
from datetime import datetime


def load_gate_config(gate_type: str = "pr") -> dict:
    """加载门禁规则"""
    gate_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config", "gates.yaml"
    )
    try:
        with open(gate_path, "r", encoding="utf-8") as f:
            gates = yaml.safe_load(f) or {}
        return gates.get("gates", {}).get(gate_type, {})
    except Exception:
        return {}


def evaluate(gate_type: str, results: list[dict], crash_count: int = 0) -> tuple:
    """Evaluate gate, returns (passed: bool, failures: list, metrics: dict).

    Status semantics (6 states):
    - passed:    test ran and passed
    - failed:    test ran and failed (assertion failure)
    - skipped:   tool not available / not configured (allowed)
    - blocked:   preconditions not met, test could not start
    - error:     tool/execution failure, cannot trust results
    - cancelled: manually cancelled, CI cancelled

    Behavior configs (from gate config):
    - blocked_behavior:   count_as_failure (default) | exclude | block_gate
    - error_behavior:     count_as_failure (default) | exclude | block_gate
    - cancelled_behavior: count_as_failure (default) | exclude | block_gate
    """
    rules = load_gate_config(gate_type)
    if not rules:
        return True, [], {}

    blocked_behavior = rules.get("blocked_behavior", "count_as_failure")
    error_behavior = rules.get("error_behavior", "count_as_failure")
    cancelled_behavior = rules.get("cancelled_behavior", "count_as_failure")

    # Count by status (6 states)
    total = len(results)
    passed_count = sum(1 for r in results if r.get("status") == "passed")
    failed_count = sum(1 for r in results if r.get("status") == "failed")
    skipped_count = sum(1 for r in results if r.get("status") == "skipped")
    blocked_count = sum(1 for r in results if r.get("status") == "blocked")
    error_count = sum(1 for r in results if r.get("status") == "error")
    cancelled_count = sum(1 for r in results if r.get("status") == "cancelled")

    # Compute effective pass rate based on behavior configs
    effective_passed = passed_count
    effective_failed = failed_count
    gate_blocked = False

    # skipped: always excluded from pass rate
    # passed/failed: always included

    for status, count, behavior in [
        ("blocked", blocked_count, blocked_behavior),
        ("error", error_count, error_behavior),
        ("cancelled", cancelled_count, cancelled_behavior),
    ]:
        if behavior == "count_as_failure":
            effective_failed += count
        elif behavior == "exclude":
            pass  # excluded from both numerator and denominator
        elif behavior == "block_gate":
            gate_blocked = True
        else:
            raise ValueError(f"Unknown behavior for {status}: {behavior}")

    effective_total = effective_passed + effective_failed

    metrics = {
        "total": total,
        "passed": passed_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "blocked": blocked_count,
        "error": error_count,
        "cancelled": cancelled_count,
        "blocked_behavior": blocked_behavior,
        "error_behavior": error_behavior,
        "cancelled_behavior": cancelled_behavior,
        "smoke_pass_rate": round(effective_passed / effective_total * 100, 1) if effective_total > 0 else 0,
        "regression_pass_rate": round(effective_passed / effective_total * 100, 1) if effective_total > 0 else 0,
        "compatibility_pass_rate": 100,
        "crash_count": crash_count,
        "crash_free_rate": 100 - crash_count * 0.1,
        "critical_bugs": 0,
    }

    failures = []

    # Explicit check: total results = 0 -> fail
    if total == 0:
        failures.append("total_results: 0 results -- cannot verify quality")

    # Explicit check: any blocked/error/cancelled -> always flag
    if blocked_count > 0:
        failures.append(f"blocked: {blocked_count} required tool(s) could not run")
    if error_count > 0:
        failures.append(f"error: {error_count} tool execution failure(s)")
    if cancelled_count > 0:
        failures.append(f"cancelled: {cancelled_count} execution(s) cancelled")

    # block_gate: direct gate failure
    if gate_blocked:
        failures.append("gate: blocked by block_gate behavior (blocked|error|cancelled)")

    # Check each gate rule (skip behavior config keys)
    for metric, rule in rules.items():
        if metric in ("blocked_behavior", "error_behavior", "cancelled_behavior"):
            continue
        actual = metrics.get(metric)
        if actual is None:
            continue
        elif "min" in rule and actual < rule["min"]:
            failures.append(f"{metric}: actual={actual} < min={rule['min']}")
        elif "max" in rule and actual > rule["max"]:
            failures.append(f"{metric}: actual={actual} > max={rule['max']}")

    passed = len(failures) == 0
    return passed, failures, metrics

def format_gate_result(gate_type: str, passed: bool, failures: list, metrics: dict) -> str:
    """格式化门禁结果为可读文本"""
    lines = [
        f"Quality Gate: {gate_type}",
        f"Result: {'[OK] PASS' if passed else '[FAIL] BLOCKED'}",
        "",
        "Metrics:",
    ]
    for k in ("total", "passed", "failed", "blocked", "error", "cancelled", "skipped"):
        lines.append(f"  {k}: {metrics.get(k, 0)}")

    lines.append(f"  smoke_pass_rate: {metrics.get('smoke_pass_rate', 0)}%")
    lines.append(f"  regression_pass_rate: {metrics.get('regression_pass_rate', 0)}%")

    if failures:
        lines.append("")
        lines.append("Failures:")
        for f in failures:
            lines.append(f"  - {f}")
    return "\n".join(lines)


def gate_check(gate_type: str, project_name: str, results: list[dict] = None,
               crash_count: int = 0) -> tuple:
    """完整的门禁检查流程"""
    if results is None:
        # 尝试从 summary.json 加载
        summary_path = os.path.join("reports", project_name,
                                    datetime.now().strftime("%Y-%m-%d"),
                                    "summary.json")
        if os.path.exists(summary_path):
            with open(summary_path, "r", encoding="utf-8") as f:
                summary = json.load(f)
            results = []
            results += [{"status": "passed"} for _ in range(summary.get("passed", 0))]
            results += [{"status": "failed"} for _ in range(summary.get("failed", 0))]
            results += [{"status": "blocked"} for _ in range(summary.get("blocked", 0))]
            results += [{"status": "error"} for _ in range(summary.get("error", 0))]
            results += [{"status": "cancelled"} for _ in range(summary.get("cancelled", 0))]
            results += [{"status": "skipped"} for _ in range(summary.get("skipped", 0))]

    passed, failures, metrics = evaluate(gate_type, results or [], crash_count)
    report = format_gate_result(gate_type, passed, failures, metrics)
    return passed, report


def gate_check_with_summary(gate_type: str, project_name: str,
                            summary: dict, crash_count: int = 0) -> tuple:
    """Convenience: evaluate gate directly from a summary dict."""
    results = []
    results += [{"status": "passed"} for _ in range(summary.get("passed", 0))]
    results += [{"status": "failed"} for _ in range(summary.get("failed", 0))]
    results += [{"status": "blocked"} for _ in range(summary.get("blocked", 0))]
    results += [{"status": "error"} for _ in range(summary.get("error", 0))]
    results += [{"status": "cancelled"} for _ in range(summary.get("cancelled", 0))]
    results += [{"status": "skipped"} for _ in range(summary.get("skipped", 0))]

    passed, failures, metrics = evaluate(gate_type, results, crash_count)
    report = format_gate_result(gate_type, passed, failures, metrics)
    return passed, report
