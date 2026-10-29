"""Airtest结果适配器 — log.txt → 统一TestResult格式"""

import os
from pathlib import Path


def collect(project_config: dict = None) -> list[dict]:
    """收集Airtest日志结果"""
    results = []
    log_dir = "reports/airtest_log/"
    if os.path.isdir(log_dir):
        for f in Path(log_dir).rglob("log.txt"):
            try:
                with open(f, "r", encoding="utf-8", errors="ignore") as logf:
                    content = logf.read()
                for line in content.splitlines():
                    if "ASSERT" in line or "ERROR" in line:
                        results.append({
                            "test_name": line.strip()[:80],
                            "status": "failed" if "ERROR" in line else "passed",
                            "tool": "airtest",
                            "duration_ms": 0,
                            "error": {"message": line.strip()} if "ERROR" in line else None,
                        })
            except Exception:
                continue
    return results
