"""Playwright wrapper — 封装 npx playwright test 命令"""

import subprocess
import json
import os


def run(project_config: dict) -> dict:
    """执行Playwright H5测试"""
    config_path = "config/tools/playwright.yaml"
    test_dir = "tests/h5/playwright/"

    if not os.path.isdir(test_dir):
        print("    [WARN] 未找到Playwright测试目录")
        return {"passed": True, "tool": "playwright", "results": [], "skipped": True}

    print(f"    ▶ Playwright测试")
    cmd = [
        "npx", "playwright", "test",
        test_dir,
        "--reporter=json",
    ]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode == 0:
            return {"passed": True, "tool": "playwright", "results": []}
        else:
            results = {"passed": False, "tool": "playwright", "results": [], "failed": []}
            try:
                data = json.loads(r.stdout)
                for suite in data.get("suites", []):
                    for spec in suite.get("specs", []):
                        for test in spec.get("tests", []):
                            for tr in test.get("results", []):
                                if tr.get("status") != "passed":
                                    results["failed"].append(test.get("title"))
            except json.JSONDecodeError:
                pass
            return results
    except FileNotFoundError:
        print("    [WARN]  Playwright 未安装，跳过 (npm init playwright)")
        return {"passed": True, "tool": "playwright", "results": [], "skipped": True}
    except subprocess.TimeoutExpired:
        return {"passed": False, "tool": "playwright", "results": [], "error": "timeout"}
