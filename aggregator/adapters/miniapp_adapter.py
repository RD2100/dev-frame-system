"""小程序自动化结果适配器 — Jest JSON → 统一TestResult格式"""

import os
import json


def collect(project_config: dict = None) -> list[dict]:
    """收集Jest测试结果（miniprogram-automator）"""
    results = []
    jest_output = "reports/jest-results.json"
    if os.path.exists(jest_output):
        try:
            with open(jest_output, "r", encoding="utf-8") as f:
                data = json.load(f)
            for tr in data.get("testResults", []):
                name = tr.get("name", "unknown")
                for assertion in tr.get("assertionResults", []):
                    results.append({
                        "test_name": f"{name} > {assertion.get('title', '')}",
                        "status": assertion.get("status", "failed"),
                        "tool": "miniapp",
                        "duration_ms": assertion.get("duration", 0),
                        "error": {
                            "message": assertion.get("failureMessages", [""])[0][:500]
                        } if assertion.get("status") == "failed" else None,
                    })
        except Exception:
            pass
    return results
