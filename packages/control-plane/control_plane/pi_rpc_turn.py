"""Pi prompt/event/abort boundary with provider-neutral terminal semantics.

The boundary speaks Pi JSONL but returns only execution state, a reason, and
hash-only event evidence. It owns neither verification nor acceptance.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import secrets
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import BinaryIO

from .local_process_containment import WindowsJob
from .pi_rpc_adapter import (
    PiRpcAdapter,
    PiRpcConfig,
    PiRpcError,
    PiRpcPreparedRuntime,
)
from .toolchain_execution import _terminate_process_tree


_PROMPT_ID_PREFIX = "devframe-pi-turn-prompt-"
_ABORT_ID_PREFIX = "devframe-pi-turn-abort-"
_MAX_MESSAGE_BYTES = 32_768
_MAX_RECORD_BYTES = 262_144
_MAX_TOTAL_RECORD_BYTES = 4_194_304
_MAX_STDERR_BYTES = 65_536
# Pi emits message_update records at streaming-delta granularity. Keep a
# separate finite count bound, while the byte bounds below remain authoritative.
MAX_PI_RPC_TURN_EVENTS = 4096
_MAX_EVENTS = MAX_PI_RPC_TURN_EVENTS
_MAX_RECORDS = _MAX_EVENTS + 2
_ABORT_GRACE_SECONDS = 0.5
_ALLOWED_EVENTS = {
    "agent_start",
    "agent_end",
    "agent_settled",
    "turn_start",
    "turn_end",
    "message_start",
    "message_update",
    "message_end",
    "bash_execution_update",
    "tool_execution_start",
    "tool_execution_update",
    "tool_execution_end",
    "queue_update",
    "compaction_start",
    "compaction_end",
    "auto_retry_start",
    "auto_retry_end",
    "summarization_retry_scheduled",
    "summarization_retry_attempt_start",
    "summarization_retry_finished",
    "extension_error",
}
_STOP_REASONS = {"stop", "length", "toolUse", "error", "aborted"}


@dataclass(frozen=True)
class PiRpcTurnResult:
    """Terminal execution facts; evidence contains hashes, never raw events."""

    execution_status: str
    reason: str
    prompt_accepted: bool
    abort_acknowledged: bool
    event_count: int
    event_evidence: tuple[str, ...]
    process_exit_code: int | None


@dataclass
class _ReaderState:
    error: str = ""
    overflow: bool = False
    data: bytearray = field(default_factory=bytearray)
    record_count: int = 0
    record_bytes: int = 0


@dataclass
class _WriterState:
    done: threading.Event = field(default_factory=threading.Event)
    error: bool = False


@dataclass
class _TurnState:
    prompt_id: str
    abort_id: str
    prompt_requested: bool = False
    prompt_accepted: bool = False
    prompt_rejected: bool = False
    abort_requested: bool = False
    abort_responded: bool = False
    abort_acknowledged: bool = False
    settled: bool = False
    stop_reason: str = ""
    evidence: list[str] = field(default_factory=list)

    def consume(self, raw: bytes) -> None:
        message = _decode_record(raw)
        if message is None:
            raise PiRpcError("Pi turn record is invalid")
        record_type = message.get("type")
        if record_type == "response":
            self._consume_response(message)
            return
        if not isinstance(record_type, str) or record_type not in _ALLOWED_EVENTS:
            raise PiRpcError("Pi turn event type is unsupported")
        if len(self.evidence) >= _MAX_EVENTS:
            raise PiRpcError("Pi turn event limit exceeded")
        canonical = _canonical_record(message)
        if canonical is None:
            raise PiRpcError("Pi turn record is invalid")
        digest = hashlib.sha256(canonical).hexdigest()
        sequence = len(self.evidence) + 1
        self.evidence.append(
            f"pi:event:{sequence:06d}:{record_type}:sha256:{digest}"
        )
        if record_type == "message_end":
            self._consume_message_end(message)
        elif record_type == "agent_settled":
            self.settled = True

    def _consume_response(self, message: dict[str, object]) -> None:
        request_id = message.get("id")
        command = message.get("command")
        success = message.get("success")
        if (
            request_id == self.prompt_id
            and command == "prompt"
            and isinstance(success, bool)
            and self.prompt_requested
            and not self.prompt_accepted
            and not self.prompt_rejected
        ):
            self.prompt_accepted = success
            self.prompt_rejected = not success
            return
        if (
            request_id == self.abort_id
            and command == "abort"
            and isinstance(success, bool)
            and self.abort_requested
            and not self.abort_responded
        ):
            self.abort_responded = True
            self.abort_acknowledged = success
            return
        raise PiRpcError("Pi turn response correlation failed")

    def _consume_message_end(self, event: dict[str, object]) -> None:
        message = event.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            return
        stop_reason = message.get("stopReason")
        if not isinstance(stop_reason, str) or stop_reason not in _STOP_REASONS:
            raise PiRpcError("Pi assistant stop reason is invalid")
        self.stop_reason = stop_reason


class _TurnProcess:
    def __init__(self, prepared: PiRpcPreparedRuntime) -> None:
        self.process: subprocess.Popen[bytes] | None = None
        self.job: WindowsJob | None = None
        self.job_assigned = False
        self.records: queue.Queue[tuple[str, bytes | None]] = queue.Queue(
            maxsize=_MAX_EVENTS + 8
        )
        self.stdout_state = _ReaderState()
        self.stderr_state = _ReaderState()
        self.stdout_thread: threading.Thread | None = None
        self.stderr_thread: threading.Thread | None = None
        self.started_threads: list[threading.Thread] = []
        self.writer_threads: list[threading.Thread] = []
        try:
            self._start(prepared)
        except BaseException as primary_error:
            try:
                self.close()
            except BaseException:
                setattr(primary_error, "cleanup_failed", True)
            raise

    def _start(self, prepared: PiRpcPreparedRuntime) -> None:
        creationflags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        )
        try:
            self.job = WindowsJob() if os.name == "nt" else None
            if self.job is not None:
                creationflags |= self.job.suspended_creation_flag()
            self.process = subprocess.Popen(
                [*prepared.command, *prepared.rpc_args],
                cwd=str(prepared.cwd),
                env=prepared.environment_dict(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                creationflags=creationflags,
                start_new_session=os.name != "nt",
            )
            if self.job is not None:
                self.job.assign(self.process)
                self.job_assigned = True
                self.job.resume(self.process)
        except OSError as exc:
            raise PiRpcError("Pi turn process could not start safely") from exc
        if self.process.stdout is None or self.process.stderr is None:
            raise PiRpcError("Pi turn process pipes are unavailable")
        self.stdout_thread = threading.Thread(
            target=_read_records,
            args=(self.process.stdout, self.records, self.stdout_state),
            name="pi-turn-stdout",
            daemon=True,
        )
        self.stderr_thread = threading.Thread(
            target=_drain_stderr,
            args=(self.process.stderr, self.stderr_state),
            name="pi-turn-stderr",
            daemon=True,
        )
        try:
            self.stdout_thread.start()
            self.started_threads.append(self.stdout_thread)
            self.stderr_thread.start()
            self.started_threads.append(self.stderr_thread)
        except RuntimeError as exc:
            raise PiRpcError("Pi turn readers could not start") from exc

    def send(
        self,
        message: dict[str, object],
        *,
        deadline: float,
        cancel_event: threading.Event | None = None,
    ) -> str:
        if self.process is None or self.process.stdin is None or self.process.stdin.closed:
            raise PiRpcError("Pi turn input is unavailable")
        if cancel_event is not None and cancel_event.is_set():
            return "cancelled"
        if time.monotonic() >= deadline:
            return "timeout"
        payload = _encode_command(message)
        if payload is None:
            raise PiRpcError("Pi turn input is invalid")
        state = _WriterState()
        writer = threading.Thread(
            target=_write_payload,
            args=(self.process.stdin, payload, state),
            name="pi-turn-stdin",
            daemon=True,
        )
        try:
            writer.start()
        except RuntimeError as exc:
            raise PiRpcError("Pi turn input writer could not start") from exc
        self.writer_threads.append(writer)
        while True:
            if cancel_event is not None and cancel_event.is_set():
                return "cancelled"
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return "timeout"
            if state.done.wait(timeout=min(0.01, remaining)):
                if state.error:
                    return "failed"
                return "sent"

    def read(self, timeout: float) -> tuple[str, bytes | None]:
        try:
            return self.records.get(timeout=max(0.001, timeout))
        except queue.Empty:
            return ("idle", None)

    def close(self) -> int | None:
        cleanup_failed = False
        unexpected_descendant = False
        process = self.process
        writer_alive = any(writer.is_alive() for writer in self.writer_threads)
        graceful_exit = process is None or process.poll() is not None
        if (
            process is not None
            and process.stdin is not None
            and not process.stdin.closed
            and not writer_alive
        ):
            try:
                process.stdin.close()
            except (OSError, ValueError):
                cleanup_failed = True
        if process is not None and process.poll() is None and not writer_alive:
            try:
                process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                graceful_exit = False
            else:
                graceful_exit = True
        if process is not None and process.poll() is not None:
            if self.job is not None and self.job_assigned:
                try:
                    unexpected_descendant = self.job.active_processes() > 0
                except OSError:
                    cleanup_failed = True
                    unexpected_descendant = True
            elif self.job is None:
                unexpected_descendant = _process_group_exists(process.pid)
        if self.job is not None and not self.job.close():
            cleanup_failed = True
        if process is not None:
            if (
                (not graceful_exit and process.poll() is None)
                or (self.job is None and unexpected_descendant)
            ):
                try:
                    _terminate_process_tree(process)
                except OSError:
                    cleanup_failed = True
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                    process.wait(timeout=5.0)
                except (OSError, subprocess.TimeoutExpired):
                    cleanup_failed = True
            if process.stdin is not None and not process.stdin.closed:
                try:
                    process.stdin.close()
                except (OSError, ValueError):
                    cleanup_failed = True
            for stream, reader in (
                (process.stdout, self.stdout_thread),
                (process.stderr, self.stderr_thread),
            ):
                if stream is not None and reader not in self.started_threads:
                    try:
                        stream.close()
                    except OSError:
                        cleanup_failed = True
        for writer in self.writer_threads:
            writer.join(timeout=2.0)
            if writer.is_alive():
                cleanup_failed = True
        for reader in self.started_threads:
            reader.join(timeout=2.0)
            if reader.is_alive():
                cleanup_failed = True
        # stdout protocol errors are delivered through ``records`` and must not
        # be reclassified as cleanup failures.  stderr is drained only for
        # lifecycle safety, so a stderr reader failure remains a cleanup error.
        if self.stderr_state.error:
            cleanup_failed = True
        if self.stdout_state.overflow or self.stderr_state.overflow:
            cleanup_failed = True
        if unexpected_descendant:
            raise PiRpcError("Pi turn left an unexpected descendant")
        if cleanup_failed:
            raise PiRpcError("Pi turn process cleanup failed")
        return None if process is None else process.returncode


class PiRpcTurnRunner:
    """Run one bounded Pi turn and map it to neutral terminal facts."""

    def __init__(self, config: PiRpcConfig) -> None:
        if not isinstance(config, PiRpcConfig):
            raise TypeError("PiRpcTurnRunner requires PiRpcConfig")
        self._config = config

    def run_turn(
        self,
        message: str,
        *,
        cancel_event: threading.Event | None = None,
    ) -> PiRpcTurnResult:
        _validate_message(message)
        if cancel_event is not None and not callable(getattr(cancel_event, "is_set", None)):
            raise TypeError("Pi turn cancel_event must expose is_set()")
        if cancel_event is not None and cancel_event.is_set():
            return _terminal_result(
                "interrupted", "CANCELLED_BEFORE_START", _new_turn_state(), None
            )
        if self._config.provider is None or self._config.model is None:
            raise PiRpcError("Pi turn model selection is unavailable")

        prepared = PiRpcAdapter(self._config).prepare_runtime()
        if cancel_event is not None and cancel_event.is_set():
            return _terminal_result(
                "interrupted", "CANCELLED_BEFORE_START", _new_turn_state(), None
            )
        deadline = time.monotonic() + prepared.timeout_seconds
        turn = _TurnProcess(prepared)
        state = _new_turn_state()
        interrupt_reason = ""
        abort_deadline = 0.0
        exit_code: int | None = None
        primary_error: BaseException | None = None
        try:
            prompt_send = turn.send(
                {"id": state.prompt_id, "type": "prompt", "message": message},
                deadline=deadline,
                cancel_event=cancel_event,
            )
            if prompt_send == "cancelled":
                interrupt_reason = "CANCELLED"
            elif prompt_send == "timeout":
                interrupt_reason = "TIMEOUT"
            elif prompt_send == "failed":
                raise PiRpcError("Pi turn input was rejected")
            else:
                state.prompt_requested = True
            while True:
                if interrupt_reason and not state.prompt_requested:
                    break
                now = time.monotonic()
                if (
                    not interrupt_reason
                    and cancel_event is not None
                    and cancel_event.is_set()
                ):
                    interrupt_reason = "CANCELLED"
                    abort_deadline = now + _ABORT_GRACE_SECONDS
                    abort_send = turn.send(
                        {"id": state.abort_id, "type": "abort"},
                        deadline=abort_deadline,
                    )
                    if abort_send == "sent":
                        state.abort_requested = True
                    else:
                        break
                elif not interrupt_reason and now >= deadline:
                    interrupt_reason = "TIMEOUT"
                    abort_deadline = now + _ABORT_GRACE_SECONDS
                    abort_send = turn.send(
                        {"id": state.abort_id, "type": "abort"},
                        deadline=abort_deadline,
                    )
                    if abort_send == "sent":
                        state.abort_requested = True
                    else:
                        break

                active_deadline = abort_deadline if interrupt_reason else deadline
                if now >= active_deadline:
                    break
                kind, raw = turn.read(min(0.05, active_deadline - now))
                if kind == "idle":
                    continue
                if kind == "error":
                    raise PiRpcError("Pi turn output framing failed")
                if kind == "eof":
                    if interrupt_reason or state.prompt_rejected:
                        break
                    if not state.settled:
                        raise PiRpcError("Pi turn ended before settling")
                    break
                assert raw is not None
                state.consume(raw)
                if state.prompt_rejected:
                    break
                if state.settled and state.prompt_accepted:
                    if not interrupt_reason or state.abort_acknowledged:
                        break
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            try:
                exit_code = turn.close()
            except BaseException:
                if primary_error is None:
                    raise
                setattr(primary_error, "cleanup_failed", True)

        if interrupt_reason:
            return _terminal_result(
                "interrupted", interrupt_reason, state, exit_code
            )
        if state.prompt_rejected:
            return _terminal_result("failed", "PROMPT_REJECTED", state, exit_code)
        if not state.prompt_accepted or not state.settled or not state.stop_reason:
            raise PiRpcError("Pi turn terminal evidence is incomplete")
        if state.stop_reason == "stop":
            if exit_code != 0:
                raise PiRpcError("Pi turn process did not exit cleanly")
            return _terminal_result("completed", "STOP", state, exit_code)
        if state.stop_reason == "aborted":
            return _terminal_result("interrupted", "ABORTED", state, exit_code)
        return _terminal_result(
            "failed", f"PI_STOP_{state.stop_reason.upper()}", state, exit_code
        )


def _new_turn_state() -> _TurnState:
    token = secrets.token_hex(12)
    return _TurnState(
        prompt_id=f"{_PROMPT_ID_PREFIX}{token}",
        abort_id=f"{_ABORT_ID_PREFIX}{token}",
    )


def _terminal_result(
    status: str,
    reason: str,
    state: _TurnState,
    exit_code: int | None,
) -> PiRpcTurnResult:
    return PiRpcTurnResult(
        execution_status=status,
        reason=reason,
        prompt_accepted=state.prompt_accepted,
        abort_acknowledged=state.abort_acknowledged,
        event_count=len(state.evidence),
        event_evidence=tuple(state.evidence),
        process_exit_code=exit_code,
    )


def _validate_message(message: object) -> None:
    if not isinstance(message, str) or not message.strip() or "\x00" in message:
        raise ValueError("Pi turn message must be non-empty text")
    encoded_length = _utf8_length(message)
    if encoded_length is None:
        raise ValueError("Pi turn message must be valid UTF-8 text")
    if encoded_length > _MAX_MESSAGE_BYTES:
        raise ValueError("Pi turn message exceeds the byte limit")


def _utf8_length(value: str) -> int | None:
    try:
        return len(value.encode("utf-8", errors="strict"))
    except UnicodeEncodeError:
        return None


def _decode_record(raw: bytes) -> dict[str, object] | None:
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(text)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _canonical_record(message: dict[str, object]) -> bytes | None:
    try:
        return json.dumps(
            message,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return None


def _encode_command(message: dict[str, object]) -> bytes | None:
    try:
        return json.dumps(
            message,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict") + b"\n"
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return None


def _write_payload(stream: BinaryIO, payload: bytes, state: _WriterState) -> None:
    try:
        if stream.write(payload) != len(payload):
            state.error = True
            return
        stream.flush()
    except (BrokenPipeError, OSError, ValueError):
        state.error = True
    finally:
        state.done.set()


def _read_records(
    stream: BinaryIO,
    records: queue.Queue[tuple[str, bytes | None]],
    state: _ReaderState,
) -> None:
    try:
        while True:
            raw = stream.readline(_MAX_RECORD_BYTES + 1)
            if not raw:
                _put_record(records, ("eof", None), state)
                return
            if len(raw) > _MAX_RECORD_BYTES or not raw.endswith(b"\n"):
                state.error = "framing"
                _put_record(records, ("error", None), state)
                return
            payload = raw[:-1]
            # Python text writers normalize LF to CRLF on Windows.  Pi's
            # protocol is still one JSON value per line, so tolerate exactly
            # that transport terminator while keeping all other framing strict.
            if payload.endswith(b"\r"):
                payload = payload[:-1]
            if not payload:
                state.error = "framing"
                _put_record(records, ("error", None), state)
                return
            state.record_count += 1
            state.record_bytes += len(payload)
            if (
                state.record_count > _MAX_RECORDS
                or state.record_bytes > _MAX_TOTAL_RECORD_BYTES
            ):
                state.error = "limit"
                _put_record(records, ("error", None), state)
                return
            if not _put_record(records, ("record", payload), state):
                return
    except OSError:
        state.error = "read"
        _put_record(records, ("error", None), state)


def _put_record(
    records: queue.Queue[tuple[str, bytes | None]],
    item: tuple[str, bytes | None],
    state: _ReaderState,
) -> bool:
    try:
        records.put_nowait(item)
    except queue.Full:
        state.overflow = True
        return False
    return True


def _drain_stderr(stream: BinaryIO, state: _ReaderState) -> None:
    try:
        while True:
            chunk = stream.read(16_384)
            if not chunk:
                return
            remaining = max(0, _MAX_STDERR_BYTES - len(state.data))
            if remaining:
                state.data.extend(chunk[:remaining])
            if len(chunk) > remaining:
                state.overflow = True
    except OSError:
        state.error = "read"


def _process_group_exists(pid: int) -> bool:
    if os.name == "nt":
        return False
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
