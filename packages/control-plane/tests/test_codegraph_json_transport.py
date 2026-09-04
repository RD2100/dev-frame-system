"""Tests for the bounded CodeGraph JSON context transport."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import control_plane.codegraph_json_transport as transport
from control_plane.codegraph_json_transport import (
    CodeGraphJsonTransportError,
    build_codegraph_context_projection,
    query_codegraph_context,
)
from control_plane.graph_projection_validator import validate_graph_projection


def _node(node_id: str, kind: str, name: str, start: int, end: int) -> dict:
    return {
        "id": node_id,
        "kind": kind,
        "name": name,
        "qualifiedName": name,
        "filePath": "src/graph.py",
        "language": "python",
        "startLine": start,
        "endLine": end,
    }


def _payload() -> dict:
    file_node = _node("file:file123", "file", "graph.py", 1, 50)
    function_node = _node(
        "function:abc123", "function", "build_projection", 10, 20
    )
    return {
        "query": "inspect graph projection",
        "summary": "Found two relevant symbols.",
        "entryPoints": [function_node],
        "nodes": [file_node, function_node],
        "edges": [
            {
                "source": "file:file123",
                "target": "function:abc123",
                "kind": "contains",
                "line": 10,
                "column": 1,
            }
        ],
        "codeBlocks": [],
        "relatedFiles": ["src/graph.py"],
        "stats": {"nodeCount": 2, "edgeCount": 1, "fileCount": 1},
    }


def _build(payload: dict | None = None) -> dict:
    return build_codegraph_context_projection(
        payload or _payload(),
        graph_projection_id="graph-codegraph-json-1",
        project_id="project-1",
        resource_id="codegraph-project-1",
        index_name="project-1-codegraph",
        index_status="current",
        index_freshness="current",
        privacy_class="public_repo",
        source_snapshot_refs=["repo://codegraph/context"],
    )


def test_json_context_maps_to_valid_non_authoritative_projection():
    projection = _build()

    assert validate_graph_projection(projection).valid
    assert [node["id"] for node in projection["nodes"]] == [
        "file:file123",
        "function:abc123",
    ]
    assert projection["nodes"][1]["source_ref"] == "code://src/graph.py#function-abc123"
    assert projection["nodes"][1]["authority"] == "none"
    assert projection["edges"][0]["type"] == "inferred"
    assert projection["edges"][0]["relation_kind"] == "contains"
    assert projection["source_adapter"]["transport"] == "codegraph_json_context"
    assert "task_hash" not in projection["source_adapter"]


def test_local_privacy_keeps_projection_content_free():
    projection = build_codegraph_context_projection(
        _payload(),
        graph_projection_id="graph-codegraph-json-1",
        project_id="project-1",
        resource_id="codegraph-project-1",
        index_name="project-1-codegraph",
        privacy_class="local_path_only",
    )

    serialized = json.dumps(projection, ensure_ascii=True)
    assert "graph.py" not in serialized
    assert "src/graph.py" not in serialized
    assert all(set(node) <= {
        "id",
        "type",
        "authority",
        "privacy_class",
        "freshness",
        "confidence",
    } for node in projection["nodes"])


def test_stale_metadata_is_preserved_without_trust():
    projection = build_codegraph_context_projection(
        _payload(),
        graph_projection_id="graph-codegraph-json-1",
        project_id="project-1",
        resource_id="codegraph-project-1",
        index_name="project-1-codegraph",
        index_status="stale",
        index_freshness="stale",
        privacy_class="public_repo",
    )

    assert {node["freshness"] for node in projection["nodes"]} == {"stale"}
    assert projection["source_adapter"]["index_status"] == "stale"
    assert projection["source_adapter"]["trusted_for_current_run"] is False


def test_payload_is_not_mutated_and_output_is_deterministic():
    payload = _payload()
    before = copy.deepcopy(payload)

    first = _build(payload)
    second = _build(payload)

    assert payload == before
    assert first == second


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda value: value.update({"unknown": True}), "unsupported fields"),
        (lambda value: value.update({"codeBlocks": [{"text": "secret"}]}), "code blocks"),
        (lambda value: value["nodes"][0].update({"filePath": r"D:\\private\\graph.py"}), "path"),
        (lambda value: value["nodes"].append({"id": "bad", "kind": "unknown", "filePath": "src/bad.py"}), "kind"),
        (lambda value: value["edges"][0].update({"target": "missing"}), "endpoint"),
    ],
)
def test_malformed_or_unsafe_payload_fails_closed(mutator, message: str):
    payload = _payload()
    mutator(payload)

    with pytest.raises(CodeGraphJsonTransportError, match=message):
        _build(payload)


def test_path_traversal_in_related_files_fails_closed():
    payload = _payload()
    payload["relatedFiles"] = ["src/../secret.py"]

    with pytest.raises(CodeGraphJsonTransportError, match="path"):
        _build(payload)


def test_subprocess_uses_exact_read_only_argv_without_shell(tmp_path, monkeypatch):
    calls: list[tuple[list[str], dict]] = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return type("Result", (), {"returncode": 0, "stdout": json.dumps(_payload()), "stderr": "secret stderr"})()

    monkeypatch.setattr(transport.subprocess, "run", fake_run)
    projection = query_codegraph_context(
        project_root=tmp_path,
        task="inspect graph projection",
        graph_projection_id="graph-codegraph-json-1",
        project_id="project-1",
        resource_id="codegraph-project-1",
        index_name="project-1-codegraph",
        index_status="unknown",
        index_freshness="unknown",
        privacy_class="public_repo",
    )

    assert validate_graph_projection(projection).valid
    argv, kwargs = calls[0]
    assert argv == [
        transport.DEFAULT_EXECUTABLE,
        "context",
        "--format",
        "json",
        "--max-nodes",
        "50",
        "--no-code",
        "--path",
        str(Path(tmp_path).resolve()),
        "inspect graph projection",
    ]
    assert kwargs["shell"] is False
    assert kwargs["cwd"] == Path(tmp_path).resolve()
    assert projection["source_adapter"]["transport"] == "codegraph_json_context"


@pytest.mark.parametrize(
    ("exception", "code"),
    [(TimeoutError(), "timeout"), (FileNotFoundError(), "unavailable")],
)
def test_subprocess_failures_are_stable_and_do_not_leak_stderr(
    tmp_path, monkeypatch, exception: Exception, code: str
):
    def fake_run(*_args, **_kwargs):
        raise exception

    monkeypatch.setattr(transport.subprocess, "run", fake_run)

    with pytest.raises(CodeGraphJsonTransportError) as raised:
        query_codegraph_context(
            project_root=tmp_path,
            task="inspect graph projection",
            graph_projection_id="graph-codegraph-json-1",
            project_id="project-1",
            resource_id="codegraph-project-1",
            index_name="project-1-codegraph",
        )
    assert raised.value.code == code
    assert "stderr" not in str(raised.value)


def test_nonzero_and_malformed_json_fail_closed(tmp_path, monkeypatch):
    class Result:
        returncode = 2
        stdout = "{}"
        stderr = "private command details"

    monkeypatch.setattr(transport.subprocess, "run", lambda *_args, **_kwargs: Result())
    with pytest.raises(CodeGraphJsonTransportError, match="failed") as raised:
        query_codegraph_context(
            project_root=tmp_path,
            task="inspect graph projection",
            graph_projection_id="graph-codegraph-json-1",
            project_id="project-1",
            resource_id="codegraph-project-1",
            index_name="project-1-codegraph",
        )
    assert "private command" not in str(raised.value)

    Result.returncode = 0
    Result.stdout = "not json"
    with pytest.raises(CodeGraphJsonTransportError, match="JSON"):
        query_codegraph_context(
            project_root=tmp_path,
            task="inspect graph projection",
            graph_projection_id="graph-codegraph-json-1",
            project_id="project-1",
            resource_id="codegraph-project-1",
            index_name="project-1-codegraph",
        )


def test_task_output_and_numeric_bounds_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(
        transport.subprocess,
        "run",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": 0, "stdout": "{}", "stderr": ""})(),
    )
    with pytest.raises(CodeGraphJsonTransportError, match="task"):
        query_codegraph_context(
            project_root=tmp_path,
            task="x" * 513,
            graph_projection_id="graph-codegraph-json-1",
            project_id="project-1",
            resource_id="codegraph-project-1",
            index_name="project-1-codegraph",
        )
    with pytest.raises(CodeGraphJsonTransportError, match="max_nodes"):
        query_codegraph_context(
            project_root=tmp_path,
            task="inspect",
            graph_projection_id="graph-codegraph-json-1",
            project_id="project-1",
            resource_id="codegraph-project-1",
            index_name="project-1-codegraph",
            max_nodes=513,
        )
    with pytest.raises(CodeGraphJsonTransportError, match="timeout"):
        query_codegraph_context(
            project_root=tmp_path,
            task="inspect",
            graph_projection_id="graph-codegraph-json-1",
            project_id="project-1",
            resource_id="codegraph-project-1",
            index_name="project-1-codegraph",
            timeout_seconds=31,
        )


def test_output_limit_and_unsafe_executable_fail_closed(tmp_path, monkeypatch):
    huge = "{" + "x" * 1_000_001 + "}"
    monkeypatch.setattr(
        transport.subprocess,
        "run",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": 0, "stdout": huge, "stderr": ""})(),
    )
    with pytest.raises(CodeGraphJsonTransportError, match="output"):
        query_codegraph_context(
            project_root=tmp_path,
            task="inspect",
            graph_projection_id="graph-codegraph-json-1",
            project_id="project-1",
            resource_id="codegraph-project-1",
            index_name="project-1-codegraph",
        )

    with pytest.raises(CodeGraphJsonTransportError, match="executable"):
        query_codegraph_context(
            project_root=tmp_path,
            task="inspect",
            graph_projection_id="graph-codegraph-json-1",
            project_id="project-1",
            resource_id="codegraph-project-1",
            index_name="project-1-codegraph",
            executable="powershell",
        )
