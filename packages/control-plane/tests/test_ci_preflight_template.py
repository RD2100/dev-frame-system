from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_ROOT = (
    REPO_ROOT / "packages" / "agent-acceptance" / "templates" / "ci-preflight"
)
EVIDENCE_SCHEMA = REPO_ROOT / "schemas" / "agent-runtime" / "evidence-capture.schema.json"
MIRRORED_EVIDENCE_SCHEMA = (
    REPO_ROOT
    / "packages"
    / "test-frame"
    / "schemas"
    / "agent-runtime"
    / "evidence-capture.schema.json"
)
POWERSHELL = shutil.which("powershell.exe") or shutil.which("powershell")
GIT = shutil.which("git.exe") or shutil.which("git")


pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or POWERSHELL is None or GIT is None,
    reason="requires Git for Windows and Windows PowerShell",
)


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _run_ok(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = _run(command, cwd=cwd, env=env)
    assert result.returncode == 0, (
        f"command failed ({result.returncode}): {command!r}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return result


def _powershell(script: Path, *arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    assert POWERSHELL is not None
    return _run(
        [
            POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            *arguments,
        ],
        cwd=cwd,
    )


def _copy_template(target: Path) -> None:
    for source in TEMPLATE_ROOT.iterdir():
        destination = target / source.name
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)


def _init_repository(repo: Path) -> None:
    assert GIT is not None
    _run_ok([GIT, "init", "--initial-branch=main"], cwd=repo)
    _run_ok([GIT, "config", "--local", "user.name", "DevFrame Test"], cwd=repo)
    _run_ok(
        [GIT, "config", "--local", "user.email", "devframe-test@example.invalid"],
        cwd=repo,
    )


def _register(repo: Path) -> subprocess.CompletedProcess[str]:
    return _powershell(
        repo / "register-hooks.ps1",
        "-PythonExecutable",
        sys.executable,
        cwd=repo,
    )


def _write_guard(repo: Path) -> None:
    tools = repo / "tools"
    tools.mkdir()
    (tools / "ai_guard.py").write_text(
        """\
import json
import os
from pathlib import Path
import sys

marker = Path(os.environ["DEVFRAME_GUARD_MARKER"])
with marker.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({"executable": sys.executable, "mode": sys.argv[1]}) + "\\n")
raise SystemExit(int(os.environ.get("DEVFRAME_GUARD_EXIT", "0")))
""",
        encoding="utf-8",
    )


def _fake_path_environment(repo: Path) -> tuple[dict[str, str], Path, Path]:
    fake_bin = repo / "fake-bin"
    fake_bin.mkdir()
    fake_marker = repo / "fake-python-ran.txt"
    guard_marker = repo / "guard-ran.jsonl"
    (fake_bin / "python.cmd").write_text(
        "@echo off\r\n"
        "echo fake-python>>\"%DEVFRAME_FAKE_PYTHON_MARKER%\"\r\n"
        "exit /b 0\r\n",
        encoding="ascii",
    )
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["DEVFRAME_FAKE_PYTHON_MARKER"] = str(fake_marker)
    env["DEVFRAME_GUARD_MARKER"] = str(guard_marker)
    return env, fake_marker, guard_marker


def _stage(repo: Path, name: str, content: str) -> None:
    assert GIT is not None
    (repo / name).write_text(content, encoding="utf-8")
    _run_ok([GIT, "add", "--", name], cwd=repo)


def _head(repo: Path) -> str | None:
    assert GIT is not None
    result = _run([GIT, "rev-parse", "HEAD"], cwd=repo)
    return result.stdout.strip() if result.returncode == 0 else None


def _load_receipt(repo: Path) -> dict[str, object]:
    receipt_path = repo / "_evidence" / "hook-output" / "latest.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    schema = json.loads(EVIDENCE_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(receipt, schema, format_checker=jsonschema.FormatChecker())
    return receipt


def _config_path(repo: Path) -> Path:
    assert GIT is not None
    result = _run_ok(
        [GIT, "rev-parse", "--git-path", "devframe/ci-preflight-python.json"],
        cwd=repo,
    )
    candidate = Path(result.stdout.strip())
    return candidate if candidate.is_absolute() else repo / candidate


def _git_config_path(repo: Path) -> Path:
    assert GIT is not None
    result = _run_ok([GIT, "rev-parse", "--git-path", "config"], cwd=repo)
    candidate = Path(result.stdout.strip())
    return candidate if candidate.is_absolute() else repo / candidate


def _core_hooks_path(repo: Path) -> str | None:
    assert GIT is not None
    result = _run([GIT, "config", "--local", "--get", "core.hooksPath"], cwd=repo)
    return result.stdout.strip() if result.returncode == 0 else None


def _tree_snapshot(root: Path) -> dict[str, bytes | None]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
        for path in sorted(root.rglob("*"))
    }


def _assert_interpreter_pass(receipt: dict[str, object], hook_name: str) -> None:
    assert receipt["hook_name"] == hook_name
    assert receipt["overall_result"] == "PASS"
    interpreter = receipt["python_interpreter"]
    assert isinstance(interpreter, dict)
    assert os.path.normcase(interpreter["executable"]) == os.path.normcase(
        str(Path(sys.executable).resolve())
    )
    assert interpreter["version"] == ".".join(map(str, sys.version_info[:3]))
    assert interpreter["selection_source"] == "explicit_parameter"
    assert interpreter["health"] == "healthy"
    assert interpreter["exit_code"] == 0
    assert interpreter["status"] == "PASS"


def _assert_blocked_commit(
    repo: Path,
    *,
    env: dict[str, str],
    message: str,
    expected_health: str,
) -> dict[str, object]:
    assert GIT is not None
    before = _head(repo)
    result = _run([GIT, "commit", "-m", message], cwd=repo, env=env)
    assert result.returncode != 0, result.stdout + result.stderr
    assert _head(repo) == before
    receipt = _load_receipt(repo)
    assert receipt["hook_name"] == "pre-commit"
    assert receipt["overall_result"] == "BLOCKED"
    interpreter = receipt["python_interpreter"]
    assert isinstance(interpreter, dict)
    assert interpreter["health"] == expected_health
    assert interpreter["status"] == "BLOCKED"
    return receipt


def test_actual_commit_ignores_fake_path_python_and_records_attestation() -> None:
    assert GIT is not None
    with tempfile.TemporaryDirectory(prefix="devframe-hook-commit-") as raw_temp:
        repo = Path(raw_temp) / "repo"
        repo.mkdir()
        _init_repository(repo)
        _copy_template(repo)
        _write_guard(repo)
        registration = _register(repo)
        assert registration.returncode == 0, registration.stdout + registration.stderr

        env, fake_marker, guard_marker = _fake_path_environment(repo)
        _stage(repo, "tracked.txt", "guard must run\n")
        commit = _run([GIT, "commit", "-m", "test: attested hook"], cwd=repo, env=env)

        assert commit.returncode == 0, commit.stdout + commit.stderr
        assert not fake_marker.exists()
        guard_runs = [json.loads(line) for line in guard_marker.read_text().splitlines()]
        assert guard_runs == [{"executable": sys.executable, "mode": "staged"}]
        receipt = _load_receipt(repo)
        _assert_interpreter_pass(receipt, "pre-commit")
        assert any(
            stage["name"] == "ai-guard" and stage["exit_code"] == 0
            for stage in receipt["stages"]
        )
        assert _head(repo) is not None

    assert not Path(raw_temp).exists()


def test_missing_drifted_and_unhealthy_interpreters_block_actual_commits() -> None:
    assert GIT is not None
    with tempfile.TemporaryDirectory(prefix="devframe-hook-blocked-") as raw_temp:
        repo = Path(raw_temp) / "repo"
        repo.mkdir()
        _init_repository(repo)
        _copy_template(repo)
        _write_guard(repo)
        registration = _register(repo)
        assert registration.returncode == 0, registration.stdout + registration.stderr
        env, _, _ = _fake_path_environment(repo)

        _stage(repo, "tracked.txt", "initial\n")
        initial = _run([GIT, "commit", "-m", "test: initial"], cwd=repo, env=env)
        assert initial.returncode == 0, initial.stdout + initial.stderr

        config_path = _config_path(repo)
        original_config = json.loads(config_path.read_text(encoding="utf-8"))

        _stage(repo, "tracked.txt", "missing\n")
        config_path.unlink()
        missing = _assert_blocked_commit(
            repo,
            env=env,
            message="test: missing interpreter",
            expected_health="missing_config",
        )
        assert missing["python_interpreter"]["executable"] is None
        assert missing["python_interpreter"]["exit_code"] is None

        config_path.parent.mkdir(parents=True, exist_ok=True)
        drifted_config = dict(original_config)
        drifted_config["version"] = "0.0.0"
        config_path.write_text(json.dumps(drifted_config), encoding="utf-8")
        drifted = _assert_blocked_commit(
            repo,
            env=env,
            message="test: drifted interpreter",
            expected_health="version_drift",
        )
        assert drifted["python_interpreter"]["executable"] == original_config["executable"]

        binary_drift_config = dict(original_config)
        binary_drift_config["sha256"] = "0" * 64
        config_path.write_text(json.dumps(binary_drift_config), encoding="utf-8")
        binary_drift = _assert_blocked_commit(
            repo,
            env=env,
            message="test: binary drift",
            expected_health="binary_drift",
        )
        assert binary_drift["python_interpreter"]["exit_code"] is None

        unhealthy_executable = repo / "unhealthy-python.cmd"
        unhealthy_executable.write_text("@exit /b 17\r\n", encoding="ascii")
        unhealthy_config = dict(original_config)
        unhealthy_config.update(
            {
                "executable": str(unhealthy_executable),
                "sha256": hashlib.sha256(unhealthy_executable.read_bytes()).hexdigest(),
                "version": ".".join(map(str, sys.version_info[:3])),
            }
        )
        config_path.write_text(json.dumps(unhealthy_config), encoding="utf-8")
        unhealthy = _assert_blocked_commit(
            repo,
            env=env,
            message="test: unhealthy interpreter",
            expected_health="probe_failed",
        )
        assert unhealthy["python_interpreter"]["executable"] == str(unhealthy_executable)
        assert unhealthy["python_interpreter"]["exit_code"] == 17

    assert not Path(raw_temp).exists()


def test_guard_failure_blocks_commit_and_healthy_retry_commits() -> None:
    assert GIT is not None
    with tempfile.TemporaryDirectory(prefix="devframe-hook-guard-") as raw_temp:
        repo = Path(raw_temp) / "repo"
        repo.mkdir()
        _init_repository(repo)
        _copy_template(repo)
        _write_guard(repo)
        registration = _register(repo)
        assert registration.returncode == 0, registration.stdout + registration.stderr
        env, fake_marker, _ = _fake_path_environment(repo)
        _stage(repo, "tracked.txt", "guard failure\n")

        failing_env = env.copy()
        failing_env["DEVFRAME_GUARD_EXIT"] = "23"
        before = _head(repo)
        blocked = _run(
            [GIT, "commit", "-m", "test: guard blocks"],
            cwd=repo,
            env=failing_env,
        )
        assert blocked.returncode != 0, blocked.stdout + blocked.stderr
        assert _head(repo) == before
        blocked_receipt = _load_receipt(repo)
        assert blocked_receipt["overall_result"] == "BLOCKED"
        assert any(
            stage["name"] == "ai-guard" and stage["exit_code"] == 23
            for stage in blocked_receipt["stages"]
        )

        passing = _run([GIT, "commit", "-m", "test: guard passes"], cwd=repo, env=env)
        assert passing.returncode == 0, passing.stdout + passing.stderr
        assert _head(repo) is not None
        assert not fake_marker.exists()
        _assert_interpreter_pass(_load_receipt(repo), "pre-commit")

    assert not Path(raw_temp).exists()


def test_pre_push_and_manual_preflight_reuse_attested_interpreter() -> None:
    assert GIT is not None
    with tempfile.TemporaryDirectory(prefix="devframe-hook-reuse-") as raw_temp:
        repo = Path(raw_temp) / "repo"
        repo.mkdir()
        _init_repository(repo)
        _copy_template(repo)
        _write_guard(repo)
        registration = _register(repo)
        assert registration.returncode == 0, registration.stdout + registration.stderr
        env, fake_marker, guard_marker = _fake_path_environment(repo)

        hook = _run([GIT, "hook", "run", "pre-push"], cwd=repo, env=env)
        assert hook.returncode == 0, hook.stdout + hook.stderr
        _assert_interpreter_pass(_load_receipt(repo), "pre-push")

        assert POWERSHELL is not None
        preflight = _run(
            [
                POWERSHELL,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(repo / "ci-preflight.ps1"),
            ],
            cwd=repo,
            env=env,
        )
        assert preflight.returncode == 0, preflight.stdout + preflight.stderr
        _assert_interpreter_pass(_load_receipt(repo), "ci-preflight")
        assert not fake_marker.exists()
        modes = [json.loads(line)["mode"] for line in guard_marker.read_text().splitlines()]
        assert modes == ["full", "full"]

    assert not Path(raw_temp).exists()


def test_actual_push_blocks_invalid_interpreter_and_preserves_remote_ref() -> None:
    assert GIT is not None
    with tempfile.TemporaryDirectory(prefix="devframe-hook-push-blocked-") as raw_temp:
        root = Path(raw_temp)
        repo = root / "repo"
        remote = root / "remote.git"
        repo.mkdir()
        remote.mkdir()
        _init_repository(repo)
        _copy_template(repo)

        _stage(repo, "tracked.txt", "initial\n")
        _run_ok([GIT, "commit", "-m", "test: initial"], cwd=repo)
        _run_ok([GIT, "init", "--bare", "--initial-branch=main"], cwd=remote)
        _run_ok([GIT, "remote", "add", "origin", str(remote)], cwd=repo)
        _run_ok([GIT, "push", "-u", "origin", "main"], cwd=repo)

        registration = _register(repo)
        assert registration.returncode == 0, registration.stdout + registration.stderr
        _stage(repo, "tracked.txt", "pending push\n")
        _run_ok([GIT, "commit", "-m", "test: pending push"], cwd=repo)

        config_path = _config_path(repo)
        invalid_config = json.loads(config_path.read_text(encoding="utf-8"))
        invalid_config["version"] = "0.0.0"
        config_path.write_text(json.dumps(invalid_config), encoding="utf-8")

        remote_before = _run_ok(
            [GIT, "rev-parse", "refs/heads/main"], cwd=remote
        ).stdout.strip()
        push = _run([GIT, "push", "origin", "main"], cwd=repo)
        assert push.returncode != 0, push.stdout + push.stderr
        remote_after = _run_ok(
            [GIT, "rev-parse", "refs/heads/main"], cwd=remote
        ).stdout.strip()
        assert remote_after == remote_before

        receipt = _load_receipt(repo)
        assert receipt["hook_name"] == "pre-push"
        assert receipt["overall_result"] == "BLOCKED"
        interpreter = receipt["python_interpreter"]
        assert isinstance(interpreter, dict)
        assert interpreter["health"] == "version_drift"
        assert interpreter["selection_source"] == "explicit_parameter"
        assert interpreter["status"] == "BLOCKED"

    assert not Path(raw_temp).exists()


def test_registration_rejects_nested_target_before_repo_writes() -> None:
    assert GIT is not None
    with tempfile.TemporaryDirectory(prefix="devframe-hook-register-nested-") as raw_temp:
        parent = Path(raw_temp) / "parent"
        nested = parent / "nested"
        parent.mkdir()
        nested.mkdir()
        _init_repository(parent)
        _copy_template(nested)
        _run_ok(
            [GIT, "config", "--local", "core.hooksPath", "existing-hooks"],
            cwd=parent,
        )

        config_path = _git_config_path(parent)
        config_before = config_path.read_bytes()
        hooks_path_before = _core_hooks_path(parent)
        target_before = _tree_snapshot(nested)
        python_config = _config_path(parent)
        assert not python_config.exists()

        registration = _register(nested)
        assert registration.returncode != 0, registration.stdout + registration.stderr
        assert config_path.read_bytes() == config_before
        assert _core_hooks_path(parent) == hooks_path_before
        assert _tree_snapshot(nested) == target_before
        assert not python_config.exists()

    assert not Path(raw_temp).exists()


def test_installer_rejects_nested_target_before_file_or_repo_writes() -> None:
    assert GIT is not None
    with tempfile.TemporaryDirectory(prefix="devframe-hook-install-nested-") as raw_temp:
        parent = Path(raw_temp) / "parent"
        nested = parent / "nested"
        parent.mkdir()
        nested.mkdir()
        _init_repository(parent)
        (nested / "sentinel.txt").write_bytes(b"unchanged\r\n")
        _run_ok(
            [GIT, "config", "--local", "core.hooksPath", "existing-hooks"],
            cwd=parent,
        )

        config_path = _git_config_path(parent)
        config_before = config_path.read_bytes()
        hooks_path_before = _core_hooks_path(parent)
        target_before = _tree_snapshot(nested)
        python_config = _config_path(parent)
        assert not python_config.exists()

        install = _powershell(
            TEMPLATE_ROOT / "install.ps1",
            "-TargetProject",
            str(nested),
            "-PythonExecutable",
            sys.executable,
            cwd=parent,
        )
        assert install.returncode != 0, install.stdout + install.stderr
        assert config_path.read_bytes() == config_before
        assert _core_hooks_path(parent) == hooks_path_before
        assert _tree_snapshot(nested) == target_before
        assert not python_config.exists()

    assert not Path(raw_temp).exists()


def test_installer_requires_explicit_python_and_registers_only_target_repo() -> None:
    assert GIT is not None
    with tempfile.TemporaryDirectory(prefix="devframe-hook-install-") as raw_temp:
        root = Path(raw_temp)
        target = root / "target"
        other = root / "other"
        target.mkdir()
        other.mkdir()
        _init_repository(target)
        _init_repository(other)

        install = _powershell(
            TEMPLATE_ROOT / "install.ps1",
            "-TargetProject",
            str(target),
            "-PythonExecutable",
            sys.executable,
            cwd=other,
        )
        assert install.returncode == 0, install.stdout + install.stderr
        assert (target / "hooks" / "python-interpreter.ps1").is_file()
        assert _config_path(target).is_file()
        assert _run_ok(
            [GIT, "config", "--local", "--get", "core.hooksPath"], cwd=target
        ).stdout.strip() == "hooks"
        assert _run(
            [GIT, "config", "--local", "--get", "core.hooksPath"], cwd=other
        ).returncode != 0

        missing_python = _powershell(
            TEMPLATE_ROOT / "install.ps1",
            "-TargetProject",
            str(other),
            cwd=other,
        )
        assert missing_python.returncode != 0
        assert _run(
            [GIT, "config", "--local", "--get", "core.hooksPath"], cwd=other
        ).returncode != 0

    assert not Path(raw_temp).exists()


def test_evidence_schema_mirror_is_exact_and_requires_python_attestation() -> None:
    canonical = EVIDENCE_SCHEMA.read_bytes()
    assert MIRRORED_EVIDENCE_SCHEMA.read_bytes() == canonical
    schema = json.loads(canonical)
    assert "hook_name" in schema["required"]
    assert "python_interpreter" in schema["required"]
    interpreter = schema["properties"]["python_interpreter"]
    assert interpreter["required"] == [
        "executable",
        "version",
        "selection_source",
        "health",
        "exit_code",
        "status",
    ]


def test_agent_prompt_embeds_the_canonical_executable_templates() -> None:
    prompt = (TEMPLATE_ROOT / "AGENT_PROMPT.md").read_text(encoding="utf-8")
    embedded_files = {
        "hooks/pre-commit": TEMPLATE_ROOT / "hooks" / "pre-commit",
        "hooks/pre-commit.governance.ps1": (
            TEMPLATE_ROOT / "hooks" / "pre-commit.governance.ps1"
        ),
        "hooks/pre-push": TEMPLATE_ROOT / "hooks" / "pre-push",
        "hooks/pre-push.governance.ps1": (
            TEMPLATE_ROOT / "hooks" / "pre-push.governance.ps1"
        ),
        "hooks/python-interpreter.ps1": (
            TEMPLATE_ROOT / "hooks" / "python-interpreter.ps1"
        ),
        "register-hooks.ps1": TEMPLATE_ROOT / "register-hooks.ps1",
        "ci-preflight.ps1": TEMPLATE_ROOT / "ci-preflight.ps1",
    }

    for label, source in embedded_files.items():
        heading = f"#### {label}\n"
        section_start = prompt.index(heading) + len(heading)
        fence_start = prompt.index("```", section_start)
        body_start = prompt.index("\n", fence_start) + 1
        fence_end = prompt.index("\n```", body_start)
        assert prompt[body_start:fence_end] == source.read_text(
            encoding="utf-8"
        ).rstrip("\n")

    activation = prompt[prompt.index("### 第四步：激活") :]
    assert "-PythonExecutable $PythonExecutable" in activation
    assert "<absolute-path-to-healthy-python.exe>" in activation
    assert "& python " not in prompt
