#!/usr/bin/env python3
"""
Validation script for A4: Source Integration MVP
Runs 12 checks covering BibTeX parsing, vault scanning, source cache,
build_from_vault, rejection fixtures, and schema validation.
"""
import json
import sys
import tempfile
from pathlib import Path

# Setup path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ai-workflow-hub" / "src"))

FIXTURES = ROOT / "ai-workflow-hub" / "src" / "ai_workflow_hub" / "domains" / "paper" / "fixtures"
MINI_VAULT = FIXTURES / "mini_vault"
BIBTEX = FIXTURES / "bibtex_references.sample.bib"
TASK_SPEC_A4 = FIXTURES / "paper_task_a4.sample.yaml"

passed = 0
failed = 0
checks = []


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        status = "PASS"
    else:
        failed += 1
        status = "FAIL"
    checks.append((name, status, detail))
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


print("=" * 60)
print("A4 Source Integration Validation")
print("=" * 60)

# 1. BibTeX parser
print("\n1. BibTeX Parser")
from ai_workflow_hub.context_layer.parsers.bibtex_parser import parse_bibtex_file
records = parse_bibtex_file(BIBTEX)
check("BibTeX parses 8 entries", len(records) == 8, f"got {len(records)}")
check("BibTeX records have metadata+source_path",
      all("metadata" in r and "source_path" in r for r in records))

# 2. BibTeX entry types
item_types = {r["metadata"]["citekey"]: r["metadata"]["item_type"] for r in records}
check("BibTeX type mapping correct",
      item_types.get("Smith2023ContextRetrieval") == "journal_article"
      and item_types.get("Johnson2022ResearchMethods") == "book"
      and item_types.get("Lee2021MetadataScoring") == "thesis")

# 3. Vault scanner
print("\n2. Vault Scanner")
from ai_workflow_hub.context_layer.sources.vault_scanner import scan_vault
vault_results = scan_vault(MINI_VAULT)
check("Vault scan finds 8 files (excl. sensitive)",
      len(vault_results) == 8, f"got {len(vault_results)}")
check("Vault scan excludes sensitive",
      not any("sensitive" in r["relative_path"].lower() for r in vault_results))

# 4. Source cache
print("\n3. Source Cache")
from ai_workflow_hub.context_layer.sources.source_cache import (
    load_cache, save_cache, update_cache, cache_stats,
)
with tempfile.TemporaryDirectory() as tmpdir:
    cp = Path(tmpdir) / "cache.json"
    cache = load_cache(cp)
    cache = update_cache(cache, vault_results, source_kind="obsidian")
    save_cache(cache, cp)
    stats = cache_stats(cache)
    check("Source cache saves/loads correctly", cp.exists())
    check("Source cache has 8 obsidian sources",
          stats["by_kind"].get("obsidian", 0) == 8, f"got {stats}")

# 5. build_from_vault
print("\n4. build_from_vault Integration")
from ai_workflow_hub.context_layer.builders.paper_context_pack_builder import build_from_vault
pack = build_from_vault(
    task_spec_path=TASK_SPEC_A4,
    vault_dir=MINI_VAULT,
    bibtex_path=BIBTEX,
    top_k=5,
)
check("build_from_vault returns valid pack", pack is not None and "pack_id" in pack)
check("Pack has retrieval_trace with vault_scan",
      "retrieval_trace" in pack and "vault_scan" in pack["retrieval_trace"])
check("Pack source_manifest has scores",
      all("retrieval_score" in e for e in pack["source_manifest"]))

# 6. Privacy filter
manifest_ids = [e["source_id"] for e in pack["source_manifest"]]
check("Sensitive source excluded from manifest",
      "sensitive-reviewer-notes" not in manifest_ids)

# 7. Rejection fixture (top_k=3)
print("\n5. Rejection Fixture")
pack_reject = build_from_vault(
    task_spec_path=TASK_SPEC_A4,
    vault_dir=MINI_VAULT,
    bibtex_path=BIBTEX,
    top_k=3,
)
trace = pack_reject["retrieval_trace"]
check("Top-k=3 produces rejections",
      trace["total_rejected"] > 0, f"rejected={trace['total_rejected']}")
check("Trace has rejected_entries list",
      len(trace.get("rejected_entries", [])) > 0)

# 8. Schema validation (already implicit if build_from_vault returned)
print("\n6. Schema Validation")
import jsonschema
schema = json.loads(
    (FIXTURES.parent / "contracts" / "paper_context_pack.schema.json").read_text(encoding="utf-8")
)
try:
    jsonschema.validate(instance=pack, schema=schema)
    check("Generated pack validates against schema", True)
except jsonschema.ValidationError as e:
    check("Generated pack validates against schema", False, str(e)[:100])

# Summary
print("\n" + "=" * 60)
print(f"Results: {passed}/{passed+failed} passed, {failed} failed")
print("=" * 60)

sys.exit(0 if failed == 0 else 1)
