from __future__ import annotations

import json
import os
import signal
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from threading import Thread

import pytest

from control_plane.client_launcher import build_client_launch_plan
from control_plane.cluster_run import _pid_alive
from control_plane.cluster_run import list_cluster_runs
from control_plane.dashboard import build_dashboard_server
from control_plane.go_dispatch import execute_go_run, run_go_dispatch
from control_plane.provider_secret import ProviderSecretError, resolve_provider_secret
from control_plane.t3_bridge_bundle import (
    build_t3_bridge_bundle,
    install_t3_bridge_bundle,
)


SECRET_ENV = "OPENCODE_API_KEY"


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "target.py").write_text("value = 1\n", encoding="utf-8")
    return project


def _write_worker(
    tmp_path: Path,
    *,
    timeout: bool = False,
    lingering_child: bool = False,
) -> tuple[list[str], Path]:
    script_name = (
        "timeout_worker.py"
        if timeout
        else ("lingering_worker.py" if lingering_child else "safe_worker.py")
    )
    marker_name = (
        "timeout-spawned.json"
        if timeout
        else ("lingering-spawned.json" if lingering_child else "spawned.json")
    )
    script = tmp_path / script_name
    marker = tmp_path / marker_name
    timeout_block = (
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        "Path(os.environ['RDGOAL_PACKET_DIR'], 'child.pid').write_text("
        "str(child.pid), encoding='utf-8')\n"
        "time.sleep(120)\n"
        if timeout
        else ""
    )
    lingering_block = (
        "child = subprocess.Popen(\n"
        "    [sys.executable, '-c', 'import time; time.sleep(120)'],\n"
        "    stdin=subprocess.DEVNULL,\n"
        "    stdout=subprocess.DEVNULL,\n"
        "    stderr=subprocess.DEVNULL,\n"
        ")\n"
        "Path(os.environ['RDGOAL_PACKET_DIR'], 'child.pid').write_text("
        "str(child.pid), encoding='utf-8')\n"
        if lingering_child
        else ""
    )
    script.write_text(
        "import json\n"
        "import os\n"
        "import subprocess\n"
        "import sys\n"
        "import time\n"
        "from pathlib import Path\n"
        "\n"
        f"secret = os.environ.get({SECRET_ENV!r}, '')\n"
        "Path(sys.argv[1]).write_text(json.dumps({\n"
        "    'secretPresent': bool(secret),\n"
        "    'secretLength': len(secret),\n"
        "}), encoding='utf-8')\n"
        "report = Path(os.environ['RDGOAL_REPORT_PATH'])\n"
        "report.write_text(\n"
        "    '## ExecutionReport: provider-secret-probe\\n\\n'\n"
        "    '- **Status**: pass\\n'\n"
        "    '- **Review Status**: draft\\n'\n"
        "    f'- **Summary**: controlled worker received {secret}\\n'\n"
        "    '- **Changed Files**:\\n- (none)\\n'\n"
        "    f'- **Evidence**: provider boundary {secret}\\n'\n"
        "    '- **Risks**: synthetic containment probe.\\n',\n"
        "    encoding='utf-8',\n"
        ")\n"
        "print(f'provider-stdout:{secret}', flush=True)\n"
        "print(f'provider-stderr:{secret}', file=sys.stderr, flush=True)\n"
        + lingering_block
        + timeout_block,
        encoding="utf-8",
    )
    return [sys.executable, str(script), str(marker)], marker


def _synthetic_secret() -> str:
    return f"test_provider_secret_{uuid.uuid4().hex}"


def _install_generated_bridge(tmp_path: Path, runtime: Path) -> Path:
    t3_root = tmp_path / "t3code"
    (t3_root / "apps" / "web").mkdir(parents=True)
    (t3_root / "package.json").write_text('{"type":"module"}\n', encoding="utf-8")
    bundle = build_t3_bridge_bundle(build_client_launch_plan(runtime_dir=runtime))
    install_t3_bridge_bundle(t3_root, bundle)
    return t3_root


def _run_generated_bridge_goal(
    t3_root: Path,
    *,
    base_url: str,
    project: Path,
) -> dict[str, object]:
    node = shutil.which("node")
    assert node is not None, (
        "Node.js is required for the generated RD-Code bridge probe"
    )
    probe = t3_root / "provider-secret-e2e.ts"
    probe.write_text(
        "import { startDevFrameCoordinatorGoal } from "
        '"./apps/web/src/devframe/devframeShellBridge.ts";\n'
        f"const config = {{ controlPlaneBaseUrl: {json.dumps(base_url)} }};\n"
        "const result = await startDevFrameCoordinatorGoal(config, {\n"
        f"  projectId: {json.dumps(str(project))},\n"
        '  target: "coordinator",\n'
        '  goal: "Implement the bounded provider containment probe.",\n'
        '  executor: "opencode",\n'
        '  modelProvider: "opencode-api",\n'
        '  model: "openai/synthetic-model",\n'
        "});\n"
        "console.log(JSON.stringify(result));\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [node, str(probe)],
        cwd=t3_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(completed.stdout)


def _assert_secret_absent(root: Path, secret: str) -> None:
    if not root.exists():
        return
    needle = secret.encode("utf-8")
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            content = path.read_bytes()
        except OSError:
            continue
        if needle in content:
            pytest.fail(f"synthetic provider secret persisted in {path}")


def _force_kill(pid: int) -> None:
    if not _pid_alive(pid):
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return


def _run_windows_job_setup_failure_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    job_unavailable: bool,
) -> None:
    import control_plane.worker as worker_module

    project = _project(tmp_path)
    runtime = tmp_path / "runtime"
    command, marker = _write_worker(tmp_path, lingering_child=True)
    secret = _synthetic_secret()
    unrelated_env = os.environ.copy()
    unrelated_env.pop(SECRET_ENV, None)
    unrelated = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(120)"],
        env=unrelated_env,
    )
    monkeypatch.setenv(SECRET_ENV, secret)
    original_popen = subprocess.Popen
    worker_processes: list[subprocess.Popen[str]] = []
    child_pid = 0

    def capture_worker(
        popen_command: list[str],
        *args: object,
        **kwargs: object,
    ) -> subprocess.Popen[str]:
        process = original_popen(popen_command, *args, **kwargs)
        if str(command[1]) in popen_command:
            worker_processes.append(process)
        return process

    monkeypatch.setattr(worker_module.subprocess, "Popen", capture_worker)
    if job_unavailable:
        monkeypatch.setattr(worker_module, "_create_windows_kill_job", lambda: None)
    else:
        monkeypatch.setattr(
            worker_module,
            "_assign_windows_kill_job",
            lambda _job_handle, _process: False,
        )

    try:
        result = run_go_dispatch(
            project,
            "Fail closed before an uncontained provider worker can run.",
            runtime_dir=runtime,
            agents=1,
            targets=["target.py"],
            execute=True,
            worker_command=command,
            model_provider="opencode-api",
            timeout_seconds=10,
        )
        child_pid_files = list(runtime.rglob("child.pid"))
        if child_pid_files:
            child_pid = int(child_pid_files[0].read_text(encoding="utf-8"))
        deadline = time.monotonic() + 5
        while (
            any(process.poll() is None for process in worker_processes)
            or (child_pid and _pid_alive(child_pid))
        ) and time.monotonic() < deadline:
            time.sleep(0.05)

        assert result.status == "failed"
        assert not marker.exists()
        assert not child_pid_files
        assert all(process.poll() is not None for process in worker_processes)
        assert unrelated.poll() is None
        _assert_secret_absent(runtime, secret)
        _assert_secret_absent(project, secret)
    finally:
        for process in worker_processes:
            _force_kill(process.pid)
        if child_pid:
            _force_kill(child_pid)
        _force_kill(unrelated.pid)
        unrelated.wait(timeout=5)


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object regression")
def test_secret_worker_fails_closed_when_windows_job_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _run_windows_job_setup_failure_probe(
        tmp_path,
        monkeypatch,
        job_unavailable=True,
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object regression")
def test_secret_worker_fails_closed_when_windows_job_assignment_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _run_windows_job_setup_failure_probe(
        tmp_path,
        monkeypatch,
        job_unavailable=False,
    )


def test_provider_secret_resolution_errors_are_structured_and_value_free() -> None:
    secret = _synthetic_secret()

    class BrokenEnvironment(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            raise RuntimeError(secret)

    cases = [
        (
            "unknown_provider",
            lambda: resolve_provider_secret(f"unknown-{secret}", environ={}),
        ),
        ("empty_provider", lambda: resolve_provider_secret(" \t", environ={})),
        ("invalid_provider_type", lambda: resolve_provider_secret(7, environ={})),
        (
            "invalid_secret_source_type",
            lambda: resolve_provider_secret("opencode-api", environ=[]),  # type: ignore[arg-type]
        ),
        (
            "invalid_secret_value_type",
            lambda: resolve_provider_secret("opencode-api", environ={SECRET_ENV: 7}),
        ),
        (
            "secret_source_initialization_failed",
            lambda: resolve_provider_secret(
                "opencode-api", environ=BrokenEnvironment()
            ),
        ),
    ]

    for expected_code, call in cases:
        with pytest.raises(ProviderSecretError) as caught:
            call()
        assert caught.value.code == expected_code
        assert caught.value.to_dict()["error"] == "provider_secret_rejected"
        assert secret not in str(caught.value)
        assert secret not in repr(caught.value.to_dict())


def test_paid_provider_missing_secret_rejects_before_packet_metadata_or_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    runtime = tmp_path / "runtime"
    command, marker = _write_worker(tmp_path)
    monkeypatch.delenv(SECRET_ENV, raising=False)

    with pytest.raises(ValueError) as caught:
        run_go_dispatch(
            project,
            "Exercise the paid provider boundary.",
            runtime_dir=runtime,
            agents=1,
            targets=["target.py"],
            execute=True,
            worker_command=command,
            model_provider="opencode-api",
        )

    error = caught.value
    assert getattr(error, "code", "") == "missing_external_secret"
    assert SECRET_ENV in str(error)
    assert not marker.exists()
    assert not runtime.exists()


def test_prepared_paid_run_reattests_before_worker_or_metadata_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    runtime = tmp_path / "runtime"
    command, marker = _write_worker(tmp_path)
    monkeypatch.setenv(SECRET_ENV, _synthetic_secret())
    prepared = run_go_dispatch(
        project,
        "Prepare, then execute through the governed boundary.",
        runtime_dir=runtime,
        agents=1,
        targets=["target.py"],
        execute=False,
        worker_command=command,
        model_provider="opencode-api",
    )
    metadata = Path(prepared.metadata_path)
    before = metadata.read_bytes()
    monkeypatch.delenv(SECRET_ENV)

    with pytest.raises(ValueError) as caught:
        execute_go_run(runtime, prepared.go_run_id)

    assert getattr(caught.value, "code", "") == "missing_external_secret"
    assert metadata.read_bytes() == before
    assert not marker.exists()
    assert not (runtime / "team-events.jsonl").exists()


def test_paid_provider_value_reaches_only_worker_boundary_and_never_persists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    runtime = tmp_path / "runtime"
    command, marker = _write_worker(tmp_path)
    secret = _synthetic_secret()
    monkeypatch.setenv(SECRET_ENV, secret)
    parent_environment = dict(os.environ)

    result = run_go_dispatch(
        project,
        "Prove controlled provider injection and redaction.",
        runtime_dir=runtime,
        agents=1,
        targets=["target.py"],
        execute=True,
        worker_command=command,
        model_provider="opencode-api",
    )

    assert result.status == "passed"
    assert json.loads(marker.read_text(encoding="utf-8")) == {
        "secretPresent": True,
        "secretLength": len(secret),
    }
    assert result.model_provider == "opencode-api"
    assert result.agents[0].model_provider == "opencode-api"
    assert dict(os.environ) == parent_environment
    _assert_secret_absent(runtime, secret)
    _assert_secret_absent(project, secret)
    assert secret not in repr(result)


def test_generated_rdcode_bridge_actual_dashboard_workflow_and_worker_contain_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    runtime = tmp_path / "runtime"
    t3_root = _install_generated_bridge(tmp_path, runtime)
    command, marker = _write_worker(tmp_path)
    secret = _synthetic_secret()
    monkeypatch.setenv(SECRET_ENV, secret)

    import control_plane.go_dispatch as go_dispatch_module

    monkeypatch.setattr(
        go_dispatch_module,
        "build_go_worker_command",
        lambda **_kwargs: list(command),
    )
    server = build_dashboard_server(runtime_dir=runtime, host="127.0.0.1", port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        response = _run_generated_bridge_goal(
            t3_root,
            base_url=base_url,
            project=project,
        )
        assert response["started"] is True
        deadline = time.monotonic() + 20
        records: list[dict[str, object]] = []
        while time.monotonic() < deadline:
            records = list_cluster_runs(runtime)
            if records and records[0].get("finishedAt"):
                break
            time.sleep(0.05)

        assert len(records) == 1
        record = records[0]
        assert record["status"] == "passed"
        assert record.get("goRunId")
        metadata_path = runtime / "go-runs" / str(record["goRunId"]) / "go-run.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert metadata["model_provider"] == "opencode-api"
        assert {agent["model_provider"] for agent in metadata["agents"]} == {
            "opencode-api"
        }
        assert marker.is_file()
        _assert_secret_absent(runtime, secret)
        _assert_secret_absent(project, secret)
        _assert_secret_absent(t3_root, secret)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_keyless_provider_does_not_inherit_unneeded_paid_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    runtime = tmp_path / "runtime"
    command, marker = _write_worker(tmp_path)
    secret = _synthetic_secret()
    monkeypatch.setenv(SECRET_ENV, secret)

    result = run_go_dispatch(
        project,
        "Use the explicit keyless provider.",
        runtime_dir=runtime,
        agents=1,
        targets=["target.py"],
        execute=True,
        worker_command=command,
        model_provider="local-ollama",
    )

    assert result.status == "passed"
    assert json.loads(marker.read_text(encoding="utf-8")) == {
        "secretPresent": False,
        "secretLength": 0,
    }
    _assert_secret_absent(runtime, secret)
    _assert_secret_absent(project, secret)


def test_provider_neutral_custom_worker_does_not_inherit_paid_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    runtime = tmp_path / "runtime"
    command, marker = _write_worker(tmp_path)
    secret = _synthetic_secret()
    monkeypatch.setenv(SECRET_ENV, secret)

    result = run_go_dispatch(
        project,
        "Use a custom worker without selecting a provider.",
        runtime_dir=runtime,
        agents=1,
        targets=["target.py"],
        execute=True,
        worker_command=command,
    )

    assert result.status == "passed"
    assert result.model_provider == ""
    assert json.loads(marker.read_text(encoding="utf-8")) == {
        "secretPresent": False,
        "secretLength": 0,
    }
    _assert_secret_absent(runtime, secret)
    _assert_secret_absent(project, secret)


def test_normal_success_cleans_lingering_secret_bearing_descendant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    runtime = tmp_path / "runtime"
    command, _marker = _write_worker(tmp_path, lingering_child=True)
    secret = _synthetic_secret()
    monkeypatch.setenv(SECRET_ENV, secret)
    child_pid = 0

    try:
        result = run_go_dispatch(
            project,
            "Finish while a controlled descendant is still alive.",
            runtime_dir=runtime,
            agents=1,
            targets=["target.py"],
            execute=True,
            worker_command=command,
            model_provider="opencode-api",
            timeout_seconds=10,
        )
        child_pid_files = list(runtime.rglob("child.pid"))
        assert len(child_pid_files) == 1
        child_pid = int(child_pid_files[0].read_text(encoding="utf-8"))
        deadline = time.monotonic() + 5
        while _pid_alive(child_pid) and time.monotonic() < deadline:
            time.sleep(0.05)

        assert result.status == "passed"
        assert not _pid_alive(child_pid)
        _assert_secret_absent(runtime, secret)
        _assert_secret_absent(project, secret)
    finally:
        if child_pid:
            _force_kill(child_pid)


def test_timeout_kills_secret_bearing_process_tree_and_redacts_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    runtime = tmp_path / "runtime"
    command, marker = _write_worker(tmp_path, timeout=True)
    secret = _synthetic_secret()
    monkeypatch.setenv(SECRET_ENV, secret)
    child_pid = 0

    try:
        result = run_go_dispatch(
            project,
            "Timeout the controlled provider worker.",
            runtime_dir=runtime,
            agents=1,
            targets=["target.py"],
            execute=True,
            worker_command=command,
            model_provider="opencode-api",
            timeout_seconds=1,
        )
        child_pid_files = list(runtime.rglob("child.pid"))
        assert len(child_pid_files) == 1
        child_pid = int(child_pid_files[0].read_text(encoding="utf-8"))
        deadline = time.monotonic() + 5
        while _pid_alive(child_pid) and time.monotonic() < deadline:
            time.sleep(0.05)

        assert result.status == "failed"
        assert marker.exists()
        assert not _pid_alive(child_pid)
        _assert_secret_absent(runtime, secret)
        _assert_secret_absent(project, secret)
    finally:
        if child_pid:
            _force_kill(child_pid)


def test_cancellation_cleans_secret_bearing_process_tree_and_partial_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project(tmp_path)
    runtime = tmp_path / "runtime"
    command, _marker = _write_worker(tmp_path, timeout=True)
    secret = _synthetic_secret()
    monkeypatch.setenv(SECRET_ENV, secret)
    prepared = run_go_dispatch(
        project,
        "Cancel the contained provider worker.",
        runtime_dir=runtime,
        agents=1,
        targets=["target.py"],
        execute=False,
        worker_command=command,
        model_provider="opencode-api",
    )
    child_pid_path = Path(prepared.agents[0].packet_dir) / "child.pid"
    original_communicate = subprocess.Popen.communicate
    interrupted = False
    child_pid = 0

    def interrupt_worker_once(
        process: subprocess.Popen[str],
        *args: object,
        **kwargs: object,
    ) -> tuple[str, str]:
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            deadline = time.monotonic() + 5
            while not child_pid_path.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            raise KeyboardInterrupt
        return original_communicate(process, *args, **kwargs)

    monkeypatch.setattr(subprocess.Popen, "communicate", interrupt_worker_once)
    try:
        with pytest.raises(KeyboardInterrupt):
            execute_go_run(runtime, prepared.go_run_id, timeout_seconds=30)
        assert child_pid_path.is_file()
        child_pid = int(child_pid_path.read_text(encoding="utf-8"))
        deadline = time.monotonic() + 5
        while _pid_alive(child_pid) and time.monotonic() < deadline:
            time.sleep(0.05)

        assert not _pid_alive(child_pid)
        _assert_secret_absent(runtime, secret)
        _assert_secret_absent(project, secret)
    finally:
        if child_pid:
            _force_kill(child_pid)
