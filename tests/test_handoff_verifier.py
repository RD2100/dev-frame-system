import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from control_plane.handoff_verifier import (
    validate_handoff, parse_bootstrap_reply, is_handoff_verified
)


def test_validate_valid_handoff():
    text = """## 1. Project Identity
## 2. Current Status
## 5. Safety Boundaries
## 6. Next Phase
## 9. Expected Response
handoff_understood: yes
safety_boundaries_understood: yes
## 10. Failure Policy"""
    ok, errors = validate_handoff(text)
    assert ok is True
    assert len(errors) == 0


def test_validate_missing_sections():
    ok, errors = validate_handoff("no sections here")
    assert ok is False
    assert len(errors) > 0


def test_parse_valid_bootstrap_reply():
    reply = """overall_judgment: accepted
handoff_understood: true
safety_boundaries_understood: true
ready_for_next_authorization: true
rationale: test"""
    parsed = parse_bootstrap_reply(reply)
    assert parsed["handoff_understood"] is True
    assert parsed["overall_judgment"] == "accepted"


def test_parse_invalid_yaml():
    parsed = parse_bootstrap_reply("not: valid: yaml: :::")
    assert "error" in parsed


def test_is_handoff_verified_true():
    assert is_handoff_verified({
        "handoff_understood": True,
        "safety_boundaries_understood": True,
        "overall_judgment": "accepted",
    }) is True


def test_is_handoff_verified_false():
    assert is_handoff_verified({
        "handoff_understood": False,
        "safety_boundaries_understood": True,
        "overall_judgment": "accepted",
    }) is False
