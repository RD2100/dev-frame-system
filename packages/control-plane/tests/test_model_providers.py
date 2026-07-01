"""Hermetic tests for the model-provider registry."""
import pytest

from control_plane.model_providers import (
    DEFAULT_MODEL_PROVIDER,
    list_model_providers,
    render_model_providers_text,
    resolve_model_provider,
)


def test_registry_has_three_builtin_providers():
    ids = {p.provider_id for p in list_model_providers()}
    assert ids == {"opencode-api", "local-ollama", "web-chatgpt-shim"}


def test_default_provider_resolves_and_is_api_ready():
    provider = resolve_model_provider(None)
    assert provider.provider_id == DEFAULT_MODEL_PROVIDER == "opencode-api"
    assert provider.kind == "api"
    assert provider.requires_key is True
    assert provider.live_backend == "ready"
    assert provider.task_weight == "any"


def test_local_provider_is_free_and_keyless():
    provider = resolve_model_provider("local-ollama")
    assert provider.kind == "local"
    assert provider.requires_key is False
    assert provider.cost == "free"
    assert provider.live_backend == "ready"


def test_web_shim_carries_safety_flags():
    provider = resolve_model_provider("web-chatgpt-shim")
    assert provider.kind == "web-shim"
    assert provider.requires_key is False
    assert provider.tos_risk == "elevated"
    assert provider.live_backend == "deferred"
    assert provider.task_weight == "light"
    assert provider.degradation_notes  # must surface failure modes


def test_unknown_provider_raises():
    with pytest.raises(ValueError) as exc:
        resolve_model_provider("does-not-exist")
    assert "unknown model provider" in str(exc.value)
    assert "opencode-api" in str(exc.value)


def test_render_lists_all_providers_with_labels():
    text = render_model_providers_text(list_model_providers())
    assert "DevFrame model providers" in text
    assert "status-only" in text
    for pid in ("opencode-api", "local-ollama", "web-chatgpt-shim"):
        assert pid in text
    # web-shim degradation warnings must be visible
    assert "tos risk: elevated" in text
    assert "live backend: deferred" in text
    assert "warn    :" in text


def test_to_dict_is_json_friendly():
    provider = resolve_model_provider("web-chatgpt-shim")
    data = provider.to_dict()
    assert data["provider_id"] == "web-chatgpt-shim"
    assert isinstance(data["degradation_notes"], list)
