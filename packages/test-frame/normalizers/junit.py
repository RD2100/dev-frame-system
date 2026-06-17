# -*- coding: utf-8 -*-
"""JUnit XML normalizer: standard JUnit XML report -> CanonicalTestResult."""

import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from schema.canonical import CanonicalTestResult, Summary, ToolStats
from normalizers.base import (
    _utc_now,
    _generate_result_id,
    _build_tool_info,
    _build_suite_info,
    make_error_result,
)


# ---- JUnit status mapping ----

def _map_junit_status(element: ET.Element) -> str:
    """Map JUnit testcase element to CanonicalStatus."""
    if element.find("error") is not None:
        return "error"
    if element.find("failure") is not None:
        return "failed"
    if element.find("skipped") is not None:
        return "skipped"
    return "passed"


# ---- Parse helpers ----

def _parse_junit(root: ET.Element, context: dict) -> tuple[dict, list[dict], list[dict]]:
    """Parse JUnit XML tree into counts, tests, and errors.

    Returns:
        (counts_dict, tests_list, errors_list)
    """
    counts = {
        "total": 0, "passed": 0, "failed": 0, "skipped": 0,
        "error": 0, "blocked": 0, "cancelled": 0, "duration_ms": 0,
    }
    tests: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    tool_name = context["tool_name"]
    stage = context.get("stage", "unknown")
    idx = 0

    # Handle top-level <testsuites> vs individual <testsuite>
    suites = root.findall("testsuite")
    if not suites:
        suites = [root] if root.tag == "testsuite" else []

    for suite in suites:
        suite_name = suite.get("name", "unknown")
        suite_time = float(suite.get("time", 0))
        counts["duration_ms"] += int(suite_time * 1000)

        for tc in suite.findall("testcase"):
            idx += 1
            name = tc.get("name", "unknown")
            classname = tc.get("classname", "")
            tc_time = float(tc.get("time", 0))
            status = _map_junit_status(tc)

            counts["total"] += 1
            counts[status] += 1

            # Build test case
            failure_el = tc.find("failure")
            error_el = tc.find("error")
            skipped_el = tc.find("skipped")

            message = None
            trace = None
            if failure_el is not None:
                message = failure_el.get("message") or failure_el.text
                trace = failure_el.text
            elif error_el is not None:
                message = error_el.get("message") or error_el.text
                trace = error_el.text
            elif skipped_el is not None:
                message = skipped_el.get("message", "skipped")

            tests.append({
                "test_id": f"{tool_name}-{idx:04d}",
                "name": name,
                "full_name": f"{classname}.{name}" if classname else name,
                "file": tc.get("file"),
                "line": int(tc.get("line")) if tc.get("line") else None,
                "status": status,
                "raw_status": status,
                "duration_ms": int(tc_time * 1000),
                "started_at": None,
                "ended_at": None,
                "attempt": 1,
                "retry": 0,
                "tags": [suite_name],
                "message": message[:500] if message else None,
                "trace": trace[:2000] if trace else None,
                "evidence_refs": [],
            })

            # Build errors for non-passing tests
            if status == "failed":
                errors.append({
                    "error_id": f"err-{uuid.uuid4().hex[:8]}",
                    "type": "TEST_ASSERTION_FAILED",
                    "severity": "error",
                    "message": message or "Test failed",
                    "tool": tool_name,
                    "stage": stage,
                    "test_id": name,
                    "retryable": False,
                    "raw_status": "failed",
                    "raw_ref": None,
                })
            elif status == "error":
                errors.append({
                    "error_id": f"err-{uuid.uuid4().hex[:8]}",
                    "type": "TOOL_PROCESS_ERROR",
                    "severity": "error",
                    "message": message or "Test error",
                    "tool": tool_name,
                    "stage": stage,
                    "test_id": name,
                    "retryable": True,
                    "raw_status": "error",
                    "raw_ref": None,
                })

    return counts, tests, errors


# ---- Main normalizer ----

def normalize_junit_xml(
    payload: str | bytes | Path | ET.Element,
    context: dict,
) -> CanonicalTestResult:
    """Convert a JUnit XML report to CanonicalTestResult.

    Args:
        payload: XML string, bytes, file path, or pre-parsed ElementTree Element.
        context: NormalizeContext with run_id, stage, tool_name, etc.

    Returns:
        A CanonicalTestResult with full test case details.
    """
    tool_name = context["tool_name"]
    stage = context.get("stage", "unknown")
    now = _utc_now()

    # Parse payload
    if isinstance(payload, ET.Element):
        root = payload
    elif isinstance(payload, (str, Path)):
        path = Path(payload)
        if path.exists():
            root = ET.parse(str(path)).getroot()
        else:
            # Try parsing as raw XML string
            try:
                root = ET.fromstring(str(payload))
            except ET.ParseError as e:
                return make_error_result(
                    context=context,
                    error_type="PARSE_ERROR",
                    message=f"JUnit XML parse error: {e}",
                )
    elif isinstance(payload, bytes):
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as e:
            return make_error_result(
                context=context,
                error_type="PARSE_ERROR",
                message=f"JUnit XML parse error: {e}",
            )
    else:
        return make_error_result(
            context=context,
            error_type="PARSE_ERROR",
            message=f"Unsupported payload type: {type(payload)}",
        )

    counts, tests, errors = _parse_junit(root, context)

    # Derive overall status
    if counts["error"] > 0:
        status = "error"
    elif counts["failed"] > 0:
        status = "failed"
    elif counts["passed"] > 0:
        status = "passed"
    elif counts["skipped"] > 0 and counts["total"] == counts["skipped"]:
        status = "skipped"
    else:
        status = "failed"

    executed = counts["passed"] + counts["failed"] + counts["error"]
    test_pass_rate = (counts["passed"] / executed * 100) if executed > 0 else None

    summary = Summary(
        total=counts["total"],
        passed=counts["passed"],
        failed=counts["failed"],
        skipped=counts["skipped"],
        error=counts["error"],
        blocked=0,
        cancelled=0,
        test_pass_rate=test_pass_rate,
        test_pass_rate_basis="executed_tests",
        duration_ms=counts["duration_ms"],
    )

    tool_stats = {
        tool_name: ToolStats(
            status=status,
            total=counts["total"],
            passed=counts["passed"],
            failed=counts["failed"],
            skipped=counts["skipped"],
            error=counts["error"],
            blocked=0,
            cancelled=0,
            duration_ms=counts["duration_ms"],
        )
    }

    return CanonicalTestResult(
        schema_version="test-frame.canonical.v1",
        result_id=_generate_result_id(stage, tool_name),
        run_id=context.get("run_id", "unknown"),
        stage=stage,
        tool=_build_tool_info(context),
        suite=_build_suite_info(context, status, now, now),
        status=status,
        summary=summary,
        tool_stats=tool_stats,
        tests=tests,
        signals=[],
        issues=[],
        quality={},
        errors=errors,
        evidence=[],
        environment=context.get("environment", {}),
        source={
            "type": "junit_xml",
            "path": str(payload) if isinstance(payload, (str, Path)) else None,
        },
        metadata={"normalizer": "junit_xml_v1"},
    )
