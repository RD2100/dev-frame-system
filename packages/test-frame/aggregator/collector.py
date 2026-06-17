"""结果聚合器 — 多源测试结果 → 统一格式 → Allure报告

各工具适配器在 adapters/ 目录下独立维护，每个模块提供 collect() 函数。
"""

import os
import json
import uuid
import subprocess
from datetime import datetime
from pathlib import Path

from aggregator.allure_generator import AllureGenerationResult, generate_allure_report
from schema.stage_results import iter_public_tool_results

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


_ALLURE_STATUS_BY_CANONICAL = {
    "passed": "passed",
    "failed": "failed",
    "skipped": "skipped",
    "blocked": "broken",
    "error": "broken",
    "cancelled": "broken",
}


def _stage_results_to_report_results(stage_results: dict) -> list[dict]:
    """Convert orchestrator stage results into report-compatible items."""
    return [
        {
            "test_name": f"{item['stage']}.{item['tool']}",
            "status": item["status"],
            "tool": item["tool"],
            "stage": item["stage"],
        }
        for item in iter_public_tool_results(stage_results)
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


def _legacy_collect_and_generate(project_name: str, date: str = None, output_dir: str = None,
                                 project_config: dict = None, stage_results: dict = None,
                                 profile: str = None, quality_gate: dict = None,
                                 base_url: str = "", command: str = "") -> str:
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
    if stage_results is not None:
        results = _stage_results_to_report_results(stage_results)
    else:
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

    has_report_context = (
        stage_results is not None
        or profile is not None
        or quality_gate is not None
        or bool(base_url)
        or bool(command)
    )
    if has_report_context:
        from aggregator.report import generate_regression_report

        report_profile = profile
        if report_profile is None and project_config:
            report_profile = project_config.get("_profile")

        generate_regression_report(
            project_name=project_name,
            profile=report_profile or "unknown",
            results=results,
            stage_results=stage_results or {},
            quality_gate=quality_gate,
            base_url=base_url,
            command=command,
            date=os.path.basename(base_dir),
            output_dir=base_dir,
            project_config=project_config,
        )

    return allure_report_dir


def collect_and_generate(project_name: str, date: str = None, output_dir: str = None,
                         project_config: dict = None, stage_results: dict = None,
                         profile: str = None, quality_gate: dict = None,
                         base_url: str = "", command: str = "") -> AllureGenerationResult:
    """Collect results, write machine-readable outputs, then generate Allure HTML if available."""
    base_dir = output_dir or os.path.join("reports", project_name)
    if date is None:
        base_dir = os.path.join(base_dir, datetime.now().strftime("%Y-%m-%d"))
    else:
        base_dir = os.path.join(base_dir, date)

    allure_results_dir = os.path.join(base_dir, "allure-results")
    allure_report_dir = os.path.join(base_dir, "allure-report")
    os.makedirs(allure_results_dir, exist_ok=True)

    if stage_results is not None:
        results = _stage_results_to_report_results(stage_results)
    else:
        results = collect_all_results(project_config)

    for result in results:
        _write_allure_result(result, allure_results_dir)

    summary_path = os.path.join(base_dir, "summary.json")
    _write_summary(results, summary_path)

    allure_generation = generate_allure_report(
        allure_results_dir,
        allure_report_dir,
        summary_path=summary_path,
    )
    if allure_generation.status == "PASS":
        print(f"  [REPORT] Allure HTML report: {allure_generation.html_path}")
    elif allure_generation.status == "BLOCKED":
        print(
            "  [REPORT][BLOCKED] Allure HTML not generated: "
            f"{allure_generation.reason}; fallback manifest: {allure_generation.manifest_path}"
        )
    else:
        print(
            "  [REPORT][FAILED] Allure HTML generation failed: "
            f"{allure_generation.reason}; manifest: {allure_generation.manifest_path}"
        )

    has_report_context = (
        stage_results is not None
        or profile is not None
        or quality_gate is not None
        or bool(base_url)
        or bool(command)
    )
    if has_report_context:
        from aggregator.report import generate_regression_report

        report_profile = profile
        if report_profile is None and project_config:
            report_profile = project_config.get("_profile")

        generate_regression_report(
            project_name=project_name,
            profile=report_profile or "unknown",
            results=results,
            stage_results=stage_results or {},
            quality_gate=quality_gate,
            base_url=base_url,
            command=command,
            date=os.path.basename(base_dir),
            output_dir=base_dir,
            project_config=project_config,
            allure_generation=allure_generation.to_dict(),
        )

    return allure_generation


_legacy_collect_and_generate = None


def collect_failed_results(project_config: dict = None) -> list[dict]:
    """只收集失败的结果，用于归因分析"""
    all_results = collect_all_results(project_config)
    return [r for r in all_results if r.get("status") == "failed"]


def _write_allure_result(result: dict, output_dir: str):
    """将统一格式的测试结果写入Allure JSON"""
    canonical_status = result["status"]
    allure_result = {
        "name": result["test_name"],
        "status": _ALLURE_STATUS_BY_CANONICAL.get(canonical_status, "broken"),
        "stage": "finished",
        "labels": [
            {"name": "tool", "value": result["tool"]},
            {"name": "language", "value": "python"},
            {"name": "canonical_status", "value": canonical_status},
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
    blocked = sum(1 for r in results if r.get("status") == "blocked")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    error = sum(1 for r in results if r.get("status") == "error")
    cancelled = sum(1 for r in results if r.get("status") == "cancelled")

    by_tool = {}
    for r in results:
        tool = r.get("tool", "unknown")
        status = r.get("status", "unknown")
        if tool not in by_tool:
            by_tool[tool] = {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "blocked": 0,
                "skipped": 0,
                "error": 0,
                "cancelled": 0,
            }
        by_tool[tool]["total"] += 1
        if status in by_tool[tool]:
            by_tool[tool][status] += 1

    summary = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "blocked": blocked,
        "skipped": skipped,
        "error": error,
        "cancelled": cancelled,
        "pass_rate": round(passed / total * 100, 1) if total > 0 else 0,
        "by_tool": by_tool,
        "generated_at": datetime.now().isoformat(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
