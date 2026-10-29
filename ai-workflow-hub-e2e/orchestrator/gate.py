"""质量门禁评估器

Future metrics (not yet active):
  - task_spec_compliance: validates execution stayed within TaskSpec scope.
    Placeholder rules are defined in config/gates.yaml (commented) and will be
    activated once the TaskSpec adapter is stable.
"""

import os
import json
import yaml
from datetime import datetime


def load_gate_config(gate_type: str = "pr") -> dict:
    """加载门禁规则.

    返回规则 dict 或 {"_load_error": "<reason>"}（加载失败时）。
    """
    gate_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config", "gates.yaml"
    )
    try:
        with open(gate_path, "r", encoding="utf-8") as f:
            gates = yaml.safe_load(f) or {}
        return gates.get("gates", {}).get(gate_type, {})
    except FileNotFoundError:
        return {"_load_error": f"gates.yaml not found: {gate_path}"}
    except yaml.YAMLError as e:
        return {"_load_error": f"gates.yaml parse error: {e}"}
    except Exception as e:
        return {"_load_error": f"gates.yaml load error: {e}"}


def evaluate(gate_type: str, results: list[dict], crash_count: int = 0) -> tuple:
    """评估门禁，返回 (passed: bool, failures: list, metrics: dict).

    若配置加载失败（含 _load_error 标记），返回 passed=False，
    failures 中包含加载错误信息。不再静默通过。
    """
    rules = load_gate_config(gate_type)
    if not rules:
        return True, [], {}
    if "_load_error" in rules:
        return False, [rules["_load_error"]], {}

    # 从结果列表计算指标
    total = len(results)
    passed_count = sum(1 for r in results if r.get("status") == "passed")
    failed_count = sum(1 for r in results if r.get("status") == "failed")

    metrics = {
        "total": total,
        "passed": passed_count,
        "failed": failed_count,
        "smoke_pass_rate": round(passed_count / total * 100, 1) if total > 0 else 0,
        "regression_pass_rate": round(passed_count / total * 100, 1) if total > 0 else 0,
        "compatibility_pass_rate": 100,  # 默认100，有数据后覆盖
        "crash_count": crash_count,
        "crash_free_rate": 100 - crash_count * 0.1,
        "critical_bugs": 0,
        "min_evidence_count": total,  # evidence count = total test results
    }

    # 逐项比对
    failures = []
    for metric, rule in rules.items():
        actual = metrics.get(metric)
        if actual is None:
            # Missing metrics are skipped, not failed
            # (metric comes from a stage that may not have run)
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
    for k, v in metrics.items():
        lines.append(f"  {k}: {v}")

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
            results = [{"status": "passed"} for _ in range(summary.get("passed", 0))]
            results += [{"status": "failed"} for _ in range(summary.get("failed", 0))]

    passed, failures, metrics = evaluate(gate_type, results or [], crash_count)
    report = format_gate_result(gate_type, passed, failures, metrics)
    return passed, report
