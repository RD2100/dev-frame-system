"""
Tests for the Paper Context Pack Builder and Privacy Filter.
"""
import json
from pathlib import Path

import pytest
import jsonschema

from ai_workflow_hub.context_layer.builders.paper_context_pack_builder import (
    build_context_pack,
    build_from_fixtures,
    FIXTURES_DIR,
)
from ai_workflow_hub.context_layer.privacy.privacy_filter import (
    classify_source,
    filter_sources,
)


# ── Privacy filter tests ──────────────────────────────────────────

class TestPrivacyFilter:
    def test_public_allowed(self):
        src = {"metadata": {"confidentiality": "public", "note_id": "n1"}, "body": "ok"}
        result = classify_source(src)
        assert result["allowed"] is True

    def test_private_allowed(self):
        src = {"metadata": {"confidentiality": "private", "note_id": "n2"}, "body": "ok"}
        result = classify_source(src)
        assert result["allowed"] is True

    def test_sensitive_blocked(self):
        src = {"metadata": {"confidentiality": "sensitive", "note_id": "n3"}, "body": "secret"}
        result = classify_source(src)
        assert result["allowed"] is False
        assert "sensitive" in result["reason"]

    def test_missing_confidentiality_fail_closed(self):
        src = {"metadata": {"note_id": "n4"}, "body": "no conf field"}
        result = classify_source(src)
        assert result["allowed"] is False
        assert "fail-closed" in result["reason"]

    def test_unknown_confidentiality_fail_closed(self):
        src = {"metadata": {"confidentiality": "top_secret", "note_id": "n5"}, "body": "x"}
        result = classify_source(src)
        assert result["allowed"] is False

    def test_filter_sources_excludes_sensitive(self):
        obs = [
            {"metadata": {"note_id": "pub1", "type": "literature_note", "confidentiality": "public"}, "body": "ok"},
            {"metadata": {"note_id": "sens1", "type": "literature_note", "confidentiality": "sensitive"}, "body": "secret"},
        ]
        zot = [
            {"metadata": {"citekey": "ref1", "confidentiality": "public"}, "source_path": "x"},
        ]
        result = filter_sources(obs, zot)
        assert result["passed"] is True
        assert len(result["allowed_obsidian"]) == 1
        assert len(result["allowed_zotero"]) == 1
        assert "sens1" in result["excluded_sources"]
        assert "sens1" in result["excluded_sensitive_sources"]

    def test_filter_sources_all_excluded(self):
        obs = [
            {"metadata": {"note_id": "s1", "confidentiality": "sensitive"}, "body": "x"},
        ]
        result = filter_sources(obs, [])
        assert result["passed"] is False


# ── Context Pack Builder tests ────────────────────────────────────

class TestContextPackBuilder:
    def test_build_from_fixtures(self):
        """Build from default fixtures — should not raise."""
        pack = build_from_fixtures()
        assert pack["task_id"]
        assert pack["pack_id"]

    def test_schema_validation(self):
        """Generated pack must validate against paper_context_pack.schema.json."""
        pack = build_from_fixtures()
        from ai_workflow_hub.context_layer.builders.paper_context_pack_builder import _load_schema
        schema = _load_schema()
        jsonschema.validate(instance=pack, schema=schema)

    def test_source_manifest_not_empty(self):
        pack = build_from_fixtures()
        assert len(pack["source_manifest"]) > 0

    def test_writing_rules_populated(self):
        pack = build_from_fixtures()
        assert len(pack["writing_rules"]) >= 1

    def test_retrieved_literature_populated(self):
        pack = build_from_fixtures()
        assert len(pack["retrieved_literature"]) >= 1

    def test_retrieved_bad_examples_populated(self):
        pack = build_from_fixtures()
        assert len(pack["retrieved_bad_examples"]) >= 1

    def test_privacy_filter_passed(self):
        pack = build_from_fixtures()
        assert pack["privacy_filter_result"]["passed"] is True

    def test_no_sensitive_sources_in_fixtures(self):
        """Our sample fixtures have no 'sensitive' items."""
        pack = build_from_fixtures()
        assert len(pack["excluded_sensitive_sources"]) == 0

    def test_generated_file_validates(self, tmp_path):
        """Write to file and re-validate."""
        out = tmp_path / "test_pack.json"
        pack = build_from_fixtures(output_path=out)
        assert out.exists()

        written = json.loads(out.read_text(encoding="utf-8"))
        from ai_workflow_hub.context_layer.builders.paper_context_pack_builder import _load_schema
        jsonschema.validate(instance=written, schema=_load_schema())

    def test_sensitive_obsidian_excluded_from_pack(self, tmp_path):
        """A sensitive Obsidian note should be excluded from the pack."""
        # Create a sensitive fixture
        sensitive_md = tmp_path / "sensitive_note.md"
        sensitive_md.write_text(
            "---\n"
            "note_id: sens-001\n"
            "type: literature_note\n"
            "project_id: test\n"
            "status: active\n"
            "confidentiality: sensitive\n"
            "---\n\nSecret content\n",
            encoding="utf-8",
        )

        task_spec = FIXTURES_DIR / "paper_task_spec.sample.yaml"
        obsidian_paths = [sensitive_md]
        zotero_paths = [FIXTURES_DIR / "zotero_reference.sample.json"]

        pack = build_context_pack(task_spec, obsidian_paths, zotero_paths)
        assert "sens-001" in pack["excluded_sensitive_sources"]
        assert "sens-001" in pack["privacy_filter_result"]["excluded_sources"]
        # Should not appear in retrieved_literature
        lit_ids = [e.get("note_id") or e.get("citekey") for e in pack["retrieved_literature"]]
        assert "sens-001" not in lit_ids


# ── A3 Retrieval Integration Tests ─────────────────────────────────

class TestRetrievalIntegration:
    """Tests verifying the builder integrates retrieval correctly."""

    def test_retrieval_trace_present(self):
        """Generated pack must contain retrieval_trace."""
        pack = build_from_fixtures()
        assert "retrieval_trace" in pack
        trace = pack["retrieval_trace"]
        assert trace["total_candidates"] > 0
        assert trace["total_selected"] > 0

    def test_retrieval_trace_has_pipeline(self):
        """retrieval_trace must include pipeline stages."""
        pack = build_from_fixtures()
        pipeline = pack["retrieval_trace"]["pipeline"]
        assert "privacy_filter" in pipeline
        assert "metadata_filter" in pipeline
        assert "keyword_scoring" in pipeline
        assert "topk_selection" in pipeline

    def test_source_manifest_has_retrieval_scores(self):
        """source_manifest entries must include retrieval_score."""
        pack = build_from_fixtures()
        for entry in pack["source_manifest"]:
            assert "retrieval_score" in entry
            assert "retrieval_method" in entry
            assert entry["retrieval_method"] == "metadata_filter+keyword_search+topk"

    def test_top_k_limits_sources(self, tmp_path):
        """With top_k=1, at most 1 source should appear in each field."""
        # Create multiple Obsidian notes
        notes = []
        for i in range(5):
            note_path = tmp_path / f"note_{i}.md"
            note_path.write_text(
                "---\n"
                f"note_id: lit-{i:03d}\n"
                "type: literature_note\n"
                "project_id: test\n"
                "status: active\n"
                "confidentiality: public\n"
                f"chapter: 引言\n"
                f"tags: [education-policy]\n"
                "---\n\n"
                f"教育政策研究内容第{i}部分\n",
                encoding="utf-8",
            )
            notes.append(note_path)

        task_spec = FIXTURES_DIR / "paper_task_spec.sample.yaml"
        pack = build_context_pack(task_spec, notes, [], top_k=1)
        # Only 1 literature note should be selected
        assert len(pack["retrieved_literature"]) <= 1

    def test_keywords_extracted(self):
        """retrieval_trace should show extracted keywords."""
        pack = build_from_fixtures()
        keywords = pack["retrieval_trace"]["pipeline"]["keyword_scoring"]["keywords_extracted"]
        assert len(keywords) > 0

    def test_retrieval_score_in_source_manifest_schema(self):
        """Schema must accept retrieval_score in source_manifest."""
        pack = build_from_fixtures()
        from ai_workflow_hub.context_layer.builders.paper_context_pack_builder import _load_schema
        schema = _load_schema()
        jsonschema.validate(instance=pack, schema=schema)
