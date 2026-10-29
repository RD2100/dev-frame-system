"""Airtest wrapper — 封装 airtest run 命令"""

import subprocess
import os
from pathlib import Path


def run(project_config: dict) -> dict:
    """执行Airtest回归测试"""
    test_dir = project_config.get("airtest", {}).get("test_dir", "tests/android/airtest/")
    device_uri = project_config.get("airtest", {}).get("device_uri", "Android:///")
    log_dir = project_config.get("airtest", {}).get("log_dir", "reports/airtest_log/")

    os.makedirs(log_dir, exist_ok=True)

    test_files = list(Path(test_dir).glob("*.py")) if os.path.isdir(test_dir) else []
    if not test_files:
        print("    [WARN] 未找到Airtest测试文件")
        return {"passed": True, "tool": "airtest", "results": [], "skipped": True}

    results = {"passed": True, "tool": "airtest", "results": [], "failed": []}

    for test_file in test_files:
        name = test_file.stem
        print(f"    ▶ {name}")
        cmd = [
            "python", "-m", "airtest", "run",
            str(test_file),
            "--device", device_uri,
            "--log", os.path.join(log_dir, name),
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if r.returncode == 0:
                results["results"].append({"name": name, "status": "passed"})
            else:
                results["passed"] = False
                results["failed"].append(name)
                results["results"].append({
                    "name": name, "status": "failed",
                    "error": r.stderr[:500] if r.stderr else ""
                })
        except FileNotFoundError:
            print("    [WARN] Airtest 未安装，跳过 (pip install airtest pocoui)")
            return {"passed": True, "tool": "airtest", "results": [], "skipped": True}
        except subprocess.TimeoutExpired:
            results["passed"] = False
            results["failed"].append(name)

    return results
