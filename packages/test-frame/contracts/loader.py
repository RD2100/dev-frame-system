# -*- coding: utf-8 -*-
"""Tool Contract v1 YAML loader."""

import os
import yaml
from pathlib import Path
from contracts.tool_contract import (
    ToolContract,
    CliExecution,
    ApiLifecycle,
    ApiLifecycleStep,
    NormalizationConfig,
    QualitySignalDecl,
    ArtifactDecl,
)


def load_contract(path: str | Path) -> ToolContract:
    """Load a Tool Contract from a YAML file.

    Args:
        path: Path to a YAML file with schema_version: test-frame.tool-contract.v1

    Returns:
        A ToolContract instance.

    Raises:
        ValueError: If schema_version is missing or unrecognized.
        FileNotFoundError: If the file does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Tool contract not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    sv = data.get("schema_version", "")
    if sv != "test-frame.tool-contract.v1":
        raise ValueError(
            f"Unsupported schema_version: {sv!r}. "
            "Expected test-frame.tool-contract.v1"
        )

    return _parse_contract(data)


def load_contracts_dir(directory: str | Path) -> dict[str, ToolContract]:
    """Load all Tool Contracts from a directory.

    Returns a dict mapping tool name to ToolContract.
    Only files with schema_version: test-frame.tool-contract.v1 are loaded.
    """
    contracts = {}
    for f in Path(directory).glob("*.yaml"):
        try:
            tc = load_contract(f)
            contracts[tc.tool] = tc
        except (ValueError, FileNotFoundError):
            continue  # Skip non-contract YAML files
    return contracts


def _parse_contract(data: dict) -> ToolContract:
    """Parse raw YAML dict into ToolContract."""

    # Parse execution
    execution = None
    exec_data = data.get("execution")
    if exec_data:
        cmd = exec_data.get("command", {})
        execution = CliExecution(
            executable=cmd.get("executable", ""),
            args=cmd.get("args", []),
            cwd=exec_data.get("cwd", "."),
            capture_stdout=exec_data.get("stdout", {}).get("capture", True),
            capture_stderr=exec_data.get("stderr", {}).get("capture", True),
            save_stdout=exec_data.get("stdout", {}).get("save_as"),
            save_stderr=exec_data.get("stderr", {}).get("save_as"),
            exit_code_nonzero_when_report_parseable=(
                exec_data.get("exit_code", {}).get("treat_nonzero_as", {}).get("when_report_parseable", "failed")
            ),
            exit_code_nonzero_when_report_missing=(
                exec_data.get("exit_code", {}).get("treat_nonzero_as", {}).get("when_report_missing", "error")
            ),
        )

    # Parse lifecycle
    lifecycle = None
    life_data = data.get("lifecycle")
    if life_data:
        steps = {}
        for step_name in ("submit", "poll", "download", "parse"):
            step_data = life_data.get(step_name)
            if step_data:
                steps[step_name] = ApiLifecycleStep(
                    method=step_data.get("method", "GET"),
                    url=step_data.get("url", ""),
                    headers=step_data.get("headers", {}),
                    body=step_data.get("body"),
                    interval_seconds=step_data.get("interval_seconds", 30),
                    max_attempts=step_data.get("max_attempts", 240),
                    save_as=step_data.get("save_as"),
                    job_id_path=step_data.get("response", {}).get("job_id_path") if step_name == "submit" else step_data.get("job_id_path"),
                    status_path=step_data.get("status_path"),
                    terminal_statuses=step_data.get("terminal_statuses", {}),
                    error_message_path=step_data.get("error_message_path"),
                    accepted_status_codes=step_data.get("response", {}).get("accepted_status_codes", [200]) if step_name in ("submit", "download") else step_data.get("accepted_status_codes", [200]),
                )
        lifecycle = ApiLifecycle(**steps)

    # Parse normalization
    norm_data = data.get("normalization", {})
    normalization = NormalizationConfig(
        result_source=norm_data.get("result_source", "stdout"),
        format=norm_data.get("format", "wrapper_dict"),
        normalizer=norm_data.get("normalizer", "wrapper_dict_v1"),
        suite_name=norm_data.get("suite_name", data.get("tool", "")),
        suite_type=norm_data.get("suite_type", "unknown"),
    )

    # Parse quality signals
    quality_signals = []
    for sig in data.get("quality_signals", []):
        quality_signals.append(QualitySignalDecl(
            name=sig.get("name", ""),
            type=sig.get("type", "count"),
            source=sig.get("source", ""),
            unit=sig.get("unit", ""),
        ))

    # Parse artifacts
    artifacts = []
    for art in data.get("artifacts", []):
        artifacts.append(ArtifactDecl(
            type=art.get("type", "other"),
            path=art.get("path", ""),
            required=art.get("required", False),
        ))

    # Parse adapter
    adapter_data = data.get("adapter", {})

    return ToolContract(
        schema_version=data.get("schema_version", ""),
        tool=data.get("tool", ""),
        display_name=data.get("display_name", data.get("tool", "")),
        enabled=data.get("enabled", True),
        stages=data.get("stages", []),
        adapter_type=adapter_data.get("type", "wrapper"),
        timeout_seconds=data.get("timeout", {}).get("total_seconds", 1800),
        env=data.get("env", {}),
        auth=data.get("auth", {}),
        execution=execution,
        lifecycle=lifecycle,
        normalization=normalization,
        quality_signals=quality_signals,
        artifacts=artifacts,
        labels=data.get("labels", []),
    )
