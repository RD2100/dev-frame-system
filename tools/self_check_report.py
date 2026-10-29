#!/usr/bin/env python3
"""
self_check_report.py — Parse final-report.md and validate against S1 synthesis rule.

Usage: python tools/self_check_report.py <final-report.md path>
Exit: 0 = valid, 1 = invalid (fake-green detected)
"""

import sys
import re
from pathlib import Path


def parse_final_report(path: Path) -> dict:
    """Parse the machine-readable YAML block from final-report.md top."""
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")

    result = {"final_batch_status": None, "blocked_by": [], "source_status": {}}

    for line in lines:
        stripped = line.rstrip("\n\r")
        if stripped == "---":
            break  # End of machine-readable block
        if not stripped:
            continue  # Skip blank lines

        if stripped.startswith("final_batch_status:"):
            result["final_batch_status"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("  guard_result:"):
            result["source_status"]["guard_result"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("  evidence_status:"):
            result["source_status"]["evidence_status"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("  reviewer_verdict:"):
            result["source_status"]["reviewer_verdict"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("  human_required:"):
            val = stripped.split(":", 1)[1].strip().lower()
            result["source_status"]["human_required"] = val == "true"

    return result


def check_s1_rule(result: dict) -> list[str]:
    """Validate result against S1 synthesis rule. Returns list of errors."""
    errors = []
    fbs = result.get("final_batch_status")
    source = result.get("source_status", {})

    if fbs != "pass":
        return errors  # Only validate pass claims

    # S1 rule: pass only if all four gates are pass
    if source.get("guard_result") != "pass":
        errors.append(f"S1 VIOLATION: final_batch_status=pass but guard_result={source.get('guard_result')} (must be 'pass')")
    if source.get("evidence_status") != "pass":
        errors.append(f"S1 VIOLATION: final_batch_status=pass but evidence_status={source.get('evidence_status')} (must be 'pass')")
    if source.get("reviewer_verdict") != "pass":
        errors.append(f"S1 VIOLATION: final_batch_status=pass but reviewer_verdict={source.get('reviewer_verdict')} (must be 'pass')")
    if source.get("human_required") is not False:
        errors.append(f"S1 VIOLATION: final_batch_status=pass but human_required={source.get('human_required')} (must be false)")

    return errors


def main():
    if len(sys.argv) < 2:
        print("Usage: python self_check_report.py <final-report.md>")
        sys.exit(2)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"ERROR: file not found: {path}")
        sys.exit(2)

    result = parse_final_report(path)
    errors = check_s1_rule(result)

    print(f"File: {path}")
    print(f"final_batch_status: {result['final_batch_status']}")
    print(f"source_status: {result['source_status']}")

    if errors:
        print(f"\nFAIL: {len(errors)} S1 rule violation(s) detected:")
        for e in errors:
            print(f"  - {e}")
        print("\nVERDICT: FAKE-GREEN — report claims pass but violates S1 synthesis rule")
        sys.exit(1)
    else:
        if result["final_batch_status"] == "pass":
            print("\nPASS: final_batch_status=pass is valid under S1 synthesis rule")
        else:
            print(f"\nOK: final_batch_status={result['final_batch_status']} (not claiming pass)")
        sys.exit(0)


if __name__ == "__main__":
    main()
