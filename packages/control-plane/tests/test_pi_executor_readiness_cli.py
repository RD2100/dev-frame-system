"""Production CLI contract tests for provider-neutral executor readiness."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from control_plane import pi_executor_adapter as pi_executor
from control_plane.cli import main as devframe_cli_main
from control_plane.cli import _executor as executor_cli
from control_plane.executor_readiness import (
    ExecutorReadinessAdapter,
    ExecutorReadinessRegistry,
    ExecutorReadinessResult,
)
from control_plane.pi_executor_adapter import PiExecutorAdapterError
from control_plane.pi_rpc_adapter import (
    OFFICIAL_PI_CLI_SHA256,
    OFFICIAL_PI_INTEGRITY,
    OFFICIAL_PI_PACKAGE,
    OFFICIAL_PI_PROTOCOL,
    OFFICIAL_PI_VERSION,
    PiRpcError,
    PiRpcProbeResult,
)


def test_top_level_help_describes_provider_neutral_pi_selection(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(sys, "argv", ["devframe", "--help"])

    assert devframe_cli_main() == 0

    rendered = capsys.readouterr().out
    assert "provider-neutral executor" in rendered
    assert "--driver pi" in rendered
    assert "OpenCode-first" not in rendered


@pytest.mark.parametrize("command", ["code", "go"])
def test_coding_help_lists_registered_executor_drivers(
    command,
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(sys, "argv", ["devframe", command, "--help"])

    assert devframe_cli_main() == 0

    rendered = capsys.readouterr().out
    assert "--driver command|acp|pi" in rendered


def _ready_probe() -> PiRpcProbeResult:
    return PiRpcProbeResult(
        adapter_id="pi-rpc",
        protocol=OFFICIAL_PI_PROTOCOL,
        package=OFFICIAL_PI_PACKAGE,
        version=OFFICIAL_PI_VERSION,
        integrity=OFFICIAL_PI_INTEGRITY,
        artifact_sha256=OFFICIAL_PI_CLI_SHA256,
        state_received=True,
        is_streaming=False,
        message_count=0,
        process_exit_code=0,
    )


def test_executor_readiness_lists_registered_drivers_without_probing(
    monkeypatch,
    capsys,
):
    observed: list[str] = []

    def unexpected_probe(_project_root):
        observed.append("probe-called")
        raise AssertionError("driver discovery must not probe an executor")

    registry = ExecutorReadinessRegistry(
        (
            ExecutorReadinessAdapter(driver="zeta", _probe=unexpected_probe),
            ExecutorReadinessAdapter(driver="alpha", _probe=unexpected_probe),
        )
    )
    monkeypatch.setattr(
        executor_cli,
        "_default_readiness_registry",
        lambda: registry,
    )
    monkeypatch.setattr(
        executor_cli,
        "_resolve_local_project",
        lambda _value: pytest.fail("list must not resolve a project"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "executor",
            "readiness",
            "--list",
            "--format",
            "json",
        ],
    )

    assert devframe_cli_main() == 0
    assert observed == []
    assert json.loads(capsys.readouterr().out) == {
        "drivers": ["alpha", "zeta"],
    }


def test_executor_readiness_lists_an_empty_registry_without_fallback(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        executor_cli,
        "_default_readiness_registry",
        ExecutorReadinessRegistry,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "executor",
            "readiness",
            "--list",
            "--format",
            "json",
        ],
    )

    assert devframe_cli_main() == 0
    assert json.loads(capsys.readouterr().out) == {"drivers": []}


def test_executor_readiness_lists_registered_drivers_as_text(
    monkeypatch,
    capsys,
):
    registry = ExecutorReadinessRegistry(
        (
            ExecutorReadinessAdapter(
                driver="zeta",
                _probe=lambda _project: pytest.fail("list must not probe"),
            ),
            ExecutorReadinessAdapter(
                driver="alpha",
                _probe=lambda _project: pytest.fail("list must not probe"),
            ),
        )
    )
    monkeypatch.setattr(
        executor_cli,
        "_default_readiness_registry",
        lambda: registry,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["devframe", "executor", "readiness", "--list"],
    )

    assert devframe_cli_main() == 0
    assert capsys.readouterr().out == (
        "Executor readiness drivers\n"
        "alpha\n"
        "zeta\n"
    )


def test_executor_readiness_list_does_not_construct_pi_runtime(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        pi_executor,
        "PiRpcAdapter",
        lambda *_args, **_kwargs: pytest.fail("list must not construct Pi runtime"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "executor",
            "readiness",
            "--list",
            "--format",
            "json",
        ],
    )

    assert devframe_cli_main() == 0
    assert json.loads(capsys.readouterr().out) == {"drivers": ["pi"]}


def test_executor_readiness_help_exposes_driver_discovery(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        sys,
        "argv",
        ["devframe", "executor", "readiness", "--help"],
    )

    assert devframe_cli_main() == 0
    assert capsys.readouterr().out == (
        "Usage: devframe executor readiness (--driver pi | --list) "
        "[--project <dir>] [--format text|json]\n"
    )


@pytest.mark.parametrize(
    "selection",
    [
        [],
        ["--list", "--driver", "pi"],
    ],
)
def test_executor_readiness_requires_one_selection(
    selection,
    monkeypatch,
):
    monkeypatch.setattr(
        sys,
        "argv",
        ["devframe", "executor", "readiness", *selection],
    )

    with pytest.raises(SystemExit) as exc_info:
        devframe_cli_main()

    assert exc_info.value.code == 2


def test_executor_readiness_uses_registered_provider_neutral_probe(
    tmp_path,
    monkeypatch,
    capsys,
):
    observed: list[object] = []

    def probe(project_root):
        observed.append(project_root)
        return ExecutorReadinessResult(
            status="ready",
            details=(("adapter_id", "replaceable-test-adapter"),),
        )

    registry = ExecutorReadinessRegistry(
        (ExecutorReadinessAdapter(driver="pi", _probe=probe),)
    )
    monkeypatch.setattr(
        executor_cli,
        "_default_readiness_registry",
        lambda: registry,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "executor",
            "readiness",
            "--driver",
            "pi",
            "--project",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    assert devframe_cli_main() == 0
    assert observed == [tmp_path.resolve()]
    assert json.loads(capsys.readouterr().out) == {
        "adapter_id": "replaceable-test-adapter",
        "driver": "pi",
        "status": "ready",
    }


def test_executor_readiness_rejects_non_contract_registry_result(
    tmp_path,
    monkeypatch,
    capsys,
):
    registry = ExecutorReadinessRegistry(
        (
            ExecutorReadinessAdapter(
                driver="pi",
                _probe=lambda _project: {"status": "ready"},  # type: ignore[arg-type]
            ),
        )
    )
    monkeypatch.setattr(executor_cli, "_default_readiness_registry", lambda: registry)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "executor",
            "readiness",
            "--driver",
            "pi",
            "--project",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    assert devframe_cli_main() == 1
    assert json.loads(capsys.readouterr().out) == {
        "driver": "pi",
        "reason": "READINESS_FAILED",
        "status": "blocked",
    }


def test_executor_readiness_rejects_result_subclass_payload_override(
    tmp_path,
    monkeypatch,
    capsys,
):
    class ForgedResult(ExecutorReadinessResult):
        def payload(self, driver):
            return {
                "driver": driver,
                "status": "ready",
                "verification": "accepted",
                "version": "safe\nstatus: forged",
            }

    registry = ExecutorReadinessRegistry(
        (
            ExecutorReadinessAdapter(
                driver="pi",
                _probe=lambda _project: ForgedResult(status="ready"),
            ),
        )
    )
    monkeypatch.setattr(executor_cli, "_default_readiness_registry", lambda: registry)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "executor",
            "readiness",
            "--driver",
            "pi",
            "--project",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    assert devframe_cli_main() == 1
    rendered = capsys.readouterr().out
    assert json.loads(rendered) == {
        "driver": "pi",
        "reason": "READINESS_FAILED",
        "status": "blocked",
    }
    assert "verification" not in rendered
    assert "forged" not in rendered


def test_executor_readiness_revalidates_mutated_exact_result(
    tmp_path,
    monkeypatch,
    capsys,
):
    forged = ExecutorReadinessResult(status="ready")
    object.__setattr__(forged, "details", (("verification", "accepted"),))
    registry = ExecutorReadinessRegistry(
        (
            ExecutorReadinessAdapter(
                driver="pi",
                _probe=lambda _project: forged,
            ),
        )
    )
    monkeypatch.setattr(executor_cli, "_default_readiness_registry", lambda: registry)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "executor",
            "readiness",
            "--driver",
            "pi",
            "--project",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    assert devframe_cli_main() == 1
    rendered = capsys.readouterr().out
    assert json.loads(rendered) == {
        "driver": "pi",
        "reason": "READINESS_FAILED",
        "status": "blocked",
    }
    assert "verification" not in rendered
    assert "accepted" not in rendered


def test_readiness_registry_rejects_adapter_subclass_override():
    class ForgedAdapter(ExecutorReadinessAdapter):
        def probe(self, project_root):
            return ExecutorReadinessResult(status="ready")

    with pytest.raises(ValueError):
        ExecutorReadinessRegistry(
            (
                ForgedAdapter(
                    driver="pi",
                    _probe=lambda _project: ExecutorReadinessResult(status="ready"),
                ),
            )
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": "ready", "reason": "IMPOSSIBLE"},
        {"status": "blocked"},
        {"status": "ready", "details": (("status", "shadowed"),)},
        {"status": "ready", "details": (("version", "raw\x00value"),)},
        {"status": "ready", "details": (("version", "x" * 2049),)},
        {"status": "ready", "details": (("state_received", 1),)},
        {"status": "ready", "details": (("artifact_sha256", "not-a-digest"),)},
        {
            "status": "ready",
            "details": (("version", "first"), ("version", "second")),
        },
    ],
)
def test_readiness_result_rejects_ambiguous_or_unbounded_projection(kwargs):
    with pytest.raises(ValueError):
        ExecutorReadinessResult(**kwargs)


@pytest.mark.parametrize(
    "bad_value",
    [
        "safe\nstatus: forged",
        "safe\rstatus: forged",
        "safe\tstatus: forged",
        "safe\x1b[31mstatus: forged",
        "safe\u2028status: forged",
        "safe-\u03c0",
    ],
)
def test_executor_readiness_text_rejects_control_character_injection(
    tmp_path,
    monkeypatch,
    capsys,
    bad_value,
):
    registry = ExecutorReadinessRegistry(
        (
            ExecutorReadinessAdapter(
                driver="pi",
                _probe=lambda _project: ExecutorReadinessResult(
                    status="ready",
                    details=(("version", bad_value),),
                ),
            ),
        )
    )
    monkeypatch.setattr(executor_cli, "_default_readiness_registry", lambda: registry)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "executor",
            "readiness",
            "--driver",
            "pi",
            "--project",
            str(tmp_path),
            "--format",
            "text",
        ],
    )

    assert devframe_cli_main() == 1
    rendered = capsys.readouterr().out
    assert bad_value not in rendered
    assert rendered == (
        "Executor readiness\n"
        "driver: pi\n"
        "reason: READINESS_FAILED\n"
        "status: blocked\n"
    )


@pytest.mark.parametrize(
    "authority_key",
    [
        "verification",
        "acceptance",
        "accepted",
        "final_verdict",
        "review_status",
        "execution_status",
        "changed_files",
        "worker_status",
        "Verification",
        "Status",
        "DRIVER",
        "Reason",
    ],
)
def test_executor_readiness_rejects_non_identity_authority_keys(
    tmp_path,
    monkeypatch,
    capsys,
    authority_key,
):
    registry = ExecutorReadinessRegistry(
        (
            ExecutorReadinessAdapter(
                driver="pi",
                _probe=lambda _project: ExecutorReadinessResult(
                    status="ready",
                    details=((authority_key, "accepted"),),
                ),
            ),
        )
    )
    monkeypatch.setattr(executor_cli, "_default_readiness_registry", lambda: registry)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "executor",
            "readiness",
            "--driver",
            "pi",
            "--project",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    assert devframe_cli_main() == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "driver": "pi",
        "reason": "READINESS_FAILED",
        "status": "blocked",
    }
    assert authority_key not in payload


def test_executor_readiness_routes_real_cli_and_projects_sanitized_json(
    tmp_path,
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        pi_executor,
        "_environment_config",
        lambda invocation: SimpleNamespace(project_root=invocation.project_root),
    )
    monkeypatch.setattr(
        pi_executor,
        "PiRpcAdapter",
        lambda _config: SimpleNamespace(probe=_ready_probe),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "executor",
            "readiness",
            "--driver",
            "pi",
            "--project",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    assert devframe_cli_main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "adapter_id": "pi-rpc",
        "artifact_sha256": OFFICIAL_PI_CLI_SHA256,
        "driver": "pi",
        "integrity": OFFICIAL_PI_INTEGRITY,
        "package": OFFICIAL_PI_PACKAGE,
        "protocol": OFFICIAL_PI_PROTOCOL,
        "state_received": True,
        "status": "ready",
        "version": OFFICIAL_PI_VERSION,
    }
    rendered = json.dumps(payload, sort_keys=True)
    assert str(tmp_path) not in rendered
    assert "provider" not in rendered
    assert "model" not in rendered


@pytest.mark.parametrize(
    ("stage", "error", "reason"),
    [
        (
            "config",
            PiExecutorAdapterError("secret runtime path"),
            "RUNTIME_UNAVAILABLE",
        ),
        ("config", RuntimeError("SECRET_CONFIG_PATH"), "RUNTIME_UNAVAILABLE"),
        ("probe", PiRpcError("raw child output"), "READINESS_FAILED"),
        ("probe", OSError("SECRET_PROBE_PATH"), "READINESS_FAILED"),
    ],
)
def test_executor_readiness_fails_closed_without_exception_text(
    tmp_path,
    monkeypatch,
    capsys,
    stage,
    error,
    reason,
):
    def fail_config(_invocation):
        if stage == "config":
            raise error
        return SimpleNamespace()

    class FailingAdapter:
        def __init__(self, _config):
            pass

        def probe(self):
            raise error

    monkeypatch.setattr(pi_executor, "_environment_config", fail_config)
    monkeypatch.setattr(pi_executor, "PiRpcAdapter", FailingAdapter)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "executor",
            "readiness",
            "--driver",
            "pi",
            "--project",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    assert devframe_cli_main() == 1

    rendered = capsys.readouterr().out
    assert json.loads(rendered) == {
        "driver": "pi",
        "reason": reason,
        "status": "blocked",
    }
    assert str(error) not in rendered
    assert str(tmp_path) not in rendered


def test_executor_readiness_rejects_remote_project_before_boundary(
    monkeypatch,
    capsys,
):
    registry = ExecutorReadinessRegistry(
        (
            ExecutorReadinessAdapter(
                driver="pi",
                _probe=lambda _project: (_ for _ in ()).throw(
                    AssertionError("remote project reached boundary")
                ),
            ),
        )
    )
    monkeypatch.setattr(executor_cli, "_default_readiness_registry", lambda: registry)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "executor",
            "readiness",
            "--driver",
            "pi",
            "--project",
            r"\\example.invalid\share\project",
            "--format",
            "json",
        ],
    )

    assert devframe_cli_main() == 2
    assert json.loads(capsys.readouterr().out) == {
        "driver": "pi",
        "reason": "PROJECT_INVALID",
        "status": "blocked",
    }


def test_executor_readiness_rejects_resolution_failure_before_boundary(
    tmp_path,
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        executor_cli.Path,
        "resolve",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("loop")),
    )
    registry = ExecutorReadinessRegistry(
        (
            ExecutorReadinessAdapter(
                driver="pi",
                _probe=lambda _project: (_ for _ in ()).throw(
                    AssertionError("invalid project reached boundary")
                ),
            ),
        )
    )
    monkeypatch.setattr(executor_cli, "_default_readiness_registry", lambda: registry)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "executor",
            "readiness",
            "--driver",
            "pi",
            "--project",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    assert devframe_cli_main() == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "PROJECT_INVALID"


def test_executor_readiness_rejects_untrusted_probe_shape(
    tmp_path,
    monkeypatch,
    capsys,
):
    forged = _ready_probe()
    forged = PiRpcProbeResult(
        **{
            **forged.__dict__,
            "process_exit_code": False,
        }
    )
    monkeypatch.setattr(
        pi_executor,
        "_environment_config",
        lambda invocation: SimpleNamespace(project_root=invocation.project_root),
    )
    monkeypatch.setattr(
        pi_executor,
        "PiRpcAdapter",
        lambda _config: SimpleNamespace(probe=lambda: forged),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "devframe",
            "executor",
            "readiness",
            "--driver",
            "pi",
            "--project",
            str(tmp_path),
            "--format",
            "json",
        ],
    )

    assert devframe_cli_main() == 1
    assert json.loads(capsys.readouterr().out) == {
        "driver": "pi",
        "reason": "READINESS_FAILED",
        "status": "blocked",
    }
