"""pytest API wrapper — 封装 pytest 执行"""

import subprocess
import os
from pathlib import Path


def run(project_config: dict) -> dict:
    """执行 pytest API 测试"""
    test_dir = project_config.get("pytest_api", {}).get("test_dir", "tests/api/")
    # 也支持 demo 目录
    alt_dir = project_config.get("pytest_api", {}).get("alt_test_dir", "")
    if alt_dir and os.path.isdir(alt_dir):
        test_dir = alt_dir

    if not os.path.isdir(test_dir):
        print("    [WARN] pytest test directory not found, skip")
        return {"passed": True, "tool": "pytest_api", "results": [], "skipped": True}

    results_dir = "reports/allure-results"
    os.makedirs(results_dir, exist_ok=True)

    test_files = list(Path(test_dir).glob("test_*.py"))
    if not test_files:
        print("    [WARN] No pytest test files found")
        return {"passed": True, "tool": "pytest_api", "results": [], "skipped": True}

    report_json = os.path.join("reports", "pytest_results.json")
    cmd = [
        "python", "-m", "pytest", test_dir,
        "-v",
        "--tb=short",
        f"--alluredir={results_dir}",
        f"--json-report",
        f"--json-report-file={report_json}",
    ]

    print(f"    > pytest {test_dir}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        # pytest exit codes: 0=all pass, 1=tests failed, others=error
        passed = r.returncode == 0
        return {
            "passed": passed,
            "tool": "pytest_api",
            "results": _parse_pytest_output(r.stdout),
            "failed": [] if passed else _extract_failed(r.stdout),
        }
    except FileNotFoundError:
        print("    [WARN] pytest not available, skip")
        return {"passed": True, "tool": "pytest_api", "results": [], "skipped": True}
    except subprocess.TimeoutExpired:
        return {"passed": False, "tool": "pytest_api", "results": [], "error": "timeout"}


def _parse_pytest_output(stdout: str) -> list:
    """从 pytest stdout 提取结果摘要"""
    results = []
    for line in stdout.splitlines():
        if "PASSED" in line or "FAILED" in line or "ERROR" in line:
            results.append({"status_line": line.strip()})
    return results


def _extract_failed(stdout: str) -> list:
    """提取失败用例名"""
    failed = []
    for line in stdout.splitlines():
        if "FAILED" in line and "::" in line:
            name = line.strip().split(" - ")[0] if " - " in line else line.strip()
            failed.append(name)
    return failed
