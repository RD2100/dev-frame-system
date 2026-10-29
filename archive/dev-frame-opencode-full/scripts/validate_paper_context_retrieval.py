"""
A3 Validation Script: Paper Context Retrieval MVP
Validates the full pipeline: fixtures -> parsers -> privacy -> retrieval -> context pack
"""
import json
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_workflow_hub.context_layer.builders.paper_context_pack_builder import (
    build_from_fixtures,
    FIXTURES_DIR,
    _load_schema,
)

import jsonschema


def main():
    print("=" * 60)
    print("A3 Validation: Paper Context Retrieval MVP")
    print("=" * 60)

    checks = []

    # 1. Build from fixtures (with retrieval)
    print("\n[1] Building context pack from fixtures with retrieval...")
    output_path = FIXTURES_DIR / "generated" / "paper_context_pack.generated.json"
    try:
        pack = build_from_fixtures(output_path=output_path, top_k=5)
        checks.append(("Build from fixtures (with retrieval)", True, ""))
    except Exception as e:
        checks.append(("Build from fixtures (with retrieval)", False, str(e)))
        _print_results(checks)
        return 1

    # 2. Schema validation
    print("[2] Validating against paper_context_pack.schema.json...")
    try:
        schema = _load_schema()
        jsonschema.validate(instance=pack, schema=schema)
        checks.append(("Schema validation", True, ""))
    except jsonschema.ValidationError as e:
        checks.append(("Schema validation", False, e.message))
        _print_results(checks)
        return 1

    # 3. Retrieval trace present
    print("[3] Checking retrieval_trace presence...")
    has_trace = "retrieval_trace" in pack
    trace = pack.get("retrieval_trace", {})
    checks.append(("retrieval_trace present", has_trace, f"keys: {list(trace.keys())}"))

    # 4. Pipeline stages in trace
    print("[4] Checking pipeline stages in retrieval_trace...")
    pipeline = trace.get("pipeline", {})
    stages = ["privacy_filter", "metadata_filter", "keyword_scoring", "topk_selection"]
    has_all_stages = all(s in pipeline for s in stages)
    checks.append(("Pipeline stages complete", has_all_stages,
                    f"found: {list(pipeline.keys())}"))

    # 5. Source manifest has retrieval scores
    print("[5] Checking source_manifest retrieval scores...")
    manifest = pack.get("source_manifest", [])
    all_have_scores = all(
        "retrieval_score" in entry and "retrieval_method" in entry
        for entry in manifest
    )
    checks.append(("source_manifest has retrieval scores", all_have_scores,
                    f"entries: {len(manifest)}"))

    # 6. Keywords extracted
    print("[6] Checking keyword extraction...")
    keywords = pipeline.get("keyword_scoring", {}).get("keywords_extracted", [])
    checks.append(("Keywords extracted", len(keywords) > 0,
                    f"count: {len(keywords)}, sample: {keywords[:5]}"))

    # 7. Privacy filter still works
    print("[7] Checking privacy filter integration...")
    privacy = pack.get("privacy_filter_result", {})
    checks.append(("Privacy filter passed", privacy.get("passed") is True,
                    f"excluded: {privacy.get('excluded_sources', [])}"))

    # 8. Content fields populated
    print("[8] Checking content field population...")
    content_ok = (
        len(pack.get("writing_rules", [])) >= 1
        and len(pack.get("retrieved_literature", [])) >= 1
        and len(pack.get("retrieved_bad_examples", [])) >= 1
    )
    checks.append(("Content fields populated", content_ok,
                    f"rules={len(pack.get('writing_rules', []))}, "
                    f"lit={len(pack.get('retrieved_literature', []))}, "
                    f"bad={len(pack.get('retrieved_bad_examples', []))}"))

    # 9. Generated file written and re-validates
    print("[9] Re-validating written file...")
    if output_path.exists():
        written = json.loads(output_path.read_text(encoding="utf-8"))
        try:
            jsonschema.validate(instance=written, schema=schema)
            checks.append(("Generated file re-validates", True, ""))
        except jsonschema.ValidationError as e:
            checks.append(("Generated file re-validates", False, e.message))
    else:
        checks.append(("Generated file exists", False, f"not found: {output_path}"))

    # 10. Retrieval trace selected_entries structure
    print("[10] Checking retrieval_trace entry structure...")
    selected_entries = trace.get("selected_entries", [])
    rejected_entries = trace.get("rejected_entries", [])
    entry_ok = all(
        "source_id" in e and "final_score" in e and "reason" in e
        for e in selected_entries
    ) if selected_entries else True
    checks.append(("Trace entry structure valid", entry_ok,
                    f"selected: {len(selected_entries)}, rejected: {len(rejected_entries)}"))

    # Print results
    return _print_results(checks)


def _print_results(checks):
    print("\n" + "=" * 60)
    print("VALIDATION RESULTS")
    print("=" * 60)
    passed = 0
    failed = 0
    for name, ok, detail in checks:
        status = "[PASS]" if ok else "[FAIL]"
        line = f"  {status} {name}"
        if detail:
            line += f"  ({detail})"
        print(line)
        if ok:
            passed += 1
        else:
            failed += 1

    total = passed + failed
    print(f"\nResult: {passed}/{total} checks passed, {failed} failed")
    if failed == 0:
        print("ALL CHECKS PASSED")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
