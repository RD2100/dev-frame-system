"""
Top-K Selector
Combines metadata score + keyword score into a final relevance score,
selects the top-k sources, and produces a retrieval trace.
"""
from typing import Any


# Default weights for score combination
METADATA_WEIGHT = 0.4
KEYWORD_WEIGHT = 0.6


def compute_final_score(
    metadata_score: float,
    keyword_score: float,
    metadata_weight: float = METADATA_WEIGHT,
    keyword_weight: float = KEYWORD_WEIGHT,
) -> float:
    """Compute weighted final relevance score.

    Returns:
        Final score in [0.0, 1.0].
    """
    total_weight = metadata_weight + keyword_weight
    if total_weight == 0:
        return 0.0
    raw = (metadata_score * metadata_weight + keyword_score * keyword_weight) / total_weight
    return min(1.0, max(0.0, raw))


def select_topk(
    scored_sources: list[dict[str, Any]],
    k: int = 5,
    min_score: float = 0.05,
    metadata_weight: float = METADATA_WEIGHT,
    keyword_weight: float = KEYWORD_WEIGHT,
) -> dict[str, Any]:
    """Select top-k sources from scored candidates.

    Args:
        scored_sources: List of sources with '_metadata_score' and '_keyword_score'.
        k: Maximum number of sources to select.
        min_score: Minimum final score to be included.
        metadata_weight: Weight for metadata score component.
        keyword_weight: Weight for keyword score component.

    Returns:
        {
            "selected": [...],       # top-k sources with final scores
            "rejected": [...],       # sources that didn't make the cut
            "retrieval_trace": {...} # full retrieval evidence
        }
    """
    # Compute final scores
    for source in scored_sources:
        meta_score = source.get("_metadata_score", 0.0)
        kw_score = source.get("_keyword_score", 0.0)
        source["_final_score"] = compute_final_score(
            meta_score, kw_score, metadata_weight, keyword_weight
        )

    # Sort by final score descending
    scored_sources.sort(key=lambda s: s["_final_score"], reverse=True)

    selected = []
    rejected = []

    for source in scored_sources:
        if source["_final_score"] < min_score:
            rejected.append(source)
            continue

        if len(selected) < k:
            selected.append(source)
        else:
            rejected.append(source)

    # Build retrieval trace
    trace = _build_retrieval_trace(selected, rejected, k)

    return {
        "selected": selected,
        "rejected": rejected,
        "retrieval_trace": trace,
    }


def _source_id(source: dict[str, Any]) -> str:
    """Extract a human-readable source identifier."""
    meta = source.get("metadata", {})
    return meta.get("note_id") or meta.get("citekey") or source.get("source_path", "unknown")


def _build_retrieval_trace(
    selected: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    k: int,
) -> dict[str, Any]:
    """Build a structured retrieval trace for evidence/audit.

    The trace records every decision made during retrieval:
    - Total candidates evaluated
    - Selected sources with scores and reasons
    - Rejected sources with scores and rejection reasons
    """
    trace: dict[str, Any] = {
        "total_candidates": len(selected) + len(rejected),
        "total_selected": len(selected),
        "total_rejected": len(rejected),
        "k": k,
        "selected_entries": [],
        "rejected_entries": [],
    }

    for source in selected:
        meta = source.get("metadata", {})
        entry = {
            "source_id": _source_id(source),
            "source_type": "zotero_reference" if "citekey" in meta else "obsidian_note",
            "final_score": round(source.get("_final_score", 0.0), 4),
            "metadata_score": round(source.get("_metadata_score", 0.0), 4),
            "keyword_score": round(source.get("_keyword_score", 0.0), 4),
            "reason": "selected — score above threshold and within top-k",
        }
        trace["selected_entries"].append(entry)

    for source in rejected:
        meta = source.get("metadata", {})
        final_score = source.get("_final_score", 0.0)
        if final_score < 0.05:
            reason = "rejected — final score below minimum threshold"
        else:
            reason = f"rejected — ranked #{len(selected) + rejected.index(source) + 1}, outside top-k={k}"

        entry = {
            "source_id": _source_id(source),
            "source_type": "zotero_reference" if "citekey" in meta else "obsidian_note",
            "final_score": round(final_score, 4),
            "metadata_score": round(source.get("_metadata_score", 0.0), 4),
            "keyword_score": round(source.get("_keyword_score", 0.0), 4),
            "reason": reason,
        }
        trace["rejected_entries"].append(entry)

    return trace
