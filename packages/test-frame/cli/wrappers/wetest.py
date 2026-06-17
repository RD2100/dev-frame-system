"""WeTest wrapper — 通过API上传APK并触发云真机兼容性测试"""

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
        return {"passed": False, "tool": "wetest", "results": [], "skipped": True,
                "reason": "WeTest API key not configured"}

    apk_path = project_config.get("project", {}).get("apk_path", "")
    if not apk_path or not os.path.exists(apk_path):
        print(f"    [WARN] APK未找到 ({apk_path})，跳过")
        return {"passed": False, "tool": "wetest", "results": [], "skipped": True,
                "reason": f"APK not found: {apk_path}"}

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

        # TODO(2026-05-26): 需要WeTest账户环境验证真实API集成
        #   - 取消注释 _upload_apk / _create_task / _poll_results
        #   - 验证上传/创建/轮询流程
        #   - 当前为桩实现，所有路径返回 skipped
        print("    [WARN] WeTest API集成待验证WeTest账户环境")
        return {"passed": False, "tool": "wetest", "results": [], "skipped": True,
                "reason": "WeTest stub — real API calls are commented out, needs account verification",
                "note": "需要WeTest账户验证API"}

    except Exception as e:
        print(f"    [WARN] WeTest执行异常: {e}")
        return {"passed": False, "tool": "wetest", "results": [], "skipped": True,
                "reason": f"WeTest execution error: {str(e)[:200]}"}
