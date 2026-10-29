#!/usr/bin/env python3
"""
Validation script for PAPER-CONTEXT-INGEST-MVP-A2.

Runs the full ingest pipeline on fixture data:
  1. Parse Obsidian fixtures
  2. Parse Zotero fixtures
  3. Apply privacy filter
  4. Build context pack
  5. Validate output against schema

Exit code 0 = all pass, non-zero = failure.
"""
import json
import sys
from pathlib import Path

# Ensure the project src is on sys.path
SRC = Path(__file__).resolve().parent.parent / "ai-workflow-hub" / "src"
sys.path.insert(0, str(SRC))

from ai_workflow_hub.context_layer.builders.paper_context_pack_builder import (
    build_from_fixtures,
    FIXTURES_DIR,
)

OUTPUT_PATH = FIXTURES_DIR / "generated" / "paper_context_pack.generated.json"


def main() -> int:
    print("=" * 60)
    print("PAPER-CONTEXT-INGEST-MVP-A2  Validation")
    print("=" * 60)

    # Step 1 – build from fixtures (internally validates against schema)
    print("\n[1/3] Building context pack from fixtures …")
    try:
        pack = build_from_fixtures(output_path=OUTPUT_PATH)
    except Exception as exc:
        print(f"FAIL – build_from_fixtures raised: {exc}")
        return 1
    print("  [PASS] Context pack built and validated against schema")
    print(f"  [PASS] Written to {OUTPUT_PATH}")

    # Step 2 – quick sanity checks
    print("\n[2/3] Sanity checks …")
    checks_passed = True

    # source_manifest non-empty
    if pack.get("source_manifest"):
        print(f"  [PASS] source_manifest has {len(pack['source_manifest'])} entries")
    else:
        print("  [FAIL] source_manifest is empty")
        checks_passed = False

    # privacy_filter_result.passed is True
    pfr = pack.get("privacy_filter_result", {})
    if pfr.get("passed"):
        print(f"  [PASS] privacy_filter_result.passed = True")
    else:
        print("  [FAIL] privacy_filter_result.passed is not True")
        checks_passed = False

    # At least one retrieved_literature entry
    if pack.get("retrieved_literature"):
        print(f"  [PASS] retrieved_literature has {len(pack['retrieved_literature'])} entries")
    else:
        print("  [FAIL] retrieved_literature is empty")
        checks_passed = False

    # At least one writing_rule
    if pack.get("writing_rules"):
        print(f"  [PASS] writing_rules has {len(pack['writing_rules'])} entries")
    else:
        print("  [FAIL] writing_rules is empty")
        checks_passed = False

    # At least one bad_example
    if pack.get("retrieved_bad_examples"):
        print(f"  [PASS] retrieved_bad_examples has {len(pack['retrieved_bad_examples'])} entries")
    else:
        print("  [FAIL] retrieved_bad_examples is empty")
        checks_passed = False

    # excluded_sensitive_sources should be empty for our fixtures (none are sensitive)
    if not pack.get("excluded_sensitive_sources"):
        print("  [PASS] excluded_sensitive_sources is empty (no sensitive fixtures)")
    else:
        print(f"  [WARN] excluded_sensitive_sources: {pack['excluded_sensitive_sources']}")

    if not checks_passed:
        print("\nFAIL – some sanity checks failed")
        return 1

    # Step 3 – re-read and re-validate the written file
    print("\n[3/3] Re-validating written JSON file …")
    from ai_workflow_hub.context_layer.builders.paper_context_pack_builder import _load_schema
    import jsonschema

    written = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    schema = _load_schema()
    try:
        jsonschema.validate(instance=written, schema=schema)
        print("  [PASS] Written file passes schema validation")
    except jsonschema.ValidationError as exc:
        print(f"  [FAIL] Schema validation failed: {exc.message}")
        return 1

    print("\n" + "=" * 60)
    print("ALL CHECKS PASSED")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
