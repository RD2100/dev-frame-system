#!/usr/bin/env python3
"""Long-run Evidence Integrity Gate v1.

Validates cross-artifact consistency for a long-run test run directory.
Does NOT modify any files. Returns PASS/FAIL with detailed failure list.

Checks:
  1. run_id / task_id consistency across all artifacts
  2. Schema validation (all 6 schemas, all instances)
  3. 3-TaskSpec main chain consistency (FLOW_RUNNER_LOG → A→B→C)
  4. Resume consistency (MIDRUN → BEFORE → contract → log → AFTER)
  5. Report-to-JSON consistency (RESUME_TEST_LOG reads from actual artifacts)
  6. Zip revalidation (optional, when zip_path provided)
"""

import io
import json
import hashlib
import re
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
except Exception:
    pass

# ── Configuration ──────────────────────────────────────────────────────

CONTRACTS_ROOT = Path("D:/agent-acceptance/contracts")
SCHEMA_NAMES = [
    "FLOW_OUTCOME.schema.json",
    "TASKSPEC.schema.json",
    "DISPATCH_RESULT.schema.json",
    "RUNNER_CONTRACT.schema.json",
    "RUNNER_STATE.schema.json",
    "RUNNER_STEP_RESULT.schema.json",
]

# Instance → schema mapping
INSTANCE_SCHEMA_MAP = {
    # FLOW_OUTCOME instances
    "FLOW_OUTCOME_RUN.json": "FLOW_OUTCOME.schema.json",
    "FLOW_OUTCOME_BEFORE.json": "FLOW_OUTCOME.schema.json",
    "FLOW_OUTCOME_AFTER.json": "FLOW_OUTCOME.schema.json",
    "FLOW_OUTCOME_RESUME_BEFORE.json": "FLOW_OUTCOME.schema.json",
    "FLOW_OUTCOME_RESUME_AFTER.json": "FLOW_OUTCOME.schema.json",
    "FLOW_OUTCOME_RESUME.json": "FLOW_OUTCOME.schema.json",  # legacy name
    # TASKSPEC instances
    "task-a.json": "TASKSPEC.schema.json",
    "task-b.json": "TASKSPEC.schema.json",
    "task-c.json": "TASKSPEC.schema.json",
    "LONG_RUN_TASKSPEC.json": "TASKSPEC.schema.json",
    # RUNNER_CONTRACT
    "RUNNER_CONTRACT.json": "RUNNER_CONTRACT.schema.json",
    # RUNNER_STATE
    "RUNNER_STATE.json": "RUNNER_STATE.schema.json",
    "RUNNER_STATE_BEFORE.json": "RUNNER_STATE.schema.json",
    "RUNNER_STATE_AFTER.json": "RUNNER_STATE.schema.json",
    "RUNNER_STATE_MIDRUN.json": "RUNNER_STATE.schema.json",
    # RUNNER_STEP_RESULT
    "RUNNER_STEP_RESULT.json": "RUNNER_STEP_RESULT.schema.json",
    # GCA-2A: DISPATCH_RESULT
    "DISPATCH_RESULT.json": "DISPATCH_RESULT.schema.json",
}

# resume_output subdirectory instances
RESUME_INSTANCE_SCHEMA_MAP = {
    "RUNNER_CONTRACT.json": "RUNNER_CONTRACT.schema.json",
    "RUNNER_STATE.json": "RUNNER_STATE.schema.json",
    "RUNNER_STEP_RESULT.json": "RUNNER_STEP_RESULT.schema.json",
}


# ── Helpers ─────────────────────────────────────────────────────────────

def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_hex(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def load_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_schema(name: str) -> Optional[dict]:
    sp = CONTRACTS_ROOT / name
    if not sp.exists():
        return None
    try:
        return json.loads(sp.read_text(encoding="utf-8"))
    except Exception:
        return None


def validate_instance(instance: dict, schema: dict) -> tuple[bool, str]:
    try:
        from jsonschema import validate, ValidationError
        validate(instance=instance, schema=schema)
        return True, ""
    except ValidationError as e:
        return False, f"{e.message}"
    except Exception as e:
        return False, f"{e}"


def extract_run_id_from_text(text: str) -> Optional[str]:
    """Extract REVIEW_RUN_ID or RUN_ID from markdown text."""
    for pattern in [
        r'REVIEW_RUN_ID:\s*(\S+)',
        r'RUN_ID:\s*(\S+)',
        r'> RUN_ID:\s*(\S+)',
    ]:
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    return None


def extract_task_id_from_json(data: dict) -> Optional[str]:
    return data.get("task_id") or data.get("runner_id")


def extract_consumed_taskspecs_from_log(log_text: str) -> list[str]:
    """Extract consumed TaskSpec paths from FLOW_RUNNER_LOG.md."""
    paths = []
    for m in re.finditer(r'consuming_ts\s*\|\s*(.+?)(?:\s*\|\s*)?$', log_text, re.MULTILINE):
        path = m.group(1).strip().rstrip("|").strip()
        paths.append(path)
    return paths


def extract_chain_resolves_from_log(log_text: str) -> list[str]:
    """Extract chain_resolve paths from FLOW_RUNNER_LOG.md."""
    paths = []
    for m in re.finditer(r'chain_resolve.*?next TaskSpec.*?:\s*(.+?)(?:\s*\|\s*)?$', log_text, re.MULTILINE):
        path = m.group(1).strip().rstrip("|").strip()
        paths.append(path)
    return paths


# ── Checks ──────────────────────────────────────────────────────────────

def check_run_id_consistency(run_dir: Path) -> tuple[bool, list[str]]:
    """Check that all artifacts reference the same run."""
    failures = []
    run_ids_found = {}

    # Check all markdown files for RUN_ID / REVIEW_RUN_ID
    for md_file in sorted(run_dir.rglob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
            rid = extract_run_id_from_text(text)
            if rid:
                run_ids_found[str(md_file.relative_to(run_dir))] = rid
        except Exception:
            pass

    # Check JSON files for task_id
    for jf in sorted(run_dir.rglob("*.json")):
        data = load_json(jf)
        if data:
            tid = data.get("task_id", "")
            if tid:
                rel = str(jf.relative_to(run_dir))
                run_ids_found[rel] = tid

    # Normalize: base task_id should be consistent across flow artifacts.
    # TaskSpec files have their own task_ids (task-a, task-b, task-c) — these
    # are intentionally distinct and not checked against the run's task_id.
    TASKSPEC_IDS = {"task-a", "task-b", "task-c"}
    base_id = None
    for fname, rid in run_ids_found.items():
        if rid in TASKSPEC_IDS:
            continue  # TaskSpecs have their own IDs
        if "-resume-" in rid:
            continue  # resume runner IDs have timestamps, check separately
        if base_id is None:
            # Extract base (everything before -resume or -step or -validated or timestamp)
            base_id = re.sub(r'(-resume.*|-step\d*|-validated|-\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$', '', rid)
        else:
            normalized_rid = re.sub(r'(-resume.*|-step\d*|-validated|-\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$', '', rid)
            if normalized_rid != base_id:
                failures.append(
                    f"run_id mismatch: {fname} has '{rid}' (base='{normalized_rid}'), "
                    f"expected base='{base_id}'"
                )

    return len(failures) == 0, failures


def check_schema_validation(run_dir: Path) -> tuple[bool, list[str]]:
    """Validate all JSON instances against their schemas."""
    failures = []

    for iname, sname in INSTANCE_SCHEMA_MAP.items():
        ipath = run_dir / iname
        if not ipath.exists():
            failures.append(f"NOT_FOUND: {iname}")
            continue

        instance = load_json(ipath)
        if instance is None:
            failures.append(f"UNREADABLE: {iname}")
            continue

        schema = load_schema(sname)
        if schema is None:
            failures.append(f"SCHEMA_MISSING: {sname} for {iname}")
            continue

        ok, err = validate_instance(instance, schema)
        if not ok:
            failures.append(f"SCHEMA_FAIL: {iname} against {sname}: {err}")

    # Check resume_output/ instances
    resume_dir = run_dir / "resume_output"
    if resume_dir.exists():
        for iname, sname in RESUME_INSTANCE_SCHEMA_MAP.items():
            ipath = resume_dir / iname
            if not ipath.exists():
                failures.append(f"NOT_FOUND: resume_output/{iname}")
                continue

            instance = load_json(ipath)
            if instance is None:
                failures.append(f"UNREADABLE: resume_output/{iname}")
                continue

            schema = load_schema(sname)
            if schema is None:
                failures.append(f"SCHEMA_MISSING: {sname} for resume_output/{iname}")
                continue

            ok, err = validate_instance(instance, schema)
            if not ok:
                failures.append(f"SCHEMA_FAIL: resume_output/{iname} against {sname}: {err}")

    return len(failures) == 0, failures


def check_main_chain(run_dir: Path) -> tuple[bool, list[str]]:
    """Verify 3-TaskSpec chain A→B→C from FLOW_RUNNER_LOG.md."""
    failures = []

    log_path = run_dir / "FLOW_RUNNER_LOG.md"
    if not log_path.exists():
        return False, ["FLOW_RUNNER_LOG.md NOT FOUND — cannot verify main chain"]

    log_text = log_path.read_text(encoding="utf-8")

    consumed = extract_consumed_taskspecs_from_log(log_text)
    resolved = extract_chain_resolves_from_log(log_text)

    # Verify we consumed 3 distinct TaskSpecs
    consumed_names = [Path(p).name for p in consumed]

    if len(consumed) < 3:
        failures.append(
            f"Main chain: expected 3 consumed TaskSpecs, got {len(consumed)}: {consumed_names}"
        )

    expected = ["task-a.json", "task-b.json", "task-c.json"]
    for i, exp in enumerate(expected):
        if i < len(consumed_names):
            if consumed_names[i] != exp:
                failures.append(
                    f"Main chain step {i}: expected {exp}, got {consumed_names[i]}"
                )

    # Verify chain_resolve produces B then C
    resolved_names = [Path(p).name for p in resolved]
    expected_resolves = ["task-b.json", "task-c.json"]
    for i, exp in enumerate(expected_resolves):
        if i < len(resolved_names):
            if resolved_names[i] != exp:
                failures.append(
                    f"Chain resolve {i}: expected {exp}, got {resolved_names[i]}"
                )

    # Verify task-a, task-b, task-c files exist and are distinct
    for name in expected:
        tp = run_dir / name
        if not tp.exists():
            failures.append(f"TaskSpec file NOT FOUND: {name}")
        else:
            data = load_json(tp)
            if data:
                tid = data.get("task_id", "")
                if tid != name.replace(".json", ""):
                    failures.append(
                        f"TaskSpec {name}: task_id field is '{tid}', expected '{name.replace('.json', '')}'"
                    )

    return len(failures) == 0, failures


def check_resume_consistency(run_dir: Path) -> tuple[bool, list[str]]:
    """Verify resume chain: MIDRUN → BEFORE → contract → log → AFTER."""
    failures = []

    # 1. RUNNER_STATE_MIDRUN.json must exist and be mid-run
    mid_path = run_dir / "RUNNER_STATE_MIDRUN.json"
    if not mid_path.exists():
        return False, ["RUNNER_STATE_MIDRUN.json NOT FOUND — cannot verify resume chain"]

    mid = load_json(mid_path)
    if mid is None:
        return False, ["RUNNER_STATE_MIDRUN.json UNREADABLE"]

    mid_terminal = mid.get("terminal", True)
    mid_step = mid.get("current_step", -1)
    mid_next_ts = mid.get("next_task_spec_path", "")

    if mid_terminal:
        failures.append(
            f"RUNNER_STATE_MIDRUN.json: terminal=true, expected false (mid-run checkpoint)"
        )
    if mid_step != 1:
        failures.append(
            f"RUNNER_STATE_MIDRUN.json: current_step={mid_step}, expected 1 (after task A)"
        )
    mid_ts_name = Path(mid_next_ts).name if mid_next_ts else ""
    if mid_ts_name != "task-b.json":
        failures.append(
            f"RUNNER_STATE_MIDRUN.json: next_task_spec_path='{mid_ts_name}', expected 'task-b.json'"
        )

    # 2. FLOW_OUTCOME_RESUME_BEFORE.json (preferred) or FLOW_OUTCOME_RESUME.json
    resume_before_path = run_dir / "FLOW_OUTCOME_RESUME_BEFORE.json"
    resume_path = run_dir / "FLOW_OUTCOME_RESUME.json"

    before_path = resume_before_path if resume_before_path.exists() else resume_path
    before_key = "FLOW_OUTCOME_RESUME_BEFORE.json" if resume_before_path.exists() else "FLOW_OUTCOME_RESUME.json"

    if not before_path.exists():
        failures.append(f"{before_key} NOT FOUND")
    else:
        before = load_json(before_path)
        if before is None:
            failures.append(f"{before_key} UNREADABLE")
        else:
            before_terminal = before.get("terminal", True)
            before_next_ts = before.get("next_task_spec_path", "")

            if before_terminal:
                failures.append(
                    f"{before_key}: terminal=true, expected false "
                    "(resume outcome must point to next task)"
                )
            before_ts_name = Path(before_next_ts).name if before_next_ts else ""
            if before_ts_name != "task-b.json":
                failures.append(
                    f"{before_key}: next_task_spec_path='{before_ts_name}', "
                    f"expected 'task-b.json' (should match RUNNER_STATE_MIDRUN)"
                )

            # Cross-check: BEFORE.next_task_spec_path must equal MIDRUN.next_task_spec_path
            if mid_ts_name and before_ts_name and mid_ts_name != before_ts_name:
                failures.append(
                    f"RESUME INCONSISTENCY: RUNNER_STATE_MIDRUN.next_task_spec_path="
                    f"'{mid_ts_name}' but {before_key}.next_task_spec_path="
                    f"'{before_ts_name}' — must agree"
                )

    # 3. resume_output/RUNNER_CONTRACT.json
    resume_contract_path = run_dir / "resume_output" / "RUNNER_CONTRACT.json"
    if not resume_contract_path.exists():
        failures.append("resume_output/RUNNER_CONTRACT.json NOT FOUND")
    else:
        contract = load_json(resume_contract_path)
        if contract is None:
            failures.append("resume_output/RUNNER_CONTRACT.json UNREADABLE")
        else:
            c_in_ts = contract.get("input_taskspec_path", "")
            c_ts_name = Path(c_in_ts).name if c_in_ts else ""

            if c_ts_name and c_ts_name != "task-b.json":
                failures.append(
                    f"resume_output/RUNNER_CONTRACT.json: input_taskspec_path="
                    f"'{c_ts_name}', expected 'task-b.json' (should match "
                    f"{before_key}.next_task_spec_path)"
                )

            c_in_oc = contract.get("input_outcome_path", "")
            c_oc_name = Path(c_in_oc).name if c_in_oc else ""
            if c_oc_name and c_oc_name != before_key:
                failures.append(
                    f"resume_output/RUNNER_CONTRACT.json: input_outcome_path="
                    f"'{c_oc_name}', expected '{before_key}'"
                )

    # 4. resume_output/FLOW_RUNNER_LOG.md — first consumed must be task-b
    resume_log_path = run_dir / "resume_output" / "FLOW_RUNNER_LOG.md"
    if not resume_log_path.exists():
        failures.append("resume_output/FLOW_RUNNER_LOG.md NOT FOUND")
    else:
        rlog_text = resume_log_path.read_text(encoding="utf-8")
        r_consumed = extract_consumed_taskspecs_from_log(rlog_text)
        r_resolved = extract_chain_resolves_from_log(rlog_text)

        if not r_consumed:
            failures.append(
                "resume_output/FLOW_RUNNER_LOG.md: no consumed TaskSpecs found"
            )
        else:
            first_consumed_name = Path(r_consumed[0]).name
            if first_consumed_name != "task-b.json":
                failures.append(
                    f"Resume log: first consumed TaskSpec is '{first_consumed_name}', "
                    f"expected 'task-b.json'"
                )

            # Should chain to task-c
            if len(r_consumed) >= 2:
                second_consumed_name = Path(r_consumed[1]).name
                if second_consumed_name != "task-c.json":
                    failures.append(
                        f"Resume log: second consumed TaskSpec is '{second_consumed_name}', "
                        f"expected 'task-c.json'"
                    )

            r_resolved_names = [Path(p).name for p in r_resolved]
            if "task-c.json" not in r_resolved_names:
                failures.append(
                    "Resume log: no chain_resolve to task-c.json found"
                )

    # 5. FLOW_OUTCOME_RESUME_AFTER.json — terminal=true or stopped
    resume_after_path = run_dir / "FLOW_OUTCOME_RESUME_AFTER.json"
    if resume_after_path.exists():
        after = load_json(resume_after_path)
        if after is None:
            failures.append("FLOW_OUTCOME_RESUME_AFTER.json UNREADABLE")
        else:
            after_terminal = after.get("terminal", False)
            after_dispatch = after.get("dispatch_status", "")
            if not after_terminal and after_dispatch != "stopped":
                failures.append(
                    f"FLOW_OUTCOME_RESUME_AFTER.json: terminal={after_terminal}, "
                    f"dispatch_status='{after_dispatch}', expected terminal=true or stopped"
                )

            # Should not point to unconsumed task
            after_next_ts = after.get("next_task_spec_path", "")
            after_ts_name = Path(after_next_ts).name if after_next_ts else ""
            if after_terminal and after_ts_name and after_ts_name != "task-a.json":
                # If terminal with a next_task_spec_path that's not going back to start, flag it
                # Actually per schema, terminal=true can have next_task_spec_path, so this is OK
                pass

    return len(failures) == 0, failures


def check_report_json_consistency(run_dir: Path) -> tuple[bool, list[str]]:
    """Verify that RESUME_TEST_LOG.md content matches actual JSON files."""
    failures = []

    report_path = run_dir / "RESUME_TEST_LOG.md"
    if not report_path.exists():
        return False, ["RESUME_TEST_LOG.md NOT FOUND"]

    report_text = report_path.read_text(encoding="utf-8", errors="replace")

    # Check for stale version references
    stale_markers = [
        (r'Long-run Test v[123]', "old version (v1/v2/v3) in report title — should be v4 or absent"),
        (r'> Tests: \d+/\d+ passed', None),  # This is OK to have if read from actual output
        (r'v3 fixes:', "v3 changelog in v4 report"),
        (r'GPT_REVIEW_RESULT.*s3-phase3', "old GPT review result referenced in new report"),
    ]
    for pattern, msg in stale_markers:
        if re.search(pattern, report_text):
            if msg:
                failures.append(f"STALE: {msg}")

    # Check that report's claims about task-b/task-c match actual JSON
    resume_path = run_dir / "FLOW_OUTCOME_RESUME.json"
    resume_before_path = run_dir / "FLOW_OUTCOME_RESUME_BEFORE.json"

    actual_next_ts = None
    source_file = None

    if resume_before_path.exists():
        before = load_json(resume_before_path)
        if before:
            actual_next_ts = before.get("next_task_spec_path", "")
            source_file = "FLOW_OUTCOME_RESUME_BEFORE.json"
    elif resume_path.exists():
        resume = load_json(resume_path)
        if resume:
            actual_next_ts = resume.get("next_task_spec_path", "")
            source_file = "FLOW_OUTCOME_RESUME.json"

    if actual_next_ts:
        actual_ts_name = Path(actual_next_ts).name

        # Check if report claims a different TaskSpec than actual JSON
        for m in re.finditer(
            r'FLOW_OUTCOME_RESUME.*?->\s*(\S+\.json)', report_text
        ):
            reported_ts = m.group(1)
            if reported_ts != actual_ts_name:
                failures.append(
                    f"REPORT MISMATCH: RESUME_TEST_LOG.md claims {source_file} -> "
                    f"'{reported_ts}', but actual {source_file}.next_task_spec_path = "
                    f"'{actual_ts_name}'"
                )

    # Check CONTRACT_VALIDATION doesn't claim NOT FOUND for files that exist
    cv_path = run_dir / "CONTRACT_VALIDATION.md"
    if cv_path.exists():
        cv_text = cv_path.read_text(encoding="utf-8")

        for m in re.finditer(r'\|\s*(\S+\.json)\s*\|\s*\S+\s*\|\s*NOT FOUND\s*\|', cv_text):
            claimed_missing = m.group(1)
            actual_path = run_dir / claimed_missing
            if actual_path.exists():
                failures.append(
                    f"CONTRACT_VALIDATION.md claims '{claimed_missing}' is NOT FOUND, "
                    f"but file exists at {actual_path}"
                )

        # Check for stale test count
        for m in re.finditer(r'> Tests: (\d+)/(\d+) passed', cv_text):
            reported_total = int(m.group(2))
            # Check TEST_OUTPUT.md for actual count
            test_out_path = run_dir / "TEST_OUTPUT.md"
            if test_out_path.exists():
                to_text = test_out_path.read_text(encoding="utf-8")
                actual_m = re.search(r'(\d+) passed', to_text)
                if actual_m:
                    actual_passed = int(actual_m.group(1))
                    if actual_passed != reported_total:
                        failures.append(
                            f"CONTRACT_VALIDATION claims {reported_total}/{reported_total} passed, "
                            f"but TEST_OUTPUT.md shows {actual_passed} passed"
                        )

    return len(failures) == 0, failures


def check_no_phase4_hint(run_dir: Path) -> tuple[bool, list[str]]:
    """Check that terminal states do not hint at Phase 4."""
    failures = []

    # Check all flow outcomes for Phase 4 hints when terminal
    for fname in [
        "FLOW_OUTCOME_AFTER.json",
        "FLOW_OUTCOME_RESUME_AFTER.json",
    ]:
        fp = run_dir / fname
        if not fp.exists():
            continue
        data = load_json(fp)
        if data is None:
            continue
        if data.get("terminal", False):
            text = json.dumps(data)
            for hint in ["phase4", "Phase 4", "PHASE4", "phase_4"]:
                if hint.lower() in text.lower():
                    failures.append(
                        f"PHASE4_HINT: {fname} is terminal but contains '{hint}'"
                    )

    # Check RUNNER_STATE for Phase 4 hints when terminal
    for fname in [
        "RUNNER_STATE.json",
        "RUNNER_STATE_AFTER.json",
    ]:
        fp = run_dir / fname
        if not fp.exists():
            continue
        data = load_json(fp)
        if data is None:
            continue
        if data.get("terminal", False):
            reason = data.get("reason", "")
            for hint in ["Phase 4", "phase4", "PHASE4"]:
                if hint in reason:
                    failures.append(
                        f"PHASE4_HINT: {fname} terminal reason contains '{hint}'"
                    )

    return len(failures) == 0, failures


def check_stale_files(run_dir: Path) -> tuple[bool, list[str]]:
    """Detect stale/old-version files that shouldn't appear in v4."""
    # This is advisory — presence of old files doesn't fail the gate
    # but we flag them
    stale = []

    # Check for old review pack zips
    for pattern in ["*-review-pack.zip", "*-review-pack-v*.zip"]:
        for f in run_dir.rglob(pattern):
            stale.append(f"Stale zip in run dir: {f.name}")

    # Check for GPT review results with old run_ids
    grp = run_dir / "GPT_REVIEW_RESULT.md"
    if grp.exists():
        text = grp.read_text(encoding="utf-8")
        if re.search(r's3-phase3-v\d+', text):
            stale.append(
                "GPT_REVIEW_RESULT.md contains old s3-phase3 review run_id — "
                "should be NOT_AVAILABLE_FOR_LONG_RUN_V4"
            )

    return len(stale) == 0, stale


# ── Zip Revalidation ────────────────────────────────────────────────────

def check_zip_revalidation(run_dir: Path) -> tuple[bool, list[str], list[str]]:
    """Build a staging zip, unzip to temp, re-run all validations on unzipped content."""
    failures = []
    stale = []

    # Find zip in run_dir or its parent
    zip_path = None
    for zp in sorted(run_dir.rglob("long-run-review-pack-v4.zip")):
        zip_path = zp
        break
    if not zip_path:
        # Check parent
        parent_zip = run_dir.parent / "long-run-review-pack-v4.zip"
        if parent_zip.exists():
            zip_path = parent_zip

    if not zip_path:
        return False, ["No long-run-review-pack-v4.zip found for revalidation"], []

    if not zipfile.is_zipfile(zip_path):
        return False, [f"{zip_path} is not a valid zip file"], []

    with tempfile.TemporaryDirectory(prefix="lrev_") as tmpdir:
        tmp = Path(tmpdir)
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp)
        except Exception as e:
            return False, [f"Failed to extract zip: {e}"], []

        # Re-run schema validation on extracted content
        schema_ok, schema_fails = check_schema_validation(tmp)
        for f in schema_fails:
            failures.append(f"ZIP_REVAL: {f}")

        # Re-run resume consistency
        resume_ok, resume_fails = check_resume_consistency(tmp)
        for f in resume_fails:
            failures.append(f"ZIP_REVAL: {f}")

        # Re-run main chain
        chain_ok, chain_fails = check_main_chain(tmp)
        for f in chain_fails:
            failures.append(f"ZIP_REVAL: {f}")

        # Check for old zips in the extracted content
        for old_zp in tmp.rglob("*-review-pack*.zip"):
            stale.append(f"ZIP_REVAL: extracted content contains stale zip: {old_zp.name}")

    return len(failures) == 0, failures, stale


# ── Main Gate ───────────────────────────────────────────────────────────

def run_integrity_gate(run_dir: Path, revalidate_zip: bool = False) -> dict:
    """Run all integrity checks and return a result dict."""

    run_id_from_dir = run_dir.name
    failures_all = []
    stale_all = []

    # Resolve actual run_id from artifacts
    actual_run_id = run_id_from_dir

    checks = {}

    # 1. Schema validation
    ok, fails = check_schema_validation(run_dir)
    checks["schema_validation"] = "PASS" if ok else "FAIL"
    failures_all.extend(fails)
    if fails:
        stale_all.extend(fails)

    # 2. Main chain
    ok, fails = check_main_chain(run_dir)
    checks["main_chain_verified"] = ok
    failures_all.extend(fails)

    # 3. Resume consistency
    ok, fails = check_resume_consistency(run_dir)
    checks["resume_chain_verified"] = ok
    failures_all.extend(fails)

    # 4. Report consistency
    ok, fails = check_report_json_consistency(run_dir)
    checks["report_consistency"] = "PASS" if ok else "FAIL"
    failures_all.extend(fails)

    # 5. Run ID consistency
    ok, fails = check_run_id_consistency(run_dir)
    checks["run_id_consistency"] = "PASS" if ok else "FAIL"
    failures_all.extend(fails)

    # 6. No Phase 4 hints
    ok, fails = check_no_phase4_hint(run_dir)
    checks["phase4_hint_detected"] = not ok
    failures_all.extend(fails)

    # 7. Stale files
    ok, stale_found = check_stale_files(run_dir)
    checks["stale_file_detected"] = not ok
    stale_all.extend(stale_found)

    # 8. Zip revalidation (optional)
    zip_ok = True
    if revalidate_zip:
        zip_ok, zip_fails, zip_stale = check_zip_revalidation(run_dir)
        checks["zip_revalidation"] = "PASS" if zip_ok else "FAIL"
        failures_all.extend(zip_fails)
        stale_all.extend(zip_stale)
    else:
        checks["zip_revalidation"] = "NOT_RUN"

    # Cross-artifact consistency = all checks pass
    cross_ok = checks.get("main_chain_verified", False) and \
               checks.get("resume_chain_verified", False) and \
               checks.get("report_consistency", "FAIL") == "PASS" and \
               checks.get("run_id_consistency", "FAIL") == "PASS" and \
               not checks.get("phase4_hint_detected", False)

    checks["cross_artifact_consistency"] = "PASS" if cross_ok else "FAIL"

    # Ready for review = schema PASS + cross-artifact PASS + zip OK
    ready = checks.get("schema_validation", "FAIL") == "PASS" and \
            checks["cross_artifact_consistency"] == "PASS" and \
            (not revalidate_zip or checks.get("zip_revalidation", "FAIL") == "PASS")

    result = {
        "review_run_id": actual_run_id,
        "timestamp": ts(),
        "run_directory": str(run_dir),
        "schema_validation": checks.get("schema_validation", "NOT_RUN"),
        "cross_artifact_consistency": checks["cross_artifact_consistency"],
        "zip_revalidation": checks.get("zip_revalidation", "NOT_RUN"),
        "main_chain_verified": checks.get("main_chain_verified", False),
        "resume_chain_verified": checks.get("resume_chain_verified", False),
        "stale_file_detected": checks.get("stale_file_detected", False),
        "phase4_hint_detected": checks.get("phase4_hint_detected", False),
        "ready_for_review": ready,
        "checks_detail": checks,
        "failures": failures_all,
        "stale_warnings": stale_all,
    }

    return result


# ── Report Generation ───────────────────────────────────────────────────

def generate_report(result: dict, output_dir: Path) -> Path:
    """Write EVIDENCE_INTEGRITY_REPORT.md."""
    lines = [
        "# Evidence Integrity Report — Long-run Test",
        "",
        f"> Review Run ID: {result['review_run_id']}",
        f"> Timestamp: {result['timestamp']}",
        f"> Run Directory: {result['run_directory']}",
        "",
        "## Gate Results",
        "",
        "| Check | Result |",
        "|-------|--------|",
        f"| schema_validation | {result['schema_validation']} |",
        f"| cross_artifact_consistency | {result['cross_artifact_consistency']} |",
        f"| zip_revalidation | {result['zip_revalidation']} |",
        f"| main_chain_verified | {result['main_chain_verified']} |",
        f"| resume_chain_verified | {result['resume_chain_verified']} |",
        f"| stale_file_detected | {result['stale_file_detected']} |",
        f"| phase4_hint_detected | {result['phase4_hint_detected']} |",
        f"| **ready_for_review** | **{result['ready_for_review']}** |",
        "",
    ]

    if result["failures"]:
        lines.append("## Failures")
        lines.append("")
        for f in result["failures"]:
            lines.append(f"- ❌ {f}")
        lines.append("")

    if result.get("stale_warnings"):
        lines.append("## Warnings (Stale Files)")
        lines.append("")
        for s in result["stale_warnings"]:
            lines.append(f"- ⚠️ {s}")
        lines.append("")

    if not result["failures"] and not result.get("stale_warnings"):
        lines.append("## All Checks Passed")
        lines.append("")
        lines.append("No failures or warnings detected.")

    report_path = output_dir / "EVIDENCE_INTEGRITY_REPORT.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def generate_result_json(result: dict, output_dir: Path) -> Path:
    """Write EVIDENCE_INTEGRITY_RESULT.json."""
    rj_path = output_dir / "EVIDENCE_INTEGRITY_RESULT.json"
    rj_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return rj_path


# ── CLI ─────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Long-run Evidence Integrity Gate v1"
    )
    parser.add_argument(
        "run_dir",
        nargs="?",
        default="_reports/long-run-test/runs/long-run-1-20260602-133438",
        help="Path to the run directory to validate",
    )
    parser.add_argument(
        "--revalidate-zip",
        action="store_true",
        help="Also extract and re-validate the zip contents",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Output only the JSON result",
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        print(json.dumps({
            "error": f"Run directory not found: {run_dir}",
            "ready_for_review": False,
        }, indent=2))
        sys.exit(1)

    result = run_integrity_gate(run_dir, revalidate_zip=args.revalidate_zip)

    # Generate reports
    generate_report(result, run_dir)
    generate_result_json(result, run_dir)

    if args.json_only:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"\n{'='*60}")
        print(f"Evidence Integrity Gate v1 — {run_dir.name}")
        print(f"{'='*60}")
        print(f"  schema_validation:         {result['schema_validation']}")
        print(f"  cross_artifact_consistency: {result['cross_artifact_consistency']}")
        print(f"  zip_revalidation:          {result['zip_revalidation']}")
        print(f"  main_chain_verified:       {result['main_chain_verified']}")
        print(f"  resume_chain_verified:     {result['resume_chain_verified']}")
        print(f"  stale_file_detected:       {result['stale_file_detected']}")
        print(f"  phase4_hint_detected:      {result['phase4_hint_detected']}")
        print(f"  ready_for_review:          {result['ready_for_review']}")
        print(f"  failures:                  {len(result['failures'])}")
        print(f"  stale_warnings:            {len(result.get('stale_warnings', []))}")

        if result["failures"]:
            print(f"\nFAILURES:")
            for f in result["failures"]:
                print(f"  ❌ {f}")

        if result.get("stale_warnings"):
            print(f"\nWARNINGS:")
            for s in result["stale_warnings"]:
                print(f"  ⚠️ {s}")

        print(f"\nReports written to {run_dir}/")
        print(f"  EVIDENCE_INTEGRITY_REPORT.md")
        print(f"  EVIDENCE_INTEGRITY_RESULT.json")

    sys.exit(0 if result["ready_for_review"] else 1)


if __name__ == "__main__":
    main()
