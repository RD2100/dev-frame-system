"""Fail-closed external-secret boundary for model-provider execution.

Only explicit operating-system environment references are supported. This
module never reads OpenCode configuration, project files, tracked files, or a
local credential file. Attestations retain the provider/reference provenance
needed to launch one controlled child process, but their representation and
public metadata never contain the secret value.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .model_providers import list_model_providers, resolve_model_provider


_MAX_SECRET_CHARS = 65_536
_ERROR_NAME = "provider_secret_rejected"


@dataclass(frozen=True, slots=True)
class ProviderSecretContract:
    provider_id: str
    required: bool
    source: str
    reference: str
    child_env_name: str


_CONTRACTS = {
    "opencode-api": ProviderSecretContract(
        provider_id="opencode-api",
        required=True,
        source="environment",
        reference="env:OPENCODE_API_KEY",
        child_env_name="OPENCODE_API_KEY",
    ),
    "local-ollama": ProviderSecretContract(
        provider_id="local-ollama",
        required=False,
        source="none",
        reference="",
        child_env_name="",
    ),
    "web-chatgpt-shim": ProviderSecretContract(
        provider_id="web-chatgpt-shim",
        required=False,
        source="none",
        reference="",
        child_env_name="",
    ),
}

PROVIDER_SECRET_ENV_NAMES = frozenset(
    contract.child_env_name
    for contract in _CONTRACTS.values()
    if contract.child_env_name
)


class ProviderSecretError(ValueError):
    """Structured, value-free provider-secret rejection."""

    def __init__(
        self,
        code: str,
        *,
        provider_id: str = "",
        reference: str = "",
        detail: str,
    ) -> None:
        self.code = code
        self.provider_id = provider_id
        self.reference = reference
        self.detail = detail
        super().__init__(self._render())

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": _ERROR_NAME,
            "code": self.code,
            "provider": self.provider_id or "unrecognized",
            **({"secretReference": self.reference} if self.reference else {}),
            "detail": self.detail,
            "retry": {
                "allowed": self.code == "missing_external_secret",
                "action": (
                    "configure_external_secret"
                    if self.code == "missing_external_secret"
                    else "correct_provider_secret_contract"
                ),
            },
        }

    def _render(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=True, sort_keys=True)


class ProviderSecretAttestation:
    """Ephemeral proof that a provider's external-secret contract resolved."""

    __slots__ = (
        "provider_id",
        "required",
        "source",
        "reference",
        "child_env_name",
        "__value",
    )

    def __init__(
        self,
        contract: ProviderSecretContract,
        value: str = "",
    ) -> None:
        self.provider_id = contract.provider_id
        self.required = contract.required
        self.source = contract.source
        self.reference = contract.reference
        self.child_env_name = contract.child_env_name
        self.__value = value

    def child_environment(self) -> dict[str, str]:
        if not self.required:
            return {}
        return {self.child_env_name: self.__value}

    def redaction_values(self) -> tuple[str, ...]:
        return (self.__value,) if self.__value else ()

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider_id,
            "required": self.required,
            "source": self.source,
            "reference": self.reference,
            "status": "attested",
        }

    def __repr__(self) -> str:
        return f"ProviderSecretAttestation({self.to_safe_dict()!r})"


def resolve_provider_secret(
    provider_id: object,
    *,
    environ: Mapping[str, object] | None = None,
) -> ProviderSecretAttestation:
    """Resolve and attest one provider without reading any configuration file."""

    normalized = _normalize_provider_id(provider_id)
    try:
        provider = resolve_model_provider(normalized)
    except Exception:  # noqa: BLE001 - external selection is normalized below
        known = ", ".join(item.provider_id for item in list_model_providers())
        raise ProviderSecretError(
            "unknown_provider",
            detail=f"unknown model provider; known providers: {known}",
        ) from None

    contract = _CONTRACTS.get(provider.provider_id)
    if contract is None:
        raise ProviderSecretError(
            "unknown_secret_contract",
            provider_id=provider.provider_id,
            detail="provider has no approved external-secret contract",
        )
    if contract.required != bool(provider.requires_key):
        raise ProviderSecretError(
            "invalid_secret_contract",
            provider_id=provider.provider_id,
            reference=contract.reference,
            detail="provider registry and external-secret contract disagree",
        )
    if not contract.required:
        return ProviderSecretAttestation(contract)

    source = os.environ if environ is None else environ
    if not isinstance(source, Mapping):
        raise ProviderSecretError(
            "invalid_secret_source_type",
            provider_id=provider.provider_id,
            reference=contract.reference,
            detail="external-secret source must be an environment mapping",
        )
    try:
        value = source.get(contract.child_env_name)
    except Exception:  # noqa: BLE001 - source exceptions must be opaque
        raise ProviderSecretError(
            "secret_source_initialization_failed",
            provider_id=provider.provider_id,
            reference=contract.reference,
            detail="external-secret source could not be initialized",
        ) from None
    if value is None or value == "":
        raise ProviderSecretError(
            "missing_external_secret",
            provider_id=provider.provider_id,
            reference=contract.reference,
            detail=f"required external secret is not configured: {contract.child_env_name}",
        )
    if not isinstance(value, str):
        raise ProviderSecretError(
            "invalid_secret_value_type",
            provider_id=provider.provider_id,
            reference=contract.reference,
            detail="external-secret value must be a string",
        )
    if not value.strip() or "\x00" in value or len(value) > _MAX_SECRET_CHARS:
        raise ProviderSecretError(
            "invalid_secret_value",
            provider_id=provider.provider_id,
            reference=contract.reference,
            detail="external-secret value is empty or invalid",
        )
    return ProviderSecretAttestation(contract, value)


def redact_provider_secret_text(value: object, secrets: tuple[str, ...]) -> str:
    """Return text with all attested secret values replaced by a fixed marker."""

    text = str(value)
    for secret in sorted((item for item in secrets if item), key=len, reverse=True):
        text = text.replace(secret, "<redacted:provider-secret>")
    return text


def _normalize_provider_id(provider_id: object) -> str | None:
    if provider_id is None:
        return None
    if not isinstance(provider_id, str):
        raise ProviderSecretError(
            "invalid_provider_type",
            detail="model provider must be a string when provided",
        )
    normalized = provider_id.strip()
    if not normalized:
        raise ProviderSecretError(
            "empty_provider",
            detail="model provider must not be empty",
        )
    return normalized
