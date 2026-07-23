from __future__ import annotations

import json
import shutil
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread, current_thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from control_plane.client_launcher import build_client_launch_plan
from control_plane.dashboard import build_dashboard_server
from control_plane.go_dispatch import load_go_run_result
from control_plane.t3_bridge_bundle import build_t3_bridge_bundle, install_t3_bridge_bundle


def _json_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _install_generated_bridge(tmp_path: Path) -> Path:
    t3_root = tmp_path / "t3code"
    (t3_root / "apps" / "web").mkdir(parents=True)
    (t3_root / "package.json").write_text('{"type":"module"}\n', encoding="utf-8")
    bundle = build_t3_bridge_bundle(build_client_launch_plan(runtime_dir=tmp_path / "runtime"))
    install_t3_bridge_bundle(t3_root, bundle)
    return t3_root


def _run_request_probe(
    t3_root: Path,
    probe_body: str,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    captures: list[dict[str, object]] = []

    class CaptureHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            raw_body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            captures.append(
                {
                    "path": self.path,
                    "raw": raw_body,
                    "json": json.loads(raw_body),
                }
            )
            response = json.dumps(
                {
                    "started": True,
                    "runId": f"capture-{len(captures)}",
                    "target": "coordinator",
                    "goal": "captured",
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), CaptureHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        output = _run_generated_bridge_probe(t3_root, base_url, probe_body)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    return captures, output


def _run_generated_bridge_probe(
    t3_root: Path,
    base_url: str,
    probe_body: str,
) -> dict[str, object]:
    probe_path = t3_root / "request-probe.ts"
    probe_path.write_text(
        'import { DevFrameCoordinatorGoalError, startDevFrameCoordinatorGoal,\n'
        '  type DevFrameCoordinatorGoalRequest }\n'
        '  from "./apps/web/src/devframe/devframeShellBridge.ts";\n\n'
        f"const config = {{ controlPlaneBaseUrl: {json.dumps(base_url)} }};\n"
        + probe_body,
        encoding="utf-8",
    )
    node = shutil.which("node")
    assert node is not None, "Node.js is required for the generated bridge product-path probe"
    result = subprocess.run(
        [node, str(probe_path)],
        cwd=t3_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def _post_json(base_url: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    request = Request(
        f"{base_url}/api/t3/cluster-run",
        data=_json_bytes(payload),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _wait_for_finished_cluster_record(
    runtime: Path,
    run_id: object,
) -> dict[str, object]:
    record_path = runtime / "cluster-runs" / f"{run_id}.json"
    deadline = time.monotonic() + 10
    record: dict[str, object] = {}
    while time.monotonic() < deadline:
        if record_path.is_file():
            try:
                record = json.loads(record_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                time.sleep(0.02)
                continue
            if record.get("finishedAt") and record.get("goRunId"):
                break
        time.sleep(0.02)
    assert record.get("finishedAt"), record
    assert record.get("goRunId"), record
    return record


def _typecheck_generated_bridge(t3_root: Path) -> None:
    tsgo = shutil.which("tsgo")
    if tsgo is None:
        return
    (t3_root / "env.d.ts").write_text(
        "interface ImportMetaEnv {\n"
        "  readonly VITE_DEVFRAME_T3_SHELL_URL?: string;\n"
        "  readonly VITE_DEVFRAME_CLIENT_PLAN_URL?: string;\n"
        "  readonly VITE_DEVFRAME_CLIENT_MANIFEST_URL?: string;\n"
        "}\n"
        "interface ImportMeta { readonly env: ImportMetaEnv; }\n",
        encoding="utf-8",
    )
    (t3_root / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "allowImportingTsExtensions": True,
                    "lib": ["ES2022", "DOM"],
                    "module": "ESNext",
                    "moduleResolution": "Bundler",
                    "noEmit": True,
                    "strict": True,
                    "target": "ES2022",
                },
                "include": [
                    "apps/web/src/devframe/devframeShellBridge.ts",
                    "request-probe.ts",
                    "env.d.ts",
                ],
            }
        ),
        encoding="utf-8",
    )
    command = [tsgo, "--project", str(t3_root / "tsconfig.json"), "--pretty", "false"]
    if Path(tsgo).suffix.lower() in {".bat", ".cmd"}:
        command = [shutil.which("cmd") or "cmd", "/d", "/c", *command]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_generated_bridge_posts_explicit_provider_selection_unchanged(tmp_path: Path) -> None:
    t3_root = _install_generated_bridge(tmp_path)
    selected_requests = [
        {
            "projectId": "codex-project",
            "target": "coordinator",
            "goal": "Use the explicit GPT selection",
            "executor": "codex",
            "modelProvider": "openai",
            "model": "openai/gpt-5.6-codex",
        },
        {
            "projectId": "opencode-project",
            "target": "coordinator",
            "goal": "Use the explicit OpenCode selection",
            "executor": "opencode",
            "modelProvider": "local-ollama",
            "model": " qwen3-coder:30b ",
        },
    ]
    probe_body = (
        f"const requests: DevFrameCoordinatorGoalRequest[] = {json.dumps(selected_requests)};\n"
        "for (const request of requests) {\n"
        "  await startDevFrameCoordinatorGoal(config, request);\n"
        "}\n"
        'console.log(JSON.stringify({ requestCount: requests.length }));\n'
    )

    captures, output = _run_request_probe(t3_root, probe_body)

    assert output == {"requestCount": 2}
    assert [capture["path"] for capture in captures] == [
        "/api/t3/cluster-run",
        "/api/t3/cluster-run",
    ]
    assert [capture["json"] for capture in captures] == selected_requests
    assert [capture["raw"] for capture in captures] == [
        _json_bytes(request) for request in selected_requests
    ]
    _typecheck_generated_bridge(t3_root)


def test_generated_bridge_omits_unset_selection_and_rejects_blank_values(tmp_path: Path) -> None:
    t3_root = _install_generated_bridge(tmp_path)
    omitted_request = {
        "projectId": "compatible-project",
        "target": "coordinator",
        "goal": "Keep the pre-selection request shape",
    }
    invalid_requests = [
        {**omitted_request, "executor": ""},
        {**omitted_request, "modelProvider": " \t"},
        {**omitted_request, "model": "\n"},
    ]
    expected_errors = [
        "executor must not be blank when provided",
        "modelProvider must not be blank when provided",
        "model must not be blank when provided",
    ]
    probe_body = (
        f"const omitted: DevFrameCoordinatorGoalRequest = {json.dumps(omitted_request)};\n"
        "await startDevFrameCoordinatorGoal(config, omitted);\n"
        f"const invalid: DevFrameCoordinatorGoalRequest[] = {json.dumps(invalid_requests)};\n"
        "const errors: string[] = [];\n"
        "for (const request of invalid) {\n"
        "  try {\n"
        "    await startDevFrameCoordinatorGoal(config, request);\n"
        "  } catch (error) {\n"
        "    errors.push(error instanceof Error ? error.message : String(error));\n"
        "  }\n"
        "}\n"
        "console.log(JSON.stringify({ errors }));\n"
    )

    captures, output = _run_request_probe(t3_root, probe_body)

    assert output == {"errors": expected_errors}
    assert [capture["json"] for capture in captures] == [omitted_request]
    assert [capture["raw"] for capture in captures] == [_json_bytes(omitted_request)]
    _typecheck_generated_bridge(t3_root)


def test_generated_bridge_selection_reaches_actual_dashboard_and_durable_go_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from control_plane import workflow_engine as workflow_engine_module

    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "task.py").write_text("value = 1\n", encoding="utf-8")
    t3_root = _install_generated_bridge(tmp_path)

    def _skip_worker_execution(
        runtime_dir: str | Path,
        go_run_id: str,
        *,
        timeout_seconds: int,
    ):
        assert timeout_seconds == 900
        return load_go_run_result(runtime_dir, go_run_id)

    monkeypatch.setattr(workflow_engine_module, "execute_go_run", _skip_worker_execution)
    server = build_dashboard_server(runtime_dir=runtime, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    selected_request = {
        "projectId": str(workspace),
        "target": "coordinator",
        "goal": "Implement the selected provider path",
        "executor": "opencode",
        "modelProvider": "local-ollama",
        "model": "qwen3-coder:30b",
    }
    probe_body = (
        f"const request: DevFrameCoordinatorGoalRequest = {json.dumps(selected_request)};\n"
        "const started = await startDevFrameCoordinatorGoal(config, request);\n"
        "console.log(JSON.stringify(started));\n"
    )
    try:
        started = _run_generated_bridge_probe(t3_root, base_url, probe_body)
        assert started["executor"] == "opencode"
        assert started["modelProvider"] == "local-ollama"
        assert started["model"] == "qwen3-coder:30b"

        record = _wait_for_finished_cluster_record(runtime, started["runId"])
        assert record["executor"] == "opencode"
        assert record["modelProvider"] == "local-ollama"
        assert record["model"] == "qwen3-coder:30b"

        go_run = load_go_run_result(runtime, str(record["goRunId"]))
        assert go_run.model_provider == "local-ollama"
        assert go_run.agents
        for agent in go_run.agents:
            assert agent.model_provider == "local-ollama"
            model_index = agent.worker_command.index("-m") + 1
            assert agent.worker_command[model_index] == "qwen3-coder:30b"
        team_events = [
            json.loads(line)
            for line in (runtime / "team-events.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert any(
            event.get("run_id") == record["goRunId"]
            and event.get("event_type") == "workflow_event"
            for event in team_events
        )

        omitted_request = {
            "projectId": str(workspace),
            "target": "coordinator",
            "goal": "Keep the default execution selection",
        }
        omitted_probe = (
            f"const request: DevFrameCoordinatorGoalRequest = {json.dumps(omitted_request)};\n"
            "const started = await startDevFrameCoordinatorGoal(config, request);\n"
            "console.log(JSON.stringify(started));\n"
        )
        default_started = _run_generated_bridge_probe(t3_root, base_url, omitted_probe)
        assert "executor" not in default_started
        assert "modelProvider" not in default_started
        assert "model" not in default_started

        default_record = _wait_for_finished_cluster_record(runtime, default_started["runId"])
        assert "executor" not in default_record
        assert "modelProvider" not in default_record
        assert "model" not in default_record
        default_go_run = load_go_run_result(runtime, str(default_record["goRunId"]))
        assert default_go_run.model_provider == "opencode-api"
        assert default_go_run.agents
        for agent in default_go_run.agents:
            assert agent.model_provider == "opencode-api"
            model_index = agent.worker_command.index("-m") + 1
            assert agent.worker_command[model_index] == "stepfun/step-3.7-flash"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_generated_bridge_rejects_provider_without_default_before_runtime_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from control_plane import cluster_run as cluster_run_module

    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    t3_root = _install_generated_bridge(tmp_path)

    def _unexpected_run_id() -> str:
        raise AssertionError("provider selection reached run-id allocation")

    monkeypatch.setattr(cluster_run_module, "_new_run_id", _unexpected_run_id)
    server = build_dashboard_server(runtime_dir=runtime, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    invalid_request = {
        "projectId": str(workspace),
        "target": "coordinator",
        "goal": "Reject a local provider without a real model default",
        "executor": "opencode",
        "modelProvider": "local-ollama",
    }
    probe_body = (
        f"const request: DevFrameCoordinatorGoalRequest = {json.dumps(invalid_request)};\n"
        "try {\n"
        "  await startDevFrameCoordinatorGoal(config, request);\n"
        '  throw new Error("expected provider selection to be rejected");\n'
        "} catch (error) {\n"
        "  if (!(error instanceof DevFrameCoordinatorGoalError)) throw error;\n"
        "  console.log(JSON.stringify({\n"
        "    status: error.status,\n"
        "    code: error.code,\n"
        "    detail: error.detail,\n"
        "  }));\n"
        "}\n"
    )
    try:
        rejection = _run_generated_bridge_probe(t3_root, base_url, probe_body)
        assert rejection["status"] == 400
        assert rejection["code"] == "cluster_run_rejected"
        assert "requires an explicit model" in str(rejection["detail"])
        assert not runtime.exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_actual_dashboard_rejects_unknown_execution_selection_before_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from control_plane import cluster_run as cluster_run_module

    runtime = tmp_path / "runtime"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(cluster_run_module, "_run_cluster_workflow", lambda *args, **kwargs: None)
    server = build_dashboard_server(runtime_dir=runtime, port=0, refresh_seconds=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    base_request = {
        "projectId": str(workspace),
        "target": "coordinator",
        "goal": "Implement a fail-closed provider path",
    }
    try:
        cases = [
            ({"executor": "unknown-executor"}, "unknown executor"),
            ({"modelProvider": "unknown-provider"}, "unknown model provider"),
            ({"modelProvider": "web-chatgpt-shim"}, "deferred live backend"),
        ]
        for selection, expected_detail in cases:
            status, body = _post_json(base_url, {**base_request, **selection})
            assert status == 400
            assert body["error"] == "cluster_run_rejected"
            assert expected_detail in str(body["detail"])

        assert not (runtime / "cluster-runs").exists()
        assert not (runtime / "go-runs").exists()
        assert not (runtime / "team-events.jsonl").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_cluster_run_record_retries_transient_replace_contention(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from control_plane import cluster_run as cluster_run_module

    destination = tmp_path / "runtime" / "cluster-runs" / "g-retry.json"
    real_replace = cluster_run_module.os.replace
    attempts = 0

    def _contended_replace(source: str | Path, target: str | Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("simulated Windows reader contention")
        real_replace(source, target)

    monkeypatch.setattr(cluster_run_module.os, "replace", _contended_replace)
    cluster_run_module._atomic_write(destination, {"runId": "g-retry", "status": "running"})

    assert attempts == 3
    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "runId": "g-retry",
        "status": "running",
    }
    assert not list(destination.parent.glob(f"{destination.name}*.tmp"))


def test_cluster_run_record_removes_temp_after_terminal_replace_contention(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from control_plane import cluster_run as cluster_run_module

    destination = tmp_path / "runtime" / "cluster-runs" / "g-terminal.json"
    attempts = 0

    def _always_contended(_source: str | Path, _target: str | Path) -> None:
        nonlocal attempts
        attempts += 1
        raise PermissionError("simulated terminal contention")

    monkeypatch.setattr(cluster_run_module.os, "replace", _always_contended)
    monkeypatch.setattr(cluster_run_module.time, "sleep", lambda _seconds: None)

    with pytest.raises(PermissionError, match="terminal contention"):
        cluster_run_module._atomic_write(
            destination,
            {"runId": "g-terminal", "status": "running"},
        )

    assert attempts == cluster_run_module._ATOMIC_REPLACE_ATTEMPTS
    assert not destination.exists()
    assert not list(destination.parent.glob(f"{destination.name}*.tmp"))


def test_cluster_run_record_does_not_retry_unrelated_replace_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from control_plane import cluster_run as cluster_run_module

    destination = tmp_path / "runtime" / "cluster-runs" / "g-unrelated.json"
    attempts = 0

    def _unrelated_error(_source: str | Path, _target: str | Path) -> None:
        nonlocal attempts
        attempts += 1
        raise OSError("simulated unrelated replace failure")

    monkeypatch.setattr(cluster_run_module.os, "replace", _unrelated_error)

    with pytest.raises(OSError, match="unrelated replace failure"):
        cluster_run_module._atomic_write(
            destination,
            {"runId": "g-unrelated", "status": "running"},
        )

    assert attempts == 1
    assert not destination.exists()
    assert not list(destination.parent.glob(f"{destination.name}*.tmp"))


def test_cluster_run_record_concurrent_writers_keep_unique_payloads(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from control_plane import cluster_run as cluster_run_module

    destination = tmp_path / "runtime" / "cluster-runs" / "g-concurrent.json"
    real_replace = cluster_run_module.os.replace
    first_writer_contended = Event()
    allow_first_writer_retry = Event()
    second_writer_started = Event()
    second_writer_replacing = Event()
    successful_replacements: list[tuple[str, str]] = []
    errors: dict[str, BaseException] = {}

    def _controlled_replace(source: str | Path, target: str | Path) -> None:
        writer = current_thread().name
        if writer == "record-writer-a" and not first_writer_contended.is_set():
            first_writer_contended.set()
            raise PermissionError("simulated transient contention")
        if writer == "record-writer-b":
            second_writer_replacing.set()
        payload = json.loads(Path(source).read_text(encoding="utf-8"))
        real_replace(source, target)
        successful_replacements.append((writer, str(payload["writer"])))

    def _controlled_sleep(_seconds: float) -> None:
        if current_thread().name == "record-writer-a":
            assert allow_first_writer_retry.wait(timeout=5)

    def _write(label: str) -> None:
        try:
            if label == "B":
                second_writer_started.set()
            cluster_run_module._atomic_write(
                destination,
                {"runId": "g-concurrent", "writer": label},
            )
        except BaseException as exc:  # noqa: BLE001 - retain thread failure for assertion
            errors[label] = exc

    monkeypatch.setattr(cluster_run_module.os, "replace", _controlled_replace)
    monkeypatch.setattr(cluster_run_module.time, "sleep", _controlled_sleep)
    first = Thread(target=_write, args=("A",), name="record-writer-a")
    second = Thread(target=_write, args=("B",), name="record-writer-b")

    first.start()
    assert first_writer_contended.wait(timeout=5)
    second.start()
    try:
        assert second_writer_started.wait(timeout=5)
        assert not second_writer_replacing.wait(timeout=0.2)
    finally:
        allow_first_writer_retry.set()
        first.join(timeout=5)
        second.join(timeout=5)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == {}
    assert successful_replacements == [
        ("record-writer-a", "A"),
        ("record-writer-b", "B"),
    ]
    assert json.loads(destination.read_text(encoding="utf-8"))["writer"] == "B"
    assert not list(destination.parent.glob(f"{destination.name}*.tmp"))


def test_cluster_run_record_serializes_same_record_load_modify_write(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from control_plane import cluster_run as cluster_run_module

    runtime = tmp_path / "runtime"
    run_id = "g-serialized"
    cluster_run_module._write_run_record(
        runtime,
        {
            "runId": run_id,
            "goal": "original goal",
            "status": "running",
            "ownerPid": 424242,
            "startedAt": "2026-07-23T00:00:00+00:00",
        },
    )
    stale_record = cluster_run_module._load_run_record(runtime, run_id)
    assert stale_record is not None

    real_atomic_write = cluster_run_module._atomic_write
    interrupted_write_entered = Event()
    allow_interrupted_write = Event()
    errors: dict[str, BaseException] = {}

    def _controlled_atomic_write(path: Path, payload: dict[str, object]) -> None:
        if payload.get("status") == "interrupted" and not interrupted_write_entered.is_set():
            interrupted_write_entered.set()
            assert allow_interrupted_write.wait(timeout=5)
        real_atomic_write(path, payload)

    def _reconcile() -> None:
        try:
            cluster_run_module._reconcile_orphaned_run(runtime, stale_record)
        except BaseException as exc:  # noqa: BLE001 - retain thread failure for assertion
            errors["reconcile"] = exc

    def _update_goal() -> None:
        try:
            cluster_run_module.rename_cluster_run(runtime, run_id, "updated goal")
        except BaseException as exc:  # noqa: BLE001 - retain thread failure for assertion
            errors["update"] = exc

    monkeypatch.setattr(cluster_run_module, "_pid_alive", lambda _pid: False)
    monkeypatch.setattr(cluster_run_module, "_atomic_write", _controlled_atomic_write)
    reconcile_thread = Thread(target=_reconcile, name="record-reconcile")
    update_thread = Thread(target=_update_goal, name="record-update")

    reconcile_thread.start()
    assert interrupted_write_entered.wait(timeout=5)
    update_thread.start()
    time.sleep(0.05)
    allow_interrupted_write.set()
    reconcile_thread.join(timeout=5)
    update_thread.join(timeout=5)
    assert not reconcile_thread.is_alive()
    assert not update_thread.is_alive()

    assert errors == {}
    record = cluster_run_module._load_run_record(runtime, run_id)
    assert record is not None
    assert record["status"] == "interrupted"
    assert record["goal"] == "updated goal"
    assert not list((runtime / "cluster-runs").glob(f"{run_id}.json*.tmp"))
