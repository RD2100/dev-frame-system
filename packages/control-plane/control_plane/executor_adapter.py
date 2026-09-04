"""Thin, vendor-neutral executor seam for governed dispatch.

Adapters execute a bounded invocation and return the existing ``WorkerResult``.
They deliberately do not own TaskSpec construction, evidence ingestion, review,
gates, FinalVerdict, or acceptance state.
"""
from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Callable, Iterable

from .dispatch_packet import (
    DispatchPacket,
    ExecutionReportSummary,
)
from .executor_readiness import is_local_absolute_path
from .worker import WorkerResult


_OPEN_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_MAX_PACKET_BYTES = 1_048_576
_MAX_BINDING_NODES = 32_768
_MAX_BINDING_DEPTH = 64
_PATH_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,191}\Z")
_SUMMARY_STATUSES = frozenset(
    {"blocked", "cancelled", "fail", "failed", "human_required", "passed", "unknown"}
)
_LEGACY_PACKET_FIELDS = (
    "packet_id",
    "project_id",
    "project_root",
    "requirement",
    "operation",
    "targets",
    "decision_mode",
    "dispatch_ready",
    "task_spec",
    "objective_text",
    "context_packet_path",
    "context_ledger_path",
    "packet_dir",
    "created_at",
)
_EXTENDED_PACKET_FIELDS = _LEGACY_PACKET_FIELDS + ("run_manifest",)
_OPTIONAL_GRAPH_PACKET_FIELD = "graph_context_selection"
_LEGACY_PACKET_FIELDS_WITH_OPTIONAL_GRAPH = _LEGACY_PACKET_FIELDS + (
    _OPTIONAL_GRAPH_PACKET_FIELD,
)
_EXTENDED_PACKET_FIELDS_WITH_OPTIONAL_GRAPH = _EXTENDED_PACKET_FIELDS + (
    _OPTIONAL_GRAPH_PACKET_FIELD,
)
_LEGACY_SUMMARY_FIELDS = (
    "packet_id",
    "project_id",
    "status",
    "changed_files",
    "verification",
    "report_path",
    "ingested_at",
)
_EXTENDED_SUMMARY_FIELDS = _LEGACY_SUMMARY_FIELDS + (
    "final_candidate_identity",
    "freshness",
    "failure_class",
    "blocker",
    "observed_changed_files",
    "contract_version",
)
_LEGACY_CONTRACT_MODE = "legacy-packet-v1"
_EXTENDED_CONTRACT_MODE = "extended-packet-v2"


class ExecutorAdapterError(ValueError):
    """Raised when a dispatch cannot resolve a safe executor adapter."""


@dataclass(frozen=True)
class ExecutorInvocation:
    """Existing dispatch facts passed to an adapter without new authority."""

    runtime_dir: str
    project_root: str
    go_run_id: str
    agent: Any
    timeout_seconds: int
    cwd: str | None
    env_overrides: dict[str, str] | None
    acp_command: list[str] | None
    team: Any | None


@dataclass(frozen=True)
class _InvocationBinding:
    runtime_root: Path
    project_root: Path
    packet_root: Path
    packet_value: str
    initial_packet: DispatchPacket
    contract_mode: str


ExecutorCallable = Callable[[ExecutorInvocation], WorkerResult]


@dataclass(frozen=True)
class ExecutorAdapter:
    """One executable implementation behind a stable driver name."""

    driver: str
    adapter_id: str
    protocol: str
    _execute: ExecutorCallable

    def __post_init__(self) -> None:
        _validate_identifier(self.driver, "driver")
        _validate_identifier(self.adapter_id, "adapter_id")
        _validate_identifier(self.protocol, "protocol")
        if not callable(self._execute):
            raise ExecutorAdapterError("executor adapter must define a callable executor")

    def execute(self, invocation: ExecutorInvocation) -> WorkerResult:
        if type(invocation) is not ExecutorInvocation:
            raise ExecutorAdapterError(
                "executor adapter result is not bound to the invocation"
            )
        binding = _capture_invocation_binding(invocation)
        execution_failed = False
        result: object = None
        try:
            result = self._execute(invocation)
        except Exception:
            execution_failed = True
        except BaseException:
            _restore_agent_packet_dir(invocation.agent, binding.packet_value)
            raise
        if execution_failed:
            _restore_agent_packet_dir(invocation.agent, binding.packet_value)
            raise ExecutorAdapterError("executor adapter execution failed") from None
        if not _restore_agent_packet_dir(invocation.agent, binding.packet_value):
            raise ExecutorAdapterError(
                "executor adapter result is not bound to the invocation"
            )
        if type(result) is not WorkerResult:
            raise ExecutorAdapterError("executor adapter must return WorkerResult")
        return _bind_result_to_invocation(binding, result)


def define_executor_adapter(
    *,
    driver: str,
    adapter_id: str,
    protocol: str,
    execute: ExecutorCallable,
) -> ExecutorAdapter:
    """Define one provider-neutral adapter without exposing its storage field."""
    return ExecutorAdapter(
        driver=driver,
        adapter_id=adapter_id,
        protocol=protocol,
        _execute=execute,
    )


class ExecutorAdapterRegistry:
    """Ephemeral registry; the dispatch owns lifecycle and downstream authority."""

    def __init__(self, adapters: Iterable[ExecutorAdapter] = ()) -> None:
        self._adapters: dict[str, ExecutorAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: ExecutorAdapter) -> None:
        if type(adapter) is not ExecutorAdapter:
            raise ExecutorAdapterError("executor registry accepts ExecutorAdapter entries only")
        if adapter.driver in self._adapters:
            raise ExecutorAdapterError(f"duplicate executor driver: {adapter.driver!r}")
        self._adapters[adapter.driver] = adapter

    def resolve(self, driver: str) -> ExecutorAdapter:
        _validate_identifier(driver, "driver")
        adapter = self._adapters.get(driver)
        if adapter is None:
            available = ", ".join(repr(name) for name in sorted(self._adapters))
            raise ExecutorAdapterError(
                f"unknown driver: {driver!r} (expected one of {available or 'none'})"
            )
        return adapter


def _validate_identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not _OPEN_IDENTIFIER.fullmatch(value):
        raise ExecutorAdapterError(f"{label} must be an open identifier")


def _capture_invocation_binding(invocation: ExecutorInvocation) -> _InvocationBinding:
    binding: _InvocationBinding | None = None
    try:
        contract_mode = _contract_mode()
        runtime_root = _existing_directory(invocation.runtime_dir)
        project_root = _existing_directory(invocation.project_root)
        packet_value = getattr(invocation.agent, "packet_dir")
        if not isinstance(packet_value, str) or not is_local_absolute_path(packet_value):
            raise ValueError
        packet_root = _existing_directory(packet_value)
        packet_root.relative_to(runtime_root)

        _, packet_payload = _read_bounded_json_object(packet_root / "packet.json")
        initial_packet = _canonical_packet(packet_payload, contract_mode)
        _validate_packet_layout(
            runtime_root,
            project_root,
            packet_root,
            initial_packet,
        )
        binding = _InvocationBinding(
            runtime_root=runtime_root,
            project_root=project_root,
            packet_root=packet_root,
            packet_value=packet_value,
            initial_packet=initial_packet,
            contract_mode=contract_mode,
        )
    except Exception:
        binding = None
    if binding is None:
        raise ExecutorAdapterError(
            "executor adapter result is not bound to the invocation"
        ) from None
    return binding


def _bind_result_to_invocation(
    binding: _InvocationBinding,
    result: WorkerResult,
) -> WorkerResult:
    bound_result: WorkerResult | None = None
    try:
        runtime_root = binding.runtime_root
        project_root = binding.project_root
        packet_root = binding.packet_root
        _, packet_payload = _read_bounded_json_object(packet_root / "packet.json")
        canonical_packet = _canonical_packet(packet_payload, binding.contract_mode)
        _validate_packet_layout(runtime_root, project_root, packet_root, canonical_packet)
        if not _same_dataclass_fields(
            canonical_packet,
            binding.initial_packet,
            excluded=_packet_comparison_exclusions(binding.contract_mode),
        ):
            raise ValueError

        report_path = packet_root / "ExecutionReport.md"
        canonical_report = _existing_file(str(report_path))
        if canonical_report.parent != packet_root:
            raise ValueError

        if type(result.packet) is not DispatchPacket:
            raise ValueError
        if type(result.summary) is not ExecutionReportSummary:
            raise ValueError
        _validate_packet_shape(result.packet, binding.contract_mode)
        _validate_summary_shape(result.summary, binding.contract_mode)
        if _existing_file(result.report_path) != canonical_report:
            raise ValueError
        if _existing_file(result.summary.report_path) != canonical_report:
            raise ValueError
        if _existing_directory(result.packet.packet_dir) != packet_root:
            raise ValueError
        if _existing_directory(result.packet.project_root) != project_root:
            raise ValueError

        expected_packet_id = binding.initial_packet.packet_id
        expected_project_id = binding.initial_packet.project_id
        if (
            not _PATH_COMPONENT.fullmatch(expected_packet_id)
            or not _PATH_COMPONENT.fullmatch(expected_project_id)
            or result.packet.packet_id != expected_packet_id
            or result.packet.project_id != expected_project_id
            or result.summary.packet_id != expected_packet_id
            or result.summary.project_id != expected_project_id
        ):
            raise ValueError
        if not _same_dataclass_fields(
            result.packet,
            canonical_packet,
            excluded=_packet_comparison_exclusions(binding.contract_mode),
        ):
            raise ValueError

        summary_path = (
            runtime_root
            / "rdgoal-reports"
            / expected_project_id
            / expected_packet_id
            / "execution-summary.json"
        )
        reports_root = _existing_directory(str(runtime_root / "rdgoal-reports"))
        canonical_summary_path, summary_payload = _read_bounded_json_object(summary_path)
        if (
            canonical_summary_path.parent.parent.parent != reports_root
            or canonical_summary_path.parent.parent.name != expected_project_id
            or canonical_summary_path.parent.name != expected_packet_id
        ):
            raise ValueError
        canonical_summary = _canonical_summary(summary_payload, binding.contract_mode)
        if not _same_dataclass_fields(result.summary, canonical_summary):
            raise ValueError
        if _existing_file(canonical_summary.report_path) != canonical_report:
            raise ValueError
        bound_result = WorkerResult(
            packet=canonical_packet,
            report_path=str(canonical_report),
            summary=canonical_summary,
        )
    except Exception:
        bound_result = None
    if bound_result is None:
        raise ExecutorAdapterError(
            "executor adapter result is not bound to the invocation"
        ) from None
    return bound_result


def _read_bounded_json_object(path: Path) -> tuple[Path, dict[str, object]]:
    resolved = _existing_file(str(path))
    with resolved.open("rb") as stream:
        before = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size <= 0
            or before.st_size > _MAX_PACKET_BYTES
        ):
            raise ValueError
        raw = stream.read(_MAX_PACKET_BYTES + 1)
        after = os.fstat(stream.fileno())
    if (
        len(raw) != before.st_size
        or before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ValueError
    payload = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_unique_json_object,
        parse_constant=_reject_json_constant,
    )
    if type(payload) is not dict:
        raise ValueError
    return resolved, payload


def _contract_field_names(model: type[object]) -> tuple[str, ...]:
    return tuple(field.name for field in fields(model))


def _contract_mode() -> str:
    fingerprint = (
        _contract_field_names(DispatchPacket),
        _contract_field_names(ExecutionReportSummary),
    )
    if fingerprint in {
        (_LEGACY_PACKET_FIELDS, _LEGACY_SUMMARY_FIELDS),
        (_LEGACY_PACKET_FIELDS_WITH_OPTIONAL_GRAPH, _LEGACY_SUMMARY_FIELDS),
    }:
        return _LEGACY_CONTRACT_MODE
    if fingerprint in {
        (_EXTENDED_PACKET_FIELDS, _EXTENDED_SUMMARY_FIELDS),
        (_EXTENDED_PACKET_FIELDS_WITH_OPTIONAL_GRAPH, _EXTENDED_SUMMARY_FIELDS),
    }:
        return _EXTENDED_CONTRACT_MODE
    raise ValueError


def _expected_packet_fields(contract_mode: str) -> tuple[str, ...]:
    if contract_mode == _LEGACY_CONTRACT_MODE:
        return _LEGACY_PACKET_FIELDS
    if contract_mode == _EXTENDED_CONTRACT_MODE:
        return _EXTENDED_PACKET_FIELDS
    raise ValueError


def _expected_summary_fields(contract_mode: str) -> tuple[str, ...]:
    if contract_mode == _LEGACY_CONTRACT_MODE:
        return _LEGACY_SUMMARY_FIELDS
    if contract_mode == _EXTENDED_CONTRACT_MODE:
        return _EXTENDED_SUMMARY_FIELDS
    raise ValueError


def _packet_comparison_exclusions(contract_mode: str) -> frozenset[str]:
    if contract_mode == _LEGACY_CONTRACT_MODE:
        return frozenset()
    if contract_mode == _EXTENDED_CONTRACT_MODE:
        return frozenset({"run_manifest"})
    raise ValueError


def _canonical_packet(
    payload: dict[str, object],
    contract_mode: str,
) -> DispatchPacket:
    expected_fields = set(_expected_packet_fields(contract_mode))
    payload_fields = set(payload)
    if payload_fields != expected_fields and payload_fields != {
        *expected_fields,
        _OPTIONAL_GRAPH_PACKET_FIELD,
    }:
        raise ValueError
    if _OPTIONAL_GRAPH_PACKET_FIELD not in payload:
        payload = {**payload, _OPTIONAL_GRAPH_PACKET_FIELD: None}
    _validate_authoritative_packet(payload, contract_mode)
    packet = DispatchPacket(**payload)
    _validate_packet_shape(packet, contract_mode)
    return packet


def _validate_authoritative_packet(
    payload: dict[str, object],
    contract_mode: str,
) -> None:
    if contract_mode == _LEGACY_CONTRACT_MODE:
        return
    if contract_mode != _EXTENDED_CONTRACT_MODE:
        raise ValueError
    validator = None
    try:
        from .dispatch_packet import _validate_dispatch_packet_payload as validator
    except ImportError:
        validator = None
    if not callable(validator):
        raise ValueError from None
    validator(payload)


def _canonical_summary(
    payload: dict[str, object],
    contract_mode: str,
) -> ExecutionReportSummary:
    if set(payload) != set(_expected_summary_fields(contract_mode)):
        raise ValueError
    summary = ExecutionReportSummary(**payload)
    _validate_summary_shape(summary, contract_mode)
    return summary


def _validate_packet_shape(packet: DispatchPacket, contract_mode: str) -> None:
    if type(packet) is not DispatchPacket:
        raise ValueError
    required_strings = (
        "packet_id",
        "project_id",
        "project_root",
        "requirement",
        "operation",
        "decision_mode",
        "objective_text",
        "packet_dir",
        "created_at",
    )
    optional_strings = ("context_packet_path", "context_ledger_path")
    if any(
        type(getattr(packet, name)) is not str or not getattr(packet, name)
        for name in required_strings
    ):
        raise ValueError
    if any(type(getattr(packet, name)) is not str for name in optional_strings):
        raise ValueError
    if (
        type(packet.targets) is not list
        or any(type(item) is not str for item in packet.targets)
        or type(packet.dispatch_ready) is not bool
        or type(packet.task_spec) is not dict
        or (
            packet.graph_context_selection is not None
            and type(packet.graph_context_selection) is not dict
        )
    ):
        raise ValueError
    expected_status = "ready" if packet.dispatch_ready else "deferred"
    if (
        type(packet.task_spec.get("task_id")) is not str
        or packet.task_spec["task_id"] != packet.packet_id
        or packet.task_spec.get("status") != expected_status
    ):
        raise ValueError
    if contract_mode == _EXTENDED_CONTRACT_MODE:
        if type(packet.run_manifest) is not dict:
            raise ValueError
    elif contract_mode != _LEGACY_CONTRACT_MODE:
        raise ValueError


def _validate_summary_shape(
    summary: ExecutionReportSummary,
    contract_mode: str,
) -> None:
    if type(summary) is not ExecutionReportSummary:
        raise ValueError
    required_strings = (
        "packet_id",
        "project_id",
        "status",
        "report_path",
        "ingested_at",
    )
    if contract_mode == _EXTENDED_CONTRACT_MODE:
        required_strings += ("contract_version",)
    elif contract_mode != _LEGACY_CONTRACT_MODE:
        raise ValueError
    optional_strings = ("verification",)
    if contract_mode == _EXTENDED_CONTRACT_MODE:
        optional_strings += ("failure_class", "blocker")
    if any(
        type(getattr(summary, name)) is not str or not getattr(summary, name)
        for name in required_strings
    ):
        raise ValueError
    if any(type(getattr(summary, name)) is not str for name in optional_strings):
        raise ValueError
    if summary.status not in _SUMMARY_STATUSES:
        raise ValueError
    list_fields = ("changed_files",)
    if contract_mode == _EXTENDED_CONTRACT_MODE:
        list_fields += ("observed_changed_files",)
    for field_name in list_fields:
        values = getattr(summary, field_name)
        if type(values) is not list or any(type(item) is not str for item in values):
            raise ValueError
    if (
        contract_mode == _EXTENDED_CONTRACT_MODE
        and summary.final_candidate_identity is not None
        and type(summary.final_candidate_identity) is not dict
    ):
        raise ValueError
    if contract_mode == _EXTENDED_CONTRACT_MODE and type(summary.freshness) is not dict:
        raise ValueError


def _validate_packet_layout(
    runtime_root: Path,
    project_root: Path,
    packet_root: Path,
    packet: DispatchPacket,
) -> None:
    if (
        not _PATH_COMPONENT.fullmatch(packet.packet_id)
        or not _PATH_COMPONENT.fullmatch(packet.project_id)
    ):
        raise ValueError
    outbox_root = _existing_directory(str(runtime_root / "rdgoal-outbox"))
    if (
        packet_root.parent.parent != outbox_root
        or packet_root.parent.name != packet.project_id
        or packet_root.name != packet.packet_id
        or _existing_directory(packet.project_root) != project_root
        or _existing_directory(packet.packet_dir) != packet_root
    ):
        raise ValueError


def _same_dataclass_fields(
    supplied: object,
    expected: object,
    *,
    excluded: frozenset[str] = frozenset(),
) -> bool:
    for field in fields(type(expected)):
        if field.name in excluded:
            continue
        supplied_value = getattr(supplied, field.name)
        expected_value = getattr(expected, field.name)
        if not _bounded_json_equal(supplied_value, expected_value):
            return False
    return True


def _bounded_json_equal(supplied: object, expected: object) -> bool:
    pending = [(supplied, expected, 0)]
    visited = 0
    while pending:
        supplied_value, expected_value, depth = pending.pop()
        visited += 1
        if visited > _MAX_BINDING_NODES or depth > _MAX_BINDING_DEPTH:
            return False
        if type(supplied_value) is not type(expected_value):
            return False
        if type(expected_value) is dict:
            if (
                len(expected_value) > _MAX_BINDING_NODES
                or len(supplied_value) != len(expected_value)
                or any(type(key) is not str for key in supplied_value)
                or set(supplied_value) != set(expected_value)
            ):
                return False
            pending.extend(
                (supplied_value[key], expected_value[key], depth + 1)
                for key in expected_value
            )
            continue
        if type(expected_value) is list:
            if (
                len(expected_value) > _MAX_BINDING_NODES
                or len(supplied_value) != len(expected_value)
            ):
                return False
            pending.extend(
                (supplied_item, expected_item, depth + 1)
                for supplied_item, expected_item in zip(supplied_value, expected_value)
            )
            continue
        if expected_value is None or type(expected_value) in {bool, float, int, str}:
            if supplied_value != expected_value:
                return False
            continue
        return False
    return True


def _restore_agent_packet_dir(agent: object, packet_value: str) -> bool:
    try:
        current = getattr(agent, "packet_dir")
    except Exception:
        return False
    if type(current) is str and current == packet_value:
        return True
    try:
        setattr(agent, "packet_dir", packet_value)
    except Exception:
        try:
            object.__setattr__(agent, "packet_dir", packet_value)
        except Exception:
            return False
    return False


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> None:
    raise ValueError


def _existing_directory(value: object) -> Path:
    if not isinstance(value, str) or not is_local_absolute_path(value):
        raise ValueError
    path = Path(value)
    _reject_path_aliases(path)
    resolved = path.resolve(strict=True)
    if not is_local_absolute_path(str(resolved)):
        raise ValueError
    _reject_path_aliases(resolved)
    if not resolved.is_dir():
        raise ValueError
    return resolved


def _existing_file(value: object) -> Path:
    if not isinstance(value, str) or not is_local_absolute_path(value):
        raise ValueError
    path = Path(value)
    _reject_path_aliases(path)
    resolved = path.resolve(strict=True)
    if not is_local_absolute_path(str(resolved)):
        raise ValueError
    _reject_path_aliases(resolved)
    details = resolved.stat()
    if (
        not resolved.is_file()
        or not stat.S_ISREG(details.st_mode)
        or details.st_nlink != 1
    ):
        raise ValueError
    return resolved


def _reject_path_aliases(path: Path) -> None:
    current = Path(path.anchor)
    parts = path.parts[1:] if path.parts and path.parts[0] == path.anchor else path.parts
    for part in parts:
        current /= part
        if _is_path_alias(current):
            raise ValueError


def _is_path_alias(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction) and is_junction():
        return True
    details = path.lstat()
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(getattr(details, "st_file_attributes", 0) & reparse_flag)
