"""Pluggable model-provider registry for DevFrame coding dispatch.

OpenCode stays the executor ("hand") in every mode; this registry only decides
which model source powers it. Providers are described by capability labels
(speed, cost, reliability, ToS risk, recommended task weight) so the user can
make an informed choice. Every provider produces the same provider-neutral
`DevFrameSession`; only the recorded provider id and labels differ.

The web-shim provider is a profile only: its live browser backend is deferred
(`live_backend = "deferred"`) and carries elevated ToS risk. This module never
performs browser automation; it just records intent and labels.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

DEFAULT_MODEL_PROVIDER = "opencode-api"

_KINDS = ("api", "local", "web-shim")
_TASK_WEIGHTS = ("light", "heavy", "any")
_LIVE_BACKENDS = ("ready", "deferred")


@dataclass(frozen=True)
class ModelProvider:
    provider_id: str
    kind: str
    display: str
    requires_key: bool
    speed: str
    cost: str
    reliability: str
    tos_risk: str
    task_weight: str
    live_backend: str
    model: str = ""
    notes: str = ""
    degradation_notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["degradation_notes"] = list(self.degradation_notes)
        return data


_REGISTRY: tuple[ModelProvider, ...] = (
    ModelProvider(
        provider_id="opencode-api",
        kind="api",
        display="OpenCode + paid model API",
        requires_key=True,
        speed="fast",
        cost="paid",
        reliability="high",
        tos_risk="none",
        task_weight="any",
        live_backend="ready",
        model="stepfun/step-3.7-flash",
        notes="Default. Reliable, metered API. Use for heavy or unattended runs.",
    ),
    ModelProvider(
        provider_id="local-ollama",
        kind="local",
        display="OpenCode + local model (Ollama)",
        requires_key=False,
        speed="varies",
        cost="free",
        reliability="medium",
        tos_risk="none",
        task_weight="any",
        live_backend="ready",
        model="",
        notes="No API key. Speed/quality depend on the local model and hardware.",
    ),
    ModelProvider(
        provider_id="web-chatgpt-shim",
        kind="web-shim",
        display="OpenCode + web AI session (no key, profile only)",
        requires_key=False,
        speed="slow",
        cost="free",
        reliability="low",
        tos_risk="elevated",
        task_weight="light",
        live_backend="deferred",
        model="",
        notes=(
            "Profile only: the live browser backend is deferred. Intended for "
            "light tasks; never use for heavy or unattended runs."
        ),
        degradation_notes=(
            "rate limit / throttling on the web session",
            "session expiry or login wall",
            "tunnel loss between the local shim and the web session",
            "free-form text tool-calling is less reliable than a real API",
        ),
    ),
)


def list_model_providers() -> list[ModelProvider]:
    return list(_REGISTRY)


def resolve_model_provider(provider_id: str | None) -> ModelProvider:
    target = (provider_id or DEFAULT_MODEL_PROVIDER).strip()
    for provider in _REGISTRY:
        if provider.provider_id == target:
            return provider
    known = ", ".join(provider.provider_id for provider in _REGISTRY)
    raise ValueError(f"unknown model provider: {target!r}. Known providers: {known}")


def render_model_providers_text(providers: list[ModelProvider]) -> str:
    lines = [
        "DevFrame model providers",
        "Token mode   : status-only; no packets are created and no workers run",
        "",
        "Providers",
    ]
    for provider in providers:
        key = "key required" if provider.requires_key else "no key"
        backend = provider.live_backend
        lines.extend([
            f"- {provider.provider_id} [{provider.kind}] {provider.display}",
            f"  task    : {provider.task_weight}",
            f"  speed   : {provider.speed}   cost: {provider.cost}   reliability: {provider.reliability}",
            f"  key     : {key}   tos risk: {provider.tos_risk}   live backend: {backend}",
            f"  use     : devframe code \"<goal>\" --model-provider {provider.provider_id} --preview",
            f"  note    : {provider.notes}",
        ])
        for degradation in provider.degradation_notes:
            lines.append(f"  warn    : {degradation}")
    return "\n".join(lines) + "\n"
