"""Tests for the bounded CodeGraph status/freshness transport."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import control_plane.codegraph_status_transport as transport
from control_plane.codegraph_status_transport import (
    CodeGraphStatusTransportError,
    build_codegraph_status_attestation,
    query_codegraph_status,
)


def _payload(root: Path, *, initialized: bool = True, pending: dict | None = None) -> dict:
    return {
        "initialized": initialized,
        "projectPath": str(root.resolve()),
        "fileCount": 379,
        "nodeCount": 8263,
        "edgeCount": 15821,
        "dbSizeBytes": 28057600,
        "backend": "node-sqlite",
        "journalMode": "wal",
        "nodesByKind": {"file": 355, "function": 4041},
        "languages": ["javascript", "python", "yaml"],
        "pendingChanges": pending or {"added": 0, "modified": 0, "removed": 0},
    }


def _build(root: Path, payload: dict | None = None) -> dict:
    return build_codegraph_status_attestation(
        payload or _payload(root),
        project_root=root,
        project_id="project-1",
        resource_id="codegraph-project-1",
        index_name="project-1-codegraph",
    )


def test_clean_initialized_status_is_current_and_pathless(tmp_path):
    result = _build(tmp_path)

    assert result["index_status"] == "current"
    assert result["index_freshness"] == "current"
    assert result["trusted_for_current_run"] is False
    assert result["pending_changes"] == {"added": 0, "modified": 0, "removed": 0}
    assert result["counts"]["files"] == 379
    assert result["source_adapter"]["transport"] == "codegraph_status_json"
    assert str(tmp_path) not in json.dumps(result)


def test_pending_changes_make_status_stale(tmp_path):
    result = _build(
        tmp_path,
        _payload(tmp_path, pending={"added": 1, "modified": 0, "removed": 2}),
    )

    assert result["index_status"] == "stale"
    assert result["index_freshness"] == "stale"
    assert sum(result["pending_changes"].values()) == 3


def test_uninitialized_status_is_missing_but_not_trusted(tmp_path):
    result = _build(tmp_path, _payload(tmp_path, initialized=False))

    assert result["index_status"] == "missing"
    assert result["index_freshness"] == "unknown"
    assert result["source_adapter"]["trusted_for_current_run"] is False


def test_status_payload_is_not_mutated_and_is_deterministic(tmp_path):
    payload = _payload(tmp_path)
    before = copy.deepcopy(payload)

    first = _build(tmp_path, payload)
    second = _build(tmp_path, payload)

    assert payload == before
    assert first == second


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda value: value.update({"unknown": True}), "unsupported fields"),
        (lambda value: value.update({"projectPath": "D:/other"}), "binding"),
        (lambda value: value.update({"nodeCount": -1}), "counts"),
        (lambda value: value.update({"pendingChanges": {"extra": 1}}), "unsupported fields"),
        (lambda value: value.update({"languages": ["python\nsecret"]}), "languages"),
    ],
)
def test_malformed_status_fails_closed(tmp_path, mutator, message):
    payload = _payload(tmp_path)
    mutator(payload)

    with pytest.raises(CodeGraphStatusTransportError, match=message):
        _build(tmp_path, payload)


def test_binding_error_does_not_leak_reported_path(tmp_path):
    payload = _payload(tmp_path)
    payload["projectPath"] = r"D:\private\project"

    with pytest.raises(CodeGraphStatusTransportError) as raised:
        _build(tmp_path, payload)
    assert "D:\\private" not in str(raised.value)


def test_query_uses_exact_read_only_argv_without_shell(tmp_path, monkeypatch):
    calls: list[tuple[list[str], dict]] = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return type(
            "Result",
            (),
            {"returncode": 0, "stdout": json.dumps(_payload(tmp_path)), "stderr": "private"},
        )()

    monkeypatch.setattr(transport.subprocess, "run", fake_run)
    result = query_codegraph_status(
        project_root=tmp_path,
        project_id="project-1",
        resource_id="codegraph-project-1",
        index_name="project-1-codegraph",
    )

    argv, kwargs = calls[0]
    assert argv == [
        transport.DEFAULT_EXECUTABLE,
        "status",
        "--json",
        str(Path(tmp_path).resolve()),
    ]
    assert kwargs["shell"] is False
    assert kwargs["cwd"] == Path(tmp_path).resolve()
    assert result["index_status"] == "current"


@pytest.mark.parametrize(
    ("exception", "code"),
    [(TimeoutError(), "timeout"), (FileNotFoundError(), "unavailable")],
)
def test_query_failures_are_stable(tmp_path, monkeypatch, exception, code):
    monkeypatch.setattr(transport.subprocess, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(exception))

    with pytest.raises(CodeGraphStatusTransportError) as raised:
        query_codegraph_status(
            project_root=tmp_path,
            project_id="project-1",
            resource_id="codegraph-project-1",
            index_name="project-1-codegraph",
        )
    assert raised.value.code == code
    assert "stderr" not in str(raised.value)


def test_query_nonzero_and_malformed_json_fail_closed(tmp_path, monkeypatch):
    class Result:
        returncode = 1
        stdout = "{}"
        stderr = "private details"

    monkeypatch.setattr(transport.subprocess, "run", lambda *_args, **_kwargs: Result())
    with pytest.raises(CodeGraphStatusTransportError, match="failed"):
        query_codegraph_status(
            project_root=tmp_path,
            project_id="project-1",
            resource_id="codegraph-project-1",
            index_name="project-1-codegraph",
        )

    Result.returncode = 0
    Result.stdout = "not json"
    with pytest.raises(CodeGraphStatusTransportError, match="JSON"):
        query_codegraph_status(
            project_root=tmp_path,
            project_id="project-1",
            resource_id="codegraph-project-1",
            index_name="project-1-codegraph",
        )


def test_query_output_limit_and_executable_bounds(tmp_path, monkeypatch):
    huge = "{" + "x" * (transport.MAX_OUTPUT_CHARS + 1) + "}"
    monkeypatch.setattr(
        transport.subprocess,
        "run",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": 0, "stdout": huge, "stderr": ""})(),
    )
    with pytest.raises(CodeGraphStatusTransportError, match="output"):
        query_codegraph_status(
            project_root=tmp_path,
            project_id="project-1",
            resource_id="codegraph-project-1",
            index_name="project-1-codegraph",
        )

    with pytest.raises(CodeGraphStatusTransportError, match="executable"):
        query_codegraph_status(
            project_root=tmp_path,
            project_id="project-1",
            resource_id="codegraph-project-1",
            index_name="project-1-codegraph",
            executable="powershell",
        )


def test_query_timeout_and_metadata_bounds(tmp_path, monkeypatch):
    monkeypatch.setattr(
        transport.subprocess,
        "run",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": 0, "stdout": json.dumps(_payload(tmp_path)), "stderr": ""})(),
    )
    with pytest.raises(CodeGraphStatusTransportError, match="timeout"):
        query_codegraph_status(
            project_root=tmp_path,
            project_id="project-1",
            resource_id="codegraph-project-1",
            index_name="project-1-codegraph",
            timeout_seconds=31,
        )
    with pytest.raises(CodeGraphStatusTransportError, match="safe ID"):
        build_codegraph_status_attestation(
            _payload(tmp_path),
            project_root=tmp_path,
            project_id="project/foreign",
            resource_id="codegraph-project-1",
            index_name="project-1-codegraph",
        )


@pytest.mark.parametrize("index_name", [r"D:\private\index", "api-token"])
def test_sensitive_or_path_like_metadata_fails_closed(tmp_path, index_name):
    with pytest.raises(CodeGraphStatusTransportError):
        build_codegraph_status_attestation(
            _payload(tmp_path),
            project_root=tmp_path,
            project_id="project-1",
            resource_id="codegraph-project-1",
            index_name=index_name,
        )
