#!/usr/bin/env python
"""TestFrame 自包含 Demo — 一条命令跑通全流水线

零外部依赖，零注册，零配置。
使用 Python stdlib Mock 服务器 + pytest + requests。

用法:
    python demo/run_demo.py
    python demo/run_demo.py --open  # 自动打开浏览器看报告
"""

import sys
import os
import time
import threading
import subprocess
import json
from pathlib import Path

# Ensure project root in path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from demo.mock_server import start_server, PORT as MOCK_PORT


def main(open_report: bool = False):
    print("=" * 60)
    print("  TestFrame Demo — 全自动流水线演示")
    print("  零依赖 | 零注册 | 零配置")
    print("=" * 60)

    # ── Stage 0: 启动 Mock 服务器 ──
    print(f"\n[Stage 0] Starting Mock API server on port {MOCK_PORT}...")
    server = start_server(MOCK_PORT)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.5)
    print(f"  [OK] Mock server ready: http://127.0.0.1:{MOCK_PORT}")

    all_passed = True
    failed_names = []

    try:
        # ── Stage 1: 冒烟测试 (pytest) ──
        print(f"\n[Stage 1] Running pytest API tests...")
        print("-" * 40)

        results_dir = "reports/allure-results"
        os.makedirs(results_dir, exist_ok=True)

        # Clean previous results
        for f in Path(results_dir).glob("*.json"):
            f.unlink()

        pytest_cmd = [
            sys.executable, "-m", "pytest", "demo/test_api.py",
            "-v", "--tb=short",
            f"--alluredir={results_dir}",
        ]
        r = subprocess.run(pytest_cmd, capture_output=True, text=True, timeout=120)

        # Print pytest output
        print(r.stdout[-3000:] if len(r.stdout) > 3000 else r.stdout)
        if r.stderr and "ERROR" in r.stderr:
            print(r.stderr[:1000])

        pytest_passed = r.returncode == 0
        if not pytest_passed:
            all_passed = False
            for line in r.stdout.splitlines():
                if "FAILED" in line:
                    failed_names.append(line.strip()[:80])

        print(f"\n  Stage 1 result: {'[OK] PASS' if pytest_passed else '[FAIL]'} "
              f"(exit={r.returncode})")

        # ── Stage 2: 证据收集 ──
        print(f"\n[Stage 2] Collecting evidence...")
        allure_files = list(Path(results_dir).glob("*result.json"))
        print(f"  Allure results: {len(allure_files)} files")

        # ── Stage 3: 结果聚合 ──
        print(f"\n[Stage 3] Aggregating results...")
        from aggregator.adapters.pytest_adapter import collect as pytest_collect
        test_results = pytest_collect()
        passed_count = sum(1 for r in test_results if r.get("status") == "passed")
        failed_count = sum(1 for r in test_results if r.get("status") in ("failed", "broken"))
        print(f"  Results: {len(test_results)} tests ({passed_count} passed, {failed_count} failed)")

        # Write summary
        summary = {
            "total": len(test_results),
            "passed": passed_count,
            "failed": failed_count,
            "pass_rate": round(passed_count / len(test_results) * 100, 1) if test_results else 0,
            "by_tool": {"pytest_api": {"total": len(test_results), "passed": passed_count, "failed": failed_count}},
        }
        os.makedirs("reports/demo", exist_ok=True)
        with open("reports/demo/summary.json", "w") as f:
            json.dump(summary, f, indent=2)

        # ── Stage 4: 缺陷归因 ──
        print(f"\n[Stage 4] Defect attribution...")
        from attribution.engine import AttributionEngine
        engine = AttributionEngine()
        failed_results = [r for r in test_results if r.get("status") in ("failed", "broken")]
        attributed = engine.attribute_batch(failed_results) if failed_results else []

        matched = [a for a in attributed if a.get("matched_rule")]
        unmatched = [a for a in attributed if not a.get("matched_rule")]
        print(f"  Failed tests: {len(failed_results)}")
        print(f"  Matched rules: {len(matched)}")
        print(f"  Needs manual analysis: {len(unmatched)}")
        if matched:
            print(f"  Top attributions:")
            for a in matched[:3]:
                print(f"    [{a.get('severity', '?')}] {a['test_name'][:50]}")
                print(f"      -> {a.get('root_cause', '?')}: {a.get('suggestion', '')[:60]}")

        # ── Stage 5: 质量门禁 ──
        print(f"\n[Stage 5] Quality gate...")
        from orchestrator.gate import gate_check
        gate_passed, gate_report = gate_check("pr", "demo", test_results)
        print(gate_report)

        # ── Stage 6: 生成 Allure 报告 ──
        print(f"\n[Stage 6] Generating Allure report...")
        report_dir = "reports/demo/allure-report"
        try:
            # Use bundled allure from node_modules
            allure_bin = os.path.join(PROJECT_ROOT, "node_modules", ".bin", "allure")
            allure_bin_cmd = os.path.join(PROJECT_ROOT, "node_modules", ".bin", "allure.cmd")
            if os.path.exists(allure_bin_cmd):
                allure_bin = allure_bin_cmd  # Windows
            elif not os.path.exists(allure_bin):
                allure_bin = "allure"  # fallback to PATH

            subprocess.run(
                [allure_bin, "generate", results_dir, "-o", report_dir, "--clean"],
                capture_output=True, text=True, timeout=60
            )
            if os.path.exists(os.path.join(report_dir, "index.html")):
                print(f"  [OK] Report: {os.path.abspath(report_dir)}/index.html")
            else:
                raise FileNotFoundError(f"Report not generated at {report_dir}")
        except Exception as e:
            print(f"  [WARN] Allure report generation failed: {e}")
            print(f"  Manual: cd {PROJECT_ROOT} && npx allure serve {results_dir}")

        # ── 输出摘要 ──
        print(f"\n{'=' * 60}")
        print(f"  Demo Complete")
        print(f"  {'=' * 60}")
        print(f"  Tests:    {passed_count}/{len(test_results)} passed")
        print(f"  Gate:     {'[OK] PASS' if gate_passed else '[FAIL] BLOCKED'}")
        print(f"  Report:   {os.path.abspath(report_dir)}/index.html")
        print(f"  Rules:    {len(engine.rules)} loaded, {len(matched)} matched")

        # Open report via local HTTP server (file:// blocked by browser security)
        if open_report:
            report_html = os.path.join(report_dir, "index.html")
            if os.path.exists(report_html):
                import webbrowser
                import http.server
                import socketserver

                class QuietHandler(http.server.SimpleHTTPRequestHandler):
                    def log_message(self, *args): pass

                report_port = 8766
                httpd = socketserver.TCPServer(("127.0.0.1", report_port), QuietHandler)
                serve_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                serve_thread.start()

                url = f"http://127.0.0.1:{report_port}/reports/demo/allure-report/"
                print(f"\n  [SERVE] Report: {url}")
                webbrowser.open(url)
                print(f"  [OK] Browser opened. View report at {url}")
                print(f"  Press Ctrl+C to stop the server.")
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    print("\n  [OK] Server stopped")
                    httpd.shutdown()
            else:
                print(f"  Report not found.")
                print(f"  Manual: cd {PROJECT_ROOT} && npx allure serve reports/allure-results/")

    finally:
        # ── 清理 ──
        print(f"\n[Cleanup] Stopping Mock server...")
        server.shutdown()
        print(f"  [OK] Server stopped")

    return all_passed


if __name__ == "__main__":
    open_browser = "--open" in sys.argv or "-o" in sys.argv
    success = main(open_report=open_browser)
    sys.exit(0 if success else 1)
