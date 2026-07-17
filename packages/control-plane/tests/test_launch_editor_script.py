import os
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
LAUNCHER = REPO_ROOT / "scripts" / "launch-editor.ps1"
PWSH = shutil.which("pwsh")


def _run_launcher(tmp_path: Path, *, arguments: str, exit_code: int) -> tuple[dict[str, str], str]:
    fixture_root = tmp_path / "fixture"
    script_dir = fixture_root / "scripts"
    package_dir = fixture_root / "packages" / "control-plane"
    t3_dir = fixture_root / ".devframe-runtime" / "external" / "t3code"
    fake_bin = tmp_path / "fake-bin"
    caller_dir = tmp_path / "caller"
    trace_path = tmp_path / "python-trace.txt"

    for path in (script_dir, package_dir, t3_dir, fake_bin, caller_dir):
        path.mkdir(parents=True, exist_ok=True)
    shutil.copy2(LAUNCHER, script_dir / LAUNCHER.name)
    (t3_dir / "devframe.t3desktop.mjs").write_text("// test fixture\n", encoding="utf-8")
    (fake_bin / "python.cmd").write_text(
        "@echo off\r\n"
        '> "%TRACE_PATH%" echo cwd=%CD%\r\n'
        '>> "%TRACE_PATH%" echo args=%*\r\n'
        '>> "%TRACE_PATH%" echo app_id=%T3CODE_DESKTOP_APP_USER_MODEL_ID%\r\n'
        '>> "%TRACE_PATH%" echo force_build=%DEVFRAME_T3_FORCE_BUILD%\r\n'
        "exit /b %FAKE_EXIT_CODE%\r\n",
        encoding="ascii",
    )

    env = os.environ.copy()
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
    )

    assert completed.returncode == 0, completed.stderr
    trace = dict(line.split("=", 1) for line in trace_path.read_text(encoding="utf-8").splitlines())
    caller_state = next(line for line in completed.stdout.splitlines() if line.startswith("CALLER_STATE|"))
    return trace, caller_state


@pytest.mark.skipif(PWSH is None, reason="PowerShell is required for the Windows launcher probe")
def test_launch_editor_scopes_rebuild_and_restores_caller_state(tmp_path):
    trace, caller_state = _run_launcher(tmp_path, arguments="-Rebuild", exit_code=0)

    assert Path(trace["cwd"]) == tmp_path / "fixture" / "packages" / "control-plane"
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
