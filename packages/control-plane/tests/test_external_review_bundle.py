import json
import sys
import zipfile
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from control_plane.external_review_bundle import (  # noqa: E402
    BLOCKED,
    INCOMPLETE,
    READY,
    ReviewBundleError,
    ReviewSource,
    prepare_external_review_bundle,
    validate_external_review_bundle,
)


def test_prepare_review_bundle_is_ready_with_required_roles(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    (project / "rules").mkdir(parents=True)
    (project / "PLAN.md").write_text("# Plan\n", encoding="utf-8")
    (project / "rules" / "core.md").write_text("# Core\n", encoding="utf-8")

    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="review-1",
        review_question="Is the plan complete enough for review?",
        required_roles=["rule", "plan"],
        sources=[
            ReviewSource("rules/core.md", role="rule", authority="stable"),
            ReviewSource("PLAN.md", role="plan", authority="active-plan"),
        ],
    )

    assert result["status"] == READY
    assert result["validator"]["valid"] is True
    zip_path = Path(result["zip_path"])
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        assert "PACK_MANIFEST.json" in names
        assert "CONTEXT_LEDGER.md" in names
        assert "REVIEW_PROMPT.md" in names
        assert "sources/PLAN.md" in names


def test_prepare_review_bundle_records_deterministic_bounded_excerpt(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    source = project / "large.md"
    source.write_text("".join(f"line-{index}\n" for index in range(500)), encoding="utf-8")

    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="bounded-review",
        review_question="Can the bounded excerpt be audited?",
        required_roles=["context"],
        sources=[ReviewSource("large.md", role="context", authority="active")],
        max_source_bytes=240,
        max_total_source_bytes=240,
    )

    assert result["status"] == READY
    assert result["compression"]["policy"] == "deterministic_line_excerpt_v1"
    assert result["compression"]["truncated_sources"] == ["sources/large.md"]
    entry = next(item for item in result["package_files"] if not item["generated"])
    assert entry["compression"] == "line_excerpt"
    assert entry["truncated"] is True
    assert entry["original_size_bytes"] > entry["size_bytes"]
    assert entry["size_bytes"] <= 240
    with zipfile.ZipFile(result["zip_path"], "r") as archive:
        bundled = archive.read("sources/large.md")
    assert len(bundled) == entry["size_bytes"]
    assert b"context excerpt truncated" in bundled
    assert bundled.startswith(b"line-0")
    assert bundled.replace(b"\r\n", b"\n").endswith(b"line-499\n")


def test_prepare_review_bundle_total_budget_reports_omitted_sources(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    (project / "first.md").write_text("first\n", encoding="utf-8")
    (project / "second.md").write_text("second\n", encoding="utf-8")

    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="budget-review",
        review_question="Which context remains?",
        required_roles=["first", "second"],
        sources=[
            ReviewSource("first.md", role="first"),
            ReviewSource("second.md", role="second"),
        ],
        max_source_bytes=100,
        max_total_source_bytes=7,
    )

    assert result["status"] == INCOMPLETE
    assert result["compression"]["included_source_bytes"] == 7
    assert result["compression"]["omitted_sources"] == ["second.md"]
    assert "missing_required_role:second" in result["blocking_issues"]
    assert "context_budget_exhausted:second.md" in result["blocking_issues"]


def test_prepare_review_bundle_rejects_invalid_budgets(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "README.md").write_text("# Read me\n", encoding="utf-8")

    with pytest.raises(ReviewBundleError, match="max_source_bytes must be a positive integer"):
        prepare_external_review_bundle(
            project_root=project,
            review_question="Invalid budget?",
            sources=[ReviewSource("README.md", role="readme")],
            max_source_bytes=0,
        )


def test_prepare_review_bundle_blocks_oversized_binary_source(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    (project / "payload.bin").write_bytes(bytes(range(256)) * 2)

    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="binary-review",
        review_question="Can binary content be bounded?",
        required_roles=["payload"],
        sources=[ReviewSource("payload.bin", role="payload")],
        max_source_bytes=100,
    )

    assert result["status"] == INCOMPLETE
    assert "oversized_binary_source:payload.bin" in result["blocking_issues"]
    assert result["compression"]["included_source_bytes"] == 0


def test_bounded_manifest_matches_public_schema(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    (project / "README.md").write_text("# Read me\n", encoding="utf-8")

    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="schema-review",
        review_question="Does the manifest describe its compression?",
        required_roles=["readme"],
        sources=[ReviewSource("README.md", role="readme")],
    )
    schema_path = Path(__file__).resolve().parents[3] / "schemas" / "external_review_bundle.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft7Validator(schema).validate(
        json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    )


def test_prepare_review_bundle_marks_missing_required_role_incomplete(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    (project / "README.md").write_text("# Map\n", encoding="utf-8")

    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="review-2",
        review_question="Can GPT decide?",
        required_roles=["map", "evidence"],
        sources=[ReviewSource("README.md", role="map", authority="stable")],
    )

    assert result["status"] == INCOMPLETE
    assert result["validator"]["valid"] is False
    assert "missing_required_role:evidence" in result["blocking_issues"]


def test_prepare_review_bundle_blocks_sensitive_source(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    (project / ".env").write_text("OPENAI_API_KEY=sk-secretsecretsecretsecret\n", encoding="utf-8")

    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="review-3",
        review_question="Should this be uploaded?",
        required_roles=["secret"],
        sources=[ReviewSource(".env", role="secret", authority="forbidden")],
    )

    assert result["status"] == BLOCKED
    assert any(issue.startswith("forbidden_sensitive_path") for issue in result["blocking_issues"])


def test_prepare_review_bundle_blocks_nested_archives(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    (project / "old-review.zip").write_bytes(b"PK nested archive")

    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="review-nested",
        review_question="Can this archive be nested?",
        required_roles=["archive"],
        sources=[ReviewSource("old-review.zip", role="archive")],
    )

    assert result["status"] == BLOCKED
    assert "forbidden_nested_archive:old-review.zip" in result["blocking_issues"]


def test_prepare_review_bundle_allows_token_variable_names_without_secret_literals(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    (project / "cli.py").write_text("parser.add_argument('--token')\nvalue = args.token\n", encoding="utf-8")

    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="review-token-variable",
        review_question="Can source code with token variable names be reviewed?",
        required_roles=["code"],
        sources=[ReviewSource("cli.py", role="code")],
    )

    assert result["status"] == READY


def test_prepare_review_bundle_rejects_source_outside_project(tmp_path):
    project = tmp_path / "project"
    outside = tmp_path / "outside.md"
    project.mkdir()
    outside.write_text("outside\n", encoding="utf-8")

    with pytest.raises(ReviewBundleError, match="at least one explicit source"):
        prepare_external_review_bundle(
            project_root=project,
            review_question="No sources",
            sources=[],
            runtime_dir=tmp_path / "runtime",
        )

    result = prepare_external_review_bundle(
        project_root=project,
        review_question="Outside source",
        sources=[ReviewSource(outside, role="outside")],
        runtime_dir=tmp_path / "runtime",
        output_id="review-outside",
    )
    assert result["status"] == BLOCKED
    assert any(issue.startswith("forbidden_path_outside_project") for issue in result["blocking_issues"])


def test_validate_review_bundle_detects_hash_tamper(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    (project / "README.md").write_text("# Map\n", encoding="utf-8")
    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="review-4",
        review_question="Hash check?",
        required_roles=["map"],
        sources=[ReviewSource("README.md", role="map")],
    )
    zip_path = Path(result["zip_path"])
    tampered = tmp_path / "tampered.zip"

    with zipfile.ZipFile(zip_path, "r") as source_zip:
        with zipfile.ZipFile(tampered, "w", zipfile.ZIP_DEFLATED) as target_zip:
            for name in source_zip.namelist():
                payload = b"tampered\n" if name == "sources/README.md" else source_zip.read(name)
                target_zip.writestr(name, payload)

    validation = validate_external_review_bundle(tampered)
    assert validation["valid"] is False
    assert any(issue.startswith("sha256_mismatch") for issue in validation["issues"])
