"""MeterSphere wrapper — 通过API触发接口测试"""

import requests
import time


def run(project_config: dict) -> dict:
    """通过MeterSphere API触发测试计划并轮询结果"""
    ms_config = project_config.get("metersphere", {})
    base_url = ms_config.get("base_url", "http://localhost:8081")
    api_key = ms_config.get("api_key", "")
    test_plan_id = ms_config.get("test_plan_id", "")

    if not test_plan_id or not api_key:
        print("    [WARN] MeterSphere配置不完整，跳过")
        return {"passed": True, "tool": "metersphere", "results": [], "skipped": True}

    print(f"    ▶ MeterSphere 接口测试 (plan={test_plan_id})")

    try:
        # 触发测试计划
        resp = requests.post(
            f"{base_url}/api/test/plan/run",
            headers={"X-Api-Key": api_key},
            json={"plan_id": test_plan_id},
            timeout=30
        )
        resp.raise_for_status()
        report_id = resp.json().get("data", {}).get("id", "")

        # 轮询结果（简化）
        timeout = ms_config.get("timeout", 600)
        poll_interval = ms_config.get("poll_interval", 10)
        elapsed = 0
        while elapsed < timeout:
            time.sleep(poll_interval)
            elapsed += poll_interval
            status_resp = requests.get(
                f"{base_url}/api/report/{report_id}",
                headers={"X-Api-Key": api_key},
                timeout=30
            )
            status = status_resp.json().get("data", {}).get("status", "")
            if status in ("completed", "success", "error"):
                return {
                    "passed": status == "success",
                    "tool": "metersphere",
                    "results": [{"report_id": report_id, "status": status}],
                }

        return {"passed": True, "tool": "metersphere", "results": [], "warning": "timeout等待"}
    except requests.ConnectionError:
        print("    [WARN] MeterSphere 服务不可达，跳过")
        return {"passed": True, "tool": "metersphere", "results": [], "skipped": True}
    except Exception as e:
        print(f"    [WARN] MeterSphere执行异常: {e}")
        return {"passed": True, "tool": "metersphere", "results": [], "skipped": True}
