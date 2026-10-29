"""结果聚合器 — 多源测试结果 → 统一格式 → Allure报告

各工具适配器在 adapters/ 目录下独立维护，每个模块提供 collect() 函数。
"""

import os
import json
import uuid
import subprocess
from datetime import datetime
from pathlib import Path

from aggregator.preflight import check_credentials

# All adapter modules with collect(project_config) -> list[dict]
_ADAPTERS = [
    "aggregator.adapters.maestro_adapter",
    "aggregator.adapters.airtest_adapter",
    "aggregator.adapters.playwright_adapter",
    "aggregator.adapters.miniapp_adapter",
    "aggregator.adapters.metersphere_adapter",
    "aggregator.adapters.pytest_adapter",
    "aggregator.adapters.wetest_adapter",
    "aggregator.adapters.sentry_adapter",
    "aggregator.adapters.bugly_adapter",
]


def collect_all_results(project_config: dict = None) -> list[dict]:
    """调用所有适配器的 collect()，返回统一 TestResult 列表"""
    import importlib
    all_results = []
    _adapter_status.clear()
    _blocked_adapters.clear()
    _blocked_reasons.clear()
    for adapter_name in _ADAPTERS:
        zero_result = False
        error_type = None
        blocked = False
        short_name = adapter_name.rsplit(".", 1)[-1]  # e.g. "sentry_adapter"

        # B3: credential preflight — external adapters need env vars
        cred_check = check_credentials(short_name)
        if not cred_check["ready"]:
            blocked = True
            _blocked_adapters.append(short_name)
            _blocked_reasons[short_name] = f"missing env vars: {', '.join(cred_check['missing'])}"
            print(f"  [BLOCKED] {adapter_name}: {_blocked_reasons[short_name]}")
            _adapter_status[adapter_name] = {
                "zero_result": False,
                "error": None,
                "blocked": True,
            }
            continue

        try:
            module = importlib.import_module(adapter_name)
            results = module.collect(project_config)
            all_results.extend(results)
            if len(results) == 0:
                zero_result = True
        except ImportError as e:
            error_type = "ImportError"
            print(f"  [WARN] Adapter {adapter_name} import failed: {e}")
        except Exception as e:
            error_type = type(e).__name__
            print(f"  [WARN] Adapter {adapter_name} error: {e}")
        _adapter_status[adapter_name] = {
            "zero_result": zero_result,
            "error": error_type,
            "blocked": blocked,
        }
    return all_results


# Track per-adapter status during the most recent collect_all_results() call.
# Key: adapter module name, Value: {"zero_result": bool, "error": str|None, "blocked": bool}
_adapter_status: dict = {}

# Track blocked adapters (B3/B4)
_blocked_adapters: list = []
_blocked_reasons: dict = {}


def compute_integrity() -> dict:
    """Compute adapter-level integrity from the most recent collect_all_results() run.

    Returns a dict with keys:
        total_adapters        — number of registered adapters
        zero_result_adapters  — adapters that returned zero results (no error, not blocked)
        error_adapters        — adapters that raised an exception
        blocked_adapters      — adapters blocked by missing credentials (B3/B4)
        blocked_reasons       — {adapter_name: reason_str}
        warning               — bool, True when >50% of eligible adapters are silent/errored
                                 (blocked adapters excluded from this calculation)
        message               — human-readable summary
    """
    total = len(_ADAPTERS)
    blocked = [name for name, s in _adapter_status.items() if s.get("blocked")]
    zero_result = [name for name, s in _adapter_status.items()
                   if s["zero_result"] and not s.get("blocked")]
    errored = [name for name, s in _adapter_status.items() if s["error"]]

    # B4: blocked adapters excluded from the ">50% zero = warning" threshold
    eligible = total - len(blocked)
    silent_count = len(zero_result) + len(errored)
    warning = eligible > 0 and silent_count > eligible / 2
    message = ""
    if warning:
        parts = []
        if zero_result:
            parts.append(f"{len(zero_result)} adapters returned 0 results: {', '.join(zero_result)}")
        if errored:
            parts.append(f"{len(errored)} adapters errored: {', '.join(errored)}")
        message = "INTEGRITY WARNING: " + "; ".join(parts)

    # Build blocked_reasons from _blocked_reasons (short names) to full adapter names
    blocked_reasons = {}
    for name in blocked:
        short = name.rsplit(".", 1)[-1]
        blocked_reasons[name] = _blocked_reasons.get(short, "unknown")

    return {
        "total_adapters": total,
        "zero_result_adapters": zero_result,
        "error_adapters": errored,
        "blocked_adapters": blocked,
        "blocked_reasons": blocked_reasons,
        "warning": warning,
        "message": message,
    }


def collect_and_generate(project_name: str, date: str = None, output_dir: str = None,
                         project_config: dict = None) -> str:
    """收集所有工具结果并生成Allure报告"""
    base_dir = output_dir or os.path.join("reports", project_name)
    if date is None:
        base_dir = os.path.join(base_dir, datetime.now().strftime("%Y-%m-%d"))
    else:
        base_dir = os.path.join(base_dir, date)

    allure_results_dir = os.path.join(base_dir, "allure-results")
    allure_report_dir = os.path.join(base_dir, "allure-report")
    os.makedirs(allure_results_dir, exist_ok=True)

    # 收集所有工具结果
    results = collect_all_results(project_config)

    # 写入Allure格式
    for result in results:
        _write_allure_result(result, allure_results_dir)

    # 生成HTML报告
    try:
        subprocess.run(
            ["allure", "generate", allure_results_dir, "-o", allure_report_dir, "--clean"],
            capture_output=True, text=True, timeout=120
        )
        print(f"  [REPORT] Allure report: {allure_report_dir}")
    except FileNotFoundError:
        print("  [WARN] Allure CLI not installed, skip HTML report")
    except Exception as e:
        print(f"  [WARN] Allure report generation failed: {e}")

    # 保存统计摘要
    _write_summary(results, os.path.join(base_dir, "summary.json"))

    # 如果适配器完整性警告或阻塞，记录到 evidence 目录
    integrity = compute_integrity()
    if integrity["warning"] or integrity["blocked_adapters"]:
        try:
            from evidence.collector import EvidenceCollector
            ev_collector = EvidenceCollector(project_name)
            ev_index = ev_collector.collect()
            ev_index.add_evidence(
                type="integrity_warning",
                tool="aggregator",
                path=os.path.join(base_dir, "summary.json"),
                metadata={
                    "total_adapters": integrity["total_adapters"],
                    "zero_result_adapters": integrity["zero_result_adapters"],
                    "error_adapters": integrity["error_adapters"],
                    "blocked_adapters": integrity["blocked_adapters"],
                    "blocked_reasons": integrity["blocked_reasons"],
                    "message": integrity["message"],
                },
            )
            # Re-write evidence index with the new entry
            import json as _json
            ev_path = os.path.join(ev_collector.base_dir, "evidence.json")
            with open(ev_path, "w", encoding="utf-8") as f:
                _json.dump(ev_index.to_dict(), f, ensure_ascii=False, indent=2)
            print(f"  [INTEGRITY] Recorded to evidence: {integrity['message']}")
        except Exception as e:
            print(f"  [WARN] Failed to record integrity evidence: {e}")

    return allure_report_dir


def collect_failed_results(project_config: dict = None) -> list[dict]:
    """只收集失败的结果，用于归因分析"""
    all_results = collect_all_results(project_config)
    return [r for r in all_results if r.get("status") == "failed"]


def _write_allure_result(result: dict, output_dir: str):
    """将统一格式的测试结果写入Allure JSON"""
    allure_result = {
        "name": result["test_name"],
        "status": result["status"],
        "stage": "finished",
        "labels": [
            {"name": "tool", "value": result["tool"]},
            {"name": "language", "value": "python"},
        ],
        "description": "",
    }

    # 工具和阶段标签
    for key in ("stage", "device"):
        if result.get(key):
            allure_result["labels"].append({"name": key, "value": str(result[key])})

    # 附加元数据到description
    if result.get("metadata"):
        allure_result["description"] = json.dumps(result["metadata"], ensure_ascii=False)

    if result.get("error"):
        allure_result["statusDetails"] = {
            "message": result["error"].get("message", "")[:1000],
            "trace": result["error"].get("stack_trace", "")[:5000],
        }

    if result.get("screenshot"):
        allure_result["attachments"] = [{
            "name": "screenshot",
            "source": result["screenshot"],
            "type": "image/png",
        }]

    fname = f"{uuid.uuid4()}-result.json"
    with open(os.path.join(output_dir, fname), "w", encoding="utf-8") as f:
        json.dump(allure_result, f, ensure_ascii=False, indent=2)


def _write_summary(results: list[dict], path: str):
    """写入统计摘要JSON"""
    total = len(results)
    passed = sum(1 for r in results if r.get("status") == "passed")
    failed = sum(1 for r in results if r.get("status") == "failed")
    by_tool = {}
    for r in results:
        tool = r.get("tool", "unknown")
        if tool not in by_tool:
            by_tool[tool] = {"total": 0, "passed": 0, "failed": 0}
        by_tool[tool]["total"] += 1
        if r.get("status") == "passed":
            by_tool[tool]["passed"] += 1
        else:
            by_tool[tool]["failed"] += 1

    integrity = compute_integrity()
    summary = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / total * 100, 1) if total > 0 else 0,
        "by_tool": by_tool,
        "integrity": integrity,
        "blocked_adapters": integrity.get("blocked_adapters", []),
        "blocked_reasons": integrity.get("blocked_reasons", {}),
        "generated_at": datetime.now().isoformat(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
