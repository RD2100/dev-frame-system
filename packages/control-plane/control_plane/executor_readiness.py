"""Provider-neutral readiness facts for replaceable executor adapters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_REASON = re.compile(r"[A-Z][A-Z0-9_]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ALLOWED_DETAIL_KEYS = frozenset(
    {
        "adapter_id",
        "artifact_sha256",
        "integrity",
        "package",
        "protocol",
        "state_received",
        "version",
    }
)
_MAX_DETAILS = 16
_MAX_DETAIL_STRING_CHARS = 2048


class ExecutorReadinessError(ValueError):
    """Raised when a readiness adapter or its result violates the port."""


ReadinessScalar = str | bool


@dataclass(frozen=True)
class ExecutorReadinessResult:
    """Sanitized readiness projection; it never authorizes task execution."""

    status: str
    reason: str | None = None
    details: tuple[tuple[str, ReadinessScalar], ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"ready", "blocked"}:
            raise ExecutorReadinessError("readiness status is invalid")
        if self.status == "ready" and self.reason is not None:
            raise ExecutorReadinessError("ready result cannot include a reason")
        if self.status == "blocked" and (
            not isinstance(self.reason, str) or _REASON.fullmatch(self.reason) is None
        ):
            raise ExecutorReadinessError("blocked result requires a reason")
        if self.status == "blocked" and self.details:
            raise ExecutorReadinessError("blocked result cannot include details")
        if not isinstance(self.details, tuple) or len(self.details) > _MAX_DETAILS:
            raise ExecutorReadinessError("readiness details are invalid")
        seen: set[str] = set()
        for entry in self.details:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise ExecutorReadinessError("readiness detail entry is invalid")
            key, value = entry
            if (
                not isinstance(key, str)
                or _IDENTIFIER.fullmatch(key) is None
                or key not in _ALLOWED_DETAIL_KEYS
                or key in seen
            ):
                raise ExecutorReadinessError("readiness detail key is invalid")
            seen.add(key)
            if key == "state_received":
                if not isinstance(value, bool):
                    raise ExecutorReadinessError("readiness detail value is invalid")
                continue
            if not isinstance(value, str):
                raise ExecutorReadinessError("readiness detail value is invalid")
            if key == "artifact_sha256" and _SHA256.fullmatch(value) is None:
                raise ExecutorReadinessError("readiness detail value is invalid")
            if key in {"adapter_id", "protocol"} and _IDENTIFIER.fullmatch(value) is None:
                raise ExecutorReadinessError("readiness detail value is invalid")
            if (
                not value
                or value != value.strip()
                or "\x00" in value
                or not value.isascii()
                or not value.isprintable()
                or len(value) > _MAX_DETAIL_STRING_CHARS
            ):
                raise ExecutorReadinessError("readiness detail value is invalid")

    def payload(self, driver: str) -> dict[str, ReadinessScalar]:
        _validate_driver(driver)
        payload: dict[str, ReadinessScalar] = {
            "driver": driver,
            "status": self.status,
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        payload.update(self.details)
        return payload


ReadinessCallable = Callable[[Path], ExecutorReadinessResult]


@dataclass(frozen=True)
class ExecutorReadinessAdapter:
    """One bounded readiness implementation behind a stable driver name."""

    driver: str
    _probe: ReadinessCallable

    def __post_init__(self) -> None:
        _validate_driver(self.driver)
        if not callable(self._probe):
            raise ExecutorReadinessError("readiness adapter must define a callable probe")

    def probe(self, project_root: Path) -> ExecutorReadinessResult:
        if not isinstance(project_root, Path):
            raise ExecutorReadinessError("readiness project root must be a Path")
        result = self._probe(project_root)
        if type(result) is not ExecutorReadinessResult:
            raise ExecutorReadinessError("readiness adapter returned an invalid result")
        return ExecutorReadinessResult(
            status=result.status,
            reason=result.reason,
            details=result.details,
        )


class ExecutorReadinessRegistry:
    """Ephemeral readiness registry owned by the CLI composition root."""

    def __init__(self, adapters: Iterable[ExecutorReadinessAdapter] = ()) -> None:
        self._adapters: dict[str, ExecutorReadinessAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    @property
    def drivers(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))

    def register(self, adapter: ExecutorReadinessAdapter) -> None:
        if type(adapter) is not ExecutorReadinessAdapter:
            raise ExecutorReadinessError(
                "readiness registry accepts ExecutorReadinessAdapter entries only"
            )
        if adapter.driver in self._adapters:
            raise ExecutorReadinessError(
                f"duplicate readiness driver: {adapter.driver!r}"
            )
        self._adapters[adapter.driver] = adapter

    def resolve(self, driver: str) -> ExecutorReadinessAdapter:
        _validate_driver(driver)
        adapter = self._adapters.get(driver)
        if adapter is None:
            raise ExecutorReadinessError("readiness driver is unavailable")
        return adapter


def _validate_driver(value: object) -> None:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ExecutorReadinessError("readiness driver is invalid")


def is_local_absolute_path(value: str) -> bool:
    """Reject relative, UNC, device, and NUL-bearing local path candidates."""

    return bool(
        value
        and "\x00" not in value
        and not value.startswith(("\\\\", "//"))
        and Path(value).is_absolute()
    )
