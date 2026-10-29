"""
Tests for A3 Retrieval Pipeline:
  - metadata_filter.py
  - keyword_scorer.py
  - topk_selector.py
  - retriever.py (orchestrator)
"""
import json
from pathlib import Path

import pytest

from ai_workflow_hub.context_layer.retrieval.metadata_filter import (
    score_metadata,
    filter_by_metadata,
    _chapter_match,
    _tag_overlap,
    _status_score,
    _type_bonus,
)
from ai_workflow_hub.context_layer.retrieval.keyword_scorer import (
    extract_keywords,
    score_keywords,
)
from ai_workflow_hub.context_layer.retrieval.topk_selector import (
    compute_final_score,
    select_topk,
)
from ai_workflow_hub.context_layer.retrieval.retriever import (
    retrieve_sources,
    RetrievalResult,
)


# ── Fixtures ────────────────────────────────────────────────────────

TASK_SPEC = {
    "task_id": "paper-task-001-draft-intro",
    "task_type": "draft",
    "chapter": "引言",
    "section": "1.1 研究背景",
    "paper_type": "empirical",
    "constraints": [
        "不得使用未在 literature_notes 中出现的文献",
        "段落长度控制在 150-300 字之间",
    ],
    "acceptance_criteria": [
        "段落功能匹配度 >= 70%",
        "引用来源均在 zotero_references 中",
    ],
}


def _make_obsidian(note_id, note_type, chapter, tags, status="active",
                   confidentiality="public", body="some body text"):
    return {
        "metadata": {
            "note_id": note_id,
            "type": note_type,
            "project_id": "test-project",
            "status": status,
            "confidentiality": confidentiality,
            "chapter": chapter,
            "tags": tags,
        },
        "body": body,
        "source_path": f"vault/{note_id}.md",
    }


def _make_zotero(citekey, title, tags, year=2024, confidentiality="public"):
    return {
        "metadata": {
            "citekey": citekey,
            "title": title,
            "authors": ["Author A"],
            "year": year,
            "item_type": "journal_article",
            "tags": tags,
            "confidentiality": confidentiality,
            "citation_allowed": True,
        },
        "source_path": f"zotero/{citekey}.json",
    }


# ── Metadata Filter Tests ───────────────────────────────────────────

class TestMetadataFilter:
    def test_chapter_match_exact(self):
        assert _chapter_match("引言", "引言") == 1.0

    def test_chapter_match_null_universal(self):
        assert _chapter_match(None, "引言") == 1.0

    def test_chapter_match_mismatch(self):
        assert _chapter_match("讨论", "引言") == 0.0

    def test_chapter_match_no_task_chapter(self):
        assert _chapter_match("引言", "") == 0.5

    def test_tag_overlap_full(self):
        assert _tag_overlap(["education-policy", "cssci"], ["education-policy", "cssci"]) == 1.0

    def test_tag_overlap_partial(self):
        score = _tag_overlap(["education-policy", "other"], ["education-policy", "cssci"])
        assert 0.0 < score < 1.0

    def test_tag_overlap_none(self):
        assert _tag_overlap(["unrelated"], ["education-policy"]) == 0.0

    def test_tag_overlap_empty_keywords(self):
        assert _tag_overlap(["any"], []) == 0.5

    def test_status_score_active(self):
        assert _status_score("active") == 1.0

    def test_status_score_archived(self):
        assert _status_score("archived") == 0.3

    def test_status_score_deprecated(self):
        assert _status_score("deprecated") == 0.0

    def test_type_bonus_draft_writing_rule(self):
        bonus = _type_bonus("writing_rule", "draft")
        assert bonus > 0.0

    def test_type_bonus_unknown_task(self):
        assert _type_bonus("writing_rule", "unknown_type") == 0.0

    def test_score_metadata_obsidian_high_relevance(self):
        source = _make_obsidian(
            "lit-001", "literature_note", "引言",
            ["education-policy", "evaluation"],
            body="教育政策评估框架的研究背景"
        )
        score = score_metadata(source, TASK_SPEC, ["education-policy", "evaluation"])
        assert score > 0.3

    def test_score_metadata_obsidian_low_relevance(self):
        source = _make_obsidian(
            "unrelated-001", "project_memory", "方法论",
            ["unrelated-tag"],
            body="完全不相关的内容"
        )
        score = score_metadata(source, TASK_SPEC, ["education-policy"])
        assert score < 0.5

    def test_score_metadata_zotero(self):
        source = _make_zotero(
            "zhang2024", "教育政策执行效果研究",
            ["education-policy", "evaluation"], year=2024
        )
        score = score_metadata(source, TASK_SPEC, ["education-policy"])
        assert score > 0.3

    def test_filter_by_metadata_excludes_deprecated(self):
        sources = [
            _make_obsidian("active-001", "literature_note", "引言", ["cssci"]),
            _make_obsidian("deprecated-001", "literature_note", "讨论", ["unrelated"], status="deprecated"),
        ]
        # deprecated + wrong chapter + no matching tags → only type bonus (0.15)
        # threshold=0.2 excludes it
        filtered = filter_by_metadata(sources, TASK_SPEC, ["education-policy"], threshold=0.2)
        ids = [s["metadata"]["note_id"] for s in filtered]
        assert "active-001" in ids
        assert "deprecated-001" not in ids

    def test_filter_by_metadata_sorts_by_score(self):
        sources = [
            _make_obsidian("low-001", "project_memory", "讨论", ["unrelated"]),
            _make_obsidian("high-001", "literature_note", "引言", ["education-policy", "cssci"],
                          body="教育政策研究背景评估框架"),
        ]
        filtered = filter_by_metadata(sources, TASK_SPEC, ["education-policy"], threshold=0.05)
        if len(filtered) >= 2:
            assert filtered[0]["_metadata_score"] >= filtered[1]["_metadata_score"]


# ── Keyword Scorer Tests ────────────────────────────────────────────

class TestKeywordScorer:
    def test_extract_keywords_from_task_spec(self):
        keywords = extract_keywords(TASK_SPEC)
        assert len(keywords) > 0
        # Should contain domain-relevant terms
        assert any(kw for kw in keywords if "教育" in kw or "policy" in kw.lower() or "文献" in kw)

    def test_extract_keywords_excludes_stop_words(self):
        keywords = extract_keywords(TASK_SPEC)
        from ai_workflow_hub.context_layer.retrieval.keyword_scorer import ALL_STOP_WORDS
        for kw in keywords:
            assert kw not in ALL_STOP_WORDS

    def test_extract_keywords_max_limit(self):
        keywords = extract_keywords(TASK_SPEC, max_keywords=5)
        assert len(keywords) <= 5

    def test_score_keywords_high_match(self):
        source = _make_obsidian(
            "lit-001", "literature_note", "引言", ["cssci"],
            body="教育政策评估框架的研究背景 段落功能匹配度 文献综述 引用来源"
        )
        keywords = extract_keywords(TASK_SPEC)
        score = score_keywords(source, keywords)
        assert score > 0.0

    def test_score_keywords_no_match(self):
        source = _make_obsidian(
            "unrelated-001", "project_memory", "讨论", [],
            body="完全不相关的随机文字内容"
        )
        keywords = extract_keywords(TASK_SPEC)
        score = score_keywords(source, keywords)
        # Score should be low but not necessarily 0 (CJK bigrams may partially match)
        assert score < 0.5

    def test_score_keywords_empty_keywords(self):
        source = _make_obsidian("n1", "literature_note", "引言", [])
        score = score_keywords(source, [])
        assert score == 0.5  # neutral

    def test_score_keywords_zotero(self):
        source = _make_zotero(
            "ref1", "教育政策执行效果的实证研究",
            ["education-policy"], year=2024
        )
        keywords = extract_keywords(TASK_SPEC)
        score = score_keywords(source, keywords)
        assert score >= 0.0

    def test_score_keywords_empty_body(self):
        source = _make_obsidian("empty-001", "literature_note", "引言", [], body="")
        keywords = ["教育", "政策"]
        score = score_keywords(source, keywords)
        assert score == 0.0


# ── Top-K Selector Tests ───────────────────────────────────────────

class TestTopKSelector:
    def test_compute_final_score(self):
        score = compute_final_score(0.8, 0.6)
        assert 0.0 <= score <= 1.0
        # (0.8*0.4 + 0.6*0.6) / 1.0 = 0.68
        assert score == pytest.approx(0.68, abs=0.01)

    def test_compute_final_score_zero_weights(self):
        score = compute_final_score(0.8, 0.6, 0.0, 0.0)
        assert score == 0.0

    def test_select_topk_basic(self):
        sources = [
            {"metadata": {"note_id": f"s{i}"}, "_metadata_score": 0.5, "_keyword_score": 0.5 - i * 0.1}
            for i in range(5)
        ]
        result = select_topk(sources, k=3)
        assert len(result["selected"]) == 3
        assert len(result["rejected"]) == 2

    def test_select_topk_respects_min_score(self):
        sources = [
            {"metadata": {"note_id": "high"}, "_metadata_score": 0.8, "_keyword_score": 0.7},
            {"metadata": {"note_id": "low"}, "_metadata_score": 0.01, "_keyword_score": 0.01},
        ]
        result = select_topk(sources, k=5, min_score=0.1)
        selected_ids = [s["metadata"]["note_id"] for s in result["selected"]]
        assert "high" in selected_ids
        assert "low" not in selected_ids

    def test_select_topk_retrieval_trace_structure(self):
        sources = [
            {"metadata": {"note_id": "s1"}, "_metadata_score": 0.8, "_keyword_score": 0.6},
            {"metadata": {"citekey": "z1"}, "_metadata_score": 0.5, "_keyword_score": 0.4},
        ]
        result = select_topk(sources, k=1)
        trace = result["retrieval_trace"]
        assert trace["total_candidates"] == 2
        assert trace["total_selected"] == 1
        assert trace["k"] == 1
        assert len(trace["selected_entries"]) == 1
        assert trace["selected_entries"][0]["source_id"] == "s1"

    def test_select_topk_empty_input(self):
        result = select_topk([], k=5)
        assert result["selected"] == []
        assert result["retrieval_trace"]["total_candidates"] == 0


# ── Retriever Orchestrator Tests ───────────────────────────────────

class TestRetriever:
    def test_retrieve_sources_basic(self):
        obsidian = [
            _make_obsidian("lit-001", "literature_note", "引言", ["education-policy"],
                          body="教育政策评估框架的研究背景"),
            _make_obsidian("rule-001", "writing_rule", None, ["cssci"],
                          body="CSSCI 写作风格约束规则"),
        ]
        zotero = [
            _make_zotero("zhang2024", "教育政策执行效果研究", ["education-policy"]),
        ]
        result = retrieve_sources(TASK_SPEC, obsidian, zotero, k=5)

        assert isinstance(result, RetrievalResult)
        assert result.total_selected > 0
        assert result.retrieval_trace["pipeline"] is not None
        assert len(result.keywords) > 0

    def test_retrieve_sources_privacy_first(self):
        """Sensitive sources must be excluded before retrieval scoring."""
        obsidian = [
            _make_obsidian("pub-001", "literature_note", "引言", ["cssci"],
                          confidentiality="public"),
            _make_obsidian("sens-001", "literature_note", "引言", ["cssci"],
                          confidentiality="sensitive", body="secret data"),
        ]
        result = retrieve_sources(TASK_SPEC, obsidian, [], k=5)

        selected_ids = [s["metadata"]["note_id"] for s in result.selected_obsidian]
        assert "sens-001" not in selected_ids
        assert "pub-001" in selected_ids
        assert "sens-001" in result.privacy_result["excluded_sources"]

    def test_retrieve_sources_top_k_limit(self):
        """Ensure top-k limits the number of selected sources."""
        obsidian = [
            _make_obsidian(f"note-{i:03d}", "literature_note", "引言", ["cssci"],
                          body=f"教育政策研究内容第{i}部分")
            for i in range(10)
        ]
        result = retrieve_sources(TASK_SPEC, obsidian, [], k=3)
        assert result.total_selected <= 3

    def test_retrieve_sources_trace_has_pipeline(self):
        obsidian = [
            _make_obsidian("n1", "literature_note", "引言", ["cssci"]),
        ]
        zotero = [
            _make_zotero("z1", "教育研究", ["education"]),
        ]
        result = retrieve_sources(TASK_SPEC, obsidian, zotero)
        trace = result.retrieval_trace

        assert "pipeline" in trace
        assert "privacy_filter" in trace["pipeline"]
        assert "metadata_filter" in trace["pipeline"]
        assert "keyword_scoring" in trace["pipeline"]
        assert "topk_selection" in trace["pipeline"]

    def test_retrieve_sources_manifest_has_scores(self):
        obsidian = [
            _make_obsidian("n1", "literature_note", "引言", ["education-policy"],
                          body="教育政策评估框架的研究背景"),
        ]
        result = retrieve_sources(TASK_SPEC, obsidian, [], k=5)
        manifest = result.source_manifest_entries
        assert len(manifest) > 0
        assert "retrieval_score" in manifest[0]
        assert "retrieval_method" in manifest[0]
        assert manifest[0]["retrieval_method"] == "metadata_filter+keyword_search+topk"

    def test_retrieve_sources_all_sensitive(self):
        """If all sources are sensitive, retrieval yields nothing."""
        obsidian = [
            _make_obsidian("s1", "literature_note", "引言", [],
                          confidentiality="sensitive"),
        ]
        result = retrieve_sources(TASK_SPEC, obsidian, [], k=5)
        assert result.total_selected == 0
        assert result.privacy_result["passed"] is False

    def test_retrieve_sources_metadata_filter_removes_low_score(self):
        """Sources with very low metadata scores should be filtered out."""
        obsidian = [
            _make_obsidian("relevant-001", "literature_note", "引言",
                          ["education-policy", "evaluation"],
                          body="教育政策评估框架"),
            _make_obsidian("irrelevant-001", "project_memory", "方法论",
                          ["machine-learning", "neural-network"],
                          body="深度学习模型训练",
                          status="deprecated"),
        ]
        result = retrieve_sources(TASK_SPEC, obsidian, [], k=5,
                                  metadata_threshold=0.15)
        selected_ids = [s["metadata"]["note_id"] for s in result.selected_obsidian]
        # The irrelevant one should be filtered by metadata
        assert "irrelevant-001" not in selected_ids
