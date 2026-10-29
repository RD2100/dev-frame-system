"""pytest 结果适配器 — pytest JSON/Allure → 统一 TestResult 格式"""

import os
import json
from pathlib import Path


def collect(project_config: dict = None) -> list[dict]:
    """收集 pytest 测试结果"""
    results = []

    # 方式1: 从 Allure 结果目录读取
    allure_dir = "reports/allure-results"
    if os.path.isdir(allure_dir):
        for f in Path(allure_dir).glob("*result.json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                results.append({
                    "test_name": data.get("name", "unknown"),
                    "status": data.get("status", "unknown"),
                    "tool": "pytest_api",
                    "duration_ms": data.get("stop", 0) - data.get("start", 0),
                    "error": _extract_error(data) if data.get("status") in ("failed", "broken") else None,
                })
            except Exception:
                continue

    # 方式2: 从 pytest-json-report 读取（更丰富的统计）
    json_report = "reports/pytest_results.json"
    if os.path.exists(json_report):
        try:
            with open(json_report, "r", encoding="utf-8") as f:
                data = json.load(f)
            for test in data.get("tests", []):
                results.append({
                    "test_name": test.get("nodeid", "unknown"),
                    "status": test.get("outcome", "unknown"),
                    "tool": "pytest_api",
                    "duration_ms": test.get("duration", 0) * 1000 if test.get("duration") else 0,
                    "error": {
                        "message": test.get("call", {}).get("longrepr", "")[:500]
                    } if test.get("outcome") == "failed" else None,
                })
        except Exception:
            pass

    return results


def _extract_error(allure_result: dict) -> dict:
    details = allure_result.get("statusDetails", {})
    return {
        "message": details.get("message", "")[:500],
        "stack_trace": details.get("trace", "")[:2000],
    }
