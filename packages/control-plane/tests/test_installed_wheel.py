from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


CONTROL_PLANE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
CANARY_SKILLS = ("intent-framing-gate", "evidence-driven-acceptance")
GENERATED_DIR_NAMES = {
    "build",
    "dist",
    ".eggs",
    ".hypothesis",
    "htmlcov",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".tox",
    ".nox",
}


def _is_generated_name(name: str) -> bool:
    return (
        name in GENERATED_DIR_NAMES
        or name.endswith((".egg-info", ".pyc", ".pyo"))
        or name == ".coverage"
    )


def _is_generated_path(relative_path: Path) -> bool:
    return any(_is_generated_name(part) for part in relative_path.parts)


def _ignore_generated(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if _is_generated_name(name)}


def _snapshot_generated_state(root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if not _is_generated_path(relative):
            continue
        snapshot[relative.as_posix()] = (
            f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
            if path.is_file()
            else "directory"
        )
    return snapshot


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env["PYTHONNOUSERSITE"] = "1"
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _assert_success(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, (
        f"command failed ({result.returncode}): {result.args!r}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.fixture(scope="module")
def installed_control_plane(tmp_path_factory):
    root = tmp_path_factory.mktemp("installed-control-plane")
    wheelhouse = root / "wheelhouse"
    venv = root / "venv"
    outside = root / "outside"
    wheelhouse.mkdir()
    outside.mkdir()
    build_python = os.environ.get("DEVFRAME_WHEEL_BUILD_PYTHON", sys.executable)
    source_generated_before = _snapshot_generated_state(CONTROL_PLANE_ROOT)
    build_source = root / "control-plane-source"
    shutil.copytree(
        CONTROL_PLANE_ROOT,
        build_source,
        ignore=_ignore_generated,
    )
    build_source_generated_before = _snapshot_generated_state(build_source)

    build = _run(
        [
            build_python,
            "-m",
            "pip",
            "wheel",
            str(build_source),
            "--wheel-dir",
            str(wheelhouse),
            "--no-deps",
            "--no-build-isolation",
            "--no-index",
            "--no-cache-dir",
        ],
        cwd=outside,
    )
    _assert_success(build)
    wheels = list(wheelhouse.glob("*.whl"))
    assert len(wheels) == 1

    create_venv = _run(
        [sys.executable, "-m", "venv", "--system-site-packages", str(venv)],
        cwd=outside,
    )
    _assert_success(create_venv)
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    devframe = venv / ("Scripts/devframe.exe" if os.name == "nt" else "bin/devframe")
    install = _run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--no-index",
            "--no-cache-dir",
            str(wheels[0]),
        ],
        cwd=outside,
    )
    _assert_success(install)
    source_generated_after = _snapshot_generated_state(CONTROL_PLANE_ROOT)

    try:
        yield {
            "root": root,
            "venv": venv,
            "outside": outside,
            "python": python,
            "devframe": devframe,
            "wheel": wheels[0],
            "build_source": build_source,
            "build_source_generated_before": build_source_generated_before,
            "source_generated_before": source_generated_before,
            "source_generated_after": source_generated_after,
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_wheel_build_uses_clean_temp_source_without_touching_worktree(
    installed_control_plane,
):
    build_source = installed_control_plane["build_source"].resolve()

    assert build_source != CONTROL_PLANE_ROOT.resolve()
    assert build_source.is_relative_to(installed_control_plane["root"].resolve())
    assert installed_control_plane["build_source_generated_before"] == {}
    assert installed_control_plane["source_generated_after"] == (
        installed_control_plane["source_generated_before"]
    )


def _write_policy(runtime_dir: Path, project_id: str) -> None:
    policy_path = runtime_dir / project_id / "skills.json"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text(
        json.dumps(
            {
                "version": 1,
                "skills": [
                    {
                        "id": "workflow-canary-read-only",
                        "title": "Workflow canary read only",
                        "triggers": ["@workflow-canary-read-only"],
                        "readOnly": True,
                        "networkEnabled": False,
                        "requireRedGreenEvidence": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _run_installed_canary_preview(
    installed_control_plane: dict[str, Path],
    *,
    project_name: str,
) -> subprocess.CompletedProcess[str]:
    project = installed_control_plane["outside"] / project_name
    runtime = installed_control_plane["outside"] / f"{project_name}-runtime"
    project.mkdir()
    _write_policy(runtime, project_name)
    return _run(
        [
            str(installed_control_plane["devframe"]),
            "code",
            "@go read inspect the bounded source.",
            "--project",
            str(project),
            "--runtime-dir",
            str(runtime),
            "--workflow-canary",
            "--preview",
        ],
        cwd=installed_control_plane["outside"],
    )


def test_installed_wheel_runs_workflow_canary_preview_outside_checkout(
    installed_control_plane,
):
    result = _run_installed_canary_preview(
        installed_control_plane,
        project_name="installed-preview-project",
    )

    _assert_success(result)
    assert "workflow     : canary_only" in result.stdout
    assert "worker       : none (canary-only; no command or ACP)" in result.stdout
    assert "pre:intent" in result.stdout
    assert "post:evidence" in result.stdout
    project = installed_control_plane["outside"] / "installed-preview-project"
    runtime = installed_control_plane["outside"] / "installed-preview-project-runtime"
    assert list(project.rglob("*")) == []
    assert {
        path.relative_to(runtime).as_posix()
        for path in runtime.rglob("*")
        if path.is_file()
    } == {"installed-preview-project/skills.json"}


def test_installed_wheel_ignores_environment_root_skill_shadow(
    installed_control_plane,
):
    fake_bytes = b"---\nname: shadowed\ndescription: injected\n---\n"
    site_packages = (
        installed_control_plane["venv"] / "Lib" / "site-packages"
        if os.name == "nt"
        else next(
            path
            for path in (installed_control_plane["venv"] / "lib").glob(
                "python*/site-packages"
            )
            if path.is_dir()
        )
    )
    (site_packages / "setup.py").write_text("# environment shadow\n", encoding="utf-8")
    for prefix in (Path("tools/skills"), Path("templates/methodology-skills")):
        for skill_id in CANARY_SKILLS:
            shadow = installed_control_plane["venv"] / prefix / skill_id / "SKILL.md"
            shadow.parent.mkdir(parents=True, exist_ok=True)
            shadow.write_bytes(fake_bytes)

    result = _run_installed_canary_preview(
        installed_control_plane,
        project_name="shadow-project",
    )
    _assert_success(result)

    runtime = installed_control_plane["outside"] / "shadow-project-runtime"
    inspect_code = "\n".join(
        [
            "import json, sys",
            "from control_plane.methodology_dispatch import prepare_workflow_canary_binding",
            "profile, binding = prepare_workflow_canary_binding(runtime_dir=sys.argv[1], project_id=sys.argv[2])",
            "print(json.dumps({'module': __import__('control_plane').__file__, 'stages': binding['stage_bindings']}))",
        ]
    )
    inspection = _run(
        [
            str(installed_control_plane["python"]),
            "-c",
            inspect_code,
            str(runtime),
            "shadow-project",
        ],
        cwd=installed_control_plane["outside"],
    )
    _assert_success(inspection)
    payload = json.loads(inspection.stdout)
    module_path = Path(payload["module"]).resolve()
    assert module_path.is_relative_to(installed_control_plane["venv"].resolve())

    stages = {stage["skill_id"]: stage for stage in payload["stages"]}
    for skill_id in CANARY_SKILLS:
        canonical = REPO_ROOT / "tools" / "skills" / skill_id / "SKILL.md"
        assert stages[skill_id]["source_path"].replace("\\", "/") == (
            f"templates/methodology-skills/{skill_id}/SKILL.md"
        )
        assert stages[skill_id]["skill_fingerprint"] == (
            f"sha256:{hashlib.sha256(canonical.read_bytes()).hexdigest()}"
        )
