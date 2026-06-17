"""Bugly结果适配器 — API → 统一TestResult格式"""


def collect(project_config: dict = None) -> list[dict]:
    """从Bugly API收集崩溃数据"""
    # Bugly API集成需要有效的App ID/Key
    return []


def collect_from_response(api_response: dict) -> list[dict]:
    """从Bugly API响应中提取崩溃结果"""
    results = []
    crashes = api_response.get("crashList", [])
    for crash in crashes:
        results.append({
            "test_name": f"[Bugly] {crash.get('exceptionName', 'unknown')}",
            "status": "failed",
            "tool": "bugly",
            "error": {
                "message": crash.get("exceptionMsg", ""),
                "stack_trace": crash.get("crashStack", ""),
            },
            "metadata": {
                "crash_count": crash.get("count", 1),
                "affected_users": crash.get("affectedUserCount", 0),
                "app_version": crash.get("appVersion", ""),
            },
        })
    return results
