"Verify context handoff documents against schema."
from __future__ import annotations
from pathlib import Path


def validate_handoff(handoff_text: str) -> tuple[bool, list[str]]:
    required_sections = [
        "Project Identity",
        "Current Status",
        "Safety Boundaries",
        "Next Phase",
        "Expected Response",
        "Failure Policy",
    ]
    missing = [s for s in required_sections if s not in handoff_text]
    if missing:
        return False, [f"Missing section: {m}" for m in missing]

    # Check for YAML schema in expected response
    if "handoff_understood" not in handoff_text:
        missing.append("Missing handoff_understood in expected response schema")
    if "safety_boundaries_understood" not in handoff_text:
        missing.append("Missing safety_boundaries_understood in expected response schema")

    return len(missing) == 0, missing


def parse_bootstrap_reply(reply_text: str) -> dict:
    import yaml
    try:
        data = yaml.safe_load(reply_text)
        if not isinstance(data, dict):
            return {"error": "reply is not a YAML mapping"}
        return {
            "overall_judgment": data.get("overall_judgment", "review_unverified"),
            "handoff_understood": data.get("handoff_understood", False),
            "safety_boundaries_understood": data.get("safety_boundaries_understood", False),
            "ready_for_next_authorization": data.get("ready_for_next_authorization", False),
            "rationale": data.get("rationale", ""),
        }
    except Exception as e:
        return {"error": str(e)}


def is_handoff_verified(parsed: dict) -> bool:
    if "error" in parsed:
        return False
    return (
        parsed.get("handoff_understood") in (True, "yes")
        and parsed.get("safety_boundaries_understood") in (True, "yes")
        and parsed.get("overall_judgment") == "accepted"
    )
