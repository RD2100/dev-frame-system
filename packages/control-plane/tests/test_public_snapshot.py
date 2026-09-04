from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import uuid

from jsonschema import Draft7Validator, Draft202012Validator
import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
CONTROL_PLANE_TEMPLATES = REPO_ROOT / "packages" / "control-plane" / "templates"
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release-verify.yml"
REVIEWER_INDEX_REQUIRED_PATHS = [
    "PLAN.md",
    "AGENTS.md",
    ".github/workflows/release-verify.yml",
    "packages/control-plane/setup.py",
    "packages/control-plane/control_plane/cli/app.py",
    "packages/control-plane/control_plane/dashboard.py",
    "packages/control-plane/templates/paper_iteration/PAPER_PROFILE.yaml",
    "packages/control-plane/templates/paper_iteration/PAPER_STATE.yaml",
    "packages/control-plane/templates/visual_control_plane/CONTROL_PLANE_STATE.yaml",
    "packages/control-plane/templates/paper_iteration/WEB_AI_ADAPTER.yaml",
    "packages/control-plane/control_plane/agent_adapter.py",
    "packages/control-plane/control_plane/backup_guard.py",
    "packages/control-plane/control_plane/decision_engine.py",
    "packages/control-plane/control_plane/dispatch_packet.py",
    "packages/control-plane/control_plane/docs_drift_validator.py",
    "packages/control-plane/control_plane/orchestrator.py",
    "packages/control-plane/control_plane/project_contract.py",
    "packages/control-plane/control_plane/rdgoal.py",
    "packages/control-plane/control_plane/rdgoal_cli.py",
    "packages/control-plane/control_plane/rdreview.py",
    "packages/control-plane/control_plane/evidence_gate.py",
    "packages/control-plane/control_plane/runtime_digest.py",
    "packages/control-plane/control_plane/runtime_store.py",
    "packages/control-plane/control_plane/visual_state.py",
    "packages/control-plane/control_plane/worker.py",
    "packages/control-plane/tests/test_cli.py",
    "packages/control-plane/tests/test_docs_drift_validator.py",
    "packages/control-plane/tests/test_public_snapshot.py",
    "packages/control-plane/tests/test_rdgoal.py",
    "packages/control-plane/tests/test_rdreview.py",
    "packages/control-plane/tests/test_evidence_gate.py",
    "tests/test_go_evidence.py",
    "tools/go_evidence.py",
    "pytest.ini",
    "rules/orchestration.md",
    "rules/project-contracts/_template.md",
    "rules/web-ai-adapters.md",
    "schemas/project_contract.schema.json",
    "schemas/rdgoal_dispatch_packet.schema.json",
    "schemas/runtime-governance/context-packet.schema.json",
    "schemas/runtime-governance/context-ledger.schema.json",
    "schemas/runtime-governance/run-record.schema.json",
    "packages/test-frame/schemas/runtime-governance/context-packet.schema.json",
    "packages/test-frame/schemas/runtime-governance/context-ledger.schema.json",
    "packages/test-frame/schemas/runtime-governance/run-record.schema.json",
    "schemas/examples/runtime-governance/context-packet-valid.json",
    "schemas/examples/runtime-governance/context-packet-stale-valid.json",
    "schemas/examples/runtime-governance/context-ledger-valid.json",
    "schemas/examples/runtime-governance/context-packet-worker-final-ready-invalid.json",
    "schemas/examples/runtime-governance/context-packet-text-final-ready-invalid.json",
    "schemas/examples/runtime-governance/context-ledger-mutable-invalid.json",
    "schemas/examples/runtime-governance/run-record-review-pending-valid.json",
    "schemas/examples/runtime-governance/run-record-worker-final-ready-invalid.json",
    "schemas/examples/runtime-governance/run-record-gate-pass-missing-evidence-invalid.json",
    "schemas/examples/runtime-governance/run-record-executor-review-invalid.json",
    "schemas/examples/runtime-governance/run-record-executor-final-verdict-invalid.json",
    "schemas/examples/runtime-governance/run-record-projection-completed-invalid.json",
    "schemas/examples/runtime-governance/run-record-projection-completed-projection-only-valid.json",
    "schemas/examples/runtime-governance/run-record-test-frame-passed-missing-context-invalid.json",
    "schemas/examples/runtime-governance/run-record-test-frame-code-review-pass-missing-review-invalid.json",
    "schemas/examples/runtime-governance/run-record-final-report-pass-missing-final-verdict-invalid.json",
    "schemas/examples/runtime-governance/run-record-paper-human-required-valid.json",
    "schemas/examples/runtime-governance/run-record-paper-blocked-chain-trusted-valid.json",
    "schemas/examples/runtime-governance/run-record-unknown-domain-status-valid.json",
    "schemas/visual_control_plane_state.schema.json",
    "schemas/web_ai_adapter.schema.json",
    "scripts/verify-control-plane-wheel.ps1",
    "scripts/verify-public-snapshot.ps1",
    "scripts/verify-release.ps1",
]
PUBLIC_MARKDOWN_DOCS = [
    REPO_ROOT / "PLAN.md",
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "rules" / "core.md",
    REPO_ROOT / "rules" / "orchestration.md",
    REPO_ROOT / "rules" / "web-ai-adapters.md",
]
DOC_LINK_CHECK_MARKDOWN_DOCS = [
    REPO_ROOT / "PLAN.md",
    REPO_ROOT / "AGENTS.md",
]
LIFECYCLE_REQUIRED_STATUS_DOCS = [
    REPO_ROOT / "PLAN.md",
]
MARKDOWN_LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
FENCED_CODE_BLOCK_PATTERN = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_PATTERN = re.compile(r"`[^`\n]*`")


def _relative_markdown_links_from_text(text):
    text = FENCED_CODE_BLOCK_PATTERN.sub("", text)
    text = INLINE_CODE_PATTERN.sub("", text)
    for match in MARKDOWN_LINK_PATTERN.finditer(text):
        target = match.group(1).strip()
        if not target:
            continue
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1].strip()
        elif " " in target:
            target = target.split()[0]
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = target.split("#", 1)[0].strip()
        if target:
            yield target


def _relative_markdown_links(path):
    text = path.read_text(encoding="utf-8-sig")
    yield from _relative_markdown_links_from_text(text)


def _json_semantics(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_minimal_public_snapshot_fixture(root):
    for relative in [
        "packages/agent-acceptance",
        "packages/ai-workflow-hub",
        "packages/control-plane",
        "packages/test-frame",
        "schemas",
        "templates/runtime-bootstrap",
    ]:
        (root / relative).mkdir(parents=True, exist_ok=True)

    files = {
        "PLAN.md": "# Plan\n\nCurrent verdict: **candidate**\n\n## 15. Documentation Policy\n",
        "AGENTS.md": "Read PLAN.md; rules/recon.md; only human development authority",
        ".github/workflows/release-verify.yml": "",
        "packages/agent-acceptance/fixtures/negative-acceptance/NEG-031-missing-recon-receipt.json": '{"name": "Missing Recon Receipt"}',
        "rules/open-source-reuse.md": "rules/recon.md",
        "rules/recon.md": "RULE recon-001: Recon Gate Before Write-Capable Work",
        "scripts/verify-control-plane-wheel.ps1": "",
        "scripts/verify-release.ps1": "",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    shutil.copy2(
        REPO_ROOT / "scripts" / "verify-public-snapshot.ps1",
        root / "scripts" / "verify-public-snapshot.ps1",
    )


def _powershell_command_argument(value):
    value = str(value)
    if re.fullmatch(r"-[A-Za-z][A-Za-z0-9]*", value):
        return value
    return "'" + value.replace("'", "''") + "'"


def _run_public_snapshot(root, *args, cwd=None, script_root=None, env=None):
    script_root = root if script_root is None else script_root
    script_path = script_root / "scripts" / "verify-public-snapshot.ps1"
    command = " ".join(
        [
            "[Console]::OutputEncoding = "
            "[System.Text.UTF8Encoding]::new($false);",
            "&",
            _powershell_command_argument(script_path),
            *(_powershell_command_argument(arg) for arg in args),
            "; exit $LASTEXITCODE",
        ]
    )
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        cwd=root if cwd is None else cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=60,
        check=False,
        env=env,
    )


def _make_directory_junction(link_path, target_path):
    result = subprocess.run(
        ["cmd", "/d", "/c", "mklink", "/J", str(link_path), str(target_path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_public_snapshot_defaults_to_checkout_containing_script(tmp_path):
    snapshot_root = tmp_path / "clean export"
    caller_root = tmp_path / "caller"
    snapshot_root.mkdir()
    caller_root.mkdir()
    (caller_root / ".agents").mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)

    result = _run_public_snapshot(snapshot_root, cwd=caller_root)

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "[OK] Public snapshot required paths are present." in output
    assert ".agents" not in output


def test_public_snapshot_explicit_root_overrides_script_checkout(tmp_path):
    script_home = tmp_path / "script home"
    explicit_root = tmp_path / "explicit root"
    caller_root = tmp_path / "caller"
    (script_home / "scripts").mkdir(parents=True)
    explicit_root.mkdir()
    caller_root.mkdir()
    _write_minimal_public_snapshot_fixture(explicit_root)
    shutil.copy2(
        REPO_ROOT / "scripts" / "verify-public-snapshot.ps1",
        script_home / "scripts" / "verify-public-snapshot.ps1",
    )

    result = _run_public_snapshot(
        explicit_root,
        "-Root",
        str(explicit_root),
        cwd=caller_root,
        script_root=script_home,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "[OK] Public snapshot required paths are present." in output


@pytest.mark.skipif(os.name != "nt", reason="Windows junction contract")
def test_public_snapshot_rejects_explicit_root_junction(tmp_path):
    script_home = tmp_path / "script home"
    snapshot_target = tmp_path / "snapshot target"
    root_junction = tmp_path / "snapshot-link"
    (script_home / "scripts").mkdir(parents=True)
    snapshot_target.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_target)
    shutil.copy2(
        REPO_ROOT / "scripts" / "verify-public-snapshot.ps1",
        script_home / "scripts" / "verify-public-snapshot.ps1",
    )
    _make_directory_junction(root_junction, snapshot_target)

    result = _run_public_snapshot(
        snapshot_target,
        "-Root",
        str(root_junction),
        cwd=tmp_path,
        script_root=script_home,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "[PUBLIC-SNAPSHOT-FAIL] root contains reparse point" in output
    assert str(snapshot_target) not in output


@pytest.mark.skipif(os.name != "nt", reason="Windows junction contract")
def test_public_snapshot_rejects_directory_junction_without_scanning_target(tmp_path):
    snapshot_root = tmp_path / "clean export"
    outside_root = tmp_path / "outside"
    snapshot_root.mkdir()
    outside_root.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    (outside_root / "outside-payload.zip").write_bytes(b"synthetic-outside-bytes")
    junction_path = snapshot_root / "linked-external"
    _make_directory_junction(junction_path, outside_root)

    result = _run_public_snapshot(snapshot_root)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "[PUBLIC-SNAPSHOT-FAIL] reparse point: linked-external" in output
    assert "outside-payload.zip" not in output


@pytest.mark.skipif(os.name != "nt", reason="Windows symlink contract")
def test_public_snapshot_rejects_file_symlink_without_reading_target(tmp_path):
    snapshot_root = tmp_path / "clean export"
    outside_file = tmp_path / "outside-private.txt"
    snapshot_root.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    outside_file.write_text("synthetic-private-target", encoding="utf-8")
    link_path = snapshot_root / "linked-file.txt"
    try:
        link_path.symlink_to(outside_file)
    except OSError as exc:
        pytest.skip(f"file symlink unavailable: {exc.winerror}")

    result = _run_public_snapshot(snapshot_root)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "[PUBLIC-SNAPSHOT-FAIL] reparse point: linked-file.txt" in output
    assert "synthetic-private-target" not in output


@pytest.mark.skipif(os.name != "nt", reason="Windows junction contract")
def test_public_snapshot_rejects_git_junction_before_invoking_git(tmp_path):
    snapshot_root = tmp_path / "clean export"
    outside_git = tmp_path / "outside-git"
    snapshot_root.mkdir()
    outside_git.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    _make_directory_junction(snapshot_root / ".git", outside_git)

    result = _run_public_snapshot(snapshot_root)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "[PUBLIC-SNAPSHOT-FAIL] reparse point: .git" in output
    assert "unable to verify tracked sensitive config metadata" not in output


def test_public_snapshot_redacts_invalid_git_metadata_failure(tmp_path):
    snapshot_root = tmp_path / "clean export"
    snapshot_root.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    (snapshot_root / ".git").mkdir()

    result = _run_public_snapshot(snapshot_root)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert output.strip() == (
        "[PUBLIC-SNAPSHOT-FAIL] unable to verify tracked sensitive config metadata"
    )
    assert str(snapshot_root) not in output
    assert "fatal:" not in output


def test_public_snapshot_redacts_missing_git_invocation_failure(tmp_path):
    snapshot_root = tmp_path / "clean export"
    empty_bin = tmp_path / "empty-bin"
    snapshot_root.mkdir()
    empty_bin.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    (snapshot_root / ".git").mkdir()
    env = os.environ.copy()
    env["PATH"] = str(empty_bin)

    result = _run_public_snapshot(snapshot_root, env=env)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert output.strip() == (
        "[PUBLIC-SNAPSHOT-FAIL] unable to verify tracked sensitive config metadata"
    )
    assert str(snapshot_root) not in output
    assert "git" not in output.lower()


@pytest.mark.skipif(os.name != "nt", reason="Windows native Git failure contract")
def test_public_snapshot_redacts_strict_git_metadata_failure(tmp_path):
    snapshot_root = tmp_path / "clean export"
    fake_bin = tmp_path / "fake-bin"
    snapshot_root.mkdir()
    fake_bin.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    (snapshot_root / ".git").mkdir()
    (fake_bin / "git.cmd").write_text(
        "@echo off\n"
        "echo %* | %SystemRoot%\\System32\\findstr.exe "
        '"opencode.config.json" >nul\n'
        "if not errorlevel 1 exit /b 0\n"
        "echo SYNTHETIC_GIT_STDOUT\n"
        ">&2 echo SYNTHETIC_GIT_STDERR\n"
        "exit /b 7\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")

    result = _run_public_snapshot(
        snapshot_root,
        "-FailOnTrackedForbidden",
        env=env,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert output.strip() == (
        "[PUBLIC-SNAPSHOT-FAIL] unable to verify tracked sensitive config metadata"
    )
    assert "SYNTHETIC_GIT_STDOUT" not in output
    assert "SYNTHETIC_GIT_STDERR" not in output
    assert str(snapshot_root) not in output


@pytest.mark.skipif(os.name != "nt", reason="Windows native Git output contract")
@pytest.mark.parametrize(
    ("record_length", "expected_error"),
    [
        (
            4096,
            "[PUBLIC-SNAPSHOT-FAIL] tracked sensitive config: opencode.config.json",
        ),
        (
            4097,
            "[PUBLIC-SNAPSHOT-FAIL] unable to verify tracked sensitive config metadata",
        ),
    ],
)
def test_public_snapshot_bounds_sensitive_git_record_length(
    tmp_path,
    record_length,
    expected_error,
):
    snapshot_root = tmp_path / "clean export"
    fake_bin = tmp_path / "fake-bin"
    snapshot_root.mkdir()
    fake_bin.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    (snapshot_root / ".git").mkdir()
    (fake_bin / "git.cmd").write_text(
        "@echo off\n"
        "%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe "
        "-NoProfile -Command \"[Console]::OutputEncoding = "
        "[System.Text.UTF8Encoding]::new($false); "
        f"[Console]::Out.WriteLine(('x' * {record_length}))\"\n"
        "exit /b 0\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")

    result = _run_public_snapshot(snapshot_root, env=env)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert output.strip() == expected_error
    assert "x" * 100 not in output


@pytest.mark.skipif(os.name != "nt", reason="Windows native Git output contract")
def test_public_snapshot_rejects_late_oversized_strict_git_record(tmp_path):
    snapshot_root = tmp_path / "clean export"
    fake_bin = tmp_path / "fake-bin"
    snapshot_root.mkdir()
    fake_bin.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    (snapshot_root / ".git").mkdir()
    (fake_bin / "git.cmd").write_text(
        "@echo off\n"
        "echo %* | %SystemRoot%\\System32\\findstr.exe "
        '"opencode.config.json" >nul\n'
        "if not errorlevel 1 exit /b 0\n"
        "%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe "
        "-NoProfile -Command \"[Console]::OutputEncoding = "
        "[System.Text.UTF8Encoding]::new($false); "
        "1..65 | ForEach-Object { "
        "[Console]::Out.WriteLine(('products/item-{0:D3}.txt' -f $_)) }; "
        "[Console]::Out.WriteLine(('SYNTHETIC_LATE_GIT_SECRET' + "
        "('x' * 5000)))\"\n"
        "exit /b 0\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")

    result = _run_public_snapshot(
        snapshot_root,
        "-FailOnTrackedForbidden",
        env=env,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert output.strip() == (
        "[PUBLIC-SNAPSHOT-FAIL] unable to verify tracked sensitive config metadata"
    )
    assert "products/item-001.txt" not in output
    assert "SYNTHETIC_LATE_GIT_SECRET" not in output
    assert "x" * 100 not in output


@pytest.mark.skipif(os.name != "nt", reason="Windows native Git output contract")
def test_public_snapshot_preserves_sensitive_whitespace_output_truth(tmp_path):
    snapshot_root = tmp_path / "clean export"
    fake_bin = tmp_path / "fake-bin"
    snapshot_root.mkdir()
    fake_bin.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    (snapshot_root / ".git").mkdir()
    (fake_bin / "git.cmd").write_text(
        "@echo off\n"
        "%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe "
        "-NoProfile -Command \"[Console]::Out.WriteLine('   ')\"\n"
        "exit /b 0\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")

    result = _run_public_snapshot(snapshot_root, env=env)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert output.strip() == (
        "[PUBLIC-SNAPSHOT-FAIL] tracked sensitive config: opencode.config.json"
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows native Git output contract")
def test_public_snapshot_excludes_whitespace_from_strict_git_retention(tmp_path):
    snapshot_root = tmp_path / "clean export"
    fake_bin = tmp_path / "fake-bin"
    snapshot_root.mkdir()
    fake_bin.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    (snapshot_root / ".git").mkdir()
    (fake_bin / "git.cmd").write_text(
        "@echo off\n"
        "echo %* | %SystemRoot%\\System32\\findstr.exe "
        '"opencode.config.json" >nul\n'
        "if not errorlevel 1 exit /b 0\n"
        "%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe "
        "-NoProfile -Command \"1..70 | ForEach-Object { "
        "[Console]::Out.WriteLine('   ') }; "
        "[Console]::Out.WriteLine('products/after-whitespace.txt')\"\n"
        "exit /b 0\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")

    result = _run_public_snapshot(
        snapshot_root,
        "-FailOnTrackedForbidden",
        env=env,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert output.strip() == (
        "[PUBLIC-SNAPSHOT-FAIL] tracked bundled product: "
        "products/after-whitespace.txt"
    )
    assert "additional tracked path failures omitted" not in output


@pytest.mark.skipif(os.name != "nt", reason="Windows junction contract")
def test_public_snapshot_rejects_required_directory_junction_before_reading_target(tmp_path):
    snapshot_root = tmp_path / "clean export"
    outside_rules = tmp_path / "outside-rules"
    snapshot_root.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    shutil.copytree(snapshot_root / "rules", outside_rules)
    shutil.rmtree(snapshot_root / "rules")
    _make_directory_junction(snapshot_root / "rules", outside_rules)

    result = _run_public_snapshot(snapshot_root)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "[PUBLIC-SNAPSHOT-FAIL] reparse point: rules" in output
    assert str(outside_rules) not in output


@pytest.mark.skipif(os.name != "nt", reason="Windows junction contract")
def test_public_snapshot_rejects_required_text_junction_before_reading_target(tmp_path):
    snapshot_root = tmp_path / "clean export"
    outside_fixtures = tmp_path / "outside-fixtures"
    snapshot_root.mkdir()
    outside_fixtures.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    fixture_dir = (
        snapshot_root
        / "packages"
        / "agent-acceptance"
        / "fixtures"
        / "negative-acceptance"
    )
    shutil.rmtree(fixture_dir)
    (outside_fixtures / "NEG-031-missing-recon-receipt.json").write_text(
        "synthetic-private-target",
        encoding="utf-8",
    )
    _make_directory_junction(fixture_dir, outside_fixtures)

    result = _run_public_snapshot(snapshot_root)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert (
        "[PUBLIC-SNAPSHOT-FAIL] reparse point: "
        "packages\\agent-acceptance\\fixtures\\negative-acceptance"
    ) in output
    assert "[TEXT-FAIL]" not in output
    assert "synthetic-private-target" not in output


@pytest.mark.skipif(os.name != "nt", reason="Windows device-path contract")
def test_public_snapshot_rejects_device_root_before_filesystem_access(tmp_path):
    script_home = tmp_path / "script home"
    (script_home / "scripts").mkdir(parents=True)
    shutil.copy2(
        REPO_ROOT / "scripts" / "verify-public-snapshot.ps1",
        script_home / "scripts" / "verify-public-snapshot.ps1",
    )
    device_root = r"\\?\C:\devframe-public-snapshot-probe"

    result = _run_public_snapshot(
        tmp_path,
        "-Root",
        device_root,
        cwd=tmp_path,
        script_root=script_home,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert output.strip() == "[PUBLIC-SNAPSHOT-FAIL] invalid root"
    assert device_root not in output


def test_public_snapshot_rejects_tracked_opencode_config_before_content_scan(tmp_path):
    _write_minimal_public_snapshot_fixture(tmp_path)
    config_path = tmp_path / "opencode.config.json"
    config_path.write_text("synthetic-invalid-json-placeholder", encoding="utf-8")

    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "--", config_path.name], cwd=tmp_path, check=True)
    result = _run_public_snapshot(tmp_path)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "tracked sensitive config: opencode.config.json" in output
    assert "[JSON-FAIL]" not in output
    assert "synthetic-invalid-json-placeholder" not in output


def test_public_snapshot_ignores_local_claude_worktrees_but_rejects_tracked_state(tmp_path):
    _write_minimal_public_snapshot_fixture(tmp_path)
    state_path = tmp_path / ".claude" / "worktrees" / "local" / "state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text('{"local": true}', encoding="utf-8")

    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    untracked_result = _run_public_snapshot(tmp_path)
    assert untracked_result.returncode == 0, untracked_result.stdout + untracked_result.stderr

    subprocess.run(["git", "add", "--", state_path.relative_to(tmp_path)], cwd=tmp_path, check=True)
    tracked_result = _run_public_snapshot(tmp_path)
    output = tracked_result.stdout + tracked_result.stderr
    assert tracked_result.returncode == 1, output
    assert output.strip() == "[PUBLIC-SNAPSHOT-FAIL] tracked local agent state: .claude"


def test_gitignore_keeps_root_opencode_config_local(tmp_path):
    shutil.copy2(REPO_ROOT / ".gitignore", tmp_path / ".gitignore")
    root_config = tmp_path / "opencode.config.json"
    nested_config = tmp_path / "nested" / "opencode.config.json"
    root_config.write_text("synthetic-local-config-placeholder", encoding="utf-8")
    nested_config.parent.mkdir()
    nested_config.write_text("synthetic-nested-config-placeholder", encoding="utf-8")

    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    root_result = subprocess.run(
        ["git", "check-ignore", "--quiet", "--no-index", "--", root_config.name],
        cwd=tmp_path,
        check=False,
    )
    nested_result = subprocess.run(
        ["git", "check-ignore", "--quiet", "--no-index", "--", "nested/opencode.config.json"],
        cwd=tmp_path,
        check=False,
    )

    assert root_result.returncode == 0
    assert nested_result.returncode == 1


def test_public_snapshot_skips_untracked_root_opencode_config_content(tmp_path):
    _write_minimal_public_snapshot_fixture(tmp_path)
    shutil.copy2(REPO_ROOT / ".gitignore", tmp_path / ".gitignore")
    (tmp_path / "opencode.config.json").write_text(
        "synthetic-invalid-json-placeholder",
        encoding="utf-8",
    )

    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    result = _run_public_snapshot(tmp_path)

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "[JSON-FAIL]" not in output
    assert "synthetic-invalid-json-placeholder" not in output


def test_public_snapshot_allows_python_test_caches():
    for leftover in REPO_ROOT.glob("public-snapshot-probe-*"):
        shutil.rmtree(leftover, ignore_errors=True)

    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(REPO_ROOT / "scripts" / "verify-public-snapshot.ps1"),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_runtime_bootstrap_generates_go_wrapper(tmp_path):
    project_root = tmp_path / "demo-project"
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(REPO_ROOT / "templates" / "runtime-bootstrap" / "bootstrap.ps1"),
            "-ProjectName",
            "demo-project",
            "-ProjectRoot",
            str(project_root),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    output = result.stdout + result.stderr
    wrapper = project_root / "tools" / "devframe-go.ps1"
    agents = project_root / "AGENTS.md"

    assert result.returncode == 0, output
    assert "[GEN] tools/devframe-go.ps1" in output
    assert wrapper.exists()
    text = wrapper.read_text(encoding="utf-8-sig")
    assert "{{PROJECT_ROOT}}" not in text
    assert str(project_root) in text
    assert '"code"' in text
    assert '"--preview"' in text
    assert '"--execute"' in text
    assert "$Prepare -and $Execute" in text
    assert "[switch]$Dashboard" not in text
    assert '"--dashboard"' not in text
    assert "& devframe @argsList" in text
    assert "tools/devframe-go.ps1" in agents.read_text(encoding="utf-8-sig")

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    capture_path = tmp_path / "devframe-args.txt"
    fake_devframe = fake_bin / "devframe.cmd"
    fake_devframe.write_text(
        f"@echo off\r\necho %* > \"{capture_path}\"\r\nexit /b 0\r\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"

    wrapper_result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(wrapper),
            "-Goal",
            "Preview wrapper dispatch.",
            "-Changed",
            "-Target",
            "src/app.py",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=env,
    )

    captured_args = capture_path.read_text(encoding="utf-8").strip()

    assert wrapper_result.returncode == 0, wrapper_result.stdout + wrapper_result.stderr
    assert 'code "Preview wrapper dispatch."' in captured_args
    assert f"--project {project_root}" in captured_args
    assert "--agents auto" in captured_args
    assert "--target src/app.py" in captured_args
    assert "--changed" in captured_args
    assert "--preview" in captured_args
    assert "--execute" not in captured_args

    prepare_capture_path = tmp_path / "devframe-prepare-args.txt"
    fake_devframe.write_text(
        f"@echo off\r\necho %* > \"{prepare_capture_path}\"\r\nexit /b 0\r\n",
        encoding="utf-8",
    )
    prepare_result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(wrapper),
            "-Goal",
            "Prepare wrapper dispatch.",
            "-Changed",
            "-Prepare",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=env,
    )

    prepare_args = prepare_capture_path.read_text(encoding="utf-8").strip()

    assert prepare_result.returncode == 0, prepare_result.stdout + prepare_result.stderr
    assert 'code "Prepare wrapper dispatch."' in prepare_args
    assert "--changed" in prepare_args
    assert "--dashboard" not in prepare_args
    assert "--preview" not in prepare_args
    assert "--execute" not in prepare_args

    conflict_result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(wrapper),
            "-Goal",
            "Invalid mode.",
            "-Prepare",
            "-Execute",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=env,
    )

    assert conflict_result.returncode == 2
    assert "Use either -Prepare or -Execute" in (conflict_result.stdout + conflict_result.stderr)


def test_runtime_bootstrap_dry_run_lists_go_wrapper(tmp_path):
    project_root = tmp_path / "demo-project"
    result = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(REPO_ROOT / "templates" / "runtime-bootstrap" / "bootstrap.ps1"),
            "-ProjectName",
            "demo-project",
            "-ProjectRoot",
            str(project_root),
            "-DryRun",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    assert "devframe-go.template.ps1 -> tools/devframe-go.ps1" in output
    assert not project_root.exists()


def test_public_snapshot_rejects_generated_build_dirs():
    probe_name = f"public-snapshot-probe-{uuid.uuid4().hex}"
    probe_root = REPO_ROOT / probe_name
    build_dir = probe_root / "build"
    build_dir.mkdir(parents=True)
    try:
        result = subprocess.run(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(REPO_ROOT / "scripts" / "verify-public-snapshot.ps1"),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        output = result.stdout + result.stderr
        assert result.returncode == 1, output
        assert f"forbidden name: {probe_name}\\build" in output
    finally:
        shutil.rmtree(probe_root, ignore_errors=True)


def test_public_snapshot_ignores_gitignored_tutti_build_outputs():
    probe_dir = (
        REPO_ROOT
        / "products"
        / "tutti"
        / "apps"
        / "desktop"
        / "build"
        / "app-runtime"
        / f"snapshot-probe-{uuid.uuid4().hex}"
    )
    probe_dir.mkdir(parents=True)
    (probe_dir / "generated.txt").write_text("ignored local build output", encoding="utf-8")
    try:
        result = subprocess.run(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(REPO_ROOT / "scripts" / "verify-public-snapshot.ps1"),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)


def test_public_snapshot_ignores_empty_gitignored_tutti_build_dir():
    probe_dir = (
        REPO_ROOT
        / "products"
        / "tutti"
        / "apps"
        / "desktop"
        / "build"
        / "empty-app-runtime-probe"
    )
    probe_dir.mkdir(parents=True)
    try:
        result = subprocess.run(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(REPO_ROOT / "scripts" / "verify-public-snapshot.ps1"),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)


def test_tutti_snapshot_is_external_reference_only():
    tracked = subprocess.check_output(
        ["git", "ls-files", "--", "products/tutti"],
        cwd=REPO_ROOT,
        text=True,
    ).splitlines()

    assert tracked == []
    assert not (REPO_ROOT / "scripts" / "import-tutti-snapshot.py").exists()


def test_strict_public_snapshot_rejects_tracked_product_reference(tmp_path):
    _write_minimal_public_snapshot_fixture(tmp_path)
    product_file = tmp_path / "products" / "tutti" / "README.md"
    product_file.parent.mkdir(parents=True)
    product_file.write_text("bundled product", encoding="utf-8")

    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "products/tutti/README.md"], cwd=tmp_path, check=True)
    result = _run_public_snapshot(tmp_path, "-FailOnTrackedForbidden")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "tracked bundled product: products/tutti/README.md" in result.stdout


def test_public_snapshot_rejects_root_ai_bridge_dir():
    probe_dir = REPO_ROOT / ".ai-bridge"
    probe_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(REPO_ROOT / "scripts" / "verify-public-snapshot.ps1"),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        output = result.stdout + result.stderr
        assert result.returncode == 1, output
        assert "forbidden name: .ai-bridge" in output
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)


def test_public_snapshot_rejects_root_review_artifacts():
    bundle_dir = REPO_ROOT / f"review-bundle-probe-{uuid.uuid4().hex}"
    reply_file = REPO_ROOT / "chatgpt-review-reply.txt"
    original_reply = None
    if reply_file.exists():
        original_reply = reply_file.read_bytes()
    bundle_dir.mkdir(parents=True)
    reply_file.write_text("local review reply", encoding="utf-8")
    try:
        result = subprocess.run(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(REPO_ROOT / "scripts" / "verify-public-snapshot.ps1"),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        output = result.stdout + result.stderr
        assert result.returncode == 1, output
        assert f"forbidden root review artifact: {bundle_dir.name}" in output
        assert "forbidden root review artifact: chatgpt-review-reply.txt" in output
    finally:
        shutil.rmtree(bundle_dir, ignore_errors=True)
        if original_reply is None:
            reply_file.unlink(missing_ok=True)
        else:
            reply_file.write_bytes(original_reply)


@pytest.mark.parametrize(
    ("file_name", "content", "expected_error"),
    [
        (
            "forbidden-\u2028status.zip",
            "synthetic archive bytes",
            "[PUBLIC-SNAPSHOT-FAIL] forbidden extension: forbidden-?status.zip",
        ),
        (
            "private-\u2028status.md",
            "C:\\Users\\RD\\synthetic-private",
            "[PUBLIC-SNAPSHOT-FAIL] private-?status.md: contains "
            "private RD user home path",
        ),
    ],
)
def test_public_snapshot_sanitizes_path_derived_diagnostics(
    tmp_path,
    file_name,
    content,
    expected_error,
):
    snapshot_root = tmp_path / "clean export"
    snapshot_root.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    (snapshot_root / file_name).write_text(content, encoding="utf-8")

    result = _run_public_snapshot(snapshot_root)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert output.strip() == expected_error
    assert len(output.splitlines()) == 1
    assert "\u2028" not in output


@pytest.mark.skipif(os.name != "nt", reason="Windows native Git output contract")
@pytest.mark.parametrize(
    ("git_path_expression", "expected_error"),
    [
        (
            "'products/forged-' + [char]0x2028 + 'status.txt'",
            "[PUBLIC-SNAPSHOT-FAIL] tracked bundled product: "
            "products/forged-?status.txt",
        ),
        (
            "'../forged.txt'",
            "[PUBLIC-SNAPSHOT-FAIL] tracked forbidden review artifact: "
            "<unavailable>",
        ),
        (
            "'products/' + ('x' * 300) + '.txt'",
            "[PUBLIC-SNAPSHOT-FAIL] tracked bundled product: "
            + "products/"
            + ("x" * 231),
        ),
    ],
)
def test_public_snapshot_sanitizes_tracked_path_diagnostic(
    tmp_path,
    git_path_expression,
    expected_error,
):
    snapshot_root = tmp_path / "clean export"
    fake_bin = tmp_path / "fake-bin"
    snapshot_root.mkdir()
    fake_bin.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    (snapshot_root / ".git").mkdir()
    (fake_bin / "git.cmd").write_text(
        "@echo off\n"
        "echo %* | %SystemRoot%\\System32\\findstr.exe "
        '"opencode.config.json" >nul\n'
        "if not errorlevel 1 exit /b 0\n"
        "%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe "
        "-NoProfile -Command \"[Console]::OutputEncoding = "
        "[System.Text.UTF8Encoding]::new($false); "
        f"$p={git_path_expression}; "
        '[Console]::Out.WriteLine($p)"\n'
        "exit /b 0\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")

    result = _run_public_snapshot(
        snapshot_root,
        "-FailOnTrackedForbidden",
        env=env,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert output.strip() == expected_error
    assert len(output.splitlines()) == 1
    assert "\u2028" not in output


@pytest.mark.parametrize(
    ("failure_kind", "expected_prefix", "expected_summary"),
    [
        (
            "violation",
            "[PUBLIC-SNAPSHOT-FAIL] forbidden extension: bounded-",
            "[PUBLIC-SNAPSHOT-FAIL] additional snapshot violations omitted",
        ),
        (
            "private-text",
            "[PUBLIC-SNAPSHOT-FAIL] private-bounded-",
            "[PUBLIC-SNAPSHOT-FAIL] additional private text failures omitted",
        ),
    ],
)
def test_public_snapshot_bounds_filesystem_diagnostic_records(
    tmp_path,
    failure_kind,
    expected_prefix,
    expected_summary,
):
    snapshot_root = tmp_path / "clean export"
    snapshot_root.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    for index in range(70):
        if failure_kind == "violation":
            relative = f"bounded-{index:03d}.zip"
            content = "synthetic archive bytes"
        else:
            relative = f"private-bounded-{index:03d}.md"
            content = "C:\\Users\\RD\\synthetic-private"
        (snapshot_root / relative).write_text(content, encoding="utf-8")

    result = _run_public_snapshot(snapshot_root)

    output = result.stdout + result.stderr
    lines = output.splitlines()
    assert result.returncode == 1, output
    assert len(lines) == 65
    assert all(line.startswith(expected_prefix) for line in lines[:64])
    if failure_kind == "violation":
        assert lines[0].endswith("bounded-000.zip")
        assert lines[63].endswith("bounded-063.zip")
        assert "bounded-069.zip" not in output
    else:
        assert "private-bounded-000.md:" in lines[0]
        assert "private-bounded-063.md:" in lines[63]
        assert "private-bounded-069.md" not in output
    assert lines[-1] == expected_summary
    assert len(output.encode("utf-8")) <= 24_000


def test_public_snapshot_omits_no_records_at_diagnostic_limit(tmp_path):
    snapshot_root = tmp_path / "clean export"
    snapshot_root.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    for index in range(64):
        (snapshot_root / f"at-limit-{index:03d}.zip").write_text(
            "synthetic archive bytes",
            encoding="utf-8",
        )

    result = _run_public_snapshot(snapshot_root)

    output = result.stdout + result.stderr
    lines = output.splitlines()
    assert result.returncode == 1, output
    assert len(lines) == 64
    assert lines[0].endswith("at-limit-000.zip")
    assert lines[-1].endswith("at-limit-063.zip")
    assert "additional snapshot violations omitted" not in output


@pytest.mark.skipif(os.name != "nt", reason="Windows native Git output contract")
def test_public_snapshot_bounds_tracked_diagnostic_records(tmp_path):
    snapshot_root = tmp_path / "clean export"
    fake_bin = tmp_path / "fake-bin"
    snapshot_root.mkdir()
    fake_bin.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    (snapshot_root / ".git").mkdir()
    (fake_bin / "git.cmd").write_text(
        "@echo off\n"
        "echo %* | %SystemRoot%\\System32\\findstr.exe "
        '"opencode.config.json" >nul\n'
        "if not errorlevel 1 exit /b 0\n"
        "%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe "
        "-NoProfile -Command \"[Console]::OutputEncoding = "
        "[System.Text.UTF8Encoding]::new($false); "
        "1..70 | ForEach-Object { "
        "[Console]::Out.WriteLine(('products/item-{0:D3}.txt' -f $_)) }\"\n"
        "exit /b 0\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")

    result = _run_public_snapshot(
        snapshot_root,
        "-FailOnTrackedForbidden",
        env=env,
    )

    output = result.stdout + result.stderr
    lines = output.splitlines()
    assert result.returncode == 1, output
    assert len(lines) == 65
    assert all(
        line.startswith("[PUBLIC-SNAPSHOT-FAIL] tracked bundled product: products/")
        for line in lines[:64]
    )
    assert lines[0].endswith("products/item-001.txt")
    assert lines[63].endswith("products/item-064.txt")
    assert "products/item-070.txt" not in output
    assert lines[-1] == (
        "[PUBLIC-SNAPSHOT-FAIL] additional tracked path failures omitted"
    )
    assert len(output.encode("utf-8")) <= 24_000


def test_public_snapshot_rejects_private_text_markers():
    probe_file = REPO_ROOT / f"public-snapshot-private-path-probe-{uuid.uuid4().hex}.md"
    concrete_conversation_url = (
        "https://chatgpt.com/c/" + "6a49bdcb-5bc8-83e8-875b-44d9ed0b8e26"
    )
    probe_file.write_text(
        "\n".join([
            "This public file leaked D:\\dev-frame-system in prose.",
            "This public file also leaked D:\\devframe-system in prose.",
            "This public file also leaked D:\\test-frame in prose.",
            "It also leaked C:\\Users\\RD in prose.",
            f"It also leaked {concrete_conversation_url}.",
            "It also leaked mojibake: 锟斤拷.",
        ]),
        encoding="utf-8",
    )
    try:
        result = subprocess.run(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(REPO_ROOT / "scripts" / "verify-public-snapshot.ps1"),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        output = result.stdout + result.stderr
        assert result.returncode == 1, output
        assert probe_file.name in output
        assert "private dev-frame-system checkout path" in output
        assert "private adjacent devframe root path" in output
        assert "private RD user home path" in output
        assert "concrete ChatGPT conversation URL" in output
        assert "mojibake replacement marker" in output
    finally:
        probe_file.unlink(missing_ok=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows exclusive file handle contract")
@pytest.mark.parametrize(
    ("file_name", "display_name"),
    [
        ("locked-private.md", "locked-private.md"),
        ("locked-\u2028forged-status.md", "locked-?forged-status.md"),
    ],
)
def test_public_snapshot_fails_closed_when_private_text_file_cannot_be_read(
    tmp_path,
    file_name,
    display_name,
):
    import ctypes
    from ctypes import wintypes

    snapshot_root = tmp_path / "clean export"
    snapshot_root.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    locked_path = snapshot_root / file_name
    locked_path.write_text("C:\\Users\\RD\\synthetic-private", encoding="utf-8")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(locked_path),
        0x80000000,
        0,
        None,
        3,
        0,
        None,
    )
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        result = _run_public_snapshot(snapshot_root)
    finally:
        kernel32.CloseHandle(handle)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert output.strip() == (
        f"[PUBLIC-SNAPSHOT-FAIL] unable to inspect text: {display_name}"
    )
    assert len(output.splitlines()) == 1
    assert str(snapshot_root) not in output
    assert "synthetic-private" not in output


@pytest.mark.skipif(os.name != "nt", reason="Windows exclusive file handle contract")
def test_public_snapshot_redacts_required_text_read_failure(tmp_path):
    import ctypes
    from ctypes import wintypes

    snapshot_root = tmp_path / "clean export"
    snapshot_root.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    locked_path = snapshot_root / "rules" / "open-source-reuse.md"
    locked_path.write_text(
        "recon.md SYNTHETIC_REQUIRED_TEXT_SECRET",
        encoding="utf-8",
    )
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    handle = create_file(
        str(locked_path),
        0x80000000,
        0,
        None,
        3,
        0,
        None,
    )
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        result = _run_public_snapshot(snapshot_root)
    finally:
        if not close_handle(handle):
            raise ctypes.WinError(ctypes.get_last_error())

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert output.strip() == (
        "[TEXT-FAIL] rules\\open-source-reuse.md: unable to inspect required text"
    )
    assert len(output.splitlines()) == 1
    assert str(snapshot_root) not in output
    assert "Get-Content" not in output
    assert "CategoryInfo" not in output
    assert "FullyQualifiedErrorId" not in output
    assert "IOException" not in output
    assert "being used by another process" not in output
    assert "SYNTHETIC_REQUIRED_TEXT_SECRET" not in output


@pytest.mark.parametrize(
    ("fixture_state", "expected_error"),
    [
        ("missing", "[TEXT-FAIL] rules\\open-source-reuse.md: file missing"),
        ("empty", "[TEXT-FAIL] rules\\open-source-reuse.md: missing 'rules/recon.md'"),
        ("mismatch", "[TEXT-FAIL] rules\\open-source-reuse.md: missing 'rules/recon.md'"),
    ],
)
def test_public_snapshot_preserves_required_text_failure_categories(
    tmp_path,
    fixture_state,
    expected_error,
):
    snapshot_root = tmp_path / "clean export"
    snapshot_root.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    required_text_path = snapshot_root / "rules" / "open-source-reuse.md"
    if fixture_state == "missing":
        required_text_path.unlink()
    elif fixture_state == "empty":
        required_text_path.write_text("", encoding="utf-8")
    else:
        required_text_path.write_text("not the required literal", encoding="utf-8")

    result = _run_public_snapshot(snapshot_root)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert output.strip() == expected_error
    assert len(output.splitlines()) == 1


@pytest.mark.skipif(os.name != "nt", reason="Windows exclusive directory handle contract")
@pytest.mark.parametrize(
    ("directory_name", "expected_error"),
    [
        (
            "locked-\u2028directory",
            "[PUBLIC-SNAPSHOT-FAIL] unable to enumerate snapshot path: "
            "locked-?directory",
        ),
        (".pytest_cache", None),
    ],
)
def test_public_snapshot_redacts_directory_enumeration_failure(
    tmp_path,
    directory_name,
    expected_error,
):
    import ctypes
    from ctypes import wintypes

    snapshot_root = tmp_path / "clean export"
    snapshot_root.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    locked_dir = snapshot_root / directory_name
    locked_dir.mkdir()
    (locked_dir / "safe.txt").write_text(
        "C:\\Users\\RD\\synthetic-enumeration-private",
        encoding="utf-8",
    )
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    handle = create_file(
        str(locked_dir),
        0x80000000,
        0,
        None,
        3,
        0x02000000,
        None,
    )
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        result = _run_public_snapshot(snapshot_root)
    finally:
        if not close_handle(handle):
            raise ctypes.WinError(ctypes.get_last_error())

    output = result.stdout + result.stderr
    assert "synthetic-enumeration-private" not in output
    if expected_error is None:
        assert result.returncode == 0, output
        assert "[PUBLIC-SNAPSHOT-FAIL]" not in output
        assert "[OK] JSON files parse as UTF-8." in output
        return
    assert result.returncode == 1, output
    assert output.strip() == expected_error
    assert len(output.splitlines()) == 1
    assert str(snapshot_root) not in output
    assert "Get-ChildItem" not in output
    assert "CategoryInfo" not in output


def test_public_snapshot_fails_closed_when_private_text_is_not_utf8(tmp_path):
    snapshot_root = tmp_path / "clean export"
    snapshot_root.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    (snapshot_root / "invalid-utf8.md").write_bytes(b"\xff")

    result = _run_public_snapshot(snapshot_root)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert output.strip() == (
        "[PUBLIC-SNAPSHOT-FAIL] unable to inspect text: invalid-utf8.md"
    )
    assert str(snapshot_root) not in output
    assert "Exception" not in output


def test_public_snapshot_rejects_readable_private_text_in_minimal_snapshot(tmp_path):
    snapshot_root = tmp_path / "clean export"
    snapshot_root.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    marker_path = snapshot_root / "readable-private.md"
    marker_path.write_text("C:\\Users\\RD\\synthetic-private", encoding="utf-8")

    result = _run_public_snapshot(snapshot_root)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "readable-private.md: contains private RD user home path" in output
    assert str(snapshot_root) not in output
    assert "synthetic-private" not in output


def test_public_snapshot_redacts_malformed_json_content(tmp_path):
    snapshot_root = tmp_path / "clean export"
    snapshot_root.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    (snapshot_root / "malformed-\u2028secret.json").write_text(
        "SYNTHETIC_JSON_SECRET",
        encoding="utf-8",
    )

    result = _run_public_snapshot(snapshot_root)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert output.strip() == "[JSON-FAIL] malformed-?secret.json: unable to parse JSON"
    assert len(output.splitlines()) == 1
    assert str(snapshot_root) not in output
    assert "SYNTHETIC_JSON_SECRET" not in output
    assert "Invalid JSON primitive" not in output


def test_public_snapshot_checks_private_text_before_json_parse(tmp_path):
    snapshot_root = tmp_path / "clean export"
    snapshot_root.mkdir()
    _write_minimal_public_snapshot_fixture(snapshot_root)
    (snapshot_root / "private-malformed.json").write_text(
        "C:\\Users\\RD\\synthetic-private",
        encoding="utf-8",
    )

    result = _run_public_snapshot(snapshot_root)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "private-malformed.json: contains private RD user home path" in output
    assert "[JSON-FAIL]" not in output
    assert "synthetic-private" not in output


def test_control_plane_packaged_templates_do_not_reference_private_paths():
    forbidden = [
        "D:\\agent-acceptance",
        "D:/agent-acceptance",
    ]

    for path in CONTROL_PLANE_TEMPLATES.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8-sig")
        for marker in forbidden:
            assert marker not in text, f"{path} contains private path {marker}"


def test_public_markdown_docs_are_utf8_and_do_not_contain_mojibake_or_private_paths():
    forbidden = [
        "D:\\agent-acceptance",
        "D:/agent-acceptance",
        "D:\\dev-frame-system",
        "D:/dev-frame-system",
        "C:\\Users\\RD",
        "C:/Users/RD",
        "锛",
        "绠",
        "绋",
        "鍙",
        "丏eepSeek",
        "€?",
        "һ",
        "Ϊ",
        "ô",
        "Щ",
        "ʲ",
        "С",
        "δ",
        "ǰ",
        "ʷ",
        "¼",
        "Դ",
        "ʹ",
        "ֻ",
        "ǿ",
        "Ҫ",
        "Լ",
        "֪",
        "Ǩ",
        "װ",
        "˽",
        "ִ",
        "ָ",
        "û",
        "ÿ",
        "ı",
        "̨",
        "ƫ",
        "Ƭ",
        "Ʒ",
        "΢",
        "ţ",
        "ƽ",
        "У",
        "֤",
        "λ",
        "˵",
        "С",
        "ʧ",
        "ʿ",
        "֮",
        "ʼ",
        "ϣ",
        "λ",
        "¼",
        "ղ",
        "ܰ",
        "д",
        "δ",
        "ƫ",
        "Ư",
        "ѡ",
        "ͣ",
        "ͬ",
        "ʵ",
        "ǰ",
        "ܰ",
        "λ",
        "ֻ",
        "ֹ",
        "ÿ",
        "û",
        "ϣ",
        "΢",
        "т",
        "Ǩ",
        "֣",
        "¡",
        "ҳ",
        "Ĭ",
    ]

    for path in PUBLIC_MARKDOWN_DOCS:
        text = path.read_text(encoding="utf-8-sig")
        for marker in forbidden:
            assert marker not in text, f"{path} contains forbidden marker {marker!r}"


def test_current_entry_markdown_links_resolve_to_repo_files():
    missing = []
    for path in DOC_LINK_CHECK_MARKDOWN_DOCS:
        for target in _relative_markdown_links(path):
            if target.startswith("/"):
                resolved = REPO_ROOT / target.lstrip("/")
            else:
                resolved = path.parent / target
            if not resolved.exists():
                try:
                    resolved_label = resolved.relative_to(REPO_ROOT).as_posix()
                except ValueError:
                    resolved_label = f"outside repo: {resolved}"
                missing.append(
                    (
                        path.relative_to(REPO_ROOT).as_posix(),
                        target,
                        resolved_label,
                    )
                )

    assert missing == []


def test_plan_contains_one_verdict_next_action_and_at_most_one_active_milestone():
    text = (REPO_ROOT / "PLAN.md").read_text(encoding="utf-8-sig")

    assert len(re.findall(r"(?m)^Current verdict:", text)) == 1
    assert len(re.findall(r"(?m)^## Next Action\s*$", text)) == 1
    active_count = len(re.findall(r"(?m)^\| M\d+ .*\| active \|", text))
    assert active_count <= 1
    if active_count == 0:
        verdict = next(
            line for line in text.splitlines() if line.startswith("Current verdict:")
        )
        assert "HUMAN_REQUIRED" in verdict


def test_plan_records_fail_closed_status_semantics():
    text = (REPO_ROOT / "PLAN.md").read_text(encoding="utf-8-sig")

    for term in [
        "planned",
        "active",
        "candidate",
        "accepted",
        "blocked",
        "human_required",
        "failed",
        "deferred",
        "FinalVerdict",
    ]:
        assert term in text, f"PLAN.md missing status term: {term}"
    assert "Worker `success`" in text
    assert "不自动等于 `accepted`" in text


def test_markdown_link_check_ignores_non_file_link_shapes():
    links = list(_relative_markdown_links_from_text(
        "\n".join([
            "![image](missing-image.png)",
            "[external](https://example.com)",
            "[anchor](#local-heading)",
            "`[inline](missing-inline.md)`",
            "```",
            "[fenced](missing-fenced.md)",
            "```",
            "[local](PLAN.md#section)",
            "[titled](rules/core.md \"Core rules\")",
            "[angled](<schemas/project_contract.schema.json>)",
        ])
    ))

    assert links == [
        "PLAN.md",
        "rules/core.md",
        "schemas/project_contract.schema.json",
    ]


def test_public_scripts_and_adapters_exclude_private_machine_paths():
    forbidden = [
        "C:\\Users\\RD",
        "C:/Users/RD",
        "D:\\dev-frame-system",
        "D:/dev-frame-system",
        "D:\\agent-acceptance",
        "D:/agent-acceptance",
    ]
    paths = [
        REPO_ROOT / "packages" / "agent-acceptance" / "templates" / "ci-preflight" / "install.ps1",
        REPO_ROOT / "packages" / "ai-workflow-hub" / "src" / "ai_workflow_hub" / "context_layer" / "adapters" / "zotero_web_metadata_pilot.py",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8-sig")
        for pattern in forbidden:
            assert pattern not in text, f"{path} contains private path pattern {pattern!r}"


def test_release_workflow_installs_deps_and_invokes_single_release_gate():
    workflow = yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["release-verify"]
    run_steps = [step["run"] for step in job["steps"] if "run" in step]
    release_gate_steps = [
        step for step in run_steps
        if "scripts\\verify-release.ps1" in step
    ]

    assert workflow["on"] == {
        "push": {"branches": ["main"]},
        "pull_request": None,
        "workflow_dispatch": None,
    }
    assert job["runs-on"] == "windows-latest"
    assert 'python -m pip install -e ".\\packages\\control-plane[dev]" -e ".\\packages\\ai-workflow-hub[dev]"' in run_steps
    assert release_gate_steps == [
        "powershell -ExecutionPolicy Bypass -File scripts\\verify-release.ps1",
    ]


def test_release_gate_enables_git_index_artifact_check():
    release_script = (REPO_ROOT / "scripts" / "verify-release.ps1").read_text(
        encoding="utf-8",
    )
    snapshot_script = (
        REPO_ROOT / "scripts" / "verify-public-snapshot.ps1"
    ).read_text(encoding="utf-8")

    assert "-FailOnTrackedForbidden" in release_script
    assert "tracked forbidden review artifact" in snapshot_script
    assert "tracked bundled product" in snapshot_script


def test_release_gate_supports_explicit_offline_wheel_smoke():
    release_script = (REPO_ROOT / "scripts" / "verify-release.ps1").read_text(
        encoding="utf-8"
    )
    wheel_script = (
        REPO_ROOT / "scripts" / "verify-control-plane-wheel.ps1"
    ).read_text(encoding="utf-8")

    assert "[switch]$Offline" in release_script
    assert '$wheelSmokeArguments += "-Offline"' in release_script
    assert "[switch]$Offline" in wheel_script
    assert '"--no-build-isolation"' in wheel_script
    assert '"--system-site-packages"' in wheel_script
    assert '"--no-deps"' in wheel_script


def test_release_gate_runs_docs_drift_validator_through_pytest():
    release_script = (REPO_ROOT / "scripts" / "verify-release.ps1").read_text(
        encoding="utf-8",
    )
    docs_drift_test = (
        REPO_ROOT / "packages" / "control-plane" / "tests" / "test_docs_drift_validator.py"
    ).read_text(encoding="utf-8")

    assert 'Invoke-Step "pytest" "python" @("-m", "pytest", "-q")' in release_script
    assert "build_docs_drift_payload(REPO_ROOT)" in docs_drift_test
    assert "validate_docs_drift(payload)" in docs_drift_test


def test_plan_keeps_release_state_fail_closed_after_document_reset():
    text = (REPO_ROOT / "PLAN.md").read_text(encoding="utf-8-sig")

    assert "本次大规模迁移后必须重新运行" in text
    assert "旧数字不能证明当前树" in text
    assert "RELEASE-001" in text
    assert "blocked" in text
    assert "独立审阅" in text
    assert "精确 accepted-slice Git gate" in text


def test_plan_is_the_single_current_execution_root():
    plan = (REPO_ROOT / "PLAN.md").read_text(encoding="utf-8-sig")
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8-sig")
    docs_root = REPO_ROOT / "docs"
    docs_files = [path for path in docs_root.rglob("*") if path.is_file()]

    assert "本文件是项目唯一的人类开发权威" in plan
    assert "## Next Action" in plan
    assert "## 15. Documentation Policy" in plan
    assert "PLAN.md is the only human development authority" in " ".join(
        agents.replace("`", "").split()
    )
    assert docs_files == []
    for name in ["README.md", "README.zh-CN.md", "AGENT_HANDOFF.md"]:
        assert not (REPO_ROOT / name).exists(), name


def test_public_surface_required_paths_exist_without_reviewer_index():
    missing = [path for path in REVIEWER_INDEX_REQUIRED_PATHS if not (REPO_ROOT / path).exists()]
    assert missing == []


def test_plan_records_machine_assets_and_review_boundary():
    text = (REPO_ROOT / "PLAN.md").read_text(encoding="utf-8-sig")

    for literal in [
        "rules/",
        "schemas/",
        "运行时结构化存储",
        "产品审阅先于技术 P0–P3 审阅",
        "Human Gates",
    ]:
        assert literal in text


def test_default_web_ai_adapter_template_matches_schema():
    schema = json.loads((REPO_ROOT / "schemas" / "web_ai_adapter.schema.json").read_text(encoding="utf-8"))
    template = yaml.safe_load(
        (
            REPO_ROOT
            / "packages"
            / "control-plane"
            / "templates"
            / "paper_iteration"
            / "WEB_AI_ADAPTER.yaml"
        ).read_text(encoding="utf-8")
    )

    Draft7Validator.check_schema(schema)
    Draft7Validator(schema).validate(template)
    assert template["browser"]["provider"] == "chrome"
    assert template["web_ai"]["provider"] == "chatgpt"
    assert template["browser"]["profile_policy"] == "dsh_managed"
    assert template["safety"]["allow_browser_profile_export"] is False
    assert template["manual_fallback"]["enabled"] is True


def test_paper_iteration_metadata_templates_parse_as_yaml():
    template_dir = REPO_ROOT / "packages" / "control-plane" / "templates" / "paper_iteration"

    profile = yaml.safe_load((template_dir / "PAPER_PROFILE.yaml").read_text(encoding="utf-8"))
    state = yaml.safe_load((template_dir / "PAPER_STATE.yaml").read_text(encoding="utf-8"))

    assert profile["paper_id"] == "{{PAPER_ID}}"
    assert profile["title"] == "{{PAPER_TITLE}}"
    assert profile["versions"][0]["date"] == "{{DATE}}"
    assert state["paper_id"] == "{{PAPER_ID}}"
    assert state["status"] == "initialized"


def test_default_visual_control_plane_state_template_matches_schema():
    schema = json.loads((REPO_ROOT / "schemas" / "visual_control_plane_state.schema.json").read_text(encoding="utf-8"))
    template = yaml.safe_load(
        (
            REPO_ROOT
            / "packages"
            / "control-plane"
            / "templates"
            / "visual_control_plane"
            / "CONTROL_PLANE_STATE.yaml"
        ).read_text(encoding="utf-8")
    )

    Draft7Validator.check_schema(schema)
    Draft7Validator(schema).validate(template)
    assert template["provider_bindings"][0]["provider"] == "chatgpt"
    assert template["provider_bindings"][0]["manual_fallback_instructions"][0].startswith("Prepare")
    assert {agent["role"] for agent in template["agents"]} == {"coordinator", "reviewer"}
    assert template["runs"][0]["entrypoint"] == "rdgoal"
    assert template["gates"][0]["next_action"].startswith("Confirm human approval")
    assert template["next_actions"][0]["source_id"] == "human-gate"
    assert template["next_actions"][0]["status"] == "open"
    assert template["safety"]["raw_transcripts_persisted"] is False
    assert template["safety"]["remote_execution_default"] is False
    assert "secret_exposure" in template["safety"]["human_gate_required_for"]


def test_runtime_governance_schemas_validate_fixtures():
    cases = [
        (
            REPO_ROOT / "schemas" / "runtime-governance" / "context-packet.schema.json",
            [
                REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "context-packet-valid.json",
                REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "context-packet-stale-valid.json",
            ],
            [
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "context-packet-worker-final-ready-invalid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "context-packet-text-final-ready-invalid.json",
            ],
        ),
        (
            REPO_ROOT / "schemas" / "runtime-governance" / "context-ledger.schema.json",
            [
                REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "context-ledger-valid.json",
            ],
            [
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "context-ledger-mutable-invalid.json",
            ],
        ),
        (
            REPO_ROOT / "schemas" / "runtime-governance" / "run-record.schema.json",
            [
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-review-pending-valid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-paper-human-required-valid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-paper-blocked-chain-trusted-valid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-unknown-domain-status-valid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-projection-completed-projection-only-valid.json",
            ],
            [
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-worker-final-ready-invalid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-gate-pass-missing-evidence-invalid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-executor-review-invalid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-executor-final-verdict-invalid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-projection-completed-invalid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-test-frame-passed-missing-context-invalid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-test-frame-code-review-pass-missing-review-invalid.json",
                REPO_ROOT
                / "schemas"
                / "examples"
                / "runtime-governance"
                / "run-record-final-report-pass-missing-final-verdict-invalid.json",
            ],
        ),
    ]

    for schema_path, valid_paths, invalid_paths in cases:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        for fixture_path in valid_paths:
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
            validator.validate(fixture)
            if "constraints" in fixture:
                assert fixture["constraints"]["authority_boundary"]["can_claim_final_acceptance"] is False
            if "entries" in fixture:
                previous_hash = None
                for expected_index, entry in enumerate(fixture["entries"]):
                    assert entry["entry_index"] == expected_index
                    assert entry["previous_entry_hash"] == previous_hash
                    previous_hash = entry["entry_hash"]
            if "acceptance_state" in fixture:
                assert fixture["acceptance_state"] != "final_ready"
                if fixture_path.name == "run-record-review-pending-valid.json":
                    assert fixture["outcome"] == "passed"
                    assert fixture["review_state"] == "review_pending"
        for fixture_path in invalid_paths:
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
            errors = sorted(validator.iter_errors(fixture), key=lambda error: list(error.path))
            assert errors, f"{fixture_path} should fail {schema_path.name}"
        if schema_path.name == "context-packet.schema.json":
            uppercase_bypass = json.loads(valid_paths[0].read_text(encoding="utf-8"))
            uppercase_bypass["constraints"]["allowed_actions"] = ["CLAIM FINAL_READY"]
            errors = sorted(
                validator.iter_errors(uppercase_bypass),
                key=lambda error: list(error.path),
            )
            assert errors, "allowed_actions must reject uppercase final acceptance claims"
        if schema_path.name == "run-record.schema.json":
            final_ready_without_verdict = json.loads(valid_paths[0].read_text(encoding="utf-8"))
            final_ready_without_verdict["acceptance_state"] = "final_ready"
            final_ready_without_verdict["review_state"] = "review_passed"
            final_ready_without_verdict["gate_state"] = "gate_passed"
            errors = sorted(
                validator.iter_errors(final_ready_without_verdict),
                key=lambda error: list(error.path),
            )
            assert errors, "final_ready must require FinalVerdict, review, and gate evidence"
            review_passed_with_blocked_review = json.loads(valid_paths[0].read_text(encoding="utf-8"))
            review_passed_with_blocked_review["review_state"] = "review_passed"
            review_passed_with_blocked_review["review_refs"] = [
                {
                    "review_id": "review-blocked",
                    "reviewer_id": "reviewer-1",
                    "reviewer_role": "reviewer",
                    "verdict": "blocked",
                    "uri": "reviews/blocked.yaml",
                    "reviewed_evidence_refs": ["e-runrecord-schema"],
                }
            ]
            errors = sorted(
                validator.iter_errors(review_passed_with_blocked_review),
                key=lambda error: list(error.path),
            )
            assert errors, "review_passed must require a pass review ref"
            gate_passed_with_warning_gate = json.loads(valid_paths[0].read_text(encoding="utf-8"))
            gate_passed_with_warning_gate["gate_state"] = "gate_passed"
            gate_passed_with_warning_gate["gate_refs"] = [
                {
                    "gate_id": "gate-warning",
                    "result": "warning",
                    "uri": "reports/gate-warning.json",
                    "evidence_refs": [],
                }
            ]
            errors = sorted(
                validator.iter_errors(gate_passed_with_warning_gate),
                key=lambda error: list(error.path),
            )
            assert errors, "gate_passed must require a pass gate ref"


def test_runtime_governance_required_negative_case_fixtures_are_present():
    fixture_dir = REPO_ROOT / "schemas" / "examples" / "runtime-governance"
    expected = {
        "worker succeeded with no review": (
            "run-record-review-pending-valid.json",
            ["succeeded", "review_pending"],
        ),
        "gate pass with no evidence": (
            "run-record-gate-pass-missing-evidence-invalid.json",
            ["gate_passed", '"evidence_refs": []'],
        ),
        "final report pass missing final verdict": (
            "run-record-final-report-pass-missing-final-verdict-invalid.json",
            ["final_report_text", "PASS"],
        ),
        "executor authored review": (
            "run-record-executor-review-invalid.json",
            ['"reviewer_role": "executor"'],
        ),
        "test-frame passed missing context": (
            "run-record-test-frame-passed-missing-context-invalid.json",
            ["aggregate_status", "passed"],
        ),
        "test-frame codeReview pass missing review": (
            "run-record-test-frame-code-review-pass-missing-review-invalid.json",
            ["codeReview", "PASS"],
        ),
        "paper completed human required": (
            "run-record-paper-human-required-valid.json",
            ["acceptance_status", "human_required"],
        ),
        "paper blocked chain trusted": (
            "run-record-paper-blocked-chain-trusted-valid.json",
            ["chain_trusted", "blocked"],
        ),
        "unknown domain status": (
            "run-record-unknown-domain-status-valid.json",
            ["legacy_status", "mystery_done"],
        ),
        "projection completed without source authority": (
            "run-record-projection-completed-projection-only-valid.json",
            ['"projection_state": "completed"', '"acceptance_state": "review_pending"'],
        ),
        "stale context": (
            "context-packet-stale-valid.json",
            ["stale_refs", "blocks_acceptance"],
        ),
    }

    for label, (filename, literals) in expected.items():
        path = fixture_dir / filename
        assert path.exists(), f"missing runtime-governance fixture for {label}: {filename}"
        text = path.read_text(encoding="utf-8-sig")
        missing = [literal for literal in literals if literal not in text]
        assert missing == [], f"{filename} missing coverage literals for {label}: {missing}"

    parsed = {
        filename: json.loads((fixture_dir / filename).read_text(encoding="utf-8-sig"))
        for filename, _literals in expected.values()
    }
    assert parsed["run-record-review-pending-valid.json"]["worker_results"][0]["status"] == "succeeded"
    assert parsed["run-record-review-pending-valid.json"]["acceptance_state"] == "review_pending"
    assert "context_packet_id" not in parsed["run-record-test-frame-passed-missing-context-invalid.json"]
    assert parsed["run-record-test-frame-code-review-pass-missing-review-invalid.json"]["review_refs"] == []
    assert parsed["run-record-final-report-pass-missing-final-verdict-invalid.json"]["acceptance_state"] == "final_ready"
    assert "final_verdict_ref" not in parsed["run-record-final-report-pass-missing-final-verdict-invalid.json"]
    paper_human_required = parsed["run-record-paper-human-required-valid.json"]
    assert paper_human_required["outcome"] == "human_required"
    assert paper_human_required["acceptance_state"] == "blocked"
    paper_chain_trusted = parsed["run-record-paper-blocked-chain-trusted-valid.json"]
    assert paper_chain_trusted["domain_refs"]["chain_trusted"] is True
    assert paper_chain_trusted["outcome"] == "blocked"
    assert paper_chain_trusted["acceptance_state"] == "blocked"
    unknown_status = parsed["run-record-unknown-domain-status-valid.json"]
    assert unknown_status["outcome"] == "unknown"
    assert unknown_status["projection_state"] == "unknown"
    projection_only = parsed["run-record-projection-completed-projection-only-valid.json"]
    assert projection_only["projection_state"] == "completed"
    assert projection_only["acceptance_state"] == "review_pending"
    stale_context = parsed["context-packet-stale-valid.json"]
    assert stale_context["completeness_state"] == "insufficient_evidence"
    assert stale_context["omitted_required_refs"][0]["impact"] == "blocks_acceptance"


def test_runtime_governance_schema_mirrors_match_semantically():
    pairs = [
        (
            REPO_ROOT / "schemas" / "runtime-governance" / "context-packet.schema.json",
            REPO_ROOT
            / "packages"
            / "test-frame"
            / "schemas"
            / "runtime-governance"
            / "context-packet.schema.json",
        ),
        (
            REPO_ROOT / "schemas" / "runtime-governance" / "context-ledger.schema.json",
            REPO_ROOT
            / "packages"
            / "test-frame"
            / "schemas"
            / "runtime-governance"
            / "context-ledger.schema.json",
        ),
        (
            REPO_ROOT / "schemas" / "runtime-governance" / "run-record.schema.json",
            REPO_ROOT
            / "packages"
            / "test-frame"
            / "schemas"
            / "runtime-governance"
            / "run-record.schema.json",
        ),
    ]

    for root_path, mirror_path in pairs:
        root_semantics = _json_semantics(root_path)
        mirror_semantics = _json_semantics(mirror_path)
        assert mirror_semantics == root_semantics

        drift_probe = json.loads(json.dumps(mirror_semantics))
        drift_probe["title"] = f"{drift_probe.get('title', '')} drift"
        assert drift_probe != root_semantics


def test_agent_runtime_chain_evidence_schema_mirror_matches_semantically():
    root_path = REPO_ROOT / "schemas" / "agent-runtime" / "chain-evidence.schema.json"
    mirror_path = (
        REPO_ROOT
        / "packages"
        / "test-frame"
        / "schemas"
        / "agent-runtime"
        / "chain-evidence.schema.json"
    )

    root_semantics = _json_semantics(root_path)
    mirror_semantics = _json_semantics(mirror_path)
    assert mirror_semantics == root_semantics


def test_chain_evidence_schema_rejects_acceptance_creating_next_command():
    schema = json.loads(
        (REPO_ROOT / "schemas" / "agent-runtime" / "chain-evidence.schema.json").read_text(
            encoding="utf-8-sig"
        )
    )
    validator = Draft202012Validator(schema)
    payload = {
        "run_id": "run-1",
        "executor_id": "executor-1",
        "mode": "prepare",
        "planner": None,
        "task": "task-spec.md",
        "methodology": None,
        "evidence_files": ["chain-evidence.json"],
        "timestamps": {"created_at": "2026-07-07T00:00:00+00:00"},
        "next_commands": {
            "finalize": {
                "command_args": ["tools/go_evidence.py", "finalize", "run"],
                "authority": "guidance_only",
                "creates_acceptance": True,
                "requires_independent_review": True,
            },
        },
    }

    errors = list(validator.iter_errors(payload))

    assert errors
    assert any(
        list(error.path) == ["next_commands", "finalize", "creates_acceptance"]
        for error in errors
    )


def _final_verdict_payload(**overrides):
    payload = {
        "verdict_id": "fv-runtime-lifecycle-v2",
        "produced_by": "devframe-system-main-coordinator",
        "produced_at": "2026-07-08T00:00:00Z",
        "producer_role": "governance",
        "final_state": "blocked",
        "inputs_reviewed": ["evidence/final-verdict-v1.json", "review/review.yaml"],
        "gate_summary": [
            {
                "gate_id": "gate-runtime-lifecycle",
                "result": "blocked",
                "evidence_path": "review/review.yaml",
            }
        ],
        "reviewer_summary": {
            "reviewer_id": "reviewer-1",
            "verdict": "blocked",
            "evidence_path": "review/review.yaml",
        },
        "limitations": ["supersedes earlier verdict after new evidence"],
        "human_or_governance_reference": "governance:runtime-lifecycle-review",
    }
    payload.update(overrides)
    return payload


def test_final_verdict_schema_supports_append_only_superseding_record():
    schema = json.loads(
        (REPO_ROOT / "schemas" / "agent-runtime" / "final-verdict.schema.json").read_text(
            encoding="utf-8-sig"
        )
    )
    validator = Draft202012Validator(schema)
    payload = _final_verdict_payload(
        supersedes={
            "verdict_id": "fv-runtime-lifecycle-v1",
            "uri": "evidence/final-verdict-v1.json",
            "reason": "New independent review evidence invalidated the earlier verdict.",
        }
    )

    validator.validate(payload)


def test_final_verdict_schema_rejects_incomplete_superseding_record():
    schema = json.loads(
        (REPO_ROOT / "schemas" / "agent-runtime" / "final-verdict.schema.json").read_text(
            encoding="utf-8-sig"
        )
    )
    validator = Draft202012Validator(schema)
    payload = _final_verdict_payload(
        supersedes={
            "verdict_id": "fv-runtime-lifecycle-v1",
            "uri": "evidence/final-verdict-v1.json",
        }
    )

    errors = list(validator.iter_errors(payload))

    assert errors
    assert any(list(error.path) == ["supersedes"] for error in errors)


def test_final_verdict_schema_keeps_blocked_producer_roles_for_superseding_record():
    schema = json.loads(
        (REPO_ROOT / "schemas" / "agent-runtime" / "final-verdict.schema.json").read_text(
            encoding="utf-8-sig"
        )
    )
    validator = Draft202012Validator(schema)
    for role in ["executor", "fixer", "coder", "worker"]:
        payload = _final_verdict_payload(
            producer_role=role,
            supersedes={
                "verdict_id": "fv-runtime-lifecycle-v1",
                "uri": "evidence/final-verdict-v1.json",
                "reason": f"{role}-authored verdict must still be rejected.",
            },
        )

        errors = list(validator.iter_errors(payload))

        assert errors
        assert any(list(error.path) == ["producer_role"] for error in errors)


def test_plan_records_release_gate_and_control_plane_capabilities():
    text = (REPO_ROOT / "PLAN.md").read_text(encoding="utf-8-sig")

    for literal in [
        "scripts/verify-public-snapshot.ps1",
        "工作台",
        "Task Board",
        "Evidence",
        "Review",
        "HumanGate",
        "M7 发布收口",
    ]:
        assert literal in text, f"PLAN.md missing required literal: {literal}"


def test_public_schemas_docs_and_fixtures_exclude_private_paths():
    forbidden = [
        "C:\\Users\\RD",
        "C:/Users/RD",
        "D:\\agent-acceptance",
        "D:/agent-acceptance",
    ]
    paths = [
        REPO_ROOT / "schemas" / "resource-integration" / "script-safety-record.schema.json",
        REPO_ROOT / "schemas" / "resource-integration" / "memory-context-record.schema.json",
        REPO_ROOT / "schemas" / "resource-integration" / "codegraph-index-record.schema.json",
        REPO_ROOT / "schemas" / "agent-runtime" / "memory-update-record.schema.json",
        REPO_ROOT / "packages" / "test-frame" / "schemas" / "resource-integration" / "script-safety-record.schema.json",
        REPO_ROOT / "packages" / "test-frame" / "schemas" / "resource-integration" / "memory-context-record.schema.json",
        REPO_ROOT / "packages" / "test-frame" / "schemas" / "resource-integration" / "codegraph-index-record.schema.json",
        REPO_ROOT / "packages" / "test-frame" / "schemas" / "agent-runtime" / "memory-update-record.schema.json",
        REPO_ROOT / "schemas" / "runtime-governance" / "context-packet.schema.json",
        REPO_ROOT / "schemas" / "runtime-governance" / "context-ledger.schema.json",
        REPO_ROOT / "schemas" / "runtime-governance" / "run-record.schema.json",
        REPO_ROOT / "packages" / "test-frame" / "schemas" / "runtime-governance" / "context-packet.schema.json",
        REPO_ROOT / "packages" / "test-frame" / "schemas" / "runtime-governance" / "context-ledger.schema.json",
        REPO_ROOT / "packages" / "test-frame" / "schemas" / "runtime-governance" / "run-record.schema.json",
        REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "context-packet-valid.json",
        REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "context-packet-stale-valid.json",
        REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "context-ledger-valid.json",
        REPO_ROOT
        / "schemas"
        / "examples"
        / "runtime-governance"
        / "context-packet-worker-final-ready-invalid.json",
        REPO_ROOT
        / "schemas"
        / "examples"
        / "runtime-governance"
        / "context-packet-text-final-ready-invalid.json",
        REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "context-ledger-mutable-invalid.json",
        REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "run-record-review-pending-valid.json",
        REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "run-record-worker-final-ready-invalid.json",
        REPO_ROOT
        / "schemas"
        / "examples"
        / "runtime-governance"
        / "run-record-gate-pass-missing-evidence-invalid.json",
        REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "run-record-executor-review-invalid.json",
        REPO_ROOT
        / "schemas"
        / "examples"
        / "runtime-governance"
        / "run-record-executor-final-verdict-invalid.json",
        REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "run-record-projection-completed-invalid.json",
        REPO_ROOT
        / "schemas"
        / "examples"
        / "runtime-governance"
        / "run-record-projection-completed-projection-only-valid.json",
        REPO_ROOT
        / "schemas"
        / "examples"
        / "runtime-governance"
        / "run-record-test-frame-passed-missing-context-invalid.json",
        REPO_ROOT
        / "schemas"
        / "examples"
        / "runtime-governance"
        / "run-record-test-frame-code-review-pass-missing-review-invalid.json",
        REPO_ROOT
        / "schemas"
        / "examples"
        / "runtime-governance"
        / "run-record-final-report-pass-missing-final-verdict-invalid.json",
        REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "run-record-paper-human-required-valid.json",
        REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "run-record-paper-blocked-chain-trusted-valid.json",
        REPO_ROOT / "schemas" / "examples" / "runtime-governance" / "run-record-unknown-domain-status-valid.json",
        REPO_ROOT / "packages" / "agent-acceptance" / "fixtures" / "negative-acceptance" / "NEG-024-path-traversal-read.json",
        REPO_ROOT / "packages" / "agent-acceptance" / "fixtures" / "negative-acceptance" / "NEG-017-write-outside-scope.json",
        REPO_ROOT / "PLAN.md",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8-sig")
        for pattern in forbidden:
            assert pattern not in text, f"{path} contains private path pattern {pattern!r}"
