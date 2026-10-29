import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from control_plane.pipeline_spec import load_pipeline, validate_pipeline, get_stage_sequence
from control_plane.pipeline_runner import dry_run


def test_load_valid_pipeline():
    pipeline = load_pipeline("pipelines/example_pipeline.yaml")
    assert pipeline["pipeline_id"] == "example_pipeline"
    assert len(pipeline["stages"]) == 4


def test_validate_valid_pipeline():
    pipeline = load_pipeline("pipelines/example_pipeline.yaml")
    errors = validate_pipeline(pipeline)
    assert len(errors) == 0


def test_validate_missing_id_returns_error():
    errors = validate_pipeline({"version": 1, "stages": [{"type": "audit"}]})
    assert len(errors) > 0


def test_validate_missing_stages_returns_error():
    errors = validate_pipeline({"pipeline_id": "test", "version": 1})
    assert len(errors) > 0


def test_get_stage_sequence():
    pipeline = load_pipeline("pipelines/example_pipeline.yaml")
    seq = get_stage_sequence(pipeline)
    assert seq == ["g0_bootstrap", "g1_planning", "g2_authorization", "g2_closure"]


def test_dry_run_valid_pipeline():
    result = dry_run("pipelines/example_pipeline.yaml")
    assert result == 0


def test_dry_run_invalid_path():
    result = dry_run("nonexistent.yaml")
    assert result == 1


def test_dry_run_with_submission():
    result = dry_run("pipelines/example_pipeline.yaml", with_submission=True)
    assert result == 0


def test_dry_run_without_submission():
    result = dry_run("pipelines/example_pipeline.yaml", with_submission=False)
    assert result == 0
