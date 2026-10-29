"""MeterSphere结果适配器 — API → 统一TestResult格式"""

import requests


def collect(project_config: dict = None) -> list[dict]:
    """从MeterSphere API收集测试结果"""
    if project_config is None:
        return []

    ms_config = project_config.get("metersphere", {})
    base_url = ms_config.get("base_url", "http://localhost:8081")
    api_key = ms_config.get("api_key", "")

    if not api_key:
        return []

    try:
        resp = requests.get(
            f"{base_url}/api/report/latest",
            headers={"X-Api-Key": api_key},
            timeout=30
        )
        if resp.status_code != 200:
            return []
        data = resp.json().get("data", {})
        results = []
        for case in data.get("cases", []):
            results.append({
                "test_name": case.get("name", "unknown"),
                "status": "passed" if case.get("status") == "success" else "failed",
                "tool": "metersphere",
                "duration_ms": case.get("duration", 0),
                "error": {"message": case.get("error", "")} if case.get("error") else None,
            })
        return results
    except Exception:
        return []
