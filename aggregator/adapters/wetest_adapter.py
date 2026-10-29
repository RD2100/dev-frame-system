"""WeTest结果适配器 — API → 统一TestResult格式"""


def collect(project_config: dict = None) -> list[dict]:
    """从WeTest API收集兼容性测试结果"""
    # WeTest API集成需要有效的API Key环境
    # 返回空列表直到环境就绪
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
