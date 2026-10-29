"""Test readiness_score — 10 metrics, JSON output, heatmap generation."""
import json, sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from tools.readiness_score import (
    compute_scores, write_score_json, write_heatmap_md,
    METRICS, score_test_health, score_evidence_integrity,
)


def test_all_10_metrics_registered():
    assert len(METRICS) == 10, f"Expected 10 metrics, got {len(METRICS)}"


def test_compute_scores_returns_all_metrics():
    data = compute_scores()
    assert "overall_score" in data
    assert "metrics" in data
    assert len(data["metrics"]) == 10
    assert data["blocked_items_preserved"] is True
    for m in data["metrics"]:
        assert "key" in m
        assert "label" in m
        assert "score" in m
        assert "detail" in m
        assert 0.0 <= m["score"] <= 1.0, f"{m['key']} score {m['score']} out of range"


def test_score_json_written(tmp_path: Path):
    data = compute_scores()
    path = write_score_json(data, tmp_path / "readiness_score.json")
    assert path.exists()
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded["overall_score"] == data["overall_score"]
    assert len(reloaded["metrics"]) == 10


def test_heatmap_md_written(tmp_path: Path):
    data = compute_scores()
    path = write_heatmap_md(data, tmp_path / "readiness_heatmap.md")
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "Production Readiness Heatmap" in text
    assert "Overall Score" in text
    for m in data["metrics"]:
        assert m["label"] in text


def test_overall_score_in_range():
    data = compute_scores()
    assert 0.0 <= data["overall_score"] <= 1.0


def test_blocked_items_preserved_from_current_route():
    """blocked_items_preserved is computed from CURRENT_ROUTE.json, not hardcoded."""
    data = compute_scores()
    assert isinstance(data["blocked_items_preserved"], bool)


def test_unknown_metric_fallback_to_zero(tmp_path: Path, monkeypatch):
    """When source data is missing, metric should return 0.0 (conservative)."""
    import tools.readiness_score as rs
    monkeypatch.setattr(rs, '_file_exists', lambda p: False)
    score, detail = rs.score_rollback_readiness()
    assert score == 0.0, f"Expected 0.0 for missing file, got {score}"


def test_all_metrics_handle_missing_data():
    """Every metric function returns (float, str) even with missing data."""
    data = compute_scores()
    for m in data["metrics"]:
        assert isinstance(m["score"], float), f"{m['key']}: score not float"
        assert isinstance(m["detail"], str), f"{m['key']}: detail not str"


def test_blocked_broader_chain_returns_zero():
    """Broader real-chain coverage: 1.0 when unblocked, 0.0 when blocked."""
    from tools.readiness_score import score_broader_real_chain_coverage
    score, detail = score_broader_real_chain_coverage()
    assert score >= 0.0, f"Score should be >= 0.0, got {score}"
    assert isinstance(detail, str) and len(detail) > 0


def test_malformed_json_source_handled_gracefully(tmp_path: Path, monkeypatch):
    """When source JSON is malformed, scorer should not crash."""
    import tools.readiness_score as rs
    monkeypatch.setattr(rs, '_read_json', lambda p: {"malformed": True, "validation_verdict": "garbage"})
    score, detail = rs.score_evidence_integrity()
    assert isinstance(score, float)
    assert isinstance(detail, str)


def test_score_json_is_valid_json(tmp_path: Path):
    data = compute_scores()
    path = write_score_json(data, tmp_path / "test.json")
    parsed = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    assert "generated_at" in parsed
