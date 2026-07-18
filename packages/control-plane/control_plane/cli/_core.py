"""Core devframe commands: init, doctor, run, handoff, pack, rdgoal."""
from __future__ import annotations

from datetime import date
import re
import sys
from pathlib import Path

# Repository package root (the control-plane directory that holds templates/,
# pipelines/, schemas/ and the control_plane package). This module lives one
# level deeper than the old cli.py, so it walks up three parents.
ROOT = Path(__file__).resolve().parent.parent.parent


def _render_template_text(template: str, target_dir: Path, text: str) -> str:
    if template != "paper_iteration":
        return text
    paper_id = re.sub(r"[^A-Za-z0-9._-]+", "-", target_dir.name).strip("-")
    replacements = {
        "{{PAPER_ID}}": paper_id or "paper-project",
        "{{PAPER_TITLE}}": target_dir.name or "Paper Project",
        "{{DATE}}": date.today().isoformat(),
        "{{CURRENT_ITERATION}}": "1",
    }
    for marker, value in replacements.items():
        text = text.replace(marker, value)
    return text


def cmd_init(template: str = "code_project", target: str = ".") -> int:
    tpl_dir = ROOT / "templates" / template
    if not tpl_dir.exists():
        print(f"Unknown template: {template}")
        print(f"Available: {[d.name for d in (ROOT / 'templates').iterdir() if d.is_dir()]}")
        return 1
    target_dir = Path(target).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    for src in tpl_dir.rglob("*"):
        if src.is_file():
            rel = src.relative_to(tpl_dir)
            dst = target_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            text = _render_template_text(
                template,
                target_dir,
                src.read_text(encoding="utf-8"),
            )
            dst.write_text(text, encoding="utf-8")
            print(f"  created: {rel}")
    print(f"Project initialized from template '{template}' in {target_dir}")
    return 0


def _pipeline_file_valid(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        from ..pipeline_spec import load_pipeline, validate_pipeline
        return not validate_pipeline(load_pipeline(path))
    except Exception:
        return False


def cmd_doctor() -> int:
    gitignore_path = ROOT / ".gitignore"
    checks = {
        "templates/code_project/CURRENT_STATE.yaml": (ROOT / "templates" / "code_project" / "CURRENT_STATE.yaml").exists(),
        "templates/code_project/PIPELINE.yaml": _pipeline_file_valid(ROOT / "templates" / "code_project" / "PIPELINE.yaml"),
        "pipelines/example_pipeline.yaml": _pipeline_file_valid(ROOT / "pipelines" / "example_pipeline.yaml"),
        "pipelines/devframe_opencode.yaml": _pipeline_file_valid(ROOT / "pipelines" / "devframe_opencode.yaml"),
        "templates/code_project": (ROOT / "templates" / "code_project").is_dir(),
        "templates/paper_iteration": (ROOT / "templates" / "paper_iteration").is_dir(),
        "templates/context_handoff": (ROOT / "templates" / "context_handoff").is_dir(),
        "templates/visual_control_plane": (ROOT / "templates" / "visual_control_plane").is_dir(),
        "control_plane/rdgoal_cli.py": (ROOT / "control_plane" / "rdgoal_cli.py").exists(),
        ".gitignore covers .env": not gitignore_path.exists() or ".env" in gitignore_path.read_text(encoding="utf-8"),
    }
    passed = sum(1 for ok in checks.values() if ok)
    total = len(checks)
    for name, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}: {name}")
    print(f"Doctor: {passed}/{total} checks passed")
    return 0 if passed == total else 1


def cmd_run(pipeline_path: str, dry_run: bool = True, with_submission: bool = False) -> int:
    from ..pipeline_runner import dry_run as runner_dry_run
    return runner_dry_run(pipeline_path, with_submission=with_submission)


def cmd_handoff_generate(target: str = "new-conversation") -> int:
    from ..handoff_generator import generate_handoff
    print(generate_handoff(target))
    return 0


def cmd_handoff_validate(path: str) -> int:
    from ..handoff_verifier import validate_handoff
    text = Path(path).read_text(encoding="utf-8")
    ok, errors = validate_handoff(text)
    if ok:
        print("Handoff validation: PASSED")
        return 0
    for error in errors:
        print(f"  FAIL: {error}")
    return 1


def cmd_handoff_bootstrap(target: str = "new-conversation", dry_run: bool = True) -> int:
    from ..conversation_bootstrap import run_bootstrap
    result = run_bootstrap(target, dry_run=dry_run)
    print(f"Mode: {result.mode}")
    print(f"Handoff generated: {result.handoff_generated} ({result.handoff_length} chars)")
    print(f"Submitted: {result.submitted}")
    print(f"Reply received: {result.reply_received}")
    print(f"Handoff verified: {result.handoff_verified}")
    return 0 if result.handoff_verified else 1


def cmd_handoff_transfer() -> int:
    """Transfer handoff document. Dry-run by default; --live requires safety flag."""
    import argparse

    parser = argparse.ArgumentParser(prog="devframe handoff transfer")
    parser.add_argument("--to", dest="target_url", default=None, help="Target conversation URL or ID")
    parser.add_argument("--file", dest="handoff_file", default="HANDOFF.md", help="Handoff file to transfer")
    parser.add_argument("--live", dest="live", action="store_true", default=False, help="Execute live CDP transfer")
    parser.add_argument("--safety-flag", dest="safety_flag", action="store_true", default=False, help="Required for live mode")

    args_list = sys.argv[sys.argv.index("transfer") + 1:]
    try:
        parsed = parser.parse_args(args_list)
    except SystemExit:
        return 1

    target = parsed.target_url or "new-conversation"
    handoff_file = parsed.handoff_file

    if not parsed.live:
        print(f"Handoff transfer (dry-run): would upload {handoff_file} to {target}")
        print("  Step 1: Verify HANDOFF.md exists")
        print("  Step 2: CDP connect and navigate to target")
        print("  Step 3: Upload HANDOFF.md as .md file attachment")
        print("  Step 4: Include bootstrap prompt")
        print("  Step 5: Click send")
        print("  Step 6: Capture reply and verify handoff_verified")
        return 0

    if not parsed.safety_flag:
        print("ERROR: --safety-flag required for live CDP transfer")
        return 1

    from ..playwright_bridge import BridgeConfig, BridgeMode, health_check as bridge_health, submit_via_bridge
    from ..submission_result import SubmissionRequest

    config = BridgeConfig(mode=BridgeMode.LIVE, safety_flag=True, conversation_id=target)
    ok, reason = bridge_health(config)
    if not ok:
        print(f"ERROR: Health check failed: {reason}")
        return 1

    req = SubmissionRequest(zip_path=handoff_file, review_run_id=handoff_file)
    result = submit_via_bridge(req, config)
    print(f"Transfer result: success={result.success}, mode={result.mode}")
    print(f"Detail: {result.detail}")
    return 0 if result.success else 1


def cmd_pack_validate(zip_path: str) -> int:
    """Validate evidence pack: manifest consistency, no bypass, files present."""
    import zipfile

    from ..paper_pipeline_gate import (
        scan_submission_bypass,
        validate_evidence_pack,
        validate_paper_task_source,
    )

    zp = Path(zip_path)
    if not zp.exists():
        print(f"ERROR: ZIP not found: {zip_path}")
        return 1

    errors = 0
    pack_result = validate_evidence_pack(zp)
    if not pack_result.passed:
        for error in pack_result.errors:
            print(f"  FAIL: {error}")
        print(f"Pack validation: FAILED ({len(pack_result.errors)} errors)")
        return 1
    print(
        "  PASS: Manifest paths and SHA256 match unique, safe ZIP entries "
        f"({pack_result.details['zip_entries']} files)"
    )

    is_paper_pack = False
    with zipfile.ZipFile(zp, "r") as zf:
        namelist = set(zf.namelist())
        is_paper_pack = "paper_task/PAPER_TASK_INPUT.yaml" in namelist
        print(f"  ZIP files: {len(namelist)}")

        summary_files = {
            "GPT_REVIEW_PROMPT.md",
            "CLOSURE_REPORT.md",
            "CLOSURE_REPORT.yaml",
            "SAFETY_ATTESTATION.md",
            "PACK_MANIFEST.md",
            "WORKFLOW_CLOSURE_VALIDATION.yaml",
        }
        verify_files = {"TEST_OUTPUT.txt", "BYPASS_CHECK_OUTPUT.txt", "GATE_OUTPUT.txt", "DOCTOR_OUTPUT.txt"}
        actual_patterns = [
            "contracts/",
            "schemas/",
            "docs/",
            "templates/",
            "scripts/",
            "tests/",
            "pipelines/",
            "examples/",
            "review/",
            "input/",
            "closure/",
            "submission/",
            "control_plane/",
            "diff.patch",
        ]
        actual_deliverables = [
            file_name for file_name in namelist
            if file_name not in summary_files
            and file_name not in verify_files
            and any(file_name.startswith(pattern.rstrip("/")) or pattern.rstrip("/") in file_name for pattern in actual_patterns)
        ]
        if not actual_deliverables:
            print("  FAIL: Evidence pack is summary-only (no actual deliverables per A1 patterns)")
            errors += 1
        else:
            print(f"  PASS: Contains {len(actual_deliverables)} actual deliverable files (A1 patterns)")

    if is_paper_pack:
        paper_result = validate_paper_task_source(zp)
        if paper_result.passed:
            print("  PASS: Paper task input, output, and privacy boundary")
        else:
            errors += 1
            for error in paper_result.errors:
                print(f"  FAIL: {error}")

    bypass_result = scan_submission_bypass()
    if bypass_result.passed:
        print("  PASS: No unapproved submission path detected")
    else:
        errors += 1
        for error in bypass_result.errors:
            print(f"  FAIL: {error}")

    if errors:
        print(f"Pack validation: FAILED ({errors} errors)")
        return 1
    print("Pack validation: PASS")
    return 0


def cmd_paper_finalize(argv: list[str] | None = None) -> int:
    """Finalize a paper candidate only after explicit independent review."""
    import argparse

    from ..paper_pipeline_gate import finalize_paper_project

    parser = argparse.ArgumentParser(prog="devframe paper finalize")
    parser.add_argument("--project", required=True, help="Initialized paper project directory")
    parser.add_argument("--review", required=True, help="External independent review JSON")
    parser.add_argument(
        "--review-sha256",
        required=True,
        help="Expected SHA-256 of the external review JSON",
    )
    parser.add_argument(
        "--reviewer-id",
        required=True,
        help="Independently attested REVIEW_RUN_ID",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    result = finalize_paper_project(
        args.project,
        args.review,
        args.review_sha256,
        args.reviewer_id,
    )
    if not result.passed:
        for error in result.errors:
            print(f"  FAIL: {error}")
        print("Paper finalization: FAILED")
        return 1
    print(f"  PASS: Independent review {result.details['review_id']}")
    print(f"  FinalVerdict: {result.details['final_verdict']}")
    print("Paper finalization: PASS (accepted_with_limitation)")
    return 0


def cmd_adapter_verify(argv: list[str] | None = None) -> int:
    """Compare two existing canonical executor projections without writing state."""
    import argparse
    import json

    from ..adapter_conformance import verify_adapter_conformance

    parser = argparse.ArgumentParser(prog="devframe adapter verify")
    parser.add_argument("--reference-runtime", required=True)
    parser.add_argument("--candidate-runtime", required=True)
    parser.add_argument("--reference-run-id")
    parser.add_argument("--candidate-run-id")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    result = verify_adapter_conformance(
        args.reference_runtime,
        args.candidate_runtime,
        reference_run_id=args.reference_run_id,
        candidate_run_id=args.candidate_run_id,
    )
    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        for error in result["errors"]:
            print(f"  FAIL: {error}")
        if result["status"] == "pass":
            print(
                "Adapter conformance: PASS "
                f"({result['reference']['run_id']} -> {result['candidate']['run_id']})"
            )
        else:
            print("Adapter conformance: FAILED")
    return 0 if result["status"] == "pass" else 1


def cmd_toolchain_preview(argv: list[str] | None = None) -> int:
    """Validate a toolchain manifest without executing any command."""
    import argparse
    import json

    from ..toolchain_manifest import validate_toolchain_manifest

    parser = argparse.ArgumentParser(prog="devframe toolchain preview")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    result = validate_toolchain_manifest(args.manifest)
    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        for error in result["errors"]:
            print(f"  FAIL: {error}")
        if result["status"] == "pass":
            print(
                "Toolchain manifest: PASS "
                f"({result['toolchain_id']}; execution={result['execution']})"
            )
        else:
            print("Toolchain manifest: FAILED")
    return 0 if result["status"] == "pass" else 1


def cmd_rdgoal() -> int:
    from ..rdgoal_cli import main as rdgoal_main
    return rdgoal_main(sys.argv[2:])
