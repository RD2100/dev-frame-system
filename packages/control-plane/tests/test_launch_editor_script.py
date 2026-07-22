import os
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
LAUNCHER = REPO_ROOT / "scripts" / "launch-editor.ps1"
PWSH = shutil.which("pwsh")
T3_ROOT_ENV_VARS = ("DEVFRAME_T3_ROOT", "T3CODE_ROOT", "T3_ROOT")


def _create_t3_checkout(path: Path, *, with_bridge: bool) -> Path:
    (path / "apps" / "web").mkdir(parents=True, exist_ok=True)
    (path / "package.json").write_text('{"name":"t3code-test"}\n', encoding="utf-8")
    if with_bridge:
        (path / "devframe.t3desktop.mjs").write_text("// test fixture\n", encoding="utf-8")
    return path


def _run_launcher(
    tmp_path: Path,
    *,
    arguments: str,
    exit_code: int,
    environment: dict[str, str] | None = None,
) -> tuple[dict[str, str], str]:
    fixture_root = tmp_path / "fixture"
    script_dir = fixture_root / "scripts"
    package_dir = fixture_root / "packages" / "control-plane"
    t3_dir = fixture_root / ".devframe-runtime" / "external" / "t3code"
    fake_bin = tmp_path / "fake-bin"
    caller_dir = tmp_path / "caller"
    trace_path = tmp_path / "python-trace.txt"

    for path in (script_dir, package_dir, fake_bin, caller_dir):
        path.mkdir(parents=True, exist_ok=True)
    shutil.copy2(LAUNCHER, script_dir / LAUNCHER.name)
    _create_t3_checkout(t3_dir, with_bridge=True)
    (fake_bin / "python.cmd").write_text(
        "@echo off\r\n"
        '> "%TRACE_PATH%" echo cwd=%CD%\r\n'
        '>> "%TRACE_PATH%" echo args=%*\r\n'
        '>> "%TRACE_PATH%" echo app_id=%T3CODE_DESKTOP_APP_USER_MODEL_ID%\r\n'
        '>> "%TRACE_PATH%" echo force_build=%DEVFRAME_T3_FORCE_BUILD%\r\n'
        'if "%~1"=="-c" exit /b 0\r\n'
        "exit /b %FAKE_EXIT_CODE%\r\n",
        encoding="ascii",
    )

    env = os.environ.copy()
    for name in T3_ROOT_ENV_VARS:
        env.pop(name, None)
    env.update(environment or {})
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["TRACE_PATH"] = str(trace_path)
    env["FAKE_EXIT_CODE"] = str(exit_code)
    env["T3CODE_DESKTOP_APP_USER_MODEL_ID"] = "caller-app-id"
    env["DEVFRAME_T3_FORCE_BUILD"] = "caller-force-build"

    launcher = script_dir / LAUNCHER.name
    command = (
        "$PSNativeCommandUseErrorActionPreference = $true; "
        f"Set-Location -LiteralPath '{caller_dir}'; "
        "$caught = $false; "
        f"try {{ . '{launcher}' {arguments} }} catch {{ $caught = $true }}; "
        "Write-Output ('CALLER_STATE|{0}|{1}|{2}|{3}' -f "
        "(Get-Location).Path, $env:T3CODE_DESKTOP_APP_USER_MODEL_ID, "
        "$env:DEVFRAME_T3_FORCE_BUILD, $caught)"
    )
    completed = subprocess.run(
        [PWSH, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=caller_dir,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert completed.returncode == 0, completed.stderr
    trace = dict(line.split("=", 1) for line in trace_path.read_text(encoding="utf-8").splitlines())
    caller_state = next(line for line in completed.stdout.splitlines() if line.startswith("CALLER_STATE|"))
    return trace, caller_state


@pytest.mark.skipif(PWSH is None, reason="PowerShell is required for the Windows launcher probe")
def test_launch_editor_uses_explicit_external_t3_root_without_preinstalled_bridge(tmp_path):
    external_t3 = _create_t3_checkout(tmp_path / "external t3", with_bridge=False)
    environment_t3 = _create_t3_checkout(tmp_path / "environment t3", with_bridge=False)

    trace, caller_state = _run_launcher(
        tmp_path,
        arguments=f"-T3Root '{external_t3}'",
        exit_code=0,
        environment={"DEVFRAME_T3_ROOT": str(environment_t3)},
    )

    assert str(external_t3) in trace["args"]
    assert str(environment_t3) not in trace["args"]
    assert trace["args"].endswith("--prod")
    assert caller_state.endswith("|False")


@pytest.mark.skipif(PWSH is None, reason="PowerShell is required for the Windows launcher probe")
def test_launch_editor_uses_devframe_t3_root_without_arguments(tmp_path):
    external_t3 = _create_t3_checkout(tmp_path / "external t3", with_bridge=False)
    t3code_root = _create_t3_checkout(tmp_path / "t3code root", with_bridge=False)
    t3_root = _create_t3_checkout(tmp_path / "t3 root", with_bridge=False)

    trace, caller_state = _run_launcher(
        tmp_path,
        arguments="",
        exit_code=0,
        environment={
            "DEVFRAME_T3_ROOT": str(external_t3),
            "T3CODE_ROOT": str(t3code_root),
            "T3_ROOT": str(t3_root),
        },
    )

    assert str(external_t3) in trace["args"]
    assert str(t3code_root) not in trace["args"]
    assert str(t3_root) not in trace["args"]
    assert trace["args"].endswith("--prod")
    assert caller_state.endswith("|False")


@pytest.mark.skipif(PWSH is None, reason="PowerShell is required for the Windows launcher probe")
@pytest.mark.parametrize("variable_name", ["T3CODE_ROOT", "T3_ROOT"])
def test_launch_editor_uses_fallback_t3_root_environment_variables(tmp_path, variable_name: str):
    external_t3 = _create_t3_checkout(tmp_path / variable_name.lower(), with_bridge=False)

    trace, caller_state = _run_launcher(
        tmp_path,
        arguments="",
        exit_code=0,
        environment={variable_name: str(external_t3)},
    )

    assert str(external_t3) in trace["args"]
    assert caller_state.endswith("|False")


@pytest.mark.skipif(PWSH is None, reason="PowerShell is required for the Windows launcher probe")
def test_launch_editor_rejects_invalid_explicit_t3_root(tmp_path):
    invalid_t3 = tmp_path / "invalid t3"
    invalid_t3.mkdir()

    completed = subprocess.run(
        [
            PWSH,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(LAUNCHER),
            "-T3Root",
            str(invalid_t3),
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "NO_COLOR": "1"},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert completed.returncode == 1
    assert "Invalid T3 editor checkout at" in completed.stderr
    assert str(invalid_t3) in completed.stderr
    assert "package.json and apps\\web" in completed.stderr


@pytest.mark.skipif(PWSH is None, reason="PowerShell is required for the Windows launcher probe")
def test_launch_editor_scopes_rebuild_and_restores_caller_state(tmp_path):
    trace, caller_state = _run_launcher(tmp_path, arguments="-Rebuild", exit_code=0)

    assert Path(trace["cwd"]) == tmp_path / "fixture" / "packages" / "control-plane"
    assert str(tmp_path / "fixture" / ".devframe-runtime" / "external" / "t3code") in trace["args"]
    assert trace["args"].endswith("--prod")
    assert "--overwrite-bridge" in trace["args"].split()
    assert "--force" not in trace["args"].split()
    assert trace["force_build"] == "1"
    assert trace["app_id"] == "com.rdcode.client"
    assert caller_state == f"CALLER_STATE|{tmp_path / 'caller'}|caller-app-id|caller-force-build|False"


@pytest.mark.skipif(PWSH is None, reason="PowerShell is required for the Windows launcher probe")
def test_launch_editor_restores_caller_state_after_child_failure(tmp_path):
    trace, caller_state = _run_launcher(tmp_path, arguments="-Dev", exit_code=7)

    assert "--prod" not in trace["args"]
    assert "--overwrite-bridge" in trace["args"].split()
    assert "--force" not in trace["args"].split()
    assert trace["force_build"] == "caller-force-build"
    assert caller_state == f"CALLER_STATE|{tmp_path / 'caller'}|caller-app-id|caller-force-build|True"
