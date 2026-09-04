"""Real-process contract tests for Pi prompt/event/abort mapping."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import textwrap
import threading
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import control_plane.pi_rpc_adapter as pi_rpc_adapter_module
import control_plane.pi_rpc_turn as pi_rpc_turn_module
from control_plane.pi_rpc_adapter import (
    OFFICIAL_PI_INTEGRITY,
    OFFICIAL_PI_PACKAGE,
    OFFICIAL_PI_VERSION,
    PiRpcAdapter,
    PiRpcConfig,
    PiRpcError,
    PiRpcPreparedRuntime,
)
from control_plane.pi_rpc_turn import PiRpcTurnRunner


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_lock(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {
                    "": {"dependencies": {OFFICIAL_PI_PACKAGE: OFFICIAL_PI_VERSION}},
                    f"node_modules/{OFFICIAL_PI_PACKAGE}": {
                        "version": OFFICIAL_PI_VERSION,
                        "resolved": (
                            "https://registry.npmjs.org/@earendil-works/"
                            "pi-coding-agent/-/pi-coding-agent-0.84.1.tgz"
                        ),
                        "integrity": OFFICIAL_PI_INTEGRITY,
                        "license": "MIT",
                    },
                },
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )


def _config(tmp_path: Path, monkeypatch, script_text: str, *, timeout: float = 2.0):
    script = tmp_path / "mock_pi_turn.py"
    script.write_text(textwrap.dedent(script_text), encoding="utf-8")
    digest = _sha256(script)
    monkeypatch.setattr(pi_rpc_adapter_module, "OFFICIAL_PI_CLI_SHA256", digest)
    lock = tmp_path / "package-lock.json"
    _write_lock(lock)
    agent_dir = tmp_path / "agent-home"
    agent_dir.mkdir(exist_ok=True)
    return PiRpcConfig(
        command=(sys.executable, str(script)),
        lock_path=lock,
        artifact_path=script,
        artifact_sha256=digest,
        agent_dir=agent_dir,
        cwd=tmp_path,
        timeout_seconds=timeout,
        provider="synthetic-provider",
        model="synthetic-model",
    )


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        synchronize = 0x00100000
        wait_timeout = 0x00000102
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) == wait_timeout
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _cleanup_pid(pid: int) -> None:
    if not pid or not _pid_alive(pid):
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
    else:
        os.kill(pid, 9)


def _assert_error_redacted(error: BaseException, raw_value: str) -> None:
    assert raw_value not in str(error)
    assert raw_value not in repr(error)
    assert raw_value not in repr(error.args)
    assert error.__cause__ is None
    assert error.__context__ is None


NORMAL_TURN = """
import json
import sys

request = json.loads(sys.stdin.buffer.readline())
assert request["type"] == "prompt"
print(json.dumps({"id": request["id"], "type": "response", "command": "prompt", "success": True}))
print(json.dumps({"type": "agent_start"}))
print(json.dumps({
    "type": "message_update",
    "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0, "delta": "synthetic-secret-text"},
}))
print(json.dumps({
    "type": "message_end",
    "message": {"role": "assistant", "content": [], "stopReason": "stop"},
}))
print(json.dumps({"type": "agent_settled"}))
sys.stdout.flush()
"""


def test_turn_maps_prompt_events_without_returning_raw_content(tmp_path, monkeypatch):
    result = PiRpcTurnRunner(_config(tmp_path, monkeypatch, NORMAL_TURN)).run_turn(
        "Do the bounded synthetic task."
    )

    assert result.execution_status == "completed"
    assert result.reason == "STOP"
    assert result.prompt_accepted is True
    assert result.abort_acknowledged is False
    assert result.process_exit_code == 0
    assert result.event_count == 4
    assert len(result.event_evidence) == 4
    assert all(item.startswith("pi:event:") for item in result.event_evidence)
    assert "synthetic-secret-text" not in repr(result)
    assert not hasattr(result, "verification_verdict")
    assert not hasattr(result, "acceptance_status")


def test_turn_accepts_normal_streams_longer_than_64_events(tmp_path, monkeypatch):
    script = """
import json
import sys

request = json.loads(sys.stdin.buffer.readline())
print(json.dumps({"id": request["id"], "type": "response", "command": "prompt", "success": True}))
print(json.dumps({"type": "agent_start"}))
for _ in range(128):
    print(json.dumps({
        "type": "message_update",
        "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0, "delta": "x"},
    }))
print(json.dumps({
    "type": "message_end",
    "message": {"role": "assistant", "content": [], "stopReason": "stop"},
}))
print(json.dumps({"type": "agent_settled"}))
sys.stdout.flush()
"""

    result = PiRpcTurnRunner(_config(tmp_path, monkeypatch, script)).run_turn(
        "Complete a normal streamed turn."
    )

    assert result.execution_status == "completed"
    assert result.reason == "STOP"
    assert result.event_count == 131


def test_turn_forwards_explicit_model_selection_to_real_rpc_process(
    tmp_path, monkeypatch
):
    script = r'''
import json
import sys

assert sys.argv[-4:] == [
    "--provider", "local-loopback", "--model", "Qwen3-4B-Q4_K_M"
]
request = json.loads(sys.stdin.buffer.readline())
print(json.dumps({"id": request["id"], "type": "response", "command": "prompt", "success": True}))
print(json.dumps({"type": "message_end", "message": {"role": "assistant", "content": [], "stopReason": "stop"}}))
print(json.dumps({"type": "agent_settled"}))
sys.stdout.flush()
'''
    config = replace(
        _config(tmp_path, monkeypatch, script),
        provider="local-loopback",
        model="Qwen3-4B-Q4_K_M",
    )

    result = PiRpcTurnRunner(config).run_turn("Run one synthetic local turn.")

    assert result.execution_status == "completed"
    assert result.reason == "STOP"


def test_turn_accepts_crlf_jsonl_transport_without_weakening_records(
    tmp_path, monkeypatch
):
    script = r'''
import json
import sys

request = json.loads(sys.stdin.buffer.readline())
records = [
    {"id": request["id"], "type": "response", "command": "prompt", "success": True},
    {"type": "message_end", "message": {"role": "assistant", "content": [], "stopReason": "stop"}},
    {"type": "agent_settled"},
]
for record in records:
    sys.stdout.buffer.write(json.dumps(record).encode("utf-8") + b"\r\n")
sys.stdout.buffer.flush()
'''

    result = PiRpcTurnRunner(_config(tmp_path, monkeypatch, script)).run_turn(
        "Normalize transport framing."
    )

    assert result.execution_status == "completed"
    assert result.reason == "STOP"
    assert result.event_count == 2


def test_turn_sends_abort_after_real_prompt_readiness(tmp_path, monkeypatch):
    ready = tmp_path / "prompt-ready.txt"
    script = f"""
import json
import os
import sys
from pathlib import Path

request = json.loads(sys.stdin.buffer.readline())
print(json.dumps({{"id": request["id"], "type": "response", "command": "prompt", "success": True}}))
print(json.dumps({{"type": "agent_start"}}))
sys.stdout.flush()
Path({str(ready)!r}).write_text(str(os.getpid()), encoding="utf-8")
abort = json.loads(sys.stdin.buffer.readline())
assert abort["type"] == "abort"
print(json.dumps({{"id": abort["id"], "type": "response", "command": "abort", "success": True}}))
print(json.dumps({{
    "type": "message_end",
    "message": {{"role": "assistant", "content": [], "stopReason": "aborted"}},
}}))
print(json.dumps({{"type": "agent_settled"}}))
sys.stdout.flush()
"""
    cancel = threading.Event()

    def cancel_when_ready() -> None:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if ready.is_file():
                cancel.set()
                return
            time.sleep(0.01)

    watcher = threading.Thread(target=cancel_when_ready, name="pi-turn-cancel", daemon=True)
    watcher.start()
    result = PiRpcTurnRunner(_config(tmp_path, monkeypatch, script)).run_turn(
        "Wait for cancellation.", cancel_event=cancel
    )
    watcher.join(timeout=2.0)

    assert cancel.is_set()
    assert result.execution_status == "interrupted"
    assert result.reason == "CANCELLED"
    assert result.prompt_accepted is True
    assert result.abort_acknowledged is True
    assert result.event_count == 3
    assert not _pid_alive(int(ready.read_text(encoding="utf-8")))


@pytest.mark.skipif(os.name != "nt", reason="Windows Job containment path")
def test_windows_cancel_reaps_tree_created_before_popen_returns(tmp_path, monkeypatch):
    root_pid_path = tmp_path / "root.pid"
    child_pid_path = tmp_path / "child.pid"
    grandchild_pid_path = tmp_path / "grandchild.pid"
    late_marker = tmp_path / "late.txt"
    grandchild = tmp_path / "grandchild.py"
    grandchild.write_text(
        "import os, sys, time\n"
        "from pathlib import Path\n"
        "Path(sys.argv[1]).write_text(str(os.getpid()), encoding='utf-8')\n"
        "time.sleep(1.0)\n"
        "Path(sys.argv[2]).write_text('late', encoding='utf-8')\n"
        "time.sleep(30.0)\n",
        encoding="utf-8",
    )
    child = tmp_path / "child.py"
    child.write_text(
        "import os, subprocess, sys, time\n"
        "from pathlib import Path\n"
        f"subprocess.Popen([sys.executable, {str(grandchild)!r}, sys.argv[2], sys.argv[3]])\n"
        "Path(sys.argv[1]).write_text(str(os.getpid()), encoding='utf-8')\n"
        "time.sleep(30.0)\n",
        encoding="utf-8",
    )
    script = f'''
import json
import os
import subprocess
import sys
import time
from pathlib import Path

subprocess.Popen([
    sys.executable,
    {str(child)!r},
    {str(child_pid_path)!r},
    {str(grandchild_pid_path)!r},
    {str(late_marker)!r},
])
Path({str(root_pid_path)!r}).write_text(str(os.getpid()), encoding="utf-8")
request = json.loads(sys.stdin.buffer.readline())
print(json.dumps({{"id": request["id"], "type": "response", "command": "prompt", "success": True}}))
print(json.dumps({{"type": "agent_start"}}))
sys.stdout.flush()
time.sleep(30.0)
'''
    real_popen = subprocess.Popen
    suspended_flag = 0x00000004

    def scheduled_popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        if not int(kwargs.get("creationflags", 0)) & suspended_flag:
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                if all(
                    path.is_file()
                    for path in (root_pid_path, child_pid_path, grandchild_pid_path)
                ):
                    break
                time.sleep(0.01)
        return process

    monkeypatch.setattr(
        pi_rpc_turn_module,
        "subprocess",
        SimpleNamespace(
            CREATE_NEW_PROCESS_GROUP=getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            ),
            PIPE=subprocess.PIPE,
            Popen=scheduled_popen,
            TimeoutExpired=subprocess.TimeoutExpired,
        ),
    )
    cancel = threading.Event()

    def cancel_when_tree_ready() -> None:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if all(
                path.is_file()
                for path in (root_pid_path, child_pid_path, grandchild_pid_path)
            ):
                cancel.set()
                return
            time.sleep(0.01)

    watcher = threading.Thread(
        target=cancel_when_tree_ready,
        name="pi-turn-tree-cancel",
        daemon=True,
    )
    pids: list[int] = []
    watcher.start()
    try:
        result = PiRpcTurnRunner(
            _config(tmp_path, monkeypatch, script, timeout=3.0)
        ).run_turn("Cancel one contained process tree.", cancel_event=cancel)
        watcher.join(timeout=2.0)
        pids = [
            int(path.read_text(encoding="utf-8"))
            for path in (root_pid_path, child_pid_path, grandchild_pid_path)
        ]

        assert result.execution_status == "interrupted"
        assert result.reason == "CANCELLED"
        assert cancel.is_set()
        assert all(not _pid_alive(pid) for pid in pids)
        time.sleep(1.1)
        assert not late_marker.exists()
    finally:
        owned_pids = set(pids)
        for path in (root_pid_path, child_pid_path, grandchild_pid_path):
            if path.is_file():
                owned_pids.add(int(path.read_text(encoding="utf-8")))
        for pid in owned_pids:
            _cleanup_pid(pid)


def test_pre_cancel_does_not_launch_pi(tmp_path, monkeypatch):
    marker = tmp_path / "started.txt"
    script = f"from pathlib import Path\nPath({str(marker)!r}).write_text('started')\n"
    cancel = threading.Event()
    cancel.set()

    result = PiRpcTurnRunner(_config(tmp_path, monkeypatch, script)).run_turn(
        "Do not start.", cancel_event=cancel
    )

    assert result.execution_status == "interrupted"
    assert result.reason == "CANCELLED_BEFORE_START"
    assert result.event_evidence == ()
    assert not marker.exists()


def test_non_cancelled_turn_requires_model_selection_before_runtime_start(
    tmp_path, monkeypatch
):
    config = replace(
        _config(tmp_path, monkeypatch, NORMAL_TURN),
        provider=None,
        model=None,
    )
    monkeypatch.setattr(
        PiRpcAdapter,
        "prepare_runtime",
        lambda _self: (_ for _ in ()).throw(AssertionError("runtime started")),
    )

    with pytest.raises(PiRpcError, match="model selection is unavailable"):
        PiRpcTurnRunner(config).run_turn("Require an explicit model.")


def test_timeout_returns_partial_evidence_and_stops_process(tmp_path, monkeypatch):
    pid_file = tmp_path / "turn.pid"
    script = f"""
import json
import os
import sys
import time
from pathlib import Path

request = json.loads(sys.stdin.buffer.readline())
Path({str(pid_file)!r}).write_text(str(os.getpid()), encoding="utf-8")
print(json.dumps({{"id": request["id"], "type": "response", "command": "prompt", "success": True}}))
print(json.dumps({{"type": "agent_start"}}))
sys.stdout.flush()
time.sleep(30)
"""
    pid = 0
    try:
        result = PiRpcTurnRunner(
            _config(tmp_path, monkeypatch, script, timeout=0.2)
        ).run_turn("Time out safely.")
        pid = int(pid_file.read_text(encoding="utf-8"))

        assert result.execution_status == "interrupted"
        assert result.reason == "TIMEOUT"
        assert result.prompt_accepted is True
        assert result.abort_acknowledged is False
        assert result.event_count == 1
        assert not _pid_alive(pid)
    finally:
        _cleanup_pid(pid)


def test_unknown_event_fails_closed_without_raw_payload(tmp_path, monkeypatch):
    script = """
import json
import sys

request = json.loads(sys.stdin.buffer.readline())
print(json.dumps({"id": request["id"], "type": "response", "command": "prompt", "success": True}))
print(json.dumps({"type": "future_event", "value": "raw-sensitive-payload"}))
sys.stdout.flush()
"""

    with pytest.raises(PiRpcError) as exc_info:
        PiRpcTurnRunner(_config(tmp_path, monkeypatch, script)).run_turn("Fail closed.")

    assert "unsupported" in str(exc_info.value)
    assert "raw-sensitive-payload" not in str(exc_info.value)


def test_event_limit_fails_closed_and_stops_process(tmp_path, monkeypatch):
    pid_file = tmp_path / "overflow.pid"
    script = f'''
import json
import os
import sys
import time
from pathlib import Path

request = json.loads(sys.stdin.buffer.readline())
Path({str(pid_file)!r}).write_text(str(os.getpid()), encoding="utf-8")
print(json.dumps({{"id": request["id"], "type": "response", "command": "prompt", "success": True}}))
for _ in range({pi_rpc_turn_module.MAX_PI_RPC_TURN_EVENTS + 1}):
    print(json.dumps({{"type": "agent_start"}}))
sys.stdout.flush()
time.sleep(30)
'''
    pid = 0
    try:
        with pytest.raises(PiRpcError, match="event limit exceeded"):
            PiRpcTurnRunner(_config(tmp_path, monkeypatch, script)).run_turn(
                "Bound event evidence."
            )
        pid = int(pid_file.read_text(encoding="utf-8"))
        assert not _pid_alive(pid)
    finally:
        _cleanup_pid(pid)


def test_completed_turn_requires_clean_process_exit(tmp_path, monkeypatch):
    script = """
import json
import sys

request = json.loads(sys.stdin.buffer.readline())
print(json.dumps({"id": request["id"], "type": "response", "command": "prompt", "success": True}))
print(json.dumps({"type": "message_end", "message": {"role": "assistant", "content": [], "stopReason": "stop"}}))
print(json.dumps({"type": "agent_settled"}))
sys.stdout.flush()
raise SystemExit(9)
"""

    with pytest.raises(PiRpcError, match="did not exit cleanly"):
        PiRpcTurnRunner(_config(tmp_path, monkeypatch, script)).run_turn(
            "Reject contradictory completion."
        )


def test_prompt_write_obeys_deadline_when_child_never_reads(tmp_path, monkeypatch):
    pid_file = tmp_path / "no-read.pid"
    script = f'''
import os
import time
from pathlib import Path

Path({str(pid_file)!r}).write_text(str(os.getpid()), encoding="utf-8")
time.sleep(30)
'''
    pid = 0
    started = time.monotonic()
    try:
        result = PiRpcTurnRunner(
            _config(tmp_path, monkeypatch, script, timeout=0.2)
        ).run_turn("x" * 32_768)
        elapsed = time.monotonic() - started
        pid = int(pid_file.read_text(encoding="utf-8"))

        assert result.execution_status == "interrupted"
        assert result.reason == "TIMEOUT"
        assert result.prompt_accepted is False
        assert elapsed < 3.0
        assert not _pid_alive(pid)
    finally:
        _cleanup_pid(pid)


@pytest.mark.parametrize("response_kind", ["duplicate_prompt", "unsolicited_abort"])
def test_response_correlation_is_one_shot(tmp_path, monkeypatch, response_kind):
    second = (
        'print(json.dumps({"id": request["id"], "type": "response", "command": "prompt", "success": True}))'
        if response_kind == "duplicate_prompt"
        else 'print(json.dumps({"id": "devframe-pi-turn-abort-1", "type": "response", "command": "abort", "success": True}))'
    )
    script = f'''
import json
import sys

request = json.loads(sys.stdin.buffer.readline())
print(json.dumps({{"id": request["id"], "type": "response", "command": "prompt", "success": True}}))
{second}
sys.stdout.flush()
'''

    with pytest.raises(PiRpcError, match="response correlation failed"):
        PiRpcTurnRunner(_config(tmp_path, monkeypatch, script)).run_turn(
            "Reject response spoofing."
        )


def test_total_record_bytes_are_bounded(tmp_path, monkeypatch):
    script = '''
import json
import sys

request = json.loads(sys.stdin.buffer.readline())
print(json.dumps({"id": request["id"], "type": "response", "command": "prompt", "success": True}))
payload = "x" * 260000
for _ in range(17):
    print(json.dumps({"type": "agent_start", "padding": payload}))
sys.stdout.flush()
'''

    with pytest.raises(PiRpcError, match="output framing failed"):
        PiRpcTurnRunner(_config(tmp_path, monkeypatch, script)).run_turn(
            "Bound total output."
        )


def test_malformed_event_and_prompt_errors_retain_no_raw_value(tmp_path, monkeypatch):
    raw_event = "raw-event-secret"
    script = f'''
import json
import sys

request = json.loads(sys.stdin.buffer.readline())
print(json.dumps({{"id": request["id"], "type": "response", "command": "prompt", "success": True}}))
sys.stdout.buffer.write(b'{{"type":"agent_start","value":"{raw_event}"' + b"\n")
sys.stdout.buffer.flush()
'''

    with pytest.raises(PiRpcError) as event_error:
        PiRpcTurnRunner(_config(tmp_path, monkeypatch, script)).run_turn(
            "Reject malformed output."
        )
    _assert_error_redacted(event_error.value, raw_event)

    raw_prompt = "raw-prompt-secret\ud800"
    with pytest.raises(ValueError) as prompt_error:
        PiRpcTurnRunner(_config(tmp_path, monkeypatch, NORMAL_TURN)).run_turn(raw_prompt)
    _assert_error_redacted(prompt_error.value, raw_prompt)


def test_primary_protocol_error_survives_descendant_cleanup_failure(
    tmp_path, monkeypatch
):
    child_pid_file = tmp_path / "lingering-child.pid"
    script = f'''
import json
import os
import subprocess
import sys
from pathlib import Path

request = json.loads(sys.stdin.buffer.readline())
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
Path({str(child_pid_file)!r}).write_text(str(child.pid), encoding="utf-8")
print(json.dumps({{"id": request["id"], "type": "response", "command": "prompt", "success": True}}))
print(json.dumps({{"type": "future_event"}}))
sys.stdout.flush()
os._exit(0)
'''
    child_pid = 0
    try:
        with pytest.raises(PiRpcError, match="event type is unsupported") as exc_info:
            PiRpcTurnRunner(_config(tmp_path, monkeypatch, script)).run_turn(
                "Preserve the primary error."
            )
        child_pid = int(child_pid_file.read_text(encoding="utf-8"))
        assert getattr(exc_info.value, "cleanup_failed", False) is True
        assert not _pid_alive(child_pid)
    finally:
        _cleanup_pid(child_pid)


def test_start_error_survives_cleanup_error(monkeypatch, tmp_path):
    prepared = PiRpcPreparedRuntime(
        command=(sys.executable, str(tmp_path / "unused.py")),
        cwd=tmp_path,
        environment=(),
        timeout_seconds=1.0,
    )

    def fail_start(self, runtime):
        raise PiRpcError("primary start failure")

    def fail_cleanup(self):
        raise PiRpcError("secondary cleanup failure")

    monkeypatch.setattr(pi_rpc_turn_module._TurnProcess, "_start", fail_start)
    monkeypatch.setattr(pi_rpc_turn_module._TurnProcess, "close", fail_cleanup)

    with pytest.raises(PiRpcError, match="primary start failure") as exc_info:
        pi_rpc_turn_module._TurnProcess(prepared)
    assert getattr(exc_info.value, "cleanup_failed", False) is True


def test_abort_write_failure_returns_partial_evidence(tmp_path, monkeypatch):
    ready = tmp_path / "abort-write-ready.txt"
    script = f'''
import json
import os
import sys
import time
from pathlib import Path

request = json.loads(sys.stdin.buffer.readline())
print(json.dumps({{"id": request["id"], "type": "response", "command": "prompt", "success": True}}))
print(json.dumps({{"type": "agent_start"}}))
sys.stdout.flush()
sys.stdin.close()
Path({str(ready)!r}).write_text(str(os.getpid()), encoding="utf-8")
time.sleep(30)
'''
    cancel = threading.Event()

    def cancel_when_ready() -> None:
        while not ready.is_file():
            time.sleep(0.005)
        cancel.set()

    watcher = threading.Thread(target=cancel_when_ready, daemon=True)
    watcher.start()
    result = PiRpcTurnRunner(_config(tmp_path, monkeypatch, script)).run_turn(
        "Keep partial evidence.", cancel_event=cancel
    )
    watcher.join(timeout=2.0)

    assert result.execution_status == "interrupted"
    assert result.reason == "CANCELLED"
    assert result.abort_acknowledged is False
    assert result.event_count == 1
    assert not _pid_alive(int(ready.read_text(encoding="utf-8")))


def test_eof_after_cancel_returns_partial_evidence(tmp_path, monkeypatch):
    ready = tmp_path / "cancel-eof-ready.txt"
    script = f'''
import json
import os
import sys
import time
from pathlib import Path

request = json.loads(sys.stdin.buffer.readline())
print(json.dumps({{"id": request["id"], "type": "response", "command": "prompt", "success": True}}))
print(json.dumps({{"type": "agent_start"}}))
sys.stdout.flush()
Path({str(ready)!r}).write_text(str(os.getpid()), encoding="utf-8")
time.sleep(0.1)
'''
    cancel = threading.Event()

    def cancel_when_ready() -> None:
        while not ready.is_file():
            time.sleep(0.005)
        cancel.set()

    watcher = threading.Thread(target=cancel_when_ready, daemon=True)
    watcher.start()
    result = PiRpcTurnRunner(_config(tmp_path, monkeypatch, script)).run_turn(
        "Keep evidence on EOF.", cancel_event=cancel
    )
    watcher.join(timeout=2.0)

    assert result.execution_status == "interrupted"
    assert result.reason == "CANCELLED"
    assert result.abort_acknowledged is False
    assert result.event_count == 1
    assert not _pid_alive(int(ready.read_text(encoding="utf-8")))
