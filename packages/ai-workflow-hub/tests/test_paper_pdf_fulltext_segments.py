"""Tests for paper_pdf_fulltext_segments adapter.

All tests use injected extractors so no PDF library installation is required.
"""

from __future__ import annotations

import builtins
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from typer.testing import CliRunner

from ai_workflow_hub.cli import app
from ai_workflow_hub.context_layer.adapters.paper_pdf_fulltext_segments import (
    PROFILE,
    SCHEMA_VERSION,
    TASK_ID,
    build_pdf_fulltext_segments_report,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = REPO_ROOT / "schemas" / "paper_pdf_fulltext_segments_report.schema.json"


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate_report(report: dict) -> None:
    schema = _load_schema()
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(report)


_MULTI_PAGE_TEXT = [
    "Abstract\n\nThis paper presents a novel approach to machine learning.",
    "1. Introduction\n\nMachine learning has become a foundational technology.",
    "1.1 Background\n\nPrevious work in this area has focused on supervised methods.",
    "2. Methodology\n\nWe propose a three-stage pipeline for data processing.",
    "2.1 Data Collection\n\nData was collected from public repositories.",
    "2.2 Model Architecture\n\nThe model uses a transformer-based architecture.",
    "3. Results\n\nOur experiments show significant improvement over baselines.",
    "3.1 Quantitative Results\n\nTable 1 shows the main results across all benchmarks.",
    "3.2 Qualitative Analysis\n\nWe also performed a qualitative evaluation.",
    "4. Discussion\n\nThe results suggest that our approach generalizes well.",
    "5. Conclusion\n\nWe have presented an effective method for the task.",
    "References\n\n[1] Smith et al., 2020.\n[2] Jones et al., 2021.",
]


def _fake_extractor(pdf_path: str) -> list[str]:
    return list(_MULTI_PAGE_TEXT)


def _fake_extractor_single_page(pdf_path: str) -> list[str]:
    return ["Simple single page text content for testing."]


def _fake_extractor_empty(pdf_path: str) -> list[str]:
    return []


def _fake_extractor_fails(pdf_path: str) -> list[str]:
    raise RuntimeError("simulated extraction failure")


def _create_fake_pdf(tmp_path: Path) -> Path:
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%fakedata\n")
    return pdf_path


def _create_invalid_pdf(tmp_path: Path) -> Path:
    not_pdf = tmp_path / "not_a.pdf"
    not_pdf.write_text("This is not a PDF file.")
    return not_pdf


class TestCliEntrypoint:
    def test_cli_writes_blocked_json_report_for_invalid_pdf(self, tmp_path):
        not_pdf = _create_invalid_pdf(tmp_path)
        output = tmp_path / "report.json"

        result = CliRunner().invoke(
            app,
            [
                "paper",
                "pdf-fulltext-segments",
                "--pdf-path",
                str(not_pdf),
                "--output",
                str(output),
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        written = json.loads(output.read_text(encoding="utf-8"))
        assert payload["status"] == "BLOCKED"
        assert written == payload
        assert "invalid_pdf_signature" in payload["reasons"]
        assert str(tmp_path) not in result.stdout


class TestSuccessfulInjectedExtraction:
    def test_build_report_with_fake_extractor(self, tmp_path):
        pdf_path = _create_fake_pdf(tmp_path)
        report = build_pdf_fulltext_segments_report(
            pdf_path=pdf_path,
            extractor=_fake_extractor,
        )
        _validate_report(report)
        assert report["profile"] == PROFILE
        assert report["schema_version"] == SCHEMA_VERSION
        assert report["task_id"] == TASK_ID
        assert report["status"] == "PASS_SEGMENTED"
        assert report["backend_available"] is True
        assert report["pdf_page_count"] == len(_MULTI_PAGE_TEXT)
        assert report["segment_count"] > 0
        assert report["privacy_boundary"]["raw_full_text_in_report"] is False
        assert report["privacy_boundary"]["absolute_paths_in_report"] is False
        assert report["segment_text_store_written"] is False

    def test_report_includes_pdf_fingerprint(self, tmp_path):
        pdf_path = _create_fake_pdf(tmp_path)
        report = build_pdf_fulltext_segments_report(
            pdf_path=pdf_path,
            extractor=_fake_extractor,
        )
        assert report["pdf_fingerprint"].startswith("sha256:")
        assert len(report["pdf_fingerprint"]) > 10
        assert report["pdf_path_fingerprint"].startswith("sha256:")
        assert report["pdf_fingerprint"] != report["pdf_path_fingerprint"]

    def test_segments_have_required_fields(self, tmp_path):
        pdf_path = _create_fake_pdf(tmp_path)
        report = build_pdf_fulltext_segments_report(
            pdf_path=pdf_path,
            extractor=_fake_extractor,
        )
        for seg in report["segments"]:
            assert seg["segment_id"].startswith("seg-")
            assert isinstance(seg["section_kind"], str)
            assert len(seg["section_kind"]) > 0
            assert isinstance(seg["page_range"], list)
            assert len(seg["page_range"]) == 2
            assert seg["page_range"][0] >= 1
            assert seg["page_range"][1] >= seg["page_range"][0]
            assert seg["char_count"] >= 1
            assert seg["text_fingerprint"].startswith("sha256:")
            assert isinstance(seg.get("has_text_store", False), bool)

    def test_segments_detect_heading_sections(self, tmp_path):
        pdf_path = _create_fake_pdf(tmp_path)
        report = build_pdf_fulltext_segments_report(
            pdf_path=pdf_path,
            extractor=_fake_extractor,
        )
        kinds_found = {seg["section_kind"] for seg in report["segments"]}
        assert "abstract" in kinds_found
        assert "introduction" in kinds_found
        assert "methodology" in kinds_found
        assert "results" in kinds_found
        assert "discussion" in kinds_found
        assert "conclusion" in kinds_found
        assert "references" in kinds_found

    def test_segments_have_stable_ids(self, tmp_path):
        pdf_path = _create_fake_pdf(tmp_path)
        report_a = build_pdf_fulltext_segments_report(
            pdf_path=pdf_path,
            extractor=_fake_extractor,
        )
        report_b = build_pdf_fulltext_segments_report(
            pdf_path=pdf_path,
            extractor=_fake_extractor,
        )
        ids_a = [seg["segment_id"] for seg in report_a["segments"]]
        ids_b = [seg["segment_id"] for seg in report_b["segments"]]
        assert ids_a == ids_b

    def test_segment_char_count_increases_for_fat_sections(self, tmp_path):
        pdf_path = _create_fake_pdf(tmp_path)
        fat_text = _list_MULTI_PAGE_TEXT() + [
            "6. Extended Discussion\n\n" + ("Extended discussion text. " * 200),
        ]
        report = build_pdf_fulltext_segments_report(
            pdf_path=pdf_path,
            extractor=lambda _p: fat_text,
        )
        assert report["segment_count"] > 0
        max_char = max(seg["char_count"] for seg in report["segments"])
        assert max_char > 1000


class TestOptionalRawSegmentTextStore:
    def test_output_dir_without_write_text_creates_only_minimized_index(self, tmp_path):
        pdf_path = _create_fake_pdf(tmp_path)
        output_dir = tmp_path / "output"
        report = build_pdf_fulltext_segments_report(
            pdf_path=pdf_path,
            extractor=_fake_extractor_single_page,
            output_dir=str(output_dir),
        )
        _validate_report(report)
        assert (output_dir / "segments.index.jsonl").exists()
        assert not (output_dir / "segments-text").exists()
        assert report["segment_index_written"] is True
        assert report["segment_index_fingerprint"].startswith("sha256:")
        assert report["segment_text_store_written"] is False
        assert report["privacy_boundary"]["raw_segment_text_persisted"] is False
        for seg in report["segments"]:
            assert seg["has_text_store"] is False

    def test_output_dir_creates_segment_text_files(self, tmp_path):
        pdf_path = _create_fake_pdf(tmp_path)
        output_dir = tmp_path / "output"
        report = build_pdf_fulltext_segments_report(
            pdf_path=pdf_path,
            extractor=_fake_extractor_single_page,
            output_dir=str(output_dir),
            write_segment_text=True,
        )
        _validate_report(report)
        seg_dir = output_dir / "segments-text"
        assert seg_dir.exists()
        txt_files = list(seg_dir.glob("*.txt"))
        assert len(txt_files) > 0
        for seg in report["segments"]:
            assert seg["has_text_store"] is True
        assert report["segment_text_store_written"] is True
        assert report["segment_text_store_fingerprint"].startswith("sha256:")
        assert report["privacy_boundary"]["raw_segment_text_persisted"] is True

    def test_text_store_files_contain_page_text(self, tmp_path):
        pdf_path = _create_fake_pdf(tmp_path)
        output_dir = tmp_path / "output"
        report = build_pdf_fulltext_segments_report(
            pdf_path=pdf_path,
            extractor=_fake_extractor_single_page,
            output_dir=str(output_dir),
            write_segment_text=True,
        )
        seg_dir = output_dir / "segments-text"
        for seg in report["segments"]:
            seg_path = seg_dir / f"{seg['segment_id']}.txt"
            content = seg_path.read_text(encoding="utf-8")
            assert len(content) > 0

    def test_write_segment_text_requires_output_dir(self, tmp_path):
        pdf_path = _create_fake_pdf(tmp_path)
        report = build_pdf_fulltext_segments_report(
            pdf_path=pdf_path,
            extractor=_fake_extractor_single_page,
            write_segment_text=True,
        )
        _validate_report(report)
        assert report["status"] == "BLOCKED"
        assert report["reasons"] == ["output_dir_required_for_segment_text_store"]
        assert report["segment_text_store_written"] is False


class TestBlockedPaths:
    def test_missing_pdf_path_blocked(self, tmp_path):
        report = build_pdf_fulltext_segments_report(
            pdf_path=tmp_path / "nonexistent.pdf",
            extractor=_fake_extractor,
        )
        _validate_report(report)
        assert report["status"] == "BLOCKED"
        assert "pdf_path_not_found" in report["reasons"]
        assert report["pdf_page_count"] == 0
        assert report["segment_count"] == 0
        assert report["segments"] == []

    def test_invalid_pdf_signature_blocked(self, tmp_path):
        not_pdf = _create_invalid_pdf(tmp_path)
        report = build_pdf_fulltext_segments_report(
            pdf_path=not_pdf,
            extractor=_fake_extractor,
        )
        _validate_report(report)
        assert report["status"] == "BLOCKED"
        assert "invalid_pdf_signature" in report["reasons"]

    def test_missing_backend_blocked_when_no_extractor(self, tmp_path, monkeypatch):
        pdf_path = _create_fake_pdf(tmp_path)

        original_import = builtins.__import__

        def _block_pypdf(name, *args, **kwargs):
            if name == "pypdf":
                raise ImportError("pypdf not available")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _block_pypdf)

        if "pypdf" in sys.modules:
            monkeypatch.setitem(sys.modules, "pypdf", None)

        report = build_pdf_fulltext_segments_report(
            pdf_path=pdf_path,
        )
        _validate_report(report)
        assert report["status"] == "BLOCKED"
        assert report["backend_available"] is False

    def test_deferred_backend_blocks_without_extractor(self, tmp_path):
        pdf_path = _create_fake_pdf(tmp_path)
        report = build_pdf_fulltext_segments_report(
            pdf_path=pdf_path,
            backend="grobid",
        )
        _validate_report(report)
        assert report["status"] == "BLOCKED"
        assert report["reasons"] == ["grobid_backend_deferred"]
        assert report["backend_available"] is False


class TestOptionalRealPdfBackendSmoke:
    def test_pymupdf_backend_segments_generated_pdf_when_available(self, tmp_path):
        fitz = pytest.importorskip("fitz")
        pdf_path = tmp_path / "generated.pdf"
        document = fitz.open()
        page = document.new_page()
        page.insert_text(
            (72, 72),
            "Abstract\nThis generated PDF proves "
            + "real text extraction.\n"
            "1. Introduction\nThe segmentation layer receives real PDF text.",
        )
        document.save(pdf_path)
        document.close()

        report = build_pdf_fulltext_segments_report(
            pdf_path=pdf_path,
            backend="pymupdf",
        )

        _validate_report(report)
        assert report["status"] == "PASS_SEGMENTED"
        assert report["backend"] == "pymupdf"
        assert report["segment_count"] >= 1
        report_json = json.dumps(report)
        assert "generated PDF proves " + "real text extraction" not in report_json
        assert str(tmp_path) not in report_json


class TestPrivacyAndPathSafety:
    def test_report_contains_no_raw_full_text(self, tmp_path):
        pdf_path = _create_fake_pdf(tmp_path)
        report = build_pdf_fulltext_segments_report(
            pdf_path=pdf_path,
            extractor=_fake_extractor,
        )
        _validate_report(report)
        report_json = json.dumps(report)
        assert "presents a novel approach" not in report_json
        assert "become a foundational technology" not in report_json
        assert "was collected from public repositories" not in report_json
        assert report["privacy_boundary"]["raw_full_text_in_report"] is False
        assert report["privacy_boundary"]["raw_segment_text_in_report"] is False

    def test_report_contains_no_absolute_paths(self, tmp_path):
        not_pdf = _create_invalid_pdf(tmp_path)
        report = build_pdf_fulltext_segments_report(
            pdf_path=not_pdf,
            extractor=_fake_extractor,
        )
        _validate_report(report)
        report_json = json.dumps(report)
        abs_not_path = str(tmp_path)
        assert abs_not_path not in report_json
        assert report["privacy_boundary"]["absolute_paths_in_report"] is False

    def test_text_fingerprints_never_leak_text(self, tmp_path):
        pdf_path = _create_fake_pdf(tmp_path)
        report = build_pdf_fulltext_segments_report(
            pdf_path=pdf_path,
            extractor=_fake_extractor,
        )
        for seg in report["segments"]:
            fingerprint = seg["text_fingerprint"]
            assert " " not in fingerprint
            assert len(fingerprint) == 64 + len("sha256:")

    def test_extractor_failure_blocked_no_text_leaked(self, tmp_path):
        pdf_path = _create_fake_pdf(tmp_path)
        report = build_pdf_fulltext_segments_report(
            pdf_path=pdf_path,
            extractor=_fake_extractor_fails,
        )
        _validate_report(report)
        assert report["status"] == "BLOCKED"
        assert report["segment_count"] == 0
        assert report["segments"] == []
        report_json = json.dumps(report)
        assert "novel approach" not in report_json

    def test_empty_extraction_blocks_without_fake_green(self, tmp_path):
        pdf_path = _create_fake_pdf(tmp_path)
        report = build_pdf_fulltext_segments_report(
            pdf_path=pdf_path,
            extractor=_fake_extractor_empty,
        )
        _validate_report(report)
        assert report["status"] == "BLOCKED"
        assert report["reasons"] == ["no_extractable_text"]
        assert report["segment_count"] == 0
        assert report["segments"] == []

    def test_too_short_extraction_blocks_without_segments(self, tmp_path):
        pdf_path = _create_fake_pdf(tmp_path)
        report = build_pdf_fulltext_segments_report(
            pdf_path=pdf_path,
            extractor=lambda _pdf_path: ["Tiny"],
        )
        _validate_report(report)
        assert report["status"] == "BLOCKED"
        assert report["reasons"] == ["no_segments_extracted"]
        assert report["segment_count"] == 0
        assert report["segments"] == []


class TestSchemaValidation:
    def test_schema_validates_pass_report(self, tmp_path):
        pdf_path = _create_fake_pdf(tmp_path)
        report = build_pdf_fulltext_segments_report(
            pdf_path=pdf_path,
            extractor=_fake_extractor,
        )
        _validate_report(report)

    def test_schema_validates_blocked_report(self, tmp_path):
        not_pdf = _create_invalid_pdf(tmp_path)
        report = build_pdf_fulltext_segments_report(
            pdf_path=not_pdf,
            extractor=_fake_extractor,
        )
        _validate_report(report)

    def test_schema_itself_is_valid(self):
        schema = _load_schema()
        Draft202012Validator.check_schema(schema)


def _list_MULTI_PAGE_TEXT() -> list[str]:
    return [
        "Abstract\n\nThis paper presents a novel approach to machine learning.",
        "1. Introduction\n\nMachine learning has become a foundational technology.",
        "1.1 Background\n\nPrevious work in this area has focused on supervised methods.",
        "2. Methodology\n\nWe propose a three-stage pipeline for data processing.",
        "2.1 Data Collection\n\nData was collected from public repositories.",
        "2.2 Model Architecture\n\nThe model uses a transformer-based architecture.",
        "3. Results\n\nOur experiments show significant improvement over baselines.",
        "3.1 Quantitative Results\n\nTable 1 shows the main results across all benchmarks.",
        "3.2 Qualitative Analysis\n\nWe also performed a qualitative evaluation.",
        "4. Discussion\n\nThe results suggest that our approach generalizes well.",
        "5. Conclusion\n\nWe have presented an effective method for the task.",
        "References\n\n[1] Smith et al., 2020.\n[2] Jones et al., 2021.",
    ]
