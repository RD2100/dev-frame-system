"""
Tests for A4: Source Integration MVP
Tests BibTeX parser, vault scanner, source cache, and build_from_vault.
"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

# Paths
FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent
    / "src" / "ai_workflow_hub" / "domains" / "paper" / "fixtures"
)
MINI_VAULT_DIR = FIXTURES_DIR / "mini_vault"
BIBTEX_PATH = FIXTURES_DIR / "bibtex_references.sample.bib"
TASK_SPEC_A4 = FIXTURES_DIR / "paper_task_a4.sample.yaml"
SCHEMA_PATH = FIXTURES_DIR.parent / "contracts" / "source_cache.schema.json"


class TestBibTeXParser(unittest.TestCase):
    """Tests for bibtex_parser module."""

    def test_parse_bibtex_file_returns_records(self):
        from ai_workflow_hub.context_layer.parsers.bibtex_parser import parse_bibtex_file
        records = parse_bibtex_file(BIBTEX_PATH)
        self.assertGreater(len(records), 0, "Should parse at least one record")

    def test_parse_bibtex_file_count(self):
        from ai_workflow_hub.context_layer.parsers.bibtex_parser import parse_bibtex_file
        records = parse_bibtex_file(BIBTEX_PATH)
        self.assertEqual(len(records), 8, "Should parse all 8 BibTeX entries")

    def test_bibtex_record_has_metadata(self):
        from ai_workflow_hub.context_layer.parsers.bibtex_parser import parse_bibtex_file
        records = parse_bibtex_file(BIBTEX_PATH)
        for rec in records:
            self.assertIn("metadata", rec)
            self.assertIn("source_path", rec)
            meta = rec["metadata"]
            self.assertIn("citekey", meta)
            self.assertIn("title", meta)
            self.assertIn("authors", meta)
            self.assertIn("year", meta)
            self.assertIn("item_type", meta)

    def test_bibtex_entry_type_mapping(self):
        from ai_workflow_hub.context_layer.parsers.bibtex_parser import parse_bibtex_file
        records = parse_bibtex_file(BIBTEX_PATH)
        item_types = {rec["metadata"]["citekey"]: rec["metadata"]["item_type"] for rec in records}
        self.assertEqual(item_types.get("Smith2023ContextRetrieval"), "journal_article")
        self.assertEqual(item_types.get("Johnson2022ResearchMethods"), "book")
        self.assertEqual(item_types.get("Wang2024BibTeXParsing"), "conference_paper")
        self.assertEqual(item_types.get("Lee2021MetadataScoring"), "thesis")
        self.assertEqual(item_types.get("Davis2024PrivacyFiltering"), "report")
        self.assertEqual(item_types.get("Brown2022VaultArchitecture"), "book_section")

    def test_bibtex_author_normalization(self):
        from ai_workflow_hub.context_layer.parsers.bibtex_parser import parse_bibtex_file
        records = parse_bibtex_file(BIBTEX_PATH)
        smith = next(r for r in records if r["metadata"]["citekey"] == "Smith2023ContextRetrieval")
        authors = smith["metadata"]["authors"]
        self.assertEqual(len(authors), 2)
        self.assertIn("Smith", authors[0])

    def test_bibtex_tags_extraction(self):
        from ai_workflow_hub.context_layer.parsers.bibtex_parser import parse_bibtex_file
        records = parse_bibtex_file(BIBTEX_PATH)
        smith = next(r for r in records if r["metadata"]["citekey"] == "Smith2023ContextRetrieval")
        tags = smith["metadata"].get("tags", [])
        self.assertGreater(len(tags), 0)
        self.assertIn("context retrieval", tags)

    def test_bibtex_chinese_title(self):
        from ai_workflow_hub.context_layer.parsers.bibtex_parser import parse_bibtex_file
        records = parse_bibtex_file(BIBTEX_PATH)
        chen = next(r for r in records if r["metadata"]["citekey"] == "Chen2023ChineseTextMining")
        self.assertIn("中文", chen["metadata"]["title"])

    def test_parse_single_entry(self):
        from ai_workflow_hub.context_layer.parsers.bibtex_parser import parse_bibtex_entry
        raw = '@article{Test2024, author = {Doe, Jane}, title = {Test Title}, year = {2024}, journal = {Test Journal}}'
        result = parse_bibtex_entry(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result["citekey"], "Test2024")
        self.assertEqual(result["item_type"], "journal_article")

    def test_parse_comment_returns_none(self):
        from ai_workflow_hub.context_layer.parsers.bibtex_parser import parse_bibtex_entry
        raw = '@comment{This is a comment}'
        result = parse_bibtex_entry(raw)
        self.assertIsNone(result)

    def test_strip_latex(self):
        from ai_workflow_hub.context_layer.parsers.bibtex_parser import _strip_latex
        self.assertEqual(_strip_latex("{Test}"), "Test")
        self.assertEqual(_strip_latex(r"\'{e}"), "é")
        self.assertEqual(_strip_latex(r"100\%"), "100%")


class TestVaultScanner(unittest.TestCase):
    """Tests for vault_scanner module."""

    def test_scan_mini_vault_finds_files(self):
        from ai_workflow_hub.context_layer.sources.vault_scanner import scan_vault
        results = scan_vault(MINI_VAULT_DIR)
        self.assertGreater(len(results), 0, "Should find files in mini vault")

    def test_scan_mini_vault_excludes_sensitive(self):
        from ai_workflow_hub.context_layer.sources.vault_scanner import scan_vault
        results = scan_vault(MINI_VAULT_DIR)
        paths = [r["relative_path"] for r in results]
        # sensitive file should be excluded by default
        for p in paths:
            self.assertNotIn("sensitive", p.lower())

    def test_scan_mini_vault_includes_sensitive_when_configured(self):
        from ai_workflow_hub.context_layer.sources.vault_scanner import scan_vault
        results = scan_vault(MINI_VAULT_DIR, exclude_confidentiality=set())
        paths = [r["relative_path"] for r in results]
        has_sensitive = any("sensitive" in p.lower() for p in paths)
        self.assertTrue(has_sensitive, "Should include sensitive when not excluded")

    def test_scan_vault_returns_metadata(self):
        from ai_workflow_hub.context_layer.sources.vault_scanner import scan_vault
        results = scan_vault(MINI_VAULT_DIR)
        for r in results:
            self.assertIn("path", r)
            self.assertIn("relative_path", r)
            self.assertIn("checksum", r)
            self.assertIn("metadata", r)
            self.assertIn("discovered", r)
            self.assertTrue(r["discovered"])

    def test_scan_vault_invalid_dir_raises(self):
        from ai_workflow_hub.context_layer.sources.vault_scanner import scan_vault
        with self.assertRaises(FileNotFoundError):
            scan_vault("/nonexistent/path/to/vault")

    def test_scan_vault_filter_by_type(self):
        from ai_workflow_hub.context_layer.sources.vault_scanner import scan_vault
        results = scan_vault(MINI_VAULT_DIR, include_types={"literature_note"})
        for r in results:
            self.assertEqual(r["metadata"].get("type"), "literature_note")

    def test_scan_bibtex_files(self):
        from ai_workflow_hub.context_layer.sources.vault_scanner import scan_bibtex_files
        results = scan_bibtex_files(BIBTEX_PATH)
        self.assertEqual(len(results), 8)
        for r in results:
            self.assertIn("metadata", r)
            self.assertIn("checksum", r)

    def test_scan_bibtex_invalid_raises(self):
        from ai_workflow_hub.context_layer.sources.vault_scanner import scan_bibtex_files
        with self.assertRaises(FileNotFoundError):
            scan_bibtex_files("/nonexistent/file.bib")

    def test_scan_count_matches_vault_size(self):
        from ai_workflow_hub.context_layer.sources.vault_scanner import scan_vault
        # mini_vault has 9 files, 1 is sensitive → 8 discovered
        results = scan_vault(MINI_VAULT_DIR)
        self.assertEqual(len(results), 8)


class TestSourceCache(unittest.TestCase):
    """Tests for source_cache module."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache_path = Path(self.tmpdir) / "test_cache.json"

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_load_empty_cache(self):
        from ai_workflow_hub.context_layer.sources.source_cache import load_cache
        cache = load_cache(self.cache_path)
        self.assertEqual(cache["scan_count"], 0)
        self.assertEqual(len(cache["sources"]), 0)

    def test_save_and_load_cache(self):
        from ai_workflow_hub.context_layer.sources.source_cache import (
            load_cache, save_cache,
        )
        cache = load_cache(self.cache_path)
        save_cache(cache, self.cache_path)
        self.assertTrue(self.cache_path.exists())
        reloaded = load_cache(self.cache_path)
        self.assertEqual(reloaded["scan_count"], 0)

    def test_update_cache_adds_sources(self):
        from ai_workflow_hub.context_layer.sources.source_cache import (
            load_cache, update_cache,
        )
        cache = load_cache(self.cache_path)
        discovered = [
            {
                "path": "/test/file1.md",
                "relative_path": "file1.md",
                "checksum": "abc123",
                "metadata": {"type": "literature_note", "note_id": "test1"},
            }
        ]
        updated = update_cache(cache, discovered, source_kind="obsidian")
        self.assertEqual(len(updated["sources"]), 1)
        self.assertEqual(updated["scan_count"], 1)

    def test_update_cache_removes_stale(self):
        from ai_workflow_hub.context_layer.sources.source_cache import (
            load_cache, update_cache,
        )
        cache = load_cache(self.cache_path)
        # Add two sources
        discovered = [
            {"path": "/a.md", "relative_path": "a.md", "checksum": "aaa", "metadata": {"type": "t"}},
            {"path": "/b.md", "relative_path": "b.md", "checksum": "bbb", "metadata": {"type": "t"}},
        ]
        cache = update_cache(cache, discovered, source_kind="obsidian")
        self.assertEqual(len(cache["sources"]), 2)
        # Re-scan with only one source
        updated = update_cache(cache, [discovered[0]], source_kind="obsidian")
        self.assertEqual(len(updated["sources"]), 1)
        self.assertNotIn("obsidian:b.md", updated["sources"])

    def test_cache_stats(self):
        from ai_workflow_hub.context_layer.sources.source_cache import (
            load_cache, update_cache, cache_stats,
        )
        cache = load_cache(self.cache_path)
        discovered = [
            {"path": "/a.md", "relative_path": "a.md", "checksum": "aaa",
             "metadata": {"type": "literature_note"}},
            {"path": "/b.md", "relative_path": "b.md", "checksum": "bbb",
             "metadata": {"type": "writing_rule"}},
        ]
        cache = update_cache(cache, discovered, source_kind="obsidian")
        stats = cache_stats(cache)
        self.assertEqual(stats["total_sources"], 2)
        self.assertEqual(stats["by_kind"]["obsidian"], 2)
        self.assertEqual(stats["scan_count"], 1)

    def test_update_cache_detects_changes(self):
        from ai_workflow_hub.context_layer.sources.source_cache import (
            load_cache, update_cache,
        )
        cache = load_cache(self.cache_path)
        discovered = [
            {"path": "/a.md", "relative_path": "a.md", "checksum": "v1", "metadata": {"type": "t"}},
        ]
        cache = update_cache(cache, discovered, source_kind="obsidian")
        old_time = cache["sources"]["obsidian:a.md"]["updated_at"]
        # Same file, different checksum
        discovered[0]["checksum"] = "v2"
        import time; time.sleep(0.01)
        cache = update_cache(cache, discovered, source_kind="obsidian")
        new_time = cache["sources"]["obsidian:a.md"]["updated_at"]
        self.assertNotEqual(old_time, new_time)


class TestBuildFromVault(unittest.TestCase):
    """Tests for build_from_vault integration."""

    def test_build_from_vault_returns_pack(self):
        from ai_workflow_hub.context_layer.builders.paper_context_pack_builder import build_from_vault
        pack = build_from_vault(
            task_spec_path=TASK_SPEC_A4,
            vault_dir=MINI_VAULT_DIR,
            bibtex_path=BIBTEX_PATH,
            top_k=5,
        )
        self.assertIn("pack_id", pack)
        self.assertIn("task_id", pack)
        self.assertEqual(pack["task_id"], "paper-task-a4-source-integration")

    def test_build_from_vault_validates_schema(self):
        from ai_workflow_hub.context_layer.builders.paper_context_pack_builder import build_from_vault
        pack = build_from_vault(
            task_spec_path=TASK_SPEC_A4,
            vault_dir=MINI_VAULT_DIR,
            bibtex_path=BIBTEX_PATH,
            top_k=5,
        )
        # If we got here, schema validation passed
        self.assertIsNotNone(pack)

    def test_build_from_vault_has_retrieval_trace(self):
        from ai_workflow_hub.context_layer.builders.paper_context_pack_builder import build_from_vault
        pack = build_from_vault(
            task_spec_path=TASK_SPEC_A4,
            vault_dir=MINI_VAULT_DIR,
            bibtex_path=BIBTEX_PATH,
            top_k=5,
        )
        self.assertIn("retrieval_trace", pack)
        trace = pack["retrieval_trace"]
        self.assertIn("pipeline", trace)
        self.assertIn("vault_scan", trace)

    def test_build_from_vault_privacy_filters_sensitive(self):
        from ai_workflow_hub.context_layer.builders.paper_context_pack_builder import build_from_vault
        pack = build_from_vault(
            task_spec_path=TASK_SPEC_A4,
            vault_dir=MINI_VAULT_DIR,
            bibtex_path=BIBTEX_PATH,
            top_k=10,  # high k to include as many as possible
        )
        # Sensitive source should NOT appear in source_manifest
        manifest_ids = [e["source_id"] for e in pack["source_manifest"]]
        self.assertNotIn("sensitive-reviewer-notes", manifest_ids)

    def test_build_from_vault_source_manifest_has_scores(self):
        from ai_workflow_hub.context_layer.builders.paper_context_pack_builder import build_from_vault
        pack = build_from_vault(
            task_spec_path=TASK_SPEC_A4,
            vault_dir=MINI_VAULT_DIR,
            bibtex_path=BIBTEX_PATH,
            top_k=5,
        )
        for entry in pack["source_manifest"]:
            self.assertIn("retrieval_score", entry)
            self.assertIn("retrieval_method", entry)
            self.assertIsInstance(entry["retrieval_score"], float)

    def test_build_from_vault_with_cache(self):
        from ai_workflow_hub.context_layer.builders.paper_context_pack_builder import build_from_vault
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.json"
            pack = build_from_vault(
                task_spec_path=TASK_SPEC_A4,
                vault_dir=MINI_VAULT_DIR,
                bibtex_path=BIBTEX_PATH,
                top_k=5,
                cache_path=cache_path,
            )
            self.assertTrue(cache_path.exists())
            cache_data = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertGreater(cache_data["scan_count"], 0)
            self.assertGreater(len(cache_data["sources"]), 0)

    def test_build_from_vault_topk_limits_results(self):
        from ai_workflow_hub.context_layer.builders.paper_context_pack_builder import build_from_vault
        pack = build_from_vault(
            task_spec_path=TASK_SPEC_A4,
            vault_dir=MINI_VAULT_DIR,
            bibtex_path=BIBTEX_PATH,
            top_k=3,
        )
        # Total manifest entries should be <= 3
        self.assertLessEqual(len(pack["source_manifest"]), 3)

    def test_build_from_vault_without_bibtex(self):
        from ai_workflow_hub.context_layer.builders.paper_context_pack_builder import build_from_vault
        pack = build_from_vault(
            task_spec_path=TASK_SPEC_A4,
            vault_dir=MINI_VAULT_DIR,
            top_k=5,
        )
        # Should still work, just without Zotero/BibTeX sources
        self.assertIsNotNone(pack)
        # All sources should be obsidian type
        for entry in pack["source_manifest"]:
            self.assertEqual(entry["source_type"], "obsidian_note")


class TestRejectionFixture(unittest.TestCase):
    """Test that top-k with k < candidates produces rejections."""

    def test_rejection_entries_in_trace(self):
        from ai_workflow_hub.context_layer.builders.paper_context_pack_builder import build_from_vault
        pack = build_from_vault(
            task_spec_path=TASK_SPEC_A4,
            vault_dir=MINI_VAULT_DIR,
            bibtex_path=BIBTEX_PATH,
            top_k=3,  # less than total candidates
        )
        trace = pack["retrieval_trace"]
        # With top_k=3 and 7 vault + 8 bibtex = 15 candidates, some must be rejected
        self.assertIn("total_rejected", trace)
        # Total rejected should be > 0
        self.assertGreater(trace["total_rejected"], 0)

    def test_rejection_fixture_has_selected_and_rejected(self):
        from ai_workflow_hub.context_layer.builders.paper_context_pack_builder import build_from_vault
        pack = build_from_vault(
            task_spec_path=TASK_SPEC_A4,
            vault_dir=MINI_VAULT_DIR,
            bibtex_path=BIBTEX_PATH,
            top_k=3,
        )
        trace = pack["retrieval_trace"]
        self.assertIn("selected_entries", trace)
        self.assertIn("rejected_entries", trace)
        self.assertGreater(len(trace["selected_entries"]), 0)
        self.assertGreater(len(trace["rejected_entries"]), 0)


if __name__ == "__main__":
    unittest.main()
