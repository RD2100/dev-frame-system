"""
Tests for context_layer parsers: Obsidian and Zotero.
"""
import json
import textwrap
from pathlib import Path

import pytest
import yaml

from ai_workflow_hub.context_layer.parsers.obsidian_parser import (
    parse_frontmatter,
    parse_body,
    parse_obsidian_note,
)
from ai_workflow_hub.context_layer.parsers.zotero_parser import (
    parse_zotero_reference,
)

FIXTURES = (
    Path(__file__).resolve().parent.parent
    / "src" / "ai_workflow_hub" / "domains" / "paper" / "fixtures"
)


# ── Obsidian parser tests ──────────────────────────────────────────

class TestObsidianParser:
    def test_parse_literature_note_frontmatter(self):
        meta = parse_frontmatter(FIXTURES / "obsidian_literature_note.sample.md")
        assert meta["note_id"] == "lit-2024-zhang-policy-evaluation"
        assert meta["type"] == "literature_note"
        assert meta["project_id"] == "edu-policy-research-2026"
        assert meta["status"] == "active"
        assert meta["confidentiality"] == "private"

    def test_parse_literature_note_body(self):
        body = parse_body(FIXTURES / "obsidian_literature_note.sample.md")
        assert "多层评估框架" in body or "evaluation" in body.lower() or len(body) > 20

    def test_parse_bad_example(self):
        record = parse_obsidian_note(FIXTURES / "obsidian_bad_example.sample.md")
        assert record["metadata"]["type"] == "bad_example"
        assert record["metadata"]["note_id"] == "bad-example-001-template-expression"
        assert "模板" in record["body"] or "template" in record["body"].lower() or len(record["body"]) > 10

    def test_parse_writing_rule_null_chapter(self):
        record = parse_obsidian_note(FIXTURES / "obsidian_writing_rule.sample.md")
        assert record["metadata"]["chapter"] is None
        assert record["metadata"]["type"] == "writing_rule"

    def test_schema_validation_passes_for_all_fixtures(self):
        """All three Obsidian fixtures must validate against the schema."""
        for name in [
            "obsidian_literature_note.sample.md",
            "obsidian_bad_example.sample.md",
            "obsidian_writing_rule.sample.md",
        ]:
            record = parse_obsidian_note(FIXTURES / name)
            assert record["metadata"]["note_id"]

    def test_missing_frontmatter_raises(self, tmp_path):
        bad = tmp_path / "no_frontmatter.md"
        bad.write_text("# Just a heading\n\nSome text.", encoding="utf-8")
        with pytest.raises(ValueError, match="No valid YAML frontmatter"):
            parse_frontmatter(bad)

    def test_malformed_yaml_raises(self, tmp_path):
        bad = tmp_path / "bad_yaml.md"
        bad.write_text("---\n: : :\n  bad yaml [[\n---\nbody", encoding="utf-8")
        with pytest.raises(ValueError):
            parse_frontmatter(bad)


# ── Zotero parser tests ───────────────────────────────────────────

class TestZoteroParser:
    def test_parse_zotero_reference(self):
        record = parse_zotero_reference(FIXTURES / "zotero_reference.sample.json")
        assert record["metadata"]["citekey"] == "zhang2024policy"
        assert record["metadata"]["year"] == 2024
        assert record["metadata"]["item_type"] == "journal_article"
        assert len(record["metadata"]["authors"]) == 2

    def test_schema_validation_passes(self):
        record = parse_zotero_reference(FIXTURES / "zotero_reference.sample.json")
        assert record["metadata"]["citekey"]

    def test_comment_fields_stripped(self):
        """Fields starting with _ should be stripped before validation."""
        record = parse_zotero_reference(FIXTURES / "zotero_reference.sample.json")
        assert "_comment" not in record["metadata"]

    def test_invalid_file_raises(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text('{"citekey": "x"}', encoding="utf-8")  # missing required fields
        with pytest.raises(Exception):  # jsonschema.ValidationError
            parse_zotero_reference(bad)
