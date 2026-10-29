"""Maestro结果适配器 — JUnit XML → 统一TestResult格式"""

import os
import xml.etree.ElementTree as ET
from pathlib import Path


def collect(project_config: dict = None) -> list[dict]:
    """收集Maestro JUnit XML结果"""
    results = []
    report_dir = "reports/maestro/"
    if os.path.isdir(report_dir):
        for f in Path(report_dir).rglob("*.xml"):
            try:
                tree = ET.parse(f)
                for tc in tree.findall(".//testcase"):
                    failure = tc.find("failure")
                    error = tc.find("error")
                    is_failed = failure is not None or error is not None
                    err_msg = None
                    if is_failed:
                        err_elem = failure or error
                        err_msg = err_elem.get("message", "") if err_elem is not None else ""
                    results.append({
                        "test_name": tc.get("name", "unknown"),
                        "status": "failed" if is_failed else "passed",
                        "tool": "maestro",
                        "duration_ms": float(tc.get("time", 0)) * 1000,
                        "error": {"message": err_msg} if err_msg else None,
                    })
            except Exception:
                continue
    return results
