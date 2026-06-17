# -*- coding: utf-8 -*-
"""Async API lifecycle executor.

Executes Tool Contracts with adapter_type api_async_job or api_platform.
Life cycle: submit -> poll -> download -> parse -> CanonicalTestResult.
"""

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from schema.canonical import CanonicalTestResult
from contracts.tool_contract import ToolContract, ApiLifecycleStep
from contracts.validation import validate_lifecycle_url
from normalizers.base import make_error_result


def _map_terminal_status(status, terminal_statuses):
    for canonical, statuses in terminal_statuses.items():
        if status in statuses:
            if canonical == "success":
                return "passed"
            if canonical in ("passed", "failed", "skipped", "error", "blocked", "cancelled"):
                return canonical
            return "failed"
    return "error"


def _extract_json_path(data, path):
    if path == "$":
        return data
    if path.startswith("$."):
        path = path[2:]
    elif path.startswith("$"):
        path = path[1:]
    current = data
    for segment in path.replace("[", ".").replace("]", "").split("."):
        if not segment:
            continue
        if isinstance(current, dict):
            current = current.get(segment)
        elif isinstance(current, list) and segment.isdigit():
            idx = int(segment)
            current = current[idx] if idx < len(current) else None
        else:
            return None
        if current is None:
            return None
    return current


def _allowed_hosts(context):
    return set(context.get("allowed_lifecycle_hosts", []) or context.get("allowed_hosts", []))


def _validate_step_url(step, context, job_id=None):
    url = step.url.replace("${job_id}", job_id or "")
    error = validate_lifecycle_url(url, _allowed_hosts(context))
    if error:
        return None, error
    return url, None


def _validate_redirect(resp, context):
    if 300 <= getattr(resp, "status_code", 0) < 400:
        location = getattr(resp, "headers", {}).get("Location", "")
        if not location:
            return "Redirect response missing Location"
        error = validate_lifecycle_url(location, _allowed_hosts(context))
        if error:
            return f"Redirect URL rejected: {error}"
        return "Redirects are disabled for lifecycle requests"
    return None


def _resolve_download_path(save_as, context):
    if not save_as:
        return None, None
    root_value = (
        context.get("artifact_root")
        or context.get("run_output_root")
        or context.get("output_root")
    )
    if not root_value:
        return None, "artifact_root is required for lifecycle.download.save_as"

    raw = save_as.replace("${run_id}", context.get("run_id", "unknown"))
    raw = raw.replace("${job_id}", context.get("job_id", "unknown"))
    candidate = Path(raw)
    if candidate.is_absolute():
        return None, "lifecycle.download.save_as must be relative to artifact_root"
    if any(part == ".." for part in candidate.parts):
        return None, "lifecycle.download.save_as must not contain parent traversal"

    root = Path(root_value).resolve(strict=False)
    resolved = (root / candidate).resolve(strict=False)
    try:
        if os.path.commonpath([os.path.normcase(str(root)), os.path.normcase(str(resolved))]) != os.path.normcase(str(root)):
            return None, "lifecycle.download.save_as escapes artifact_root"
    except ValueError:
        return None, "lifecycle.download.save_as changes drive or UNC boundary"
    return str(resolved), None


def _execute_submit(step, session, contract, context):
    try:
        url, url_error = _validate_step_url(step, context)
        if url_error:
            return None, {"error": url_error, "type": "CONFIG_ERROR"}
        resp = session.request(
            method=step.method, url=url,
            headers=step.headers, json=step.body, timeout=30, allow_redirects=False,
        )
        redirect_error = _validate_redirect(resp, context)
        if redirect_error:
            return None, {"error": redirect_error, "type": "CONFIG_ERROR"}
        if resp.status_code not in step.accepted_status_codes:
            return None, {"error": f"Submit failed: {resp.status_code}", "type": "UPSTREAM_API_ERROR"}
        data = resp.json()
        job_id = _extract_json_path(data, step.job_id_path or "$")
        return str(job_id) if job_id else None, None
    except Exception as e:
        return None, {"error": f"Submit exception: {e}", "type": "UPSTREAM_API_ERROR"}


def _execute_poll(step, job_id, session, context):
    url, url_error = _validate_step_url(step, context, job_id)
    if url_error:
        return "error", url_error
    for _ in range(step.max_attempts):
        try:
            resp = session.request(method=step.method, url=url, headers=step.headers, timeout=30, allow_redirects=False)
            redirect_error = _validate_redirect(resp, context)
            if redirect_error:
                return "error", redirect_error
            data = resp.json()
            status = _extract_json_path(data, step.status_path or "$.status")
            if status is None:
                status = str(data)
            for canonical, statuses in step.terminal_statuses.items():
                if status in statuses:
                    return _map_terminal_status(status, step.terminal_statuses), None
            time.sleep(step.interval_seconds)
        except Exception as e:
            return "error", f"Poll exception: {e}"
    return "error", "TOOL_TIMEOUT"


def _execute_download(step, job_id, session, context):
    url, url_error = _validate_step_url(step, context, job_id)
    if url_error:
        return None, url_error
    try:
        resp = session.request(method=step.method, url=url, headers=step.headers, timeout=60, allow_redirects=False)
        redirect_error = _validate_redirect(resp, context)
        if redirect_error:
            return None, redirect_error
        if resp.status_code not in step.accepted_status_codes:
            return None, f"Download failed: {resp.status_code}"
        scoped_context = {**context, "job_id": job_id}
        save_path, path_error = _resolve_download_path(step.save_as, scoped_context)
        if path_error:
            return None, path_error
        if save_path:
            os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(resp.text)
        return save_path or resp.text, None
    except Exception as e:
        return None, f"Download exception: {e}"


def _execute_parse(result_path, context):
    from normalizers.base import normalize_result

    fmt = context.get("format", "wrapper_dict")
    norm_ctx = {
        "run_id": context.get("run_id", "unknown"),
        "stage": context.get("stage", "unknown"),
        "tool_name": context.get("tool_name", "unknown"),
        "adapter_type": "api_async_job",
    }

    payload = result_path
    source_path = None
    if isinstance(result_path, str):
        stripped = result_path.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                payload = json.loads(stripped)
            except (json.JSONDecodeError, TypeError):
                pass
        elif os.path.exists(stripped):
            source_path = stripped
            with open(stripped, "r", encoding="utf-8") as f:
                try:
                    payload = json.load(f)
                except (json.JSONDecodeError, TypeError):
                    payload = f.read()

    source = {"kind": fmt, "payload": payload, "path": source_path}
    return normalize_result(source, norm_ctx)


def execute_async_job(contract, context, *, session=None):
    if session is None:
        import requests
        session = requests

    if contract.lifecycle is None:
        return make_error_result(context=context, error_type="CONFIG_ERROR",
                                 message="No lifecycle config in contract")

    lc = contract.lifecycle

    if lc.submit is None or not lc.submit.url:
        return make_error_result(context=context, error_type="CONFIG_ERROR",
                                 message="No submit step configured")

    job_id, submit_error = _execute_submit(lc.submit, session, contract, context)
    if submit_error:
        return make_error_result(context=context,
                                 error_type=submit_error.get("type", "UPSTREAM_API_ERROR"),
                                 message=submit_error.get("error", "Submit failed"))

    if lc.poll and lc.poll.url:
        poll_status, poll_error = _execute_poll(lc.poll, job_id, session, context)
        if poll_error:
            return make_error_result(context=context,
                                     error_type=poll_error if poll_error in ("TOOL_TIMEOUT",) else "UPSTREAM_API_ERROR",
                                     message=poll_error)
        if poll_status != "passed":
            return make_error_result(context=context, error_type="UPSTREAM_API_ERROR",
                                     message=f"Job ended with status: {poll_status}",
                                     status=poll_status)

    result_path = None
    if lc.download and lc.download.url:
        result_path, dl_error = _execute_download(lc.download, job_id, session, context)
        if dl_error:
            return make_error_result(context=context, error_type="UPSTREAM_API_ERROR", message=dl_error)

    if result_path:
        parse_ctx = {**context, "format": getattr(lc.parse, "format", None) or "wrapper_dict"}
        result = _execute_parse(result_path, parse_ctx)
        result["source"]["job_id"] = job_id
        return result

    from normalizers.base import _utc_now, _generate_result_id, _build_tool_info, _build_suite_info
    now = _utc_now()
    return CanonicalTestResult(
        schema_version="test-frame.canonical.v1",
        result_id=_generate_result_id(context.get("stage", "unknown"), context.get("tool_name", "unknown")),
        run_id=context.get("run_id", "unknown"),
        stage=context.get("stage", "unknown"),
        tool=_build_tool_info(context),
        suite=_build_suite_info(context, "passed", now, now),
        status="passed",
        summary={"total": 0, "passed": 0, "failed": 0, "skipped": 0, "error": 0, "blocked": 0, "cancelled": 0},
        tool_stats={}, tests=[], signals=[], issues=[], quality={}, errors=[], evidence=[],
        environment=context.get("environment", {}),
        source={"type": "async_job", "job_id": job_id},
        metadata={"normalizer": "async_executor_v1"},
    )
