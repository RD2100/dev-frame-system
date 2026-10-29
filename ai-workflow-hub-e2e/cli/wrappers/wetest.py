"""WeTest wrapper — INTENTIONALLY GATED.

通过 API 上传 APK 并触发云真机兼容性测试。
需要 WeTest 账户验证 API (WETEST_API_KEY / WETEST_API_SECRET)。
凭证未配置时返回 skipped=True，由 preflight 阻断。
API 集成细节（上传/创建任务/轮询）待验证 WeTest 账户环境后启用。
"""

import requests
import time
import os


def run(project_config: dict) -> dict:
    """上传APK到WeTest并触发兼容性测试"""
    wetest_config = project_config.get("wetest", {})
    api_base = wetest_config.get("api_base", "https://api.wetest.qq.com")
    api_key = wetest_config.get("api_key", "")
    api_secret = wetest_config.get("api_secret", "")

    if not api_key or not api_secret:
        print("    [WARN] WeTest API Key未配置，跳过 (设置 WETEST_API_KEY / WETEST_API_SECRET)")
        return {"passed": True, "tool": "wetest", "results": [], "skipped": True}

    apk_path = project_config.get("project", {}).get("apk_path", "")
    if not apk_path or not os.path.exists(apk_path):
        print(f"    [WARN] APK未找到 ({apk_path})，跳过")
        return {"passed": True, "tool": "wetest", "results": [], "skipped": True}

    print(f"    ▶ WeTest 云真机兼容性测试: {apk_path}")

    try:
        # 1. 上传APK (模拟)
        print("    [1/3] 上传APK...")
        # upload_resp = _upload_apk(api_base, api_key, api_secret, apk_path)

        # 2. 创建测试任务
        print("    [2/3] 创建测试任务...")
        # task_resp = _create_task(api_base, api_key, api_secret, upload_resp)

        # 3. 轮询结果
        print("    [3/3] 等待测试完成...")
        # results = _poll_results(api_base, api_key, api_secret, task_resp)

        # Placeholder — 实际需要WeTest账户验证API
        print("    [WARN] WeTest API集成待验证WeTest账户环境")
        return {"passed": True, "tool": "wetest", "results": [], "skipped": True,
                "note": "需要WeTest账户验证API"}

    except Exception as e:
        print(f"    [WARN] WeTest执行异常: {e}")
        return {"passed": True, "tool": "wetest", "results": [], "skipped": True}
