#!/usr/bin/env python
"""FitTrack 全自动测试 — 一条命令

用法:
    python tests/fittrack/run_tests.py
    python tests/fittrack/run_tests.py --open
"""

import sys
import os
import time
import threading
import subprocess
import json
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)


def main(open_report=False):
    print("=" * 60)
    print("  FitTrack 健身管理小程序 — 全自动测试")
    print("=" * 60)

    # ── Stage 0: 启动 Mock ──
    print(f"\n[Stage 0] Starting FitTrack Mock server...")
    from tests.fittrack.mock_server import start_server, PORT as MOCK_PORT
    server = start_server(MOCK_PORT)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.3)
    print(f"  [OK] Mock server: http://127.0.0.1:{MOCK_PORT}")

    all_passed = True
    total = passed = failed = 0
    model_total = model_passed = model_failed = 0

    try:
        # ── Stage 1: API 测试 ──
        print(f"\n[Stage 1] API tests (cloud function mocks)...")
        print("-" * 40)

        results_dir = "reports/allure-results"
        os.makedirs(results_dir, exist_ok=True)
        for f in Path(results_dir).glob("*.json"):
            f.unlink()

        api_cmd = [
            sys.executable, "-m", "pytest", "tests/fittrack/test_api.py",
            "-v", "--tb=short", f"--alluredir={results_dir}",
        ]
        r = subprocess.run(api_cmd, capture_output=True, text=True, timeout=120)

        print(r.stdout[-3000:] if len(r.stdout) > 3000 else r.stdout)
        if r.stderr and "ERROR" in r.stderr:
            print(r.stderr[:1000])

        api_passed = r.returncode == 0
        if not api_passed:
            all_passed = False
        # Parse counts
        for line in r.stdout.splitlines():
            if "passed" in line and "failed" in line and "=" in line:
                try:
                    parts = line.strip().split(",")
                    for p in parts:
                        p = p.strip()
                        if "passed" in p:
                            passed = int(p.split()[0])
                        elif "failed" in p:
                            failed = int(p.split()[0])
                except Exception:
                    pass
        total = passed + failed

        print(f"\n  API: {passed}/{total} passed")

        # ── Stage 2: 模型/规则测试 ──
        print(f"\n[Stage 2] Data model & business rule tests...")
        print("-" * 40)

        model_cmd = [
            sys.executable, "-m", "pytest", "tests/fittrack/test_models.py",
            "-v", "--tb=short", f"--alluredir={results_dir}",
        ]
        r2 = subprocess.run(model_cmd, capture_output=True, text=True, timeout=60)
        print(r2.stdout[-3000:] if len(r2.stdout) > 3000 else r2.stdout)

        model_ok = r2.returncode == 0
        if not model_ok:
            all_passed = False
        for line in r2.stdout.splitlines():
            if "passed" in line and "failed" in line and "=" in line:
                try:
                    for p in line.strip().split(","):
                        p = p.strip()
                        if "passed" in p:
                            model_passed = int(p.split()[0])
                        elif "failed" in p:
                            model_failed = int(p.split()[0])
                except Exception:
                    pass
        model_total = model_passed + model_failed

        print(f"\n  Models: {model_passed}/{model_total} passed")

        # ── Stage 3: 结果聚合 ──
        print(f"\n[Stage 3] Aggregating results...")
        from aggregator.adapters.pytest_adapter import collect as pytest_collect
        results = pytest_collect()
        api_results = sum(1 for r in results if r.get("tool") == "pytest_api")
        print(f"  Total results: {api_results}")

        # ── Stage 4: 归因 ──
        print(f"\n[Stage 4] Defect attribution...")
        from attribution.engine import AttributionEngine
        engine = AttributionEngine()
        failures = [r for r in results if r.get("status") in ("failed", "broken")]
        attributed = engine.attribute_batch(failures) if failures else []
        matched = [a for a in attributed if a.get("matched_rule")]
        print(f"  Failures: {len(failures)}, Matched: {len(matched)}")
        for a in matched[:5]:
            print(f"    [{a['severity']}] {a['test_name'][:60]}")
            print(f"      → {a['root_cause']}: {a['suggestion'][:60]}")

        # ── Stage 5: 门禁 ──
        print(f"\n[Stage 5] Quality gate...")
        from orchestrator.gate import gate_check
        gate_passed, gate_report = gate_check("pr", "fittrack", results)
        print(gate_report)

        # ── Stage 6: Allure 报告 ──
        print(f"\n[Stage 6] Generating Allure report...")
        report_dir = "reports/fittrack/allure-report"
        allure_bin_cmd = os.path.join(PROJECT_ROOT, "node_modules", ".bin", "allure.cmd")
        allure_bin = os.path.join(PROJECT_ROOT, "node_modules", ".bin", "allure")
        if os.path.exists(allure_bin_cmd):
            allure_bin = allure_bin_cmd
        try:
            subprocess.run([allure_bin, "generate", results_dir, "-o", report_dir, "--clean"],
                          capture_output=True, text=True, timeout=60)
            if os.path.exists(os.path.join(report_dir, "index.html")):
                print(f"  [OK] Report: {os.path.abspath(report_dir)}/index.html")
            else:
                raise FileNotFoundError("not generated")
        except Exception as e:
            print(f"  [WARN] Allure {e}")
            print(f"  Manual: npx allure serve {results_dir}")

        # ── 摘要 ──
        print(f"\n{'=' * 60}")
        print(f"  FitTrack Test Complete")
        print(f"  {'=' * 60}")
        print(f"  API:    {passed}/{total} passed")
        print(f"  Models: {model_passed}/{model_total} passed")
        print(f"  Gate:   {'[OK] PASS' if gate_passed else '[FAIL] BLOCKED'}")
        print(f"  Rules:  {len(engine.rules)} loaded, {len(matched)} matched")

        if open_report:
            report_path = os.path.join(report_dir, "index.html")
            if os.path.exists(report_path):
                import webbrowser
                import http.server
                import socketserver

                class Q(http.server.SimpleHTTPRequestHandler):
                    def log_message(self, *a): pass

                httpd = socketserver.TCPServer(("127.0.0.1", 8767), Q)
                threading.Thread(target=httpd.serve_forever, daemon=True).start()
                url = "http://127.0.0.1:8767/reports/fittrack/allure-report/"
                webbrowser.open(url)
                print(f"\n  [SERVE] {url}")

    finally:
        print(f"\n[Cleanup] Stopping server...")
        server.shutdown()
        print(f"  [OK] Done")

    return all_passed


if __name__ == "__main__":
    open_b = "--open" in sys.argv or "-o" in sys.argv
    ok = main(open_report=open_b)
    sys.exit(0 if ok else 1)
