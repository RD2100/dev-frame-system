"""Playwright结果适配器 — JSON → 统一TestResult格式"""

import os
import json


def collect(project_config: dict = None) -> list[dict]:
    """收集Playwright JSON结果，返回统一TestResult列表"""
    results = []

    # Determine report path from config or default
    pw_config = (project_config or {}).get("playwright", {})
    report_path = pw_config.get("results_json", "test-results/.playwright-results.json")

    # Also check legacy location
    legacy_path = "test-results/.playwright-results.json"
    if not os.path.exists(report_path) and os.path.exists(legacy_path):
        report_path = legacy_path

    if not os.path.exists(report_path):
        # If playwright is required, emit a blocked result
        if pw_config.get("required", False):
            results.append({
                "test_name": "playwright_stage",
                "status": "blocked",
                "tool": "playwright",
                "duration_ms": 0,
                "error": {"message": f"Playwright results file not found: {report_path}"},
            })
        return results

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for suite in data.get("suites", []):
            suite_title = suite.get("title", "")
            for spec in suite.get("specs", []):
                spec_title = spec.get("title", "")
                spec_file = spec.get("file", "")
                for test in spec.get("tests", []):
                    test_title = test.get("title", "")
                    for r in test.get("results", []):
                        _status = r.get("status", "skipped")
                        status = _map_status(_status)

                        entry = {
                            "test_name": f"{spec_title} > {test_title}",
                            "status": status,
                            "tool": "playwright",
                            "duration_ms": r.get("duration", 0),
                            "browser": r.get("browser", "chromium"),
                            "spec_file": spec_file,
                            "error": _extract_error(r) if status != "passed" else None,
                        }
                        results.append(entry)
    except Exception:
        pass
    return results


def _map_status(status: str) -> str:
    """Map Playwright status string to TestFrame status."""
    if status in ("passed", "expected", "flaky"):
        return "passed"
    if status in ("failed", "unexpected", "interrupted", "timedOut"):
        return "failed"
    if status == "skipped":
        return "skipped"
    return "failed"


def _extract_error(result: dict) -> dict:
    """Extract error details from a Playwright test result.
    Returns None if no error content is present."""
    error = result.get("error", {})
    if not error:
        return None
    message = error.get("message", "")
    stack = error.get("stack", "")
    if not message and not stack:
        return None
    extracted = {
        "message": message,
        "stack_trace": stack,
    }
    location = error.get("location")
    if location:
        extracted["location"] = location
    return extracted
