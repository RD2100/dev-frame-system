"""Playwright结果适配器 — JSON → 统一TestResult格式"""

import os
import json


def collect(project_config: dict = None) -> list[dict]:
    """收集Playwright JSON结果"""
    results = []
    report_path = "test-results/.playwright-results.json"
    if os.path.exists(report_path):
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for suite in data.get("suites", []):
                for spec in suite.get("specs", []):
                    for test in spec.get("tests", []):
                        for r in test.get("results", []):
                            results.append({
                                "test_name": f"{spec.get('title', '')} > {test.get('title', '')}",
                                "status": "passed" if r.get("status") == "passed" else "failed",
                                "tool": "playwright",
                                "duration_ms": r.get("duration", 0),
                                "error": _extract_error(r) if r.get("status") != "passed" else None,
                            })
        except Exception:
            pass
    return results


def _extract_error(result: dict) -> dict:
    error = result.get("error", {})
    return {
        "message": error.get("message", ""),
        "stack_trace": error.get("stack", ""),
    }
