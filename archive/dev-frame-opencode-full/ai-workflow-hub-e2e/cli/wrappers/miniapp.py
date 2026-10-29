"""小程序自动化 wrapper — 封装 miniprogram-automator + Jest"""

import subprocess
import json
import os


def run(project_config: dict) -> dict:
    """执行微信小程序自动化测试"""
    test_dir = project_config.get("miniapp", {}).get("test_dir", "tests/miniapp/specs/")
    port = project_config.get("miniapp", {}).get("devtool_port", 9420)

    if not os.path.isdir(test_dir):
        print("    [WARN] 未找到小程序测试目录")
        return {"passed": True, "tool": "miniapp", "results": [], "skipped": True}

    # 启动微信开发者工具（自动化模式）
    devtool_path = os.environ.get(
        "WECHAT_DEVTOOL_PATH",
        r"C:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat"
    )

    project_path = project_config.get("miniapp", {}).get("project_path", "./")
    if os.path.exists(devtool_path):
        subprocess.Popen(
            [devtool_path, "auto", "--port", str(port), "--open", project_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        import time
        time.sleep(3)
    else:
        print("    [WARN] 微信开发者工具CLI未找到，跳过")
        return {"passed": True, "tool": "miniapp", "results": [], "skipped": True}

    print(f"    ▶ 小程序自动化测试")
    cmd = ["npx", "jest", test_dir, "--json"]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        results = {"passed": r.returncode == 0, "tool": "miniapp", "results": [], "failed": []}
        try:
            data = json.loads(r.stdout)
            for tr in data.get("testResults", []):
                name = tr.get("name", "unknown")
                if tr.get("status") == "failed":
                    results["failed"].append(name)
                    results["results"].append({"name": name, "status": "failed"})
                else:
                    results["results"].append({"name": name, "status": "passed"})
        except json.JSONDecodeError:
            pass
        return results
    except FileNotFoundError:
        print("    [WARN] Jest 未安装，跳过 (npm install -g jest)")
        return {"passed": True, "tool": "miniapp", "results": [], "skipped": True}
    except subprocess.TimeoutExpired:
        return {"passed": False, "tool": "miniapp", "results": [], "error": "timeout"}
