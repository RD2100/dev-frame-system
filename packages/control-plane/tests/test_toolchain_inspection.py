"""Production-shaped tests for read-only governed toolchain inspection."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import control_plane.toolchain_inspection as toolchain_inspection_module
from control_plane.cli.app import main
from control_plane.go_dispatch import run_go_dispatch
from control_plane.toolchain_inspection import inspect_toolchain_run


def _write_manifest(project: Path) -> Path:
    manifest = project / "toolchain.json"
    command = [
        sys.executable,
        "-c",
        "from pathlib import Path; Path('inspection-marker.txt').write_text('ok', encoding='utf-8')",
    ]
    manifest.write_text(
        json.dumps(
            {
                "toolchain_id": "inspection-python",
                "compiler": "python",
                "working_directory": ".",
                "commands": {"build": command, "test": command},
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _execute_toolchain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[Path, Path, Path, str]:
    project = tmp_path / "project"
    project.mkdir()
    manifest = _write_manifest(project)
    runtime = tmp_path / "runtime"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "toolchain",
            "run",
            "--manifest",
            str(manifest),
            "--action",
            "test",
            "--project",
            str(project),
            "--runtime-dir",
            str(runtime),
            "--execute",
            "--format",
            "json",
        ],
    )
    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    return project, manifest, runtime, payload["go_run_id"]


def _runtime_snapshot(runtime: Path) -> dict[str, tuple[str, int]]:
    return {
        str(path.relative_to(runtime)): (
            hashlib.sha256(path.read_bytes()).hexdigest(),
            path.stat().st_mtime_ns,
        )
        for path in runtime.rglob("*")
        if path.is_file()
    }


def _replace_directory_with_link(source: Path, target: Path) -> None:
    source.rename(target)
    try:
        source.symlink_to(target, target_is_directory=True)
    except OSError as symlink_error:
        if os.name != "nt":
            raise
        completed = subprocess.run(
            ["cmd", "/d", "/c", "mklink", "/J", str(source), str(target)],
            capture_output=True,
            check=False,
            text=True,
        )
        if completed.returncode != 0:
            pytest.fail(
                "could not create the required directory symlink or junction: "
                f"symlink={symlink_error}; junction={completed.stderr or completed.stdout}"
            )
    assert source.resolve() == target.resolve()


def _remove_directory_link(path: Path) -> None:
    if path.is_symlink():
        path.unlink()
    elif path.exists():
        os.rmdir(path)


def test_toolchain_status_cli_reads_structured_provenance_and_canonical_state(
    tmp_path, monkeypatch, capsys
):
    project, manifest, runtime, run_id = _execute_toolchain(
        tmp_path, monkeypatch, capsys
    )
    before = _runtime_snapshot(runtime)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "toolchain",
            "status",
            run_id,
            "--runtime-dir",
            str(runtime),
            "--format",
            "json",
        ],
    )

    assert main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["run_id"] == run_id
    assert payload["action"] == "test"
    assert payload["approved_manifest_sha256"] == hashlib.sha256(
        manifest.read_bytes()
    ).hexdigest()
    assert payload["project_root"] == str(project.resolve())
    assert payload["working_directory"] == str(project.resolve())
    assert payload["worker_outcome"] == "passed"
    assert Path(payload["report_path"]).name == "ExecutionReport.md"
    assert payload["review_state"] == "review_pending"
    assert payload["acceptance_state"] == "review_pending"
    assert payload["execution"] == "explicit_only"
    assert _runtime_snapshot(runtime) == before


def test_toolchain_status_latest_ignores_newer_generic_go_run(
    tmp_path, monkeypatch, capsys
):
    _project, _manifest, runtime, toolchain_run_id = _execute_toolchain(
        tmp_path, monkeypatch, capsys
    )
    generic_project = tmp_path / "generic-project"
    generic_project.mkdir()
    generic = run_go_dispatch(
        generic_project,
        "Prepare a newer generic run.",
        runtime_dir=runtime,
        agents=1,
        execute=False,
        model_provider="opencode-api",
    )
    assert generic.go_run_id != toolchain_run_id
    generic_metadata = runtime / "go-runs" / generic.go_run_id / "go-run.json"
    assert "toolchain" not in json.loads(generic_metadata.read_text(encoding="utf-8"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "toolchain",
            "status",
            "latest",
            "--runtime-dir",
            str(runtime),
            "--format",
            "json",
        ],
    )

    assert main() == 0

    assert json.loads(capsys.readouterr().out)["run_id"] == toolchain_run_id


def test_toolchain_status_latest_rejects_metadata_run_id_redirect(
    tmp_path, monkeypatch, capsys
):
    _project, _manifest, runtime, run_id = _execute_toolchain(
        tmp_path, monkeypatch, capsys
    )
    original = runtime / "go-runs" / run_id / "go-run.json"
    redirected = (
        runtime / "go-runs" / "toolchain-newer-redirect" / "go-run.json"
    )
    redirected.parent.mkdir(parents=True)
    redirected.write_bytes(original.read_bytes())
    newer_mtime = original.stat().st_mtime_ns + 10_000_000_000
    os.utime(redirected, ns=(newer_mtime, newer_mtime))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "toolchain",
            "status",
            "latest",
            "--runtime-dir",
            str(runtime),
        ],
    )

    assert main() == 1
    assert "metadata run id does not match directory" in capsys.readouterr().err


def test_toolchain_status_explicit_rejects_metadata_run_id_mismatch(
    tmp_path, monkeypatch, capsys
):
    _project, _manifest, runtime, run_id = _execute_toolchain(
        tmp_path, monkeypatch, capsys
    )
    metadata_path = runtime / "go-runs" / run_id / "go-run.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["go_run_id"] = "toolchain-mismatched-id"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "toolchain",
            "status",
            run_id,
            "--runtime-dir",
            str(runtime),
        ],
    )

    assert main() == 1
    assert "metadata run id does not match directory" in capsys.readouterr().err


def test_toolchain_status_rejects_metadata_replacement_between_reads(
    tmp_path, monkeypatch, capsys
):
    _project, _manifest, runtime, run_id = _execute_toolchain(
        tmp_path, monkeypatch, capsys
    )
    metadata_path = runtime / "go-runs" / run_id / "go-run.json"
    original_bytes = metadata_path.read_bytes()
    replacement = json.loads(original_bytes)
    replacement["project_id"] = "replacement-project"
    replacement["toolchain"]["action"] = "build"
    replacement_bytes = json.dumps(replacement).encode("utf-8")
    original_loader = toolchain_inspection_module.load_go_run_result_snapshot

    def load_after_replacement(runtime_root, selected_run_id):
        metadata_path.write_bytes(replacement_bytes)
        try:
            return original_loader(runtime_root, selected_run_id)
        finally:
            metadata_path.write_bytes(original_bytes)

    monkeypatch.setattr(
        toolchain_inspection_module,
        "load_go_run_result_snapshot",
        load_after_replacement,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "toolchain",
            "status",
            run_id,
            "--runtime-dir",
            str(runtime),
            "--format",
            "json",
        ],
    )

    assert main() == 1
    captured = capsys.readouterr()
    assert "metadata changed during inspection" in captured.err
    assert captured.out == ""


def test_toolchain_status_explicit_rejects_linked_metadata_outside_runtime(
    tmp_path, monkeypatch, capsys
):
    _project, _manifest, runtime, run_id = _execute_toolchain(
        tmp_path, monkeypatch, capsys
    )
    run_directory = runtime / "go-runs" / run_id
    outside_directory = tmp_path / "outside-toolchain-run"
    _replace_directory_with_link(run_directory, outside_directory)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "toolchain",
            "status",
            run_id,
            "--runtime-dir",
            str(runtime),
        ],
    )

    try:
        assert main() == 1
        assert "metadata is outside runtime" in capsys.readouterr().err
    finally:
        _remove_directory_link(run_directory)


def test_toolchain_status_cli_rejects_non_object_agent_entries(
    tmp_path, monkeypatch, capsys
):
    _project, _manifest, runtime, run_id = _execute_toolchain(
        tmp_path, monkeypatch, capsys
    )
    metadata_path = runtime / "go-runs" / run_id / "go-run.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["agents"] = [None]
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "toolchain",
            "status",
            run_id,
            "--runtime-dir",
            str(runtime),
        ],
    )

    assert main() == 1
    assert "agents must be a list of objects" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ("{not-json", "metadata is unreadable"),
        ("[]", "metadata is unreadable"),
        (
            json.dumps(
                {
                    "go_run_id": "toolchain-newer-malformed",
                    "created_at": "9999-12-31T23:59:59Z",
                    "toolchain": [],
                }
            ),
            "not a toolchain run",
        ),
    ],
)
def test_toolchain_status_latest_rejects_newer_unreadable_toolchain_metadata(
    tmp_path, monkeypatch, capsys, payload, expected
):
    _project, _manifest, runtime, _run_id = _execute_toolchain(
        tmp_path, monkeypatch, capsys
    )
    metadata = runtime / "go-runs" / "toolchain-newer-malformed" / "go-run.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(payload, encoding="utf-8")
    prior_metadata = next(
        path
        for path in (runtime / "go-runs").glob("*/go-run.json")
        if path != metadata
    )
    newer_mtime = prior_metadata.stat().st_mtime_ns + 10_000_000_000
    os.utime(metadata, ns=(newer_mtime, newer_mtime))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "toolchain",
            "status",
            "latest",
            "--runtime-dir",
            str(runtime),
        ],
    )

    assert main() == 1
    assert expected in capsys.readouterr().err


@pytest.mark.parametrize(
    "payload",
    [
        "{not-json",
        "[]",
        json.dumps({"go_run_id": "go-different-generic"}),
    ],
)
def test_toolchain_status_ignores_unrelated_corrupt_generic_metadata(
    tmp_path, monkeypatch, capsys, payload
):
    _project, _manifest, runtime, run_id = _execute_toolchain(
        tmp_path, monkeypatch, capsys
    )
    generic_metadata = runtime / "go-runs" / "go-corrupt-generic" / "go-run.json"
    generic_metadata.parent.mkdir(parents=True)
    generic_metadata.write_text(payload, encoding="utf-8")

    for selected_run_id in (run_id, "latest"):
        newer_mtime = (
            runtime / "go-runs" / run_id / "go-run.json"
        ).stat().st_mtime_ns + 10_000_000_000
        os.utime(generic_metadata, ns=(newer_mtime, newer_mtime))
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "devframe",
                "toolchain",
                "status",
                selected_run_id,
                "--runtime-dir",
                str(runtime),
                "--format",
                "json",
            ],
        )

        assert main() == 0
        assert json.loads(capsys.readouterr().out)["run_id"] == run_id


def test_toolchain_inspection_rejects_non_toolchain_run(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    runtime = tmp_path / "runtime"
    generic = run_go_dispatch(
        project,
        "Prepare a generic run.",
        runtime_dir=runtime,
        agents=1,
        execute=False,
        model_provider="opencode-api",
    )

    with pytest.raises(ValueError, match="not a toolchain run"):
        inspect_toolchain_run(runtime, generic.go_run_id)


def test_toolchain_inspection_rejects_missing_canonical_pair(
    tmp_path, monkeypatch, capsys
):
    _project, _manifest, runtime, run_id = _execute_toolchain(
        tmp_path, monkeypatch, capsys
    )
    (runtime / "team-events.jsonl").unlink()

    with pytest.raises(ValueError, match="canonical projection is unavailable"):
        inspect_toolchain_run(runtime, run_id)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("outcome", None),
        ("review_state", ""),
        ("acceptance_state", []),
    ],
)
def test_toolchain_inspection_rejects_incomplete_canonical_state(
    tmp_path, monkeypatch, capsys, field, value
):
    _project, _manifest, runtime, run_id = _execute_toolchain(
        tmp_path, monkeypatch, capsys
    )
    index = toolchain_inspection_module.build_run_index(runtime)
    entry = next(
        candidate
        for candidate in index["canonical_runs"]
        if any(
            source.get("adapter_id") == "go_run"
            and source.get("legacy_id") == run_id
            for source in candidate["provenance"]["sources"]
        )
    )
    record = entry["record"]
    if value is None:
        record.pop(field)
    else:
        record[field] = value
    monkeypatch.setattr(
        toolchain_inspection_module,
        "build_run_index",
        lambda _runtime_root: index,
    )

    with pytest.raises(ValueError, match="canonical projection is unreadable"):
        inspect_toolchain_run(runtime, run_id)


def test_toolchain_inspection_rejects_empty_runtime(tmp_path):
    with pytest.raises(ValueError, match="no toolchain runs found"):
        inspect_toolchain_run(tmp_path / "missing-runtime")


def test_toolchain_inspection_rejects_path_like_run_id(tmp_path):
    with pytest.raises(ValueError, match="toolchain run id is invalid"):
        inspect_toolchain_run(tmp_path / "runtime", "../outside")


def test_toolchain_inspection_rejects_corrupt_metadata(tmp_path):
    runtime = tmp_path / "runtime"
    metadata = runtime / "go-runs" / "toolchain-corrupt" / "go-run.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="metadata is unreadable"):
        inspect_toolchain_run(runtime, "toolchain-corrupt")


@pytest.mark.parametrize("payload", ["[]", '{"action": ["test"]}'])
def test_toolchain_inspection_rejects_non_object_or_typed_metadata(
    tmp_path, payload
):
    runtime = tmp_path / "runtime"
    run_id = "toolchain-malformed"
    metadata = runtime / "go-runs" / run_id / "go-run.json"
    metadata.parent.mkdir(parents=True)
    if payload == "[]":
        metadata.write_text(payload, encoding="utf-8")
        expected = "metadata is unreadable"
    else:
        data = {
            "go_run_id": run_id,
            "project_id": "demo",
            "project_root": str(tmp_path),
            "runtime_dir": str(runtime),
            "status": "passed",
            "execute": True,
            "agents": [],
            "toolchain": {
                "action": ["test"],
                "approved_manifest_sha256": "0" * 64,
                "manifest_path": str(tmp_path / "toolchain.json"),
                "working_directory": str(tmp_path),
            },
        }
        metadata.write_text(json.dumps(data), encoding="utf-8")
        expected = "provenance is incomplete"

    with pytest.raises(ValueError, match=expected):
        inspect_toolchain_run(runtime, run_id)


def test_toolchain_inspection_rejects_missing_report(
    tmp_path, monkeypatch, capsys
):
    _project, _manifest, runtime, run_id = _execute_toolchain(
        tmp_path, monkeypatch, capsys
    )
    report = next(runtime.rglob("ExecutionReport.md"))
    report.unlink()

    with pytest.raises(ValueError, match="toolchain report is unavailable"):
        inspect_toolchain_run(runtime, run_id)


def test_toolchain_inspection_rejects_existing_report_outside_runtime(
    tmp_path, monkeypatch, capsys
):
    _project, _manifest, runtime, run_id = _execute_toolchain(
        tmp_path, monkeypatch, capsys
    )
    outside_report = tmp_path / "outside" / "ExecutionReport.md"
    outside_report.parent.mkdir()
    outside_report.write_text("# outside\n", encoding="utf-8")
    metadata_path = runtime / "go-runs" / run_id / "go-run.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["agents"][0]["report_path"] = str(outside_report)
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    before = _runtime_snapshot(runtime)

    with pytest.raises(ValueError, match="toolchain report is unavailable"):
        inspect_toolchain_run(runtime, run_id)

    assert _runtime_snapshot(runtime) == before


def test_toolchain_status_help_is_public(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        ["devframe", "toolchain", "status", "--help"],
    )

    assert main() == 0

    assert "Usage: devframe toolchain status" in capsys.readouterr().out
