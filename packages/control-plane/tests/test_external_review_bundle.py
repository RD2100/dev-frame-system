import sys
import zipfile
from pathlib import Path

import pytest

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
    (project / "docs").mkdir(parents=True)
    (project / "docs" / "README.md").write_text("# Map\n", encoding="utf-8")
    (project / "docs" / "PLAN.md").write_text("# Plan\n", encoding="utf-8")

    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="review-1",
        review_question="Is the plan complete enough for review?",
        required_roles=["map", "plan"],
        sources=[
            ReviewSource("docs/README.md", role="map", authority="stable"),
            ReviewSource("docs/PLAN.md", role="plan", authority="active-plan"),
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
        assert "sources/docs/README.md" in names


def test_prepare_review_bundle_prompts_for_earliest_async_state_boundary(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    (project / "handler.js").write_text("async function load() {}\n", encoding="utf-8")

    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="async-state-review",
        review_question="Is this latest-wins state handler race-safe?",
        required_roles=["code"],
        sources=[ReviewSource("handler.js", role="code")],
    )

    prompt_path = Path(result["manifest_path"]).parent / "REVIEW_PROMPT.md"
    prompt = prompt_path.read_text(encoding="utf-8").lower()

    assert "async latest-wins state handler" in prompt
    assert "otherwise skip this section" in prompt
    assert "earliest await capable of producing page or application state" in prompt
    assert "out-of-order success" in prompt
    assert "out-of-order failure or rejection" in prompt
    assert "downstream-only deferral is insufficient" in prompt
    assert "ownership or generation" in prompt
    assert "below an upstream await" in prompt
    assert "fail the review" in prompt
    assert "two or more awaits" in prompt
    assert "tests control only the later await" in prompt
    assert "warn when" in prompt


def test_prepare_review_bundle_prompts_for_awaited_downstream_operation_completion(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    (project / "handler.js").write_text("async function load() {}\n", encoding="utf-8")

    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="downstream-completion-review",
        review_question="Does this handler remain busy until downstream refreshes finish?",
        required_roles=["code"],
        sources=[ReviewSource("handler.js", role="code")],
    )

    prompt_path = Path(result["manifest_path"]).parent / "REVIEW_PROMPT.md"
    prompt = prompt_path.read_text(encoding="utf-8").lower()

    assert "releases busy or lock in a finally block" in prompt
    assert (
        "every downstream promise-returning `load*` or `refresh*` boundary that "
        "defines operation completion is awaited or returned"
    ) in prompt
    assert "require a deferred probe at each such completion boundary" in prompt
    assert "downstream-only or mutation-only evidence is insufficient" in prompt


def test_prepare_review_bundle_prompts_for_navigation_return_single_flight(tmp_path):
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    (project / "handler.js").write_text("async function navigate() {}\n", encoding="utf-8")

    result = prepare_external_review_bundle(
        project_root=project,
        runtime_dir=runtime,
        output_id="navigation-return-review",
        review_question="Does navigation preserve single-flight ownership until return?",
        required_roles=["code"],
        sources=[ReviewSource("handler.js", role="code")],
    )

    prompt_path = Path(result["manifest_path"]).parent / "REVIEW_PROMPT.md"
    prompt = prompt_path.read_text(encoding="utf-8").lower()

    assert "conditional navigation single-flight review" in prompt
    assert "across navigation; otherwise skip this section" in prompt
    assert "`navigateto`/`navigateback` return lifecycle" in prompt
    assert "`redirectto`/`switchtab`/`relaunch` unload lifecycle" in prompt
    assert "busy or token remains held after a successful `navigateto`" in prompt
    assert "synchronous double-trigger probe" in prompt
    assert "success -> `onhide` -> `onshow` -> retry probe" in prompt
    assert "failure -> retry probe" in prompt
    assert "unload-stale probe" in prompt
    assert "lifecycle methods must release the return lock" in prompt
    assert "direct test-only state mutation is insufficient" in prompt


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
