"""validate_writelab_lite.py — A6 Lite API validation script.

Runs 12 checks to verify the WriteLab Lite API entry point:
  1-3:  Health endpoint
  4-7:  Version endpoint
  8-9:  Router isolation
  10-11: Analysis endpoints
  12:   No database dependency
"""

import sys
from pathlib import Path

# Ensure WriteLab backend is importable
SCRIPT_DIR = Path(__file__).resolve().parent
WRITELAB_BACKEND = Path(r"D:\writelab\backend")
sys.path.insert(0, str(WRITELAB_BACKEND))

from fastapi.testclient import TestClient
from app.main_lite import app


def run_check(check_id: int, description: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] Check {check_id:02d}: {description}")
    if detail and not passed:
        print(f"         Detail: {detail}")
    return passed


def main():
    print("=" * 60)
    print("A6 WriteLab Lite API Validation")
    print("=" * 60)

    client = TestClient(app)
    results = []

    # --- Health endpoint (1-3) ---
    health = client.get("/health").json()
    results.append(run_check(1, "Health returns status ok",
                             health.get("status") == "ok"))
    results.append(run_check(2, "Health declares stateless_analysis mode",
                             health.get("mode") == "stateless_analysis"))
    results.append(run_check(3, "Health declares no text persistence",
                             health.get("raw_text_persisted") is False))

    # --- Version endpoint (4-7) ---
    ver = client.get("/version").json()
    results.append(run_check(4, "Version returns writelab_version",
                             ver.get("writelab_version") == "0.1.0"))
    results.append(run_check(5, "Version returns lite_api_version",
                             ver.get("lite_api_version") == "0.1.0-lite"))
    results.append(run_check(6, "Version has detector_ruleset_hash (12 chars)",
                             len(ver.get("detector_ruleset_hash", "")) == 12))
    results.append(run_check(7, "Version reports 20 template patterns",
                             ver.get("template_pattern_count") == 20))

    # --- Router isolation (8-9) ---
    results.append(run_check(8, "No /api/projects route (404)",
                             client.get("/api/projects").status_code == 404))
    results.append(run_check(9, "No /api/reports route (404)",
                             client.get("/api/reports/diagnosis").status_code == 404))

    # --- Analysis endpoints (10-11) ---
    expr_resp = client.post("/api/analyze/expression", json={"paragraph": "一方面改革，另一方面稳定。"})
    results.append(run_check(10, "Expression analysis returns 200",
                             expr_resp.status_code == 200))

    para_resp = client.post("/api/analyze/paragraph-diagnosis",
                            json={"paragraph": "教育政策需要系统化方法。", "expected_function": "problem_statement"})
    results.append(run_check(11, "Paragraph diagnosis returns 200 with diagnosis",
                             para_resp.status_code == 200 and "diagnosis" in para_resp.json()))

    # --- No database (12) ---
    routes = [r.path for r in app.routes]
    has_db_routes = any("/projects" in r or "/paragraphs" in r or "/reports" in r for r in routes)
    results.append(run_check(12, "No database-dependent routers mounted",
                             not has_db_routes))

    # Summary
    passed = sum(results)
    total = len(results)
    print("=" * 60)
    print(f"Result: {passed}/{total} checks passed")
    if passed == total:
        print("STATUS: ALL CHECKS PASSED")
    else:
        print(f"STATUS: {total - passed} CHECK(S) FAILED")
    print("=" * 60)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
