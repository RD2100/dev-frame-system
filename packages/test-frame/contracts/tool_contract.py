# -*- coding: utf-8 -*-
"""Tool Contract v1 data structures.

A Tool Contract defines how a tool is executed (CLI, API, platform),
how results are normalized, and what quality signals to extract.
"""

from dataclasses import dataclass, field
from typing import Any, Literal


# ---- Adapter types ----

AdapterType = Literal["cli_json", "api_async_job", "api_platform", "api_issues", "api_crash_stats", "wrapper"]


# ---- Execution configs ----

@dataclass
class CliExecution:
    """CLI execution config (for cli_json adapters)."""
    executable: str
    args: list[str] = field(default_factory=list)
    cwd: str = "."
    capture_stdout: bool = True
    capture_stderr: bool = True
    save_stdout: str | None = None
    save_stderr: str | None = None
    exit_code_nonzero_when_report_parseable: str = "failed"
    exit_code_nonzero_when_report_missing: str = "error"


@dataclass
class ApiLifecycleStep:
    """A single step in an API lifecycle (submit, poll, download, parse)."""
    method: str = "GET"
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] | None = None
    interval_seconds: int = 30
    max_attempts: int = 240
    save_as: str | None = None
    job_id_path: str | None = None
    status_path: str | None = None
    terminal_statuses: dict[str, list[str]] = field(default_factory=dict)
    error_message_path: str | None = None
    accepted_status_codes: list[int] = field(default_factory=lambda: [200])


@dataclass
class ApiLifecycle:
    """Async API lifecycle config (for api_async_job / api_platform adapters)."""
    submit: ApiLifecycleStep = field(default_factory=ApiLifecycleStep)
    poll: ApiLifecycleStep = field(default_factory=ApiLifecycleStep)
    download: ApiLifecycleStep | None = None
    parse: ApiLifecycleStep | None = None


# ---- Normalization config ----

@dataclass
class NormalizationConfig:
    """How to normalize raw results."""
    result_source: str = "stdout"  # stdout | file | downloaded_file
    format: str = "wrapper_dict"   # wrapper_dict | playwright_json | junit_xml | ...
    normalizer: str = "wrapper_dict_v1"
    suite_name: str = ""
    suite_type: str = "unknown"


# ---- Quality signal declaration ----

@dataclass
class QualitySignalDecl:
    """Declares a quality signal to extract from results."""
    name: str
    type: str  # count | rate | duration | boolean | score
    source: str = ""
    unit: str = ""


# ---- Artifact declaration ----

@dataclass
class ArtifactDecl:
    """Declares an artifact produced by the tool."""
    type: str
    path: str
    required: bool = False


# ---- Main Tool Contract ----

@dataclass
class ToolContract:
    """Tool Contract v1: complete execution + normalization contract for a tool."""
    schema_version: str = "test-frame.tool-contract.v1"
    tool: str = ""
    display_name: str = ""
    enabled: bool = True
    stages: list[str] = field(default_factory=list)
    adapter_type: AdapterType = "wrapper"
    timeout_seconds: int = 1800
    env: dict[str, str] = field(default_factory=dict)
    auth: dict[str, str] = field(default_factory=dict)

    # Adapter-specific
    execution: CliExecution | None = None
    lifecycle: ApiLifecycle | None = None

    # Normalization
    normalization: NormalizationConfig = field(default_factory=NormalizationConfig)

    # Quality signals to extract
    quality_signals: list[QualitySignalDecl] = field(default_factory=list)

    # Declared artifacts
    artifacts: list[ArtifactDecl] = field(default_factory=list)

    # Labels
    labels: list[str] = field(default_factory=dict)


# ---- Shortcut builders ----

def cli_contract(
    tool: str,
    executable: str,
    args: list[str],
    *,
    display_name: str = "",
    stages: list[str] | None = None,
    format: str = "wrapper_dict",
    normalizer: str = "wrapper_dict_v1",
    timeout_seconds: int = 1800,
    suite_name: str = "",
    suite_type: str = "unknown",
    **kwargs,
) -> ToolContract:
    """Create a CLI tool contract quickly."""
    return ToolContract(
        tool=tool,
        display_name=display_name or tool,
        stages=stages or ["smoke", "regression"],
        adapter_type="cli_json",
        timeout_seconds=timeout_seconds,
        execution=CliExecution(executable=executable, args=args, **kwargs),
        normalization=NormalizationConfig(
            result_source="stdout",
            format=format,
            normalizer=normalizer,
            suite_name=suite_name or tool,
            suite_type=suite_type,
        ),
    )


def api_async_contract(
    tool: str,
    *,
    display_name: str = "",
    stages: list[str] | None = None,
    adapter_type: AdapterType = "api_async_job",
    timeout_seconds: int = 7200,
    format: str = "wrapper_dict",
    normalizer: str = "wrapper_dict_v1",
    suite_name: str = "",
    suite_type: str = "unknown",
) -> ToolContract:
    """Create an async API tool contract skeleton."""
    return ToolContract(
        tool=tool,
        display_name=display_name or tool,
        stages=stages or ["regression"],
        adapter_type=adapter_type,
        timeout_seconds=timeout_seconds,
        lifecycle=ApiLifecycle(),
        normalization=NormalizationConfig(
            result_source="downloaded_file",
            format=format,
            normalizer=normalizer,
            suite_name=suite_name or tool,
            suite_type=suite_type,
        ),
    )
