"""validate_writelab_client.py — A7 Paper-Lite Integration validation script.

Runs 14 checks to verify the WriteLab Lite HTTP client:
  1-3:  Module structure and imports
  4-6:  Client configuration (DI factory, base_url, token)
  7-9:  Failure semantics (degraded result schema)
  10-11: Adapter integration (convert functions importable, schema validation)
  12-14: Test suite verification
"""

import sys
import ast
import inspect
from pathlib import Path

# Ensure project is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "ai-workflow-hub" / "src"))

from ai_workflow_hub.context_layer.adapters.writelab_client import (
    WriteLabLiteClient,
    WriteLabCallResult,
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT_EXPRESSION,
    DEFAULT_TIMEOUT_DIAGNOSIS,
    DEFAULT_HEALTH_TIMEOUT,
)
from ai_workflow_hub.context_layer.adapters.writelab_adapter import (
    convert_expression_results,
    convert_paragraph_results,
    validate_review_issue,
)


def run_check(check_id: int, description: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] Check {check_id:02d}: {description}")
    if detail and not passed:
        print(f"         Detail: {detail}")
    return passed


def main():
    print("=" * 60)
    print("A7 Paper-Lite Integration (WriteLab Client) Validation")
    print("=" * 60)

    results = []

    # --- Module structure (1-3) ---
    client_file = PROJECT_ROOT / "ai-workflow-hub" / "src" / "ai_workflow_hub" / "context_layer" / "adapters" / "writelab_client.py"
    results.append(run_check(1, "writelab_client.py exists",
                             client_file.exists()))

    source = client_file.read_text(encoding="utf-8")
    tree = ast.parse(source)
    class_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    results.append(run_check(2, "WriteLabLiteClient class defined",
                             "WriteLabLiteClient" in class_names))
    results.append(run_check(3, "WriteLabCallResult dataclass defined",
                             "WriteLabCallResult" in class_names))

    # --- Client configuration (4-6) ---
    client = WriteLabLiteClient()
    results.append(run_check(4, "Default base_url is 127.0.0.1:8001",
                             client.base_url == "http://127.0.0.1:8001"))

    # Check _client_factory dependency injection
    has_factory = "_client_factory" in inspect.signature(WriteLabLiteClient.__init__).parameters
    results.append(run_check(5, "_client_factory DI parameter exists",
                             has_factory))

    token_client = WriteLabLiteClient(token="test-token")
    headers = token_client._headers()
    results.append(run_check(6, "Bearer token included in headers",
                             headers.get("Authorization") == "Bearer test-token"))

    # --- Failure semantics (7-9) ---
    degraded = client._degraded_result("test error message")
    results.append(run_check(7, "Degraded result has success=False",
                             degraded.success is False))

    results.append(run_check(8, "Degraded issue is non-blocking",
                             len(degraded.issues) == 1
                             and degraded.issues[0]["blocking"] is False
                             and degraded.issues[0]["severity"] == "info"))

    results.append(run_check(9, "Degraded diagnosis_source is 'unavailable'",
                             degraded.diagnosis_source == "unavailable"))

    # --- Adapter integration (10-11) ---
    results.append(run_check(10, "convert_expression_results importable from adapter",
                             callable(convert_expression_results)))

    # Test schema validation on a sample issue
    sample_issues = convert_expression_results([{
        "detection_id": "test-0001",
        "rule_id": "W1",
        "risk_level": "high",
        "chapter": "test",
        "section": "test",
        "paragraph_index": 0,
        "rule_description": "test rule",
        "suggestion": "fix it",
        "matched_text": "test text",
    }])
    schema_errors = validate_review_issue(sample_issues[0]) if sample_issues else ["no issues"]
    results.append(run_check(11, "Adapter-converted issues pass schema validation",
                             schema_errors == []))

    # --- Test suite (12-14) ---
    test_file = PROJECT_ROOT / "ai-workflow-hub" / "tests" / "test_writelab_client.py"
    results.append(run_check(12, "test_writelab_client.py exists",
                             test_file.exists()))

    test_source = test_file.read_text(encoding="utf-8")
    # Count test classes
    test_tree = ast.parse(test_source)
    test_classes = [n.name for n in ast.walk(test_tree)
                    if isinstance(n, ast.ClassDef) and n.name.startswith("Test")]
    results.append(run_check(13, f"Test file has 6 test classes (found {len(test_classes)})",
                             len(test_classes) == 6))

    # Check that tests use MockTransport (not patch)
    uses_mock_transport = "MockTransport" in test_source
    no_patch = "from unittest.mock import" not in test_source or "patch" not in test_source
    results.append(run_check(14, "Tests use httpx.MockTransport (no fragile patch)",
                             uses_mock_transport and no_patch))

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
