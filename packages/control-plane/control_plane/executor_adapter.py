"""Thin, vendor-neutral executor seam for governed dispatch.

Adapters execute a bounded invocation and return the existing ``WorkerResult``.
They deliberately do not own TaskSpec construction, evidence ingestion, review,
gates, FinalVerdict, or acceptance state.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from .worker import WorkerResult


_OPEN_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


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
        result = self._execute(invocation)
        if not isinstance(result, WorkerResult):
            raise ExecutorAdapterError("executor adapter must return WorkerResult")
        return result


class ExecutorAdapterRegistry:
    """Ephemeral registry; the dispatch owns lifecycle and downstream authority."""

    def __init__(self, adapters: Iterable[ExecutorAdapter] = ()) -> None:
        self._adapters: dict[str, ExecutorAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: ExecutorAdapter) -> None:
        if not isinstance(adapter, ExecutorAdapter):
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
