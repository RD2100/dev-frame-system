"""
Paper Context Pack Builder (A4 — with Vault Integration)
Assembles parsed Obsidian notes + Zotero/BibTeX references into a PaperContextPack.
Uses retrieval pipeline (metadata filter → keyword search → scoring → top-k)
to select only the most relevant sources for the context pack.
Validates output against paper_context_pack.schema.json.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from ai_workflow_hub.context_layer.parsers.obsidian_parser import parse_obsidian_note
from ai_workflow_hub.context_layer.parsers.zotero_parser import parse_zotero_reference
from ai_workflow_hub.context_layer.parsers.bibtex_parser import parse_bibtex_file
from ai_workflow_hub.context_layer.privacy.privacy_filter import filter_sources
from ai_workflow_hub.context_layer.retrieval.retriever import (
    retrieve_sources,
    RetrievalResult,
)
from ai_workflow_hub.context_layer.sources.vault_scanner import (
    scan_vault,
    scan_bibtex_files,
)
from ai_workflow_hub.context_layer.sources.source_cache import (
    load_cache,
    save_cache,
    update_cache,
)

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "domains" / "paper" / "contracts" / "paper_context_pack.schema.json"
)

FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "domains" / "paper" / "fixtures"
)


def _load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _note_type_to_field(note_type: str) -> str | None:
    """Map an Obsidian note type to the corresponding context pack field."""
    mapping = {
        "writing_rule": "writing_rules",
        "literature_note": "retrieved_literature",
        "bad_example": "retrieved_bad_examples",
        "style_example": "retrieved_style_examples",
        "revision_history": "retrieved_revision_history",
        "project_memory": "project_memory",
    }
    return mapping.get(note_type)


def _build_writing_rule_entry(record: dict[str, Any]) -> dict[str, Any]:
    """Convert a writing_rule note into a context pack entry."""
    meta = record["metadata"]
    body = record.get("body", "").strip()
    return {
        "rule_id": meta["note_id"],
        "content": body[:500],
    }


def _build_literature_entry(record: dict[str, Any], zotero_map: dict[str, Any]) -> dict[str, Any]:
    """Convert a literature_note into a context pack entry, enriching with Zotero data."""
    meta = record["metadata"]
    note_id = meta["note_id"]
    body = record.get("body", "").strip()

    citekey = None
    for key, ref in zotero_map.items():
        if key in body or key in note_id:
            citekey = key
            break

    entry: dict[str, Any] = {
        "note_id": note_id,
        "summary": body[:300],
    }
    if citekey and citekey in zotero_map:
        zref = zotero_map[citekey]["metadata"]
        entry["citekey"] = citekey
        entry["title"] = zref.get("title", "")
        entry["relevance"] = body[:150]
    return entry


def _build_bad_example_entry(record: dict[str, Any]) -> dict[str, Any]:
    """Convert a bad_example note into a context pack entry."""
    meta = record["metadata"]
    body = record.get("body", "").strip()
    return {
        "note_id": meta["note_id"],
        "summary": body[:300],
    }


def build_context_pack(
    task_spec_path: str | Path,
    obsidian_paths: list[str | Path],
    zotero_paths: list[str | Path],
    top_k: int = 5,
) -> dict[str, Any]:
    """Build a PaperContextPack with retrieval-based source selection.

    Steps:
        1. Parse task spec (YAML)
        2. Parse all Obsidian notes
        3. Parse all Zotero references
        4. Run retrieval pipeline (privacy → metadata → keyword → top-k)
        5. Populate context pack from SELECTED (top-k) sources only
        6. Attach retrieval_trace for evidence
        7. Validate against paper_context_pack.schema.json

    Args:
        task_spec_path: Path to the task spec YAML file.
        obsidian_paths: List of paths to Obsidian .md files.
        zotero_paths: List of paths to Zotero .json files.
        top_k: Maximum number of sources to include in the pack.

    Returns:
        Validated context pack dict.

    Raises:
        jsonschema.ValidationError if the generated pack fails schema validation.
    """
    # 1. Parse task spec
    task_spec_raw = yaml.safe_load(Path(task_spec_path).read_text(encoding="utf-8"))
    task_id = task_spec_raw.get("task_id", "unknown-task")

    # 2. Parse Obsidian notes
    obsidian_records = [parse_obsidian_note(p) for p in obsidian_paths]

    # 3. Parse Zotero references
    zotero_records = [parse_zotero_reference(p) for p in zotero_paths]

    # 4. Run retrieval pipeline
    retrieval_result = retrieve_sources(
        task_spec=task_spec_raw,
        obsidian_records=obsidian_records,
        zotero_records=zotero_records,
        k=top_k,
    )

    selected_obsidian = retrieval_result.selected_obsidian
    selected_zotero = retrieval_result.selected_zotero

    # Build Zotero lookup by citekey (from selected only)
    zotero_map: dict[str, dict[str, Any]] = {}
    for rec in selected_zotero:
        citekey = rec["metadata"].get("citekey", "")
        if citekey:
            zotero_map[citekey] = rec

    # 5. Build context pack from SELECTED sources only
    pack: dict[str, Any] = {
        "pack_id": f"cp-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{task_id}",
        "task_id": task_id,
        "project_memory": [],
        "task_summary": task_spec_raw.get("section", ""),
        "chapter_function": task_spec_raw.get("chapter", ""),
        "writing_rules": [],
        "forbidden_patterns": [],
        "retrieved_literature": [],
        "retrieved_style_examples": [],
        "retrieved_bad_examples": [],
        "retrieved_revision_history": [],
        "privacy_filter_result": {
            "passed": retrieval_result.privacy_result["passed"],
            "excluded_sources": retrieval_result.privacy_result["excluded_sources"],
        },
        "allowed_model_inputs": [],
        "excluded_sensitive_sources": retrieval_result.privacy_result["excluded_sensitive_sources"],
        "source_manifest": retrieval_result.source_manifest_entries,
        "retrieval_trace": retrieval_result.retrieval_trace,
    }

    # Populate from selected Obsidian notes only
    for record in selected_obsidian:
        note_type = record["metadata"].get("type", "")
        field = _note_type_to_field(note_type)
        if not field:
            continue

        if field == "writing_rules":
            pack[field].append(_build_writing_rule_entry(record))
        elif field == "retrieved_literature":
            pack[field].append(_build_literature_entry(record, zotero_map))
        elif field == "retrieved_bad_examples":
            pack[field].append(_build_bad_example_entry(record))
        elif field == "retrieved_style_examples":
            pack[field].append({"note_id": record["metadata"]["note_id"], "summary": record.get("body", "")[:300]})
        elif field == "retrieved_revision_history":
            pack[field].append({"note_id": record["metadata"]["note_id"], "summary": record.get("body", "")[:300]})
        elif field == "project_memory":
            pack[field].append({"type": "note", "content": record.get("body", "")[:300]})

    # Build allowed_model_inputs list
    allowed_fields = []
    for field_name in [
        "project_memory", "task_summary", "chapter_function",
        "writing_rules", "retrieved_literature",
        "retrieved_bad_examples", "retrieved_style_examples",
        "retrieved_revision_history",
    ]:
        val = pack.get(field_name)
        if val:
            allowed_fields.append(field_name)
    pack["allowed_model_inputs"] = allowed_fields

    # Add forbidden_patterns from bad_examples
    for entry in pack["retrieved_bad_examples"]:
        pack["forbidden_patterns"].append({
            "pattern_id": entry.get("note_id", "unknown"),
            "content": entry.get("summary", "")[:200],
        })

    # 6. Validate against schema
    schema = _load_schema()
    jsonschema.validate(instance=pack, schema=schema)

    return pack


def build_from_fixtures(
    output_path: str | Path | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """Convenience: build a context pack from the default A1 fixtures.

    If output_path is given, writes the result as JSON.
    """
    task_spec = FIXTURES_DIR / "paper_task_spec.sample.yaml"

    obsidian_paths = [
        FIXTURES_DIR / "obsidian_literature_note.sample.md",
        FIXTURES_DIR / "obsidian_bad_example.sample.md",
        FIXTURES_DIR / "obsidian_writing_rule.sample.md",
    ]

    zotero_paths = [
        FIXTURES_DIR / "zotero_reference.sample.json",
    ]

    pack = build_context_pack(task_spec, obsidian_paths, zotero_paths, top_k=top_k)

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")

    return pack


def build_from_vault(
    task_spec_path: str | Path,
    vault_dir: str | Path,
    bibtex_path: str | Path | None = None,
    top_k: int = 5,
    cache_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build a PaperContextPack from an Obsidian vault directory and optional BibTeX file.

    This is the A4 entry point: auto-discovers sources from a vault directory
    and BibTeX file, then feeds them into the A3 retrieval pipeline.

    Steps:
        1. Scan vault directory for .md files with valid frontmatter
        2. Parse BibTeX file if provided
        3. Optionally update source cache (if cache_path given)
        4. Parse all discovered sources
        5. Run retrieval pipeline (privacy → metadata → keyword → top-k)
        6. Build and validate context pack

    Args:
        task_spec_path: Path to the task spec YAML file.
        vault_dir: Path to the Obsidian vault directory.
        bibtex_path: Optional path to a .bib file.
        top_k: Maximum number of sources to include.
        cache_path: Optional path for source cache JSON file.

    Returns:
        Validated context pack dict.
    """
    # 1. Scan vault
    vault_discovered = scan_vault(vault_dir)

    # 2. Parse BibTeX if provided
    bibtex_records: list[dict[str, Any]] = []
    bibtex_discovered: list[dict[str, Any]] = []
    if bibtex_path:
        bibtex_discovered = scan_bibtex_files(bibtex_path)
        bibtex_records = [
            {"metadata": d["metadata"], "source_path": d["source_path"]}
            for d in bibtex_discovered
        ]

    # 3. Update source cache if requested
    if cache_path:
        cache = load_cache(cache_path)
        cache = update_cache(cache, vault_discovered, source_kind="obsidian")
        if bibtex_discovered:
            cache = update_cache(cache, bibtex_discovered, source_kind="bibtex")
        save_cache(cache, cache_path)

    # 4. Parse all discovered Obsidian notes
    obsidian_records = []
    for item in vault_discovered:
        try:
            record = parse_obsidian_note(item["path"])
            obsidian_records.append(record)
        except (ValueError, jsonschema.ValidationError):
            # Skip notes that fail validation
            continue

    # 5. Parse task spec and run retrieval
    task_spec_raw = yaml.safe_load(Path(task_spec_path).read_text(encoding="utf-8"))

    retrieval_result = retrieve_sources(
        task_spec=task_spec_raw,
        obsidian_records=obsidian_records,
        zotero_records=bibtex_records,
        k=top_k,
    )

    selected_obsidian = retrieval_result.selected_obsidian
    selected_zotero = retrieval_result.selected_zotero

    # Build Zotero lookup by citekey
    zotero_map: dict[str, dict[str, Any]] = {}
    for rec in selected_zotero:
        citekey = rec["metadata"].get("citekey", "")
        if citekey:
            zotero_map[citekey] = rec

    # 6. Build context pack
    task_id = task_spec_raw.get("task_id", "unknown-task")
    pack: dict[str, Any] = {
        "pack_id": f"cp-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{task_id}",
        "task_id": task_id,
        "project_memory": [],
        "task_summary": task_spec_raw.get("section", ""),
        "chapter_function": task_spec_raw.get("chapter", ""),
        "writing_rules": [],
        "forbidden_patterns": [],
        "retrieved_literature": [],
        "retrieved_style_examples": [],
        "retrieved_bad_examples": [],
        "retrieved_revision_history": [],
        "privacy_filter_result": {
            "passed": retrieval_result.privacy_result["passed"],
            "excluded_sources": retrieval_result.privacy_result["excluded_sources"],
        },
        "allowed_model_inputs": [],
        "excluded_sensitive_sources": retrieval_result.privacy_result["excluded_sensitive_sources"],
        "source_manifest": retrieval_result.source_manifest_entries,
        "retrieval_trace": retrieval_result.retrieval_trace,
    }

    # Populate from selected sources
    for record in selected_obsidian:
        note_type = record["metadata"].get("type", "")
        field_name = _note_type_to_field(note_type)
        if not field_name:
            continue

        if field_name == "writing_rules":
            pack[field_name].append(_build_writing_rule_entry(record))
        elif field_name == "retrieved_literature":
            pack[field_name].append(_build_literature_entry(record, zotero_map))
        elif field_name == "retrieved_bad_examples":
            pack[field_name].append(_build_bad_example_entry(record))
        elif field_name == "retrieved_style_examples":
            pack[field_name].append({"note_id": record["metadata"]["note_id"], "summary": record.get("body", "")[:300]})
        elif field_name == "retrieved_revision_history":
            pack[field_name].append({"note_id": record["metadata"]["note_id"], "summary": record.get("body", "")[:300]})
        elif field_name == "project_memory":
            pack[field_name].append({"type": "note", "content": record.get("body", "")[:300]})

    # Build allowed_model_inputs list
    allowed_fields = []
    for fn in [
        "project_memory", "task_summary", "chapter_function",
        "writing_rules", "retrieved_literature",
        "retrieved_bad_examples", "retrieved_style_examples",
        "retrieved_revision_history",
    ]:
        if pack.get(fn):
            allowed_fields.append(fn)
    pack["allowed_model_inputs"] = allowed_fields

    # Add forbidden_patterns from bad_examples
    for entry in pack["retrieved_bad_examples"]:
        pack["forbidden_patterns"].append({
            "pattern_id": entry.get("note_id", "unknown"),
            "content": entry.get("summary", "")[:200],
        })

    # Add vault scan metadata to retrieval_trace
    pack["retrieval_trace"]["vault_scan"] = {
        "vault_dir": str(vault_dir),
        "total_discovered": len(vault_discovered),
        "total_bibtex": len(bibtex_records),
    }

    # 7. Validate against schema
    schema = _load_schema()
    jsonschema.validate(instance=pack, schema=schema)

    return pack
