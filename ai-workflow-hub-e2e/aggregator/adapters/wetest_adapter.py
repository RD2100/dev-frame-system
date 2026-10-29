"""WeTest adapter — INTENTIONALLY GATED.

Gate: WETEST_API_KEY + WETEST_API_SECRET environment variables.
Without credentials, collect() returns [] (empty results, no error).
This is by design — see aggregator/preflight.py for the credential check.
"""


def collect(project_config: dict = None) -> list[dict]:
    """从WeTest API收集兼容性测试结果.

    需要有效的 WeTest API Key/Secret 才能调用 API。
    凭证未配置时返回空列表，由 preflight 标记为 blocked 而非 error。
    """
    return []


def collect_from_response(api_response: dict) -> list[dict]:
    """从WeTest API响应中提取结果"""
    results = []
    devices = api_response.get("devices", [])
    for device in devices:
        device_name = device.get("model", "unknown")
        for test_case in device.get("results", []):
            results.append({
                "test_name": f"[{device_name}] {test_case.get('name', '')}",
                "status": test_case.get("status", "failed"),
                "tool": "wetest",
                "duration_ms": test_case.get("duration", 0) * 1000,
                "metadata": {
                    "device": device_name,
                    "os_version": device.get("os_version", ""),
                },
                "error": {
                    "message": test_case.get("error", ""),
                    "screenshot": test_case.get("screenshot", ""),
                } if test_case.get("status") == "failed" else None,
            })
    return results
