"""
Metadata Filter
Filters parsed sources by task-relevant metadata fields:
  - chapter match (task_spec.chapter vs source chapter)
  - tag overlap with task keywords
  - status (active only by default)
  - type relevance

Each source receives a metadata_score in [0.0, 1.0].
Sources below a configurable threshold are excluded before keyword scoring.
"""
from typing import Any


def _chapter_match(source_chapter: str | None, task_chapter: str) -> float:
    """Score chapter relevance.

    - None chapter (universal rule) → full match
    - Exact chapter match → full match
    - No match → 0.0
    """
    if source_chapter is None:
        return 1.0
    if not task_chapter:
        return 0.5  # task has no chapter info, partial credit
    if source_chapter == task_chapter:
        return 1.0
    return 0.0


def _tag_overlap(source_tags: list[str], task_keywords: list[str]) -> float:
    """Score tag overlap between source tags and task keywords.

    Returns fraction of task keywords that appear in source tags.
    """
    if not task_keywords:
        return 0.5  # no keywords to match, neutral score
    if not source_tags:
        return 0.0

    normalized_tags = {t.lower().strip() for t in source_tags}
    matches = sum(1 for kw in task_keywords if kw.lower().strip() in normalized_tags)
    return matches / len(task_keywords)


def _status_score(status: str) -> float:
    """Score by source status.

    - active → 1.0
    - archived → 0.3 (still retrievable but deprioritized)
    - deprecated → 0.0 (should not be used)
    """
    mapping = {"active": 1.0, "archived": 0.3, "deprecated": 0.0}
    return mapping.get(status, 0.0)


def _type_bonus(note_type: str, task_type: str) -> float:
    """Bonus for note types especially relevant to the task type.

    For example, 'draft' tasks benefit more from writing_rules and literature_notes.
    """
    bonuses: dict[str, dict[str, float]] = {
        "draft": {
            "writing_rule": 0.2,
            "literature_note": 0.15,
            "bad_example": 0.1,
            "style_example": 0.05,
        },
        "revise": {
            "revision_history": 0.2,
            "bad_example": 0.15,
            "writing_rule": 0.1,
            "style_example": 0.1,
        },
        "review": {
            "writing_rule": 0.15,
            "bad_example": 0.15,
            "literature_note": 0.1,
        },
    }
    task_bonuses = bonuses.get(task_type, {})
    return task_bonuses.get(note_type, 0.0)


def score_metadata(
    source: dict[str, Any],
    task_spec: dict[str, Any],
    task_keywords: list[str] | None = None,
) -> float:
    """Compute a metadata relevance score for a single source.

    Args:
        source: Parsed source record (Obsidian or Zotero).
        task_spec: Parsed task spec dict.
        task_keywords: Optional list of keywords extracted from the task spec.

    Returns:
        Metadata score in [0.0, 1.0].
    """
    meta = source.get("metadata", {})
    task_chapter = task_spec.get("chapter", "")
    task_type = task_spec.get("task_type", "draft")

    # Zotero references don't have chapter/type fields like Obsidian notes
    is_zotero = "citekey" in meta

    if is_zotero:
        # For Zotero: use tag overlap + citation_allowed + year recency
        tags = meta.get("tags", [])
        kw = task_keywords or []
        tag_score = _tag_overlap(tags, kw)
        year = meta.get("year", 2000)
        # Recency bonus: papers from last 5 years get higher score
        recency = max(0.0, min(1.0, (year - 2015) / 15.0))
        citation_allowed = meta.get("citation_allowed", True)
        base = 0.4 if citation_allowed else 0.0
        return min(1.0, base + tag_score * 0.3 + recency * 0.3)

    # Obsidian note scoring
    chapter_score = _chapter_match(meta.get("chapter"), task_chapter)
    tags = meta.get("tags", [])
    kw = task_keywords or []
    tag_score = _tag_overlap(tags, kw)
    status = _status_score(meta.get("status", "active"))
    note_type = meta.get("type", "")
    type_bonus = _type_bonus(note_type, task_type)

    # Weighted combination
    raw = (
        chapter_score * 0.30
        + tag_score * 0.25
        + status * 0.35
        + type_bonus
    )
    return min(1.0, max(0.0, raw))


def filter_by_metadata(
    sources: list[dict[str, Any]],
    task_spec: dict[str, Any],
    task_keywords: list[str] | None = None,
    threshold: float = 0.1,
) -> list[dict[str, Any]]:
    """Filter and annotate sources by metadata relevance.

    Each source gets annotated with '_metadata_score'.
    Sources below threshold are excluded.

    Returns:
        List of sources that pass the metadata threshold,
        sorted by score descending.
    """
    scored = []
    for source in sources:
        score = score_metadata(source, task_spec, task_keywords)
        annotated = {**source, "_metadata_score": score}
        if score >= threshold:
            scored.append(annotated)

    scored.sort(key=lambda s: s["_metadata_score"], reverse=True)
    return scored
