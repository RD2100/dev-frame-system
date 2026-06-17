"""@go TaskSpec -> ai-workflow-hub task format adapter."""

from __future__ import annotations
from typing import Any


def from_task_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Convert a @go TaskSpec dict into the format add_task() expects.

    Expected TaskSpec fields:
        title: str
        description: str
        risk_level: str      # "P0"/"P1"/"P2"/"P3"
        scope: list[str]     # allowed files
        forbidden: list[str] # forbidden files
        verify: list[str]    # verification commands
        max_fix_rounds: int  # max fix iterations (default 3)
        mode: str            # "dry-run" | "apply"
    """
    risk_map = {"P0": "high", "P1": "high", "P2": "medium", "P3": "low"}

    return {
        "title": spec.get("title", "Untitled Task"),
        "description": spec.get("description", ""),
        "risk": risk_map.get(spec.get("risk_level", "P2"), "medium"),
        "allowed_files": spec.get("scope", []),
        "forbidden_files": spec.get("forbidden", []),
        "verification": spec.get("verify", []),
        "max_fix_rounds": spec.get("max_fix_rounds", 3),
        "mode": spec.get("mode", "dry-run"),
    }
