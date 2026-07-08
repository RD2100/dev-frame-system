"""paper_pdf_fulltext_segments.py -- PDF full-text segmentation adapter.

Builds segment records from an authorized local PDF using a pluggable
extractor backend. Outputs a minimized report with fingerprints and
counts, never raw text.

Design:
  - Thin adapter boundary around a pluggable PDF text extractor.
  - Default backend uses pypdf (BSD-3-Clause) if installed.
  - Injected extractors enable deterministic tests without installing pypdf.
  - Segmentation splits extracted page text into section/chunk records
    with stable ids, page ranges, section_kind, char_count, and text
    fingerprints.
  - The minimized report never includes raw extracted text or absolute paths.
  - Optional raw segment text store writes to a caller-provided output
    directory only when explicitly requested.

Future backends: GROBID, Docling, PyMuPDF (manual only, not default).
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

PROFILE = "paper_pdf_fulltext_segments_report"
SCHEMA_VERSION = "1.0"
TASK_ID = "PAPER_PDF_FULLTEXT_SEGMENTS_A1"

_MIN_SEGMENT_CHARS = 20

_PDF_MAGIC = b"%PDF"

_HEADING_PATTERN = re.compile(
    r"^\s*(?:(?:\d+[\.\)]\s*)+|[IVX]+[\.\)]\s*|[A-Z][\.\)]\s*)?"
    r"(?:(?:abstract|introduction|background|related\s+work|"
    r"method(?:ology|s)?|experiment(?:s|al\s+setup)?|results?(?:\s+and\s+discussion)?|"
    r"discussion|conclusion(?:s)?|"
    r"acknowledgments?|acknowledgements?|"
    r"references|bibliography|appendix|"
    r"future\s+work|limitations?|"
    r"evaluation|implementation|approach|overview|setup)\b)",
    re.IGNORECASE,
)

_HEADING_KEYWORD_KINDS = {
    "abstract": "abstract",
    "introduction": "introduction",
    "background": "introduction",
    "related work": "introduction",
    "related works": "introduction",
    "method": "methodology",
    "methods": "methodology",
    "methodology": "methodology",
    "experiment": "results",
    "experiments": "results",
    "experimental setup": "results",
    "result": "results",
    "results": "results",
    "results and discussion": "results",
    "discussion": "discussion",
    "evaluation": "results",
    "implementation": "methodology",
    "approach": "methodology",
    "overview": "introduction",
    "setup": "methodology",
    "conclusion": "conclusion",
    "conclusions": "conclusion",
    "future work": "discussion",
    "limitation": "discussion",
    "limitations": "discussion",
    "acknowledgments": "appendix",
    "acknowledgements": "appendix",
    "acknowledgment": "appendix",
    "acknowledgement": "appendix",
    "references": "references",
    "bibliography": "references",
    "appendix": "appendix",
}


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _fingerprint_path(path_text: str) -> str:
    return _sha256_text(path_text)


def _generate_segment_id(pdf_fingerprint: str, index: int) -> str:
    prefix = pdf_fingerprint.replace("sha256:", "")[:8]
    return f"seg-{prefix}-{index:04d}"


def _classify_section_kind(heading_text: str) -> str:
    text_lower = heading_text.strip().lower().rstrip(".").rstrip(",").rstrip(":")
    for keyword, kind in _HEADING_KEYWORD_KINDS.items():
        if keyword in text_lower:
            return kind
    return "body"


def _is_heading_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if len(stripped) > 120:
        return False
    if len(stripped) < 3:
        return False
    if _HEADING_PATTERN.match(stripped):
        return True
    word_count = len(stripped.split())
    if word_count <= 8 and word_count >= 2:
        caps_ratio = sum(1 for c in stripped if c.isupper()) / max(1, len(stripped.replace(" ", "")))
        if caps_ratio >= 0.5:
            return True
    if re.match(r"^\s*(?:\d+[\.\)]\s*)+[A-Z]", stripped):
        return True
    if re.match(r"^\s*[A-Z][A-Z\s\-]{3,}$", stripped) and word_count <= 6:
        return True
    return False


def _segment_pages(
    page_texts: list[str],
    pdf_fingerprint: str,
) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    current_heading = ""
    current_section_kind = "body"
    current_start_page: int | None = None
    current_end_page: int | None = None
    current_lines: list[str] = []
    segment_index = 0

    def _flush_segment() -> None:
        nonlocal segment_index
        text = "\n".join(current_lines).strip()
        if not text or len(text) < _MIN_SEGMENT_CHARS:
            return
        if current_start_page is None or current_end_page is None:
            return
        start_page = current_start_page
        segment_id = _generate_segment_id(pdf_fingerprint, segment_index)
        segment_index += 1
        segments.append({
            "segment_id": segment_id,
            "section_kind": current_section_kind,
            "page_range": [start_page + 1, current_end_page + 1],
            "char_count": len(text),
            "text_fingerprint": _sha256_text(text),
            "_text": text,
        })

    for page_idx, page_text in enumerate(page_texts):
        if not page_text.strip():
            continue
        lines = page_text.split("\n")
        for line in lines:
            is_heading = _is_heading_line(line)
            stripped = line.strip()
            if is_heading and stripped.lower() != current_heading.lower():
                _flush_segment()
                current_heading = stripped
                current_section_kind = _classify_section_kind(stripped)
                current_start_page = page_idx
                current_end_page = page_idx
                current_lines = [stripped]
            else:
                if current_start_page is None:
                    current_start_page = page_idx
                    current_heading = ""
                    current_section_kind = "body"
                current_end_page = page_idx
                current_lines.append(line)

    _flush_segment()
    return segments


def _extract_pages_with_pypdf(pdf_path: str) -> list[str]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf_not_installed") from exc

    reader = PdfReader(pdf_path)
    return [page.extract_text() or "" for page in reader.pages]


def _extract_pages_with_pymupdf(pdf_path: str) -> list[str]:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("pymupdf_not_installed") from exc

    document = fitz.open(pdf_path)
    try:
        return [page.get_text("text") or "" for page in document]
    finally:
        document.close()


def _default_extractor(pdf_path: str, backend: str) -> list[str]:
    if backend == "pypdf":
        return _extract_pages_with_pypdf(pdf_path)
    if backend == "pymupdf":
        return _extract_pages_with_pymupdf(pdf_path)
    raise RuntimeError(f"{backend}_backend_deferred")


def _blocked_report(
    generated_at: str,
    reasons: list[str],
    backend: str,
    backend_available: bool,
    pdf_path_present: bool,
    pdf_fingerprint: str = "",
    pdf_path_fingerprint: str = "",
    pdf_page_count: int = 0,
) -> dict[str, Any]:
    return {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "generated_at": generated_at,
        "status": "BLOCKED",
        "reasons": reasons,
        "pdf_path_present": pdf_path_present,
        "pdf_fingerprint": pdf_fingerprint,
        "pdf_path_fingerprint": pdf_path_fingerprint,
        "pdf_page_count": pdf_page_count,
        "segment_count": 0,
        "segment_index_written": False,
        "segment_index_fingerprint": "",
        "segment_text_store_written": False,
        "segment_text_store_fingerprint": "",
        "backend": backend,
        "backend_available": backend_available,
        "segments": [],
        "privacy_boundary": {
            "raw_full_text_in_report": False,
            "raw_segment_text_in_report": False,
            "absolute_paths_in_report": False,
            "raw_segment_text_persisted": False,
            "cloud_called": False,
            "external_parser_service_called": False,
        },
    }


def build_pdf_fulltext_segments_report(
    pdf_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    extractor: Callable[[str], list[str]] | None = None,
    backend: str = "pypdf",
    write_segment_text: bool = False,
) -> dict[str, Any]:
    """Build a minimized PDF full-text segmentation report.

    Extracts text from an authorized PDF using a pluggable backend,
    segments the text into section/chunk records, and returns a report
    with fingerprints and counts. Raw text is never included in the
    report.

    Args:
        pdf_path: Path to the PDF file.
        output_dir: Optional directory to write a minimized segment index.
        extractor: Injected page text extractor callable for testing.
            Must accept a PDF path string and return a list of page text strings.
        backend: Named backend identifier (default: "pypdf").
        write_segment_text: Explicitly write raw segment text to output_dir.
            Defaults to False.

    Returns:
        Segmentation report dict with profile, segments, and privacy boundary.

    Raises:
        FileNotFoundError: If pdf_path does not exist.
    """
    generated_at = _utc_now_text()
    pdf_path_obj = Path(pdf_path)
    backend = backend.lower().strip()

    if write_segment_text and output_dir is None:
        return _blocked_report(
            generated_at=generated_at,
            reasons=["output_dir_required_for_segment_text_store"],
            backend=backend,
            backend_available=extractor is not None,
            pdf_path_present=pdf_path_obj.exists(),
            pdf_path_fingerprint=_fingerprint_path(str(pdf_path_obj.resolve())),
        )

    if not pdf_path_obj.exists():
        return _blocked_report(
            generated_at=generated_at,
            reasons=["pdf_path_not_found"],
            backend=backend,
            backend_available=extractor is not None,
            pdf_path_present=False,
            pdf_path_fingerprint=_fingerprint_path(str(pdf_path_obj.resolve())),
        )

    try:
        pdf_bytes = pdf_path_obj.read_bytes()
    except OSError:
        return _blocked_report(
            generated_at=generated_at,
            reasons=["pdf_path_not_readable"],
            backend=backend,
            backend_available=extractor is not None,
            pdf_path_present=True,
            pdf_path_fingerprint=_fingerprint_path(str(pdf_path_obj.resolve())),
        )

    if not pdf_bytes.startswith(_PDF_MAGIC):
        return _blocked_report(
            generated_at=generated_at,
            reasons=["invalid_pdf_signature"],
            backend=backend,
            backend_available=extractor is not None,
            pdf_path_present=True,
            pdf_path_fingerprint=_fingerprint_path(str(pdf_path_obj.resolve())),
        )

    pdf_fingerprint = _sha256_bytes(pdf_bytes)
    pdf_path_fingerprint = _fingerprint_path(str(pdf_path_obj.resolve()))

    if extractor is not None:
        backend_available = True
        try:
            page_texts = extractor(str(pdf_path_obj))
        except Exception as exc:
            return _blocked_report(
                generated_at=generated_at,
                reasons=[f"extractor_failed:{type(exc).__name__}"],
                backend=backend,
                backend_available=True,
                pdf_path_present=True,
                pdf_fingerprint=pdf_fingerprint,
                pdf_path_fingerprint=pdf_path_fingerprint,
            )
    else:
        try:
            page_texts = _default_extractor(str(pdf_path_obj), backend)
            backend_available = True
        except RuntimeError as exc:
            reason = str(exc) or "backend_not_available"
            return _blocked_report(
                generated_at=generated_at,
                reasons=[reason],
                backend=backend,
                backend_available=False,
                pdf_path_present=True,
                pdf_fingerprint=pdf_fingerprint,
                pdf_path_fingerprint=pdf_path_fingerprint,
            )
        except Exception as exc:
            return _blocked_report(
                generated_at=generated_at,
                reasons=[f"extraction_failed:{type(exc).__name__}"],
                backend=backend,
                backend_available=True,
                pdf_path_present=True,
                pdf_fingerprint=pdf_fingerprint,
                pdf_path_fingerprint=pdf_path_fingerprint,
            )

    page_count = len(page_texts)
    if not any(page_text.strip() for page_text in page_texts):
        return _blocked_report(
            generated_at=generated_at,
            reasons=["no_extractable_text"],
            backend=backend,
            backend_available=backend_available,
            pdf_path_present=True,
            pdf_fingerprint=pdf_fingerprint,
            pdf_path_fingerprint=pdf_path_fingerprint,
            pdf_page_count=page_count,
        )
    internal_segments = _segment_pages(page_texts, pdf_fingerprint)
    if not internal_segments:
        return _blocked_report(
            generated_at=generated_at,
            reasons=["no_segments_extracted"],
            backend=backend,
            backend_available=backend_available,
            pdf_path_present=True,
            pdf_fingerprint=pdf_fingerprint,
            pdf_path_fingerprint=pdf_path_fingerprint,
            pdf_page_count=page_count,
        )

    output_dir_path = Path(output_dir) if output_dir else None
    segment_index_written = False
    segment_index_fingerprint = ""
    segment_text_store_written = False
    segment_text_store_fingerprint = ""
    if output_dir_path is not None:
        output_dir_path.mkdir(parents=True, exist_ok=True)
        index_path = output_dir_path / "segments.index.jsonl"
        text_dir = output_dir_path / "segments-text"
        minimized_lines: list[str] = []
        for seg in internal_segments:
            public_seg = {key: value for key, value in seg.items() if key != "_text"}
            public_seg["has_text_store"] = write_segment_text
            minimized_lines.append(json_dumps_public(public_seg))
            if write_segment_text:
                text_dir.mkdir(parents=True, exist_ok=True)
                (text_dir / f"{seg['segment_id']}.txt").write_text(
                    str(seg["_text"]),
                    encoding="utf-8",
                )
        index_path.write_text("\n".join(minimized_lines) + ("\n" if minimized_lines else ""), encoding="utf-8")
        segment_index_written = True
        segment_index_fingerprint = _sha256_file(index_path)
        if write_segment_text:
            segment_text_store_written = True
            segment_text_store_fingerprint = _fingerprint_path(str(text_dir.resolve()))

    segments: list[dict[str, Any]] = []
    for seg in internal_segments:
        public_seg = {key: value for key, value in seg.items() if key != "_text"}
        public_seg.setdefault("has_text_store", segment_text_store_written)
        segments.append(public_seg)

    return {
        "profile": PROFILE,
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "generated_at": generated_at,
        "status": "PASS_SEGMENTED",
        "reasons": [],
        "pdf_path_present": True,
        "pdf_fingerprint": pdf_fingerprint,
        "pdf_path_fingerprint": pdf_path_fingerprint,
        "pdf_page_count": page_count,
        "segment_count": len(segments),
        "segment_index_written": segment_index_written,
        "segment_index_fingerprint": segment_index_fingerprint,
        "segment_text_store_written": segment_text_store_written,
        "segment_text_store_fingerprint": segment_text_store_fingerprint,
        "backend": backend,
        "backend_available": backend_available,
        "segments": segments,
        "privacy_boundary": {
            "raw_full_text_in_report": False,
            "raw_segment_text_in_report": False,
            "absolute_paths_in_report": False,
            "raw_segment_text_persisted": segment_text_store_written,
            "cloud_called": False,
            "external_parser_service_called": False,
        },
    }


def json_dumps_public(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, sort_keys=True, ensure_ascii=False)
