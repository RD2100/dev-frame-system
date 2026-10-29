"""结果聚合器 — 多源测试结果 → 统一格式 → Allure报告

各工具适配器在 adapters/ 目录下独立维护，每个模块提供 collect() 函数。
"""

import os
import json
import uuid
import subprocess
from datetime import datetime
from pathlib import Path

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
    for adapter_name in _ADAPTERS:
        try:
            module = importlib.import_module(adapter_name)
            results = module.collect(project_config)
            all_results.extend(results)
        except ImportError:
            pass
        except Exception as e:
            print(f"  [WARN] Adapter {adapter_name} error: {e}")
    return all_results


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

    summary = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / total * 100, 1) if total > 0 else 0,
        "by_tool": by_tool,
        "generated_at": datetime.now().isoformat(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
