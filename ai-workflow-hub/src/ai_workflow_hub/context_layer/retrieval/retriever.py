"""
Retriever Orchestrator
Coordinates the full retrieval pipeline:
  privacy filter → metadata filter → keyword scoring → top-k selection

Produces a RetrievalResult containing selected sources and a retrieval trace.
"""
from dataclasses import dataclass, field
from typing import Any

from ai_workflow_hub.context_layer.privacy.privacy_filter import filter_sources
from ai_workflow_hub.context_layer.retrieval.metadata_filter import filter_by_metadata
from ai_workflow_hub.context_layer.retrieval.keyword_scorer import (
    extract_keywords,
    score_keywords,
)
from ai_workflow_hub.context_layer.retrieval.topk_selector import select_topk


@dataclass
class RetrievalResult:
    """Container for retrieval pipeline output."""
    selected_obsidian: list[dict[str, Any]]
    selected_zotero: list[dict[str, Any]]
    retrieval_trace: dict[str, Any]
    privacy_result: dict[str, Any]
    keywords: list[str] = field(default_factory=list)
    metadata_filtered_out: list[str] = field(default_factory=list)

    @property
    def total_selected(self) -> int:
        return len(self.selected_obsidian) + len(self.selected_zotero)

    @property
    def source_manifest_entries(self) -> list[dict[str, Any]]:
        """Build source_manifest entries from selected sources.

        Includes retrieval scores for traceability.
        """
        entries = []
        for source in self.selected_obsidian:
            meta = source.get("metadata", {})
            entries.append({
                "source_type": "obsidian_note",
                "source_id": meta.get("note_id", "unknown"),
                "confidentiality": meta.get("confidentiality", "unknown"),
                "retrieval_score": round(source.get("_final_score", 0.0), 4),
                "retrieval_method": "metadata_filter+keyword_search+topk",
            })
        for source in self.selected_zotero:
            meta = source.get("metadata", {})
            entries.append({
                "source_type": "zotero_reference",
                "source_id": meta.get("citekey", "unknown"),
                "confidentiality": meta.get("confidentiality", "unknown"),
                "retrieval_score": round(source.get("_final_score", 0.0), 4),
                "retrieval_method": "metadata_filter+keyword_search+topk",
            })
        return entries


def retrieve_sources(
    task_spec: dict[str, Any],
    obsidian_records: list[dict[str, Any]],
    zotero_records: list[dict[str, Any]],
    k: int = 5,
    metadata_threshold: float = 0.1,
    min_final_score: float = 0.05,
) -> RetrievalResult:
    """Run the full retrieval pipeline.

    Pipeline:
        1. Privacy filter (fail-closed, excludes sensitive/unknown)
        2. Extract keywords from task spec
        3. Metadata filter (chapter, tags, status, type scoring)
        4. Keyword scoring (text matching)
        5. Top-k selection (weighted combination)

    Args:
        task_spec: Parsed task spec dict.
        obsidian_records: Pre-parsed Obsidian note records.
        zotero_records: Pre-parsed Zotero reference records.
        k: Maximum number of sources to retrieve.
        metadata_threshold: Minimum metadata score to pass metadata filter.
        min_final_score: Minimum final combined score for selection.

    Returns:
        RetrievalResult with selected sources, trace, and metadata.
    """
    # Step 1: Privacy filter
    privacy_result = filter_sources(obsidian_records, zotero_records)
    allowed_obsidian = privacy_result["allowed_obsidian"]
    allowed_zotero = privacy_result["allowed_zotero"]

    # Step 2: Extract keywords from task spec
    keywords = extract_keywords(task_spec)

    # Step 3: Metadata filter (applied to all allowed sources together)
    all_allowed = allowed_obsidian + allowed_zotero
    meta_filtered = filter_by_metadata(
        all_allowed, task_spec, keywords, threshold=metadata_threshold
    )

    # Track which sources were filtered out by metadata
    meta_filtered_ids = set()
    for src in all_allowed:
        meta = src.get("metadata", {})
        sid = meta.get("note_id") or meta.get("citekey") or "unknown"
        if not any(
            (s.get("metadata", {}).get("note_id") or s.get("metadata", {}).get("citekey")) == sid
            for s in meta_filtered
        ):
            meta_filtered_ids.add(sid)

    # Step 4: Keyword scoring (on metadata-filtered sources)
    for source in meta_filtered:
        source["_keyword_score"] = score_keywords(source, keywords)

    # Step 5: Top-k selection
    selection = select_topk(
        meta_filtered,
        k=k,
        min_score=min_final_score,
    )

    # Separate selected sources back into obsidian/zotero
    selected_obsidian = []
    selected_zotero = []
    for source in selection["selected"]:
        meta = source.get("metadata", {})
        if "citekey" in meta:
            selected_zotero.append(source)
        else:
            selected_obsidian.append(source)

    # Build final trace with pipeline metadata
    trace = selection["retrieval_trace"]
    trace["pipeline"] = {
        "privacy_filter": {
            "total_input_obsidian": len(obsidian_records),
            "total_input_zotero": len(zotero_records),
            "allowed_obsidian": len(allowed_obsidian),
            "allowed_zotero": len(allowed_zotero),
            "excluded": privacy_result["excluded_sources"],
        },
        "metadata_filter": {
            "total_input": len(all_allowed),
            "total_passed": len(meta_filtered),
            "filtered_out": list(meta_filtered_ids),
            "threshold": metadata_threshold,
        },
        "keyword_scoring": {
            "keywords_extracted": keywords,
            "total_scored": len(meta_filtered),
        },
        "topk_selection": {
            "k": k,
            "min_final_score": min_final_score,
            "total_selected": trace["total_selected"],
            "total_rejected": trace["total_rejected"],
        },
    }

    return RetrievalResult(
        selected_obsidian=selected_obsidian,
        selected_zotero=selected_zotero,
        retrieval_trace=trace,
        privacy_result=privacy_result,
        keywords=keywords,
        metadata_filtered_out=list(meta_filtered_ids),
    )
