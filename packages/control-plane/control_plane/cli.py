"""CLI entry: devframe init, doctor, run, handoff, pack, and rdgoal."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"  created: {rel}")
    print(f"Project initialized from template '{template}' in {target_dir}")
    return 0


def _pipeline_file_valid(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        from .pipeline_spec import load_pipeline, validate_pipeline
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
    from .pipeline_runner import dry_run as runner_dry_run
    return runner_dry_run(pipeline_path, with_submission=with_submission)


def cmd_handoff_generate(target: str = "new-conversation") -> int:
    from .handoff_generator import generate_handoff
    print(generate_handoff(target))
    return 0


def cmd_handoff_validate(path: str) -> int:
    from .handoff_verifier import validate_handoff
    text = Path(path).read_text(encoding="utf-8")
    ok, errors = validate_handoff(text)
    if ok:
        print("Handoff validation: PASSED")
        return 0
    for error in errors:
        print(f"  FAIL: {error}")
    return 1


def cmd_handoff_bootstrap(target: str = "new-conversation", dry_run: bool = True) -> int:
    from .conversation_bootstrap import run_bootstrap
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

    from .playwright_bridge import BridgeConfig, BridgeMode, health_check as bridge_health, submit_via_bridge
    from .submission_result import SubmissionRequest

    config = BridgeConfig(mode=BridgeMode.LIVE, safety_flag=True, conversation_id=target)
    ok, reason = bridge_health(config)
    if not ok:
        print(f"ERROR: Health check failed: {reason}")
        return 1

    req = SubmissionRequest(review_run_id=handoff_file)
    result = submit_via_bridge(req, config)
    print(f"Transfer result: success={result.success}, mode={result.mode}")
    print(f"Detail: {result.detail}")
    return 0 if result.success else 1


def cmd_pack_validate(zip_path: str) -> int:
    """Validate evidence pack: manifest consistency, no bypass, files present."""
    import subprocess
    import zipfile

    zp = Path(zip_path)
    if not zp.exists():
        print(f"ERROR: ZIP not found: {zip_path}")
        return 1

    errors = 0
    with zipfile.ZipFile(zp, "r") as zf:
        namelist = set(zf.namelist())
        print(f"  ZIP files: {len(namelist)}")

        if "PACK_MANIFEST.md" not in namelist:
            print("  FAIL: PACK_MANIFEST.md not in ZIP")
            errors += 1
        else:
            manifest_text = zf.read("PACK_MANIFEST.md").decode("utf-8")
            manifest_files = set()
            for line in manifest_text.split("\n"):
                if line.startswith("|") and "|" in line[1:]:
                    parts = [p.strip() for p in line.split("|")[1:-1]]
                    if parts and parts[0] and not parts[0].startswith("-"):
                        manifest_files.add(parts[0])
            manifest_files.discard("path")

            extra_in_zip = namelist - manifest_files - {"PACK_MANIFEST.md"}
            extra_in_manifest = manifest_files - namelist
            if extra_in_zip:
                print(f"  FAIL: Files in ZIP but not manifest: {extra_in_zip}")
                errors += 1
            if extra_in_manifest:
                print(f"  FAIL: Files in manifest but not ZIP: {extra_in_manifest}")
                errors += 1
            if not extra_in_zip and not extra_in_manifest:
                print(f"  PASS: Manifest <-> ZIP bidirectional match ({len(manifest_files)} files)")

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

    validator_script = ROOT.parent / "agent-acceptance" / "scripts" / "validate_workflow_closure.py"
    if validator_script.exists():
        print("  Running workflow closure validator...")
        result = subprocess.run(
            [sys.executable, str(validator_script), str(zp)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        print(f"  {result.stdout.strip()}")
        if result.returncode != 0:
            errors += 1
            print("  FAIL: Workflow closure validation failed (SD-01/02/03 check)")
    else:
        print("  FAIL: agent-acceptance validator not found; cannot verify SD-01/02/03")
        errors += 1

    if errors:
        print(f"Pack validation: FAILED ({errors} errors)")
        return 1
    print("Pack validation: PASS")
    return 0


def cmd_rdgoal() -> int:
    from .rdgoal_cli import main as rdgoal_main
    return rdgoal_main(sys.argv[2:])


def main() -> int:
    if len(sys.argv) < 2:
        print("DevFrame Control Plane CLI")
        print("  devframe init [template] [target]  - initialize project")
        print("  devframe doctor                    - check package health")
        print("  devframe rdgoal <project> <goal>   - route work through rdgoal")
        print("  devframe run --pipeline <path>     - run pipeline")
        print("  devframe pack validate <zip>       - validate evidence pack")
        print("  devframe handoff generate          - generate handoff doc")
        print("  devframe handoff validate <file>   - validate handoff")
        print("  devframe handoff bootstrap         - dry-run bootstrap")
        print("  devframe handoff transfer --to <url> [--live --safety-flag] - transfer handoff")
        return 0

    cmd = sys.argv[1]
    if cmd == "handoff":
        sub = sys.argv[2] if len(sys.argv) > 2 else "generate"
        if sub == "generate":
            return cmd_handoff_generate()
        if sub == "validate":
            return cmd_handoff_validate(sys.argv[3]) if len(sys.argv) > 3 else 1
        if sub == "bootstrap":
            return cmd_handoff_bootstrap()
        if sub == "transfer":
            return cmd_handoff_transfer()
        print(f"Unknown handoff subcommand: {sub}")
        return 1

    if cmd == "init":
        template = sys.argv[2] if len(sys.argv) > 2 else "code_project"
        target = sys.argv[3] if len(sys.argv) > 3 else "."
        return cmd_init(template, target)

    if cmd == "rdgoal":
        return cmd_rdgoal()

    if cmd == "doctor":
        return cmd_doctor()

    if cmd == "run":
        if "--pipeline" not in sys.argv:
            print("Usage: devframe run --pipeline <path> [--execute] [--project <dir>]")
            return 1
        index = sys.argv.index("--pipeline")
        path = sys.argv[index + 1]
        with_submission = "--with-submission" in sys.argv
        execute = "--execute" in sys.argv

        if execute:
            from .stage_executor import execute_full_pipeline
            print(f"Pipeline: {path}")
            print("Mode: execute (via framework stage_executor)")
            results = execute_full_pipeline()
            total = len(results)
            completed = sum(1 for result in results if result.status == "completed")
            for result in results:
                status = "PASS" if result.status == "completed" else "FAIL"
                print(f"  [{status}] {result.stage_id} ({len(result.outputs)} outputs)")
            print(f"\nStages: {completed}/{total} completed")
            return 0 if completed == total else 1
        return cmd_run(path, with_submission=with_submission)

    if cmd == "pack":
        sub = sys.argv[2] if len(sys.argv) > 2 else ""
        if sub == "validate":
            if len(sys.argv) < 4:
                print("Usage: devframe pack validate <zip>")
                return 1
            return cmd_pack_validate(sys.argv[3])
        print("Usage: devframe pack validate <zip>")
        return 1

    print(f"Unknown command: {cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
