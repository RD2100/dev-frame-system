import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "context_handoff.schema.json"


def load_schema():
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def make_minimal_handoff():
    return {
        "project_id": "test-project",
        "project_name": "Test Project",
        "current_stage": "G0",
        "next_stage": "G1",
        "safety_boundaries": ["no real user data"],
        "expected_response_schema": {
            "overall_judgment": "accepted",
            "handoff_understood": "yes",
        },
        "failure_policy": {},
    }


def test_minimal_valid_handoff():
    data = make_minimal_handoff()
    # All required fields present
    required = ["project_id", "project_name", "current_stage", "next_stage", "safety_boundaries", "expected_response_schema", "failure_policy"]
    for key in required:
        assert key in data, f"Missing required: {key}"


def test_missing_safety_boundaries_fails():
    data = make_minimal_handoff()
    del data["safety_boundaries"]
    required = ["project_id", "project_name", "current_stage", "next_stage", "safety_boundaries", "expected_response_schema", "failure_policy"]
    for key in required:
        if key not in data:
            assert key == "safety_boundaries"


def test_missing_expected_response_schema_fails():
    data = make_minimal_handoff()
    del data["expected_response_schema"]
    required = ["project_id", "project_name", "current_stage", "next_stage", "safety_boundaries", "expected_response_schema", "failure_policy"]
    for key in required:
        if key not in data:
            assert key == "expected_response_schema"


def test_missing_next_stage_fails():
    data = make_minimal_handoff()
    del data["next_stage"]
    required = ["project_id", "project_name", "current_stage", "next_stage", "safety_boundaries", "expected_response_schema", "failure_policy"]
    for key in required:
        if key not in data:
            assert key == "next_stage"


def test_schema_loads_as_valid_json():
    schema = load_schema()
    assert schema["title"] == "ContextHandoff"
    assert "project_id" in schema["required"]


def test_bootstrap_reply_example_is_valid_yaml():
    import yaml
    reply_path = Path(__file__).resolve().parent.parent / "examples" / "context_handoff_g8" / "BOOTSTRAP_REPLY.example.yaml"
    data = yaml.safe_load(reply_path.read_text(encoding="utf-8"))
    assert data["handoff_understood"] in (True, "yes")
    assert data["ready_for_g8_authorization"] in (True, "yes")


def test_handoff_example_contains_required_sections():
    example_path = Path(__file__).resolve().parent.parent / "examples" / "context_handoff_g8" / "HANDOFF_G0_G7_TO_G8.example.md"
    text = example_path.read_text(encoding="utf-8")
    required_sections = ["Project Identity", "Current Status", "Safety Boundaries", "Next Phase", "Expected Response", "Failure Policy"]
    for section in required_sections:
        assert section in text, f"Missing section: {section}"
