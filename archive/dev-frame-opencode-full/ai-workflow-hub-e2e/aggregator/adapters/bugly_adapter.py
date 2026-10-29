"""Bugly adapter — INTENTIONALLY GATED.

Gate: BUGLY_ANDROID_APP_ID + BUGLY_ANDROID_APP_KEY environment variables.
Without credentials, collect() returns [] (empty results, no error).
This is by design — see aggregator/preflight.py for the credential check.
"""


def collect(project_config: dict = None) -> list[dict]:
    """从Bugly API收集崩溃数据.

    需要有效的 Bugly App ID/Key 才能调用 API。
    凭证未配置时返回空列表，由 preflight 标记为 blocked 而非 error。
    """
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
