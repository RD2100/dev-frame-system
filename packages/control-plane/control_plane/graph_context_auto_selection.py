"""Propose bounded graph context candidates from an explicit task.

This module deliberately stops at a deterministic proposal.  It consumes the
already sanitized graph-slice contract and delegates final manifest creation to
the existing graph-context selection adapter.  It never retrieves, persists,
refreshes, dispatches, or creates authority.
"""
from __future__ import annotations

from collections.abc import Sequence
from math import isfinite
import re
from typing import Any

from .graph_context_selection import (
    GraphContextSelectionError,
    build_graph_context_selection,
)


MAX_TASK_LENGTH = 512
MAX_TASK_TOKENS = 64
MAX_REQUIRED_CANDIDATES = 16

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_SENSITIVE_RE = re.compile(
    r"(?i)(?:api[_-]?key|authorization|bearer|cookie|password|secret|token)"
    r"|sk-[A-Za-z0-9_-]{12,}"
)
_AUTHORITY_WEIGHT = {
    "human_decided": 6,
    "external_reviewed": 5,
    "test_verified": 4,
    "governance_recorded": 3,
    "cited_source": 2,
    "none": 0,
}
_FRESHNESS_WEIGHT = {"current": 3, "stale": 1, "unknown": 0, "omitted": 0}


def propose_graph_context_selection(
    slice_payload: dict[str, Any],
    *,
    task: str,
    reader: str,
    decision_needed: str,
    context_profile: str = "graph-neighborhood",
    max_required_candidates: int = 8,
    max_candidates: int = 64,
    max_assumptions: int = 128,
) -> dict[str, Any]:
    """Return a deterministic, non-authoritative selection proposal."""
    terms = _task_terms(task)
    _validate_limits(slice_payload, max_required_candidates, max_candidates)
    base = build_graph_context_selection(
        slice_payload,
        reader=reader,
        decision_needed=decision_needed,
        context_profile=context_profile,
        max_candidates=max_candidates,
        max_assumptions=max_assumptions,
    )
    anchors = list(slice_payload["selected_node_ids"])
    if len(anchors) > max_required_candidates:
        raise GraphContextSelectionError(
            "explicit graph anchors exceed max_required_candidates"
        )
    selected = anchors + _ranked_ids(
        slice_payload["nodes"],
        anchors=set(anchors),
        terms=terms,
        limit=max_required_candidates - len(anchors),
    )
    if selected == anchors:
        return _with_proposal_rationale(base)
    result = _rebuild_for_selected_ids(
        slice_payload,
        selected,
        reader=reader,
        decision_needed=decision_needed,
        context_profile=context_profile,
        max_candidates=max_candidates,
        max_assumptions=max_assumptions,
    )
    return _with_proposal_rationale(result)


def _validate_limits(
    payload: object, max_required_candidates: object, max_candidates: object
) -> None:
    if not isinstance(payload, dict):
        raise GraphContextSelectionError("graph slice must be an object")
    if type(max_required_candidates) is not int or not 1 <= max_required_candidates <= MAX_REQUIRED_CANDIDATES:
        raise GraphContextSelectionError(
            f"max_required_candidates must be an integer from 1 through {MAX_REQUIRED_CANDIDATES}"
        )
    if type(max_candidates) is not int or not 1 <= max_candidates <= 128:
        raise GraphContextSelectionError(
            "max_candidates must be an integer from 1 through 128"
        )
    if max_required_candidates > max_candidates:
        raise GraphContextSelectionError(
            "max_required_candidates cannot exceed max_candidates"
        )


def _task_terms(task: object) -> frozenset[str]:
    if (
        not isinstance(task, str)
        or not task
        or len(task) > MAX_TASK_LENGTH
        or "\\" in task
        or _SENSITIVE_RE.search(task)
        or any(ord(char) < 32 for char in task)
    ):
        raise GraphContextSelectionError("task must be bounded, safe text")
    terms = {
        token.casefold()
        for token in _TOKEN_RE.findall(task)
        if len(token) >= 2 or any(ord(char) > 127 for char in token)
    }
    return frozenset(sorted(terms)[:MAX_TASK_TOKENS])


def _ranked_ids(
    nodes: Sequence[object],
    *,
    anchors: set[str],
    terms: frozenset[str],
    limit: int,
) -> list[str]:
    ranked: list[tuple[int, int, str]] = []
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or node.get("id") in anchors:
            continue
        if node.get("freshness") != "current":
            continue
        overlap = _node_overlap(node, terms)
        if overlap == 0:
            continue
        score = overlap * 100 + _AUTHORITY_WEIGHT.get(node.get("authority"), 0) * 10
        score += _FRESHNESS_WEIGHT.get(node.get("freshness"), 0) * 3
        confidence = node.get("confidence")
        if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
            confidence_value = float(confidence)
            if isfinite(confidence_value):
                score += max(0, min(10, int(confidence_value * 10)))
        ranked.append((score, index, str(node["id"])))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked[:limit]]


def _node_overlap(node: dict[str, Any], terms: frozenset[str]) -> int:
    fields = [node.get("label"), node.get("source_kind")]
    text = " ".join(value for value in fields if _safe_field(value))
    if not text:
        return 0
    node_terms = {token.casefold() for token in _TOKEN_RE.findall(text)}
    return len(node_terms & terms)


def _safe_field(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= 256
        and "\\" not in value
        and not _SENSITIVE_RE.search(value)
        and not any(ord(char) < 32 for char in value)
    )


def _rebuild_for_selected_ids(
    payload: dict[str, Any],
    selected: list[str],
    *,
    reader: str,
    decision_needed: str,
    context_profile: str,
    max_candidates: int,
    max_assumptions: int,
) -> dict[str, Any]:
    amended = dict(payload)
    amended["selected_node_ids"] = list(selected)
    return build_graph_context_selection(
        amended,
        reader=reader,
        decision_needed=decision_needed,
        context_profile=context_profile,
        max_candidates=max_candidates,
        max_assumptions=max_assumptions,
    )


def _with_proposal_rationale(manifest: dict[str, Any]) -> dict[str, Any]:
    result = dict(manifest)
    result["selection_rationale"] = (
        "Deterministic proposal preserves explicit anchors and adds bounded "
        "task-relevant candidates using authority, freshness, confidence, and "
        "source order; the result remains non-authoritative."
    )
    return result


__all__ = ["GraphContextSelectionError", "propose_graph_context_selection"]
