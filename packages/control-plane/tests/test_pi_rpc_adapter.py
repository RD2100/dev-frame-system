"""Contract tests for the pinned Pi JSONL RPC boundary."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
from dataclasses import asdict, replace
from pathlib import Path

import pytest

import control_plane.pi_rpc_adapter as pi_rpc_module
from control_plane.pi_rpc_adapter import (
    OFFICIAL_PI_CLI_SHA256,
    OFFICIAL_PI_INTEGRITY,
    OFFICIAL_PI_PACKAGE,
    OFFICIAL_PI_PROTOCOL,
    OFFICIAL_PI_VERSION,
    PiRpcAdapter,
    PiRpcConfig,
    PiRpcError,
)


MOCK_PI = textwrap.dedent(
    """
    import json
    import os
    import sys

    if "--version" in sys.argv:
        print("0.84.1")
        raise SystemExit(0)

    required = {
        "--mode", "rpc", "--offline", "--no-session", "--no-approve",
        "--no-extensions", "--no-skills", "--no-prompt-templates",
        "--no-context-files",
    }
    if not required.issubset(set(sys.argv[1:])):
        raise SystemExit(21)
    forbidden = [
        key for key in os.environ
        if key.endswith("_API_KEY") or key.endswith("_AUTH_TOKEN")
    ]
    if forbidden:
        raise SystemExit(22)
    if os.environ.get("PI_OFFLINE") != "1" or os.environ.get("PI_TELEMETRY") != "0":
        raise SystemExit(23)

    raw = sys.stdin.buffer.readline()
    message = json.loads(raw.decode("utf-8"))
    if message.get("type") != "get_state" or not message.get("id"):
        raise SystemExit(24)
    response = {
        "id": message["id"],
        "type": "response",
        "command": "get_state",
        "success": True,
        "data": {"isStreaming": False, "messageCount": 0},
    }
    sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\\n")
    sys.stdout.flush()
    """
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_lock(path: Path, *, integrity: str = OFFICIAL_PI_INTEGRITY) -> None:
    path.write_text(
        json.dumps(
            {
                "name": "pi-adapter-test",
                "lockfileVersion": 3,
                "packages": {
                    "": {"dependencies": {OFFICIAL_PI_PACKAGE: OFFICIAL_PI_VERSION}},
                    f"node_modules/{OFFICIAL_PI_PACKAGE}": {
                        "version": OFFICIAL_PI_VERSION,
                        "resolved": (
                            "https://registry.npmjs.org/@earendil-works/"
                            "pi-coding-agent/-/pi-coding-agent-0.84.1.tgz"
                        ),
                        "integrity": integrity,
                        "license": "MIT",
                    },
                },
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )


def _mock_config(
    tmp_path: Path,
    monkeypatch,
    script_text: str = MOCK_PI,
    *,
    timeout: float = 2.0,
):
    script = tmp_path / "mock_pi.py"
    script.write_text(script_text, encoding="utf-8")
    monkeypatch.setattr(pi_rpc_module, "OFFICIAL_PI_CLI_SHA256", _sha256(script))
    lock = tmp_path / "package-lock.json"
    _write_lock(lock)
    agent_dir = tmp_path / "agent-home"
    agent_dir.mkdir()
    return PiRpcConfig(
        command=(sys.executable, str(script)),
        lock_path=lock,
        artifact_path=script,
        artifact_sha256=_sha256(script),
        agent_dir=agent_dir,
        cwd=tmp_path,
        timeout_seconds=timeout,
    )


def test_probe_uses_real_jsonl_shape_without_credentials_or_session(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-must-not-enter-child")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "synthetic-must-not-enter-child")

    result = PiRpcAdapter(_mock_config(tmp_path, monkeypatch)).probe()

    assert result.adapter_id == "pi-rpc"
    assert result.protocol == OFFICIAL_PI_PROTOCOL
    assert result.package == OFFICIAL_PI_PACKAGE
    assert result.version == OFFICIAL_PI_VERSION
    assert result.integrity == OFFICIAL_PI_INTEGRITY
    assert result.artifact_sha256 == _sha256(tmp_path / "mock_pi.py")
    assert result.state_received is True
    assert result.is_streaming is False
    assert result.message_count == 0
    assert result.process_exit_code == 0
    assert "model" not in asdict(result)
    assert list((tmp_path / "agent-home").iterdir()) == []


def test_probe_forwards_explicit_non_secret_model_selection(tmp_path, monkeypatch):
    argv_path = tmp_path / "rpc-argv.json"
    script_text = MOCK_PI.replace(
        "raw = sys.stdin.buffer.readline()",
        f"Path = __import__('pathlib').Path\n"
        f"Path({str(argv_path)!r}).write_text(json.dumps(sys.argv[1:]), encoding='utf-8')\n"
        "raw = sys.stdin.buffer.readline()",
    )
    config = replace(
        _mock_config(tmp_path, monkeypatch, script_text),
        provider="local-loopback",
        model="Qwen3-4B-Q4_K_M",
    )

    result = PiRpcAdapter(config).probe()

    assert result.state_received is True
    argv = json.loads(argv_path.read_text(encoding="utf-8"))
    assert argv[-4:] == [
        "--provider",
        "local-loopback",
        "--model",
        "Qwen3-4B-Q4_K_M",
    ]
    assert "provider" not in asdict(result)
    assert "model" not in asdict(result)


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("local-loopback", None),
        (None, "Qwen3-4B-Q4_K_M"),
        ("local loopback", "Qwen3-4B-Q4_K_M"),
        ("local-loopback", "../Qwen3-4B"),
        ("local-loopback", "Qwen/foo/../bar"),
        ("local-loopback", "Qwen3\x00hidden"),
        ("local-loopback", "q" * 129),
    ],
)
def test_config_rejects_incomplete_or_unsafe_model_selection(
    tmp_path, monkeypatch, provider, model
):
    config = _mock_config(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="provider|model"):
        replace(config, provider=provider, model=model)


def test_lock_mismatch_fails_before_launch(tmp_path, monkeypatch):
    marker = tmp_path / "started.txt"
    script = tmp_path / "must_not_start.py"
    script.write_text(
        f"from pathlib import Path; Path({str(marker)!r}).write_text('started')\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(pi_rpc_module, "OFFICIAL_PI_CLI_SHA256", _sha256(script))
    lock = tmp_path / "package-lock.json"
    _write_lock(lock, integrity="sha512-wrong")
    agent_dir = tmp_path / "agent-home"
    agent_dir.mkdir()
    config = PiRpcConfig(
        command=(sys.executable, str(script)),
        lock_path=lock,
        artifact_path=script,
        artifact_sha256=_sha256(script),
        agent_dir=agent_dir,
        cwd=tmp_path,
    )

    with pytest.raises(PiRpcError, match="lock identity mismatch"):
        PiRpcAdapter(config).probe()

    assert not marker.exists()


def test_artifact_mismatch_fails_before_launch(tmp_path, monkeypatch):
    config = _mock_config(tmp_path, monkeypatch)
    config.artifact_path.write_text("changed after approval\n", encoding="utf-8")

    with pytest.raises(PiRpcError, match="artifact identity mismatch"):
        PiRpcAdapter(config).probe()


def test_config_rejects_a_caller_declared_unpinned_artifact_hash(tmp_path):
    with pytest.raises(ValueError, match="must match the pinned artifact"):
        PiRpcConfig(
            command=(sys.executable, str(tmp_path / "pi.js")),
            lock_path=tmp_path / "package-lock.json",
            artifact_path=tmp_path / "pi.js",
            artifact_sha256="0" * 64,
            agent_dir=tmp_path / "agent-home",
            cwd=tmp_path,
        )


def test_command_must_execute_the_verified_artifact(tmp_path, monkeypatch):
    config = _mock_config(tmp_path, monkeypatch)
    marker = tmp_path / "untrusted-started.txt"
    untrusted = tmp_path / "untrusted.py"
    untrusted.write_text(
        f"from pathlib import Path; Path({str(marker)!r}).write_text('started')\n",
        encoding="utf-8",
    )
    mixed = PiRpcConfig(
        command=(sys.executable, str(untrusted)),
        lock_path=config.lock_path,
        artifact_path=config.artifact_path,
        artifact_sha256=config.artifact_sha256,
        agent_dir=config.agent_dir,
        cwd=config.cwd,
    )

    with pytest.raises(PiRpcError, match="command/artifact identity mismatch"):
        PiRpcAdapter(mixed).probe()

    assert not marker.exists()


def test_malformed_rpc_response_fails_closed_without_child_output(tmp_path, monkeypatch):
    script = MOCK_PI.replace(
        'sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\\n")',
        'sys.stdout.write("not-json\\n")',
    )
    config = _mock_config(tmp_path, monkeypatch, script)

    with pytest.raises(PiRpcError) as exc_info:
        PiRpcAdapter(config).probe()

    assert "not-json" not in str(exc_info.value)


def test_timeout_is_bounded_and_fails_closed(tmp_path, monkeypatch):
    script = MOCK_PI.replace(
        "raw = sys.stdin.buffer.readline()",
        "import time; time.sleep(30); raw = sys.stdin.buffer.readline()",
    )
    config = _mock_config(tmp_path, monkeypatch, script, timeout=0.2)
    started = time.monotonic()

    with pytest.raises(PiRpcError, match="timed out"):
        PiRpcAdapter(config).probe()

    assert time.monotonic() - started < 5.0


def test_exited_parent_descendant_is_stopped_before_return(tmp_path, monkeypatch):
    pid_file = tmp_path / "child.pid"
    late_marker = tmp_path / "late-marker.txt"
    child = tmp_path / "child.py"
    child.write_text(
        "import os, sys, time\n"
        "from pathlib import Path\n"
        "Path(sys.argv[1]).write_text(str(os.getpid()), encoding='utf-8')\n"
        "time.sleep(1.0)\n"
        "Path(sys.argv[2]).write_text('late', encoding='utf-8')\n"
        "time.sleep(30.0)\n",
        encoding="utf-8",
    )
    spawn = (
        "import subprocess\n"
        f"subprocess.Popen([sys.executable, {str(child)!r}, {str(pid_file)!r}, "
        f"{str(late_marker)!r}])\n"
    )
    script = MOCK_PI.replace(
        "raw = sys.stdin.buffer.readline()",
        spawn + "raw = sys.stdin.buffer.readline()",
    )
    config = _mock_config(tmp_path, monkeypatch, script, timeout=3.0)
    real_popen = subprocess.Popen
    if os.name == "nt":
        suspended_flag = 0x00000004

        def scheduled_popen(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            if not int(kwargs.get("creationflags", 0)) & suspended_flag:
                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline and not pid_file.is_file():
                    time.sleep(0.01)
            return process

        monkeypatch.setattr(pi_rpc_module.subprocess, "Popen", scheduled_popen)
    child_pid = 0
    try:
        with pytest.raises(PiRpcError, match="unexpected descendant"):
            PiRpcAdapter(config).probe()
        if pid_file.exists():
            child_pid = int(pid_file.read_text(encoding="utf-8"))
        time.sleep(1.25)
        assert not late_marker.exists()
    finally:
        if child_pid:
            if os.name == "nt":
                cleanup = real_popen(
                    ["taskkill", "/PID", str(child_pid), "/T", "/F"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                cleanup.communicate(timeout=5.0)
            else:
                try:
                    os.kill(child_pid, 9)
                except ProcessLookupError:
                    child_pid = 0


@pytest.mark.skipif(os.name != "nt", reason="Windows Job assignment path")
def test_job_assignment_failure_closes_job_and_process(tmp_path, monkeypatch):
    config = _mock_config(tmp_path, monkeypatch)
    real_popen = pi_rpc_module.subprocess.Popen
    processes = []

    class FailingJob:
        closed = False

        def suspended_creation_flag(self):
            return 0x00000004

        def assign(self, process):
            raise OSError("synthetic assignment failure")

        def close(self):
            self.closed = True
            return False

    job = FailingJob()

    def recording_popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(pi_rpc_module, "_WindowsJob", lambda: job)
    monkeypatch.setattr(pi_rpc_module.subprocess, "Popen", recording_popen)

    with pytest.raises(PiRpcError, match="containment failed") as exc_info:
        PiRpcAdapter(config).probe()

    assert getattr(exc_info.value, "cleanup_failed", False) is True
    assert job.closed is True
    assert processes
    assert processes[0].poll() is not None


@pytest.mark.skipif(os.name != "nt", reason="Windows Job resume path")
def test_job_resume_failure_closes_job_and_process(tmp_path, monkeypatch):
    config = _mock_config(tmp_path, monkeypatch)
    real_popen = pi_rpc_module.subprocess.Popen
    processes = []

    class FailingJob:
        closed = False

        def suspended_creation_flag(self):
            return 0x00000004

        def assign(self, process):
            return None

        def resume(self, process):
            raise OSError("synthetic resume failure")

        def close(self):
            self.closed = True
            return True

    job = FailingJob()

    def recording_popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(pi_rpc_module, "_WindowsJob", lambda: job)
    monkeypatch.setattr(pi_rpc_module.subprocess, "Popen", recording_popen)

    with pytest.raises(PiRpcError, match="containment failed"):
        PiRpcAdapter(config).probe()

    assert job.closed is True
    assert processes
    assert processes[0].poll() is not None


def test_reader_start_failure_stops_process(tmp_path, monkeypatch):
    config = _mock_config(tmp_path, monkeypatch)
    real_popen = pi_rpc_module.subprocess.Popen
    real_thread_start = pi_rpc_module.threading.Thread.start
    processes = []

    def recording_popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    def fail_reader_start(self):
        if self.name == "pi-rpc-stderr":
            raise RuntimeError("synthetic reader start failure")
        return real_thread_start(self)

    monkeypatch.setattr(pi_rpc_module.subprocess, "Popen", recording_popen)
    monkeypatch.setattr(pi_rpc_module.threading.Thread, "start", fail_reader_start)

    with pytest.raises(PiRpcError, match="readers could not start"):
        PiRpcAdapter(config).probe()

    assert processes
    assert processes[0].poll() is not None


def test_real_pinned_pi_offline_rpc_when_runtime_is_available(tmp_path):
    runtime_value = os.environ.get("DEVFRAME_PI_RUNTIME", "").strip()
    if not runtime_value:
        pytest.skip("DEVFRAME_PI_RUNTIME is not set")
    runtime = Path(runtime_value).resolve()
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not available")
    artifact = runtime / "node_modules" / OFFICIAL_PI_PACKAGE / "dist" / "cli.js"
    config = PiRpcConfig(
        command=(node, str(artifact)),
        lock_path=runtime / "package-lock.json",
        artifact_path=artifact,
        artifact_sha256=OFFICIAL_PI_CLI_SHA256,
        agent_dir=tmp_path / "isolated-agent-home",
        cwd=tmp_path,
        timeout_seconds=10.0,
    )
    config.agent_dir.mkdir()

    result = PiRpcAdapter(config).probe()

    assert result.version == OFFICIAL_PI_VERSION
    assert result.protocol == OFFICIAL_PI_PROTOCOL
    assert result.state_received is True
    assert result.is_streaming is False
    assert result.message_count == 0
    assert result.process_exit_code == 0
    assert not list(config.agent_dir.rglob("*.jsonl"))
