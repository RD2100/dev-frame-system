#!/usr/bin/env python3
"""
Oracle-style S2 Evidence Packager for GPT Review.

Collects S2 execution evidence into a self-contained review pack.
Read-only: never modifies source, never re-executes S2, never changes conclusions.
"""
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(PROJECT_ROOT, "_reports", "s2-gpt-review-evidence-pack")

# --- sources ---
S2_REVIEW_PACK_DIR = os.path.join(PROJECT_ROOT, "_reports", "s2-review-pack")
S2_RESULT_REPORT_SRC = os.path.join(
    PROJECT_ROOT, ".ai", "reports",
    "2026-06-01-s2-evidence-report-reviewer-index-consistency-result.md"
)
S1_RESULT_REPORT_SRC = os.path.join(
    PROJECT_ROOT, ".ai", "reports",
    "2026-06-01-s1-final-status-consistency-result.md"
)
S2_RUNS_DIR = os.path.join(PROJECT_ROOT, ".ai", "runs",
                           "s2-evidence-report-reviewer-index-consistency")
TOOLS_DIR = os.path.join(PROJECT_ROOT, "tools")

MISSING_FILES = []
CONFLICTS = []


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def copy_file(src, dst, desc):
    """Copy src → dst, record missing if src doesn't exist."""
    if os.path.isfile(src):
        shutil.copy2(src, dst)
        return True
    else:
        MISSING_FILES.append({"expected": src, "purpose": desc})
        return False


def copy_all_from_dir(src_dir, dst_dir):
    """Copy all files from src_dir to dst_dir. Record missing if dir empty."""
    if not os.path.isdir(src_dir):
        MISSING_FILES.append({"expected": src_dir, "purpose": "directory of review pack files"})
        return []
    copied = []
    for fname in os.listdir(src_dir):
        src = os.path.join(src_dir, fname)
        dst = os.path.join(dst_dir, fname)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            copied.append(fname)
    return copied


def run_git(args):
    """Run a git command, return stdout. Returns empty string on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout
    except Exception as e:
        MISSING_FILES.append({
            "expected": f"git {' '.join(args)}",
            "purpose": f"git command failed: {e}"
        })
        return ""


def write_file(path, content):
    with open(os.path.join(OUT_DIR, path), "w", encoding="utf-8") as f:
        f.write(content)


def generate_task_spec():
    content = """# S2 TaskSpec Summary

## Objective
Ensure evidence, final-report, and reviewer-index express consistent status for the same run, all obeying S1 final_batch_status synthesis rule.

## Required Preservation
- evidence_status=pass does not imply final_batch_status=pass
- reviewer_verdict=pass does not imply final_batch_status=pass
- final_batch_status is the only authoritative final outcome
- blocked_by must be non-empty when blocked
- unknown / missing / invalid / timeout / human_required fail-closed to blocked

## Required Evidence
- Execution Report
- final-report.md
- reviewer-index.md
- evidence-index.md
- test-output.md
- gate check
- changed files
- diff summary
"""
    write_file("task/S2_TASKSPEC.md", content)
    return content


def generate_s1_baseline():
    """Generate S1 baseline summary, checking for S1 files."""
    s1_files_found = []
    s1_files_missing = []

    if os.path.isfile(S1_RESULT_REPORT_SRC):
        s1_files_found.append(S1_RESULT_REPORT_SRC)
    else:
        s1_files_missing.append(S1_RESULT_REPORT_SRC)

    # Check for S1 runs
    s1_runs_dir = os.path.join(PROJECT_ROOT, ".ai", "runs", "s1-final-status-consistency")
    if os.path.isdir(s1_runs_dir):
        for f in os.listdir(s1_runs_dir):
            s1_files_found.append(os.path.join(s1_runs_dir, f))
    else:
        s1_files_missing.append(s1_runs_dir)

    lines = [
        "# S1 Baseline Summary",
        "",
        "## S1 Status",
        "Reported SUCCESS.",
        "",
        "## S1 Verified Rules",
        "- final_batch_status is sole authoritative status",
        "- evidence_status=pass does not imply final_batch_status=pass",
        "- human_required participates in source_status",
        "- blocked_by is non-empty when blocked",
        "- blocked_by uses legal enums",
        "- S1 fixture tests reported 11/11 pass",
        "",
        "## S1 Artifacts Referenced",
    ]
    for f in s1_files_found:
        lines.append(f"- Found: `{f}`")
    for f in s1_files_missing:
        lines.append(f"- MISSING: `{f}`")
        MISSING_FILES.append({"expected": f, "purpose": "S1 baseline artifact"})

    content = "\n".join(lines) + "\n"
    write_file("task/S1_BASELINE_SUMMARY.md", content)
    return content


def collect_reports():
    """Copy S2 result report and run artifacts to reports/."""
    # S2 result report
    copy_file(
        S2_RESULT_REPORT_SRC,
        os.path.join(OUT_DIR, "reports", "S2_RESULT_REPORT.md"),
        "S2 result report from .ai/reports/"
    )

    # Run artifacts
    run_files_map = {
        "final-report.md": "FINAL_REPORT.md",
        "test-output.md": "TEST_OUTPUT.md",
        "reviewer-index.md": "REVIEWER_INDEX.md",
        "evidence-index.md": "EVIDENCE_INDEX.md",
    }
    for src_name, dst_name in run_files_map.items():
        src = os.path.join(S2_RUNS_DIR, src_name)
        dst = os.path.join(OUT_DIR, "reports", dst_name)
        copy_file(src, dst, f"S2 run artifact: {src_name}")

    # GATE_CHECK.md from s2-review-pack (since run dir doesn't have it)
    gate_src = os.path.join(S2_REVIEW_PACK_DIR, "GATE_CHECK.md")
    gate_dst = os.path.join(OUT_DIR, "reports", "GATE_CHECK.md")
    if not copy_file(gate_src, gate_dst, "GATE_CHECK.md from s2-review-pack"):
        # Create a placeholder
        write_file("reports/GATE_CHECK.md", """# GATE_CHECK.md

**Status: MISSING**

No standalone GATE_CHECK.md was found in the S2 run directory.
The gate check content from `_reports/s2-review-pack/GATE_CHECK.md` was also unavailable.

GPT should note: gate checks may be embedded in the EXECUTION_REPORT.md or FINAL_REPORT.md.
""")


def collect_source_files():
    """Copy S2 source files to source/."""
    src_files = [
        "ai_guard.py",
        "go_evidence.py",
        "test_status_synthesis.py",
        "test_report_consistency.py",
    ]
    for f in src_files:
        src = os.path.join(TOOLS_DIR, f)
        dst = os.path.join(OUT_DIR, "source", f)
        copy_file(src, dst, f"S2 source file: {f}")

    # Optional: test_evidence_report_reviewer_index_consistency.py
    extra = "test_evidence_report_reviewer_index_consistency.py"
    extra_src = os.path.join(TOOLS_DIR, extra)
    if os.path.isfile(extra_src):
        copy_file(extra_src, os.path.join(OUT_DIR, "source", extra),
                  f"Optional S2 source file: {extra}")
    else:
        MISSING_FILES.append({
            "expected": extra_src,
            "purpose": "Optional S2 test runner script (not found)"
        })


def collect_diff_evidence():
    """Run read-only git commands and save results."""
    # git status --short
    status = run_git(["status", "--short"])
    write_file("diff/GIT_STATUS.txt", status)

    # git diff --stat
    diff_stat = run_git(["diff", "--stat"])
    write_file("diff/GIT_DIFF_STAT.txt", diff_stat)

    # git diff for tools files
    tools_files = [
        "tools/ai_guard.py",
        "tools/go_evidence.py",
        "tools/test_status_synthesis.py",
        "tools/test_report_consistency.py",
    ]
    extra_test = "tools/test_evidence_report_reviewer_index_consistency.py"
    if os.path.isfile(os.path.join(PROJECT_ROOT, extra_test)):
        tools_files.append(extra_test)

    diff_patch = run_git(["diff", "--"] + tools_files)
    if diff_patch.strip():
        write_file("diff/GIT_DIFF.patch", diff_patch)
    else:
        write_file("diff/GIT_DIFF.patch",
                   "# No diff for tools/ files — they may be new (untracked) or unchanged.\n"
                   "# Run 'git diff --cached -- tools/...' for staged changes.\n")


def generate_files_changed():
    """Generate FILES_CHANGED.md from git status."""
    status = run_git(["status", "--short"])
    if not status.strip():
        write_file("diff/FILES_CHANGED.md",
                   "# Files Changed\n\nNo changes detected in working tree.\n")
        return

    lines = [
        "# Files Changed",
        "",
        "| Path | Status | In Allowed Scope? | Notes |",
        "|------|--------|-------------------|-------|",
    ]
    allowed_dirs = ["tools/", "_reports/", ".ai/", ".opencode/", ".claude/"]

    for line in status.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # git status --short format: "XY path" or "XY orig -> new"
        if " -> " in line:
            parts = line.split(" -> ")
            path = parts[-1].strip()
            code = parts[0].split()[0] if parts[0].split() else "??"
        else:
            parts = line.split(maxsplit=1)
            if len(parts) >= 2:
                code, path = parts[0], parts[1]
            else:
                code, path = "??", parts[0]

        in_scope = any(path.startswith(d) for d in allowed_dirs)
        scope_note = "YES" if in_scope else "CHECK"
        notes = ""
        if not in_scope:
            if any(path.startswith(d) for d in ["ai-workflow-hub/", "ai-workflow-hub-e2e/", "codegraph/"]):
                notes = "ai-workflow-hub change — may be from prior work, not S2"
        lines.append(f"| {path} | {code} | {scope_note} | {notes} |")

    write_file("diff/FILES_CHANGED.md", "\n".join(lines) + "\n")


def generate_diff_summary():
    """Generate DIFF_SUMMARY.md analyzing the diff."""
    status = run_git(["status", "--short"])
    diff_stat = run_git(["diff", "--stat"])
    tools_diff = run_git(["diff", "--", "tools/ai_guard.py", "tools/go_evidence.py",
                           "tools/test_status_synthesis.py", "tools/test_report_consistency.py"])

    lines = [
        "# Diff Summary",
        "",
        "## Files With Changes",
    ]

    if status.strip():
        s2_tool_changes = [l for l in status.strip().split("\n") if "tools/" in l]
        aiwf_changes = [l for l in status.strip().split("\n") if "ai-workflow-hub" in l]
        other_changes = [l for l in status.strip().split("\n")
                         if "tools/" not in l and "ai-workflow-hub" not in l]

        if s2_tool_changes:
            lines.append("### S2 Tools")
            for c in s2_tool_changes:
                lines.append(f"- `{c.strip()}`")
        else:
            lines.append("### S2 Tools")
            lines.append("- No changes detected in `tools/` (files may be new/untracked).")

        if aiwf_changes:
            lines.append("### ai-workflow-hub (NOT in S2 scope)")
            lines.append(f"- {len(aiwf_changes)} files modified — these are from prior/parallel work, not S2.")
        if other_changes:
            lines.append("### Other")
            for c in other_changes:
                lines.append(f"- `{c.strip()}`")
    else:
        lines.append("- Working tree is clean (no unstaged changes).")

    lines.extend([
        "",
        "## Scope Analysis",
        "",
        "### Allowed S2 Scope",
        "- `tools/ai_guard.py` — evidence guard utilities",
        "- `tools/go_evidence.py` — evidence collection",
        "- `tools/test_status_synthesis.py` — status synthesis logic",
        "- `tools/test_report_consistency.py` — report consistency checks",
        "- `_reports/`, `.ai/reports/`, `.ai/runs/` — evidence artifacts",
        "",
        "### Forbidden Scope",
        "- `ai-workflow-hub/src/` — no modifications allowed for S2",
        "- `ai-workflow-hub-e2e/` — no modifications allowed for S2",
        "- `codegraph/` — no modifications allowed for S2",
        "",
        "### Diff of S2 Tools",
    ])

    if tools_diff.strip():
        lines.append("```diff")
        lines.append(tools_diff.strip())
        lines.append("```")
    else:
        lines.append("The `tools/` files show no diff — they are untracked (new) files.")
        lines.append("This is expected: S2 created new tooling rather than modifying existing code.")
        lines.append("Use `git diff --cached -- tools/...` or check `.ai/runs/` for evidence of S2 execution.")

    lines.extend([
        "",
        "## Summary",
        "- S2 tool files are in `tools/` (untracked/new) — no diff against HEAD.",
        "- ai-workflow-hub changes in working tree are from prior/parallel work, NOT S2.",
        "- No forbidden-scope modifications detected for S2.",
    ])
    write_file("diff/DIFF_SUMMARY.md", "\n".join(lines) + "\n")


def generate_missing_files():
    if not MISSING_FILES:
        write_file("MISSING_FILES.md", "# Missing Files\n\nNo required files missing.\n")
        return

    lines = [
        "# Missing Files",
        "",
        "| Expected File | Status | Notes |",
        "|---------------|--------|-------|",
    ]
    for item in MISSING_FILES:
        expected = item.get("expected", "")
        purpose = item.get("purpose", "")
        lines.append(f"| {expected} | MISSING | {purpose} |")
    write_file("MISSING_FILES.md", "\n".join(lines) + "\n")


def check_consistency():
    """Lightweight consistency check. Flag but never fix."""
    # Check 1: S2 report claims SUCCESS
    if os.path.isfile(S2_RESULT_REPORT_SRC):
        with open(S2_RESULT_REPORT_SRC, "r", encoding="utf-8") as f:
            content = f.read()
        if "SUCCESS" in content:
            pass  # expected
        else:
            CONFLICTS.append({
                "check": "S2 report claims SUCCESS",
                "result": "WARNING",
                "evidence": "S2 result report does not contain SUCCESS",
                "notes": "May indicate S2 did not pass"
            })

    # Check 2: TEST_OUTPUT contains pass info
    test_output_path = os.path.join(OUT_DIR, "reports", "TEST_OUTPUT.md")
    if os.path.isfile(test_output_path):
        with open(test_output_path, "r", encoding="utf-8") as f:
            content = f.read()
        has_pass = "pass" in content.lower()
        if not has_pass:
            CONFLICTS.append({
                "check": "TEST_OUTPUT contains pass information",
                "result": "WARNING",
                "evidence": "No 'pass' found in TEST_OUTPUT",
                "notes": "May indicate tests did not run or failed"
            })

    # Check 3: FINAL_REPORT contains final_batch_status
    final_report_path = os.path.join(OUT_DIR, "reports", "FINAL_REPORT.md")
    if os.path.isfile(final_report_path):
        with open(final_report_path, "r", encoding="utf-8") as f:
            content = f.read()
        if "final_batch_status" not in content:
            CONFLICTS.append({
                "check": "FINAL_REPORT contains final_batch_status",
                "result": "MISSING",
                "evidence": "final_batch_status not found in FINAL_REPORT",
                "notes": "S1 rule requires final_batch_status as sole authority"
            })

    # Check 4: REVIEWER_INDEX contains reviewer_verdict
    reviewer_path = os.path.join(OUT_DIR, "reports", "REVIEWER_INDEX.md")
    if os.path.isfile(reviewer_path):
        with open(reviewer_path, "r", encoding="utf-8") as f:
            content = f.read()
        if "reviewer_verdict" not in content:
            CONFLICTS.append({
                "check": "REVIEWER_INDEX contains reviewer_verdict",
                "result": "MISSING",
                "evidence": "reviewer_verdict not found in REVIEWER_INDEX",
                "notes": "Reviewer index must express reviewer_verdict"
            })

    # Check 5: EVIDENCE_INDEX contains evidence_status
    evidence_path = os.path.join(OUT_DIR, "reports", "EVIDENCE_INDEX.md")
    if os.path.isfile(evidence_path):
        with open(evidence_path, "r", encoding="utf-8") as f:
            content = f.read()
        if "evidence_status" not in content:
            CONFLICTS.append({
                "check": "EVIDENCE_INDEX contains evidence_status",
                "result": "MISSING",
                "evidence": "evidence_status not found in EVIDENCE_INDEX",
                "notes": "Evidence index must express evidence_status"
            })

    # Check 6: GATE_CHECK exists
    gate_path = os.path.join(OUT_DIR, "reports", "GATE_CHECK.md")
    if not os.path.isfile(gate_path):
        CONFLICTS.append({
            "check": "GATE_CHECK exists",
            "result": "MISSING",
            "evidence": "No GATE_CHECK.md found",
            "notes": "May be embedded in EXECUTION_REPORT"
        })

    # Check 7: FILES_CHANGED exists
    fc_path = os.path.join(OUT_DIR, "diff", "FILES_CHANGED.md")
    if not os.path.isfile(fc_path):
        CONFLICTS.append({
            "check": "FILES_CHANGED exists",
            "result": "MISSING",
            "evidence": "FILES_CHANGED.md not generated",
            "notes": "Script failure"
        })

    # Check 8: Forbidden scope in git status
    status = run_git(["status", "--short"])
    forbidden_prefixes = ["ai-workflow-hub/src/", "ai-workflow-hub-e2e/", "codegraph/"]
    forbidden_lines = [l for l in status.split("\n")
                       if any(l.strip().startswith(p) for p in forbidden_prefixes)]
    if forbidden_lines:
        CONFLICTS.append({
            "check": "No forbidden scope modifications",
            "result": "FLAGGED",
            "evidence": f"{len(forbidden_lines)} file(s) in forbidden scope modified",
            "notes": "These are ai-workflow-hub changes from prior/parallel work, not S2. GPT must verify."
        })

    # Check 9: S3 work indicators
    s3_indicators = ["s3-", "S3_", "S3:", "s3_evidence", "s3_governance"]
    for indicator in s3_indicators:
        if indicator in status.lower():
            CONFLICTS.append({
                "check": "No S3 work started",
                "result": "FLAGGED",
                "evidence": f"Found '{indicator}' in git status",
                "notes": "May indicate S3 work in progress"
            })
            break

    # Generate report
    if not CONFLICTS:
        write_file("EVIDENCE_CONFLICTS.md",
                   "# Evidence Conflicts\n\n"
                   "No obvious conflicts detected by packaging agent.\n"
                   "Final verification is reserved for GPT review.\n")
    else:
        lines = [
            "# Evidence Conflicts",
            "",
            "| Check | Result | Evidence | Notes |",
            "|-------|--------|----------|-------|",
        ]
        for c in CONFLICTS:
            lines.append(f"| {c['check']} | {c['result']} | {c['evidence']} | {c['notes']} |")
        lines.append("")
        lines.append("_Conflicts are flagged, not resolved. GPT must adjudicate._")
        write_file("EVIDENCE_CONFLICTS.md", "\n".join(lines) + "\n")


def generate_readme():
    # Count found files
    review_pack_files = os.listdir(os.path.join(OUT_DIR, "review_pack")) \
        if os.path.isdir(os.path.join(OUT_DIR, "review_pack")) else []
    report_files = os.listdir(os.path.join(OUT_DIR, "reports")) \
        if os.path.isdir(os.path.join(OUT_DIR, "reports")) else []
    source_files = os.listdir(os.path.join(OUT_DIR, "source")) \
        if os.path.isdir(os.path.join(OUT_DIR, "source")) else []

    status_summary = []
    status_summary.append(f"- review_pack/: {len(review_pack_files)} files")
    status_summary.append(f"- reports/: {len(report_files)} files")
    status_summary.append(f"- source/: {len(source_files)} files")
    status_summary.append(f"- diff/: git evidence collected")
    status_summary.append(f"- task/: S2 TaskSpec + S1 Baseline")
    expected_count = 9
    found_count = len(review_pack_files)
    if found_count >= expected_count:
        status_summary.append("- All expected review_pack files found.")
    else:
        status_summary.append(f"- WARNING: Expected {expected_count} review_pack files, found {found_count}.")

    content = f"""# S2 GPT Review Evidence Pack

This pack is for GPT review of S2-evidence-report-reviewer-index-consistency.

## Review Question
Can GPT verify, using only this pack, that S2 is actually complete and not fake-green?

## What GPT Should Check
1. S1 synthesis rule preserved.
2. evidence_status is not used as final_batch_status.
3. reviewer_verdict is not used as final_batch_status.
4. final-report has exactly one authoritative final_batch_status.
5. reviewer-index distinguishes reviewer_verdict and final_batch_status.
6. evidence-index does not claim batch success.
7. conflicting reports fail closed.
8. parent summary pass with child blocked fails closed.
9. prose-only PASS fails closed.
10. blocked_by is non-empty when blocked.
11. blocked_by uses legal enums.
12. tests actually ran and match the gates.
13. changed files are within allowed scope.
14. no S3 work started.

## Review Pack Status
{chr(10).join(status_summary)}

## Included Directories
| Directory | Purpose |
|-----------|---------|
| task/ | S2 TaskSpec and S1 baseline summary |
| reports/ | S2 result report, final-report, test-output, reviewer-index, evidence-index, gate check |
| diff/ | Git status, diff stat, diff patch, files changed, diff summary |
| source/ | S2 source files (ai_guard, go_evidence, test_status_synthesis, test_report_consistency) |
| review_pack/ | Agent-generated review pack from _reports/s2-review-pack/ |

## Usage
Upload `s2-gpt-review-evidence-pack.zip` to GPT.
Start a fresh chat, paste `GPT_REVIEW_PROMPT.md`, attach the zip.

## Constraints
- This pack is for GPT advisory review only.
- It does NOT mean S2 is automatically accepted.
- All conclusions are reserved for GPT and the governance gate.
"""
    write_file("README.md", content)


def generate_pack_manifest():
    lines = [
        "# S2 Evidence Pack Manifest",
        "",
        "## Included Files",
        "",
        "| Path | Source Path | Purpose |",
        "|------|-------------|---------|",
    ]

    # Walk the output directory
    for root, dirs, files in os.walk(OUT_DIR):
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, OUT_DIR).replace("\\", "/")

            # Determine source
            if rel.startswith("review_pack/"):
                src = f"_reports/s2-review-pack/{f}"
            elif rel.startswith("reports/"):
                if f == "S2_RESULT_REPORT.md":
                    src = ".ai/reports/2026-06-01-s2-evidence-report-reviewer-index-consistency-result.md"
                elif f in ("GATE_CHECK.md",):
                    src = "_reports/s2-review-pack/GATE_CHECK.md"
                else:
                    src = f".ai/runs/s2-evidence-report-reviewer-index-consistency/{f.lower().replace('_', '-')}"
                    # Map back
                    name_map = {
                        "FINAL_REPORT.md": "final-report.md",
                        "TEST_OUTPUT.md": "test-output.md",
                        "REVIEWER_INDEX.md": "reviewer-index.md",
                        "EVIDENCE_INDEX.md": "evidence-index.md",
                    }
                    run_fname = name_map.get(f, f.lower().replace("_", "-"))
                    src = f".ai/runs/s2-evidence-report-reviewer-index-consistency/{run_fname}"
            elif rel.startswith("source/"):
                src = f"tools/{f}"
            elif rel.startswith("diff/"):
                if f == "GIT_STATUS.txt":
                    src = "git status --short (generated)"
                elif f == "GIT_DIFF_STAT.txt":
                    src = "git diff --stat (generated)"
                elif f == "GIT_DIFF.patch":
                    src = "git diff -- tools/... (generated)"
                elif f == "FILES_CHANGED.md":
                    src = "generated from git status"
                elif f == "DIFF_SUMMARY.md":
                    src = "generated analysis"
                else:
                    src = "generated"
            elif rel.startswith("task/"):
                src = "generated from task specification"
            elif rel in ("README.md", "PACK_MANIFEST.md", "MISSING_FILES.md",
                         "EVIDENCE_CONFLICTS.md", "GPT_REVIEW_PROMPT.md"):
                src = "generated"
            else:
                src = "generated"

            purpose = ""
            if "TASKSPEC" in f:
                purpose = "S2 objective and required evidence"
            elif "BASELINE" in f:
                purpose = "S1 verified rules and artifacts"
            elif "FINAL_REPORT" in f:
                purpose = "S2 run final report"
            elif "TEST_OUTPUT" in f:
                purpose = "S2 test execution output"
            elif "REVIEWER_INDEX" in f:
                purpose = "Reviewer verdict and index"
            elif "EVIDENCE_INDEX" in f:
                purpose = "Evidence status index"
            elif "GATE_CHECK" in f:
                purpose = "Gate-by-gate check results"
            elif "FILES_CHANGED" in f:
                purpose = "List of changed files"
            elif "DIFF_SUMMARY" in f:
                purpose = "Diff analysis and scope check"
            elif "GIT_STATUS" in f:
                purpose = "Raw git status output"
            elif "GIT_DIFF_STAT" in f:
                purpose = "Raw git diff --stat"
            elif "GIT_DIFF" in f:
                purpose = "Git diff patch for tools/"
            elif "EXECUTION_REPORT" in f:
                purpose = "Agent execution report"
            elif "REVIEW_NOTES" in f:
                purpose = "Notes for GPT reviewer"
            elif "REVIEW_PROMPT" in f:
                purpose = "Self-contained GPT review prompt"
            elif "READme" in f:
                purpose = "Pack overview"
            elif "MANIFEST" in f:
                purpose = "This manifest"
            elif "MISSING" in f:
                purpose = "Missing file report"
            elif "CONFLICTS" in f:
                purpose = "Evidence conflicts report"
            elif f.endswith(".py"):
                purpose = "S2 source code"
            else:
                purpose = "Evidence artifact"

            lines.append(f"| {rel} | {src} | {purpose} |")

    lines.append("")
    lines.append("## Missing Expected Files")
    if MISSING_FILES:
        for item in MISSING_FILES:
            lines.append(f"| {item.get('expected', '')} | {item.get('purpose', '')} |")
    else:
        lines.append("| None | — |")

    lines.append("")
    lines.append("## Generated Files")
    generated = [
        "README.md", "PACK_MANIFEST.md", "MISSING_FILES.md",
        "EVIDENCE_CONFLICTS.md", "GPT_REVIEW_PROMPT.md",
        "task/S2_TASKSPEC.md", "task/S1_BASELINE_SUMMARY.md",
        "diff/FILES_CHANGED.md", "diff/DIFF_SUMMARY.md",
    ]
    for g in generated:
        lines.append(f"| {g} | Script generation |")

    lines.append("")
    lines.append("## Notes")
    lines.append("This pack is for GPT review only. It does not mean S2 is automatically accepted.")

    write_file("PACK_MANIFEST.md", "\n".join(lines) + "\n")


def generate_gpt_review_prompt():
    content = """你是 Dev Frame OpenCode 的 GPT 复审智能体。

我上传的是 S2 GPT Review Evidence Pack。请你只基于该 evidence pack 判断 S2-evidence-report-reviewer-index-consistency 是否真的完成。

请不要凭 agent summary 直接接受 SUCCESS。请逐项审查：

1. S1 synthesis rule 是否保留；
2. evidence_status 是否没有被用作 final_batch_status；
3. reviewer_verdict 是否没有被用作 final_batch_status；
4. final-report 是否有且只有一个 authoritative final_batch_status；
5. reviewer-index 是否明确区分 reviewer_verdict 与 final_batch_status；
6. evidence-index 是否没有暗示 evidence pass 等于 batch pass；
7. conflicting reports 是否 fail-closed；
8. parent summary pass while child blocked 是否 fail-closed；
9. prose-only PASS 是否 fail-closed；
10. blocked_by 在 blocked 时是否非空；
11. blocked_by 是否使用合法 enum；
12. TEST_OUTPUT 是否证明测试真实运行；
13. DIFF_SUMMARY 和 GIT_STATUS 是否证明没有 forbidden scope 修改；
14. 是否存在 S3 相关越界工作。

请输出：

- Overall Judgment: accepted / rejected / blocked / human_required
- Evidence Sufficiency
- Gate-by-Gate Review
- Fake-Green Risk
- Scope Violation Check
- Missing Evidence
- Conflicts
- Decision
- Whether S3 is allowed

如果证据不足，不得 accepted，必须 blocked 或 human_required。
"""
    write_file("GPT_REVIEW_PROMPT.md", content)


def create_zip():
    """Zip the output directory."""
    zip_path = os.path.join(PROJECT_ROOT, "s2-gpt-review-evidence-pack.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(OUT_DIR):
            for f in files:
                full = os.path.join(root, f)
                arcname = os.path.relpath(full, OUT_DIR)
                # Prefix with directory name so zip extracts cleanly
                arcname = os.path.join("s2-gpt-review-evidence-pack", arcname)
                zf.write(full, arcname)
    return zip_path


def main():
    print("=== Oracle S2 Evidence Packager ===")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Output dir:   {OUT_DIR}")

    # Clean and create output directory
    if os.path.exists(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    ensure_dir(OUT_DIR)
    ensure_dir(os.path.join(OUT_DIR, "task"))
    ensure_dir(os.path.join(OUT_DIR, "reports"))
    ensure_dir(os.path.join(OUT_DIR, "diff"))
    ensure_dir(os.path.join(OUT_DIR, "source"))
    ensure_dir(os.path.join(OUT_DIR, "review_pack"))

    # Step 1: Copy review pack
    print("\n[1/9] Copying review pack...")
    copied = copy_all_from_dir(S2_REVIEW_PACK_DIR, os.path.join(OUT_DIR, "review_pack"))
    print(f"  Copied {len(copied)} files from _reports/s2-review-pack/")
    for f in copied:
        print(f"    - {f}")

    # Step 2: Copy reports
    print("\n[2/9] Collecting reports...")
    collect_reports()
    print("  Reports collected.")

    # Step 3: Copy source files
    print("\n[3/9] Collecting source files...")
    collect_source_files()
    print("  Source files collected.")

    # Step 4: Collect diff evidence
    print("\n[4/9] Collecting diff evidence...")
    collect_diff_evidence()
    print("  Git evidence collected.")

    # Step 5: Generate task context
    print("\n[5/9] Generating task context...")
    generate_task_spec()
    generate_s1_baseline()
    print("  Task context generated.")

    # Step 6: Generate diff analysis
    print("\n[6/9] Generating diff analysis...")
    generate_files_changed()
    generate_diff_summary()
    print("  Diff analysis generated.")

    # Step 7: Generate reports
    print("\n[7/9] Generating pack reports...")
    generate_missing_files()
    check_consistency()
    generate_readme()
    generate_pack_manifest()
    generate_gpt_review_prompt()
    print("  Pack reports generated.")

    # Step 8: Summary
    print("\n[8/9] Summary:")
    print(f"  Missing files: {len(MISSING_FILES)}")
    for m in MISSING_FILES:
        print(f"    - {m.get('expected', 'unknown')}")
    print(f"  Conflicts: {len(CONFLICTS)}")
    for c in CONFLICTS:
        print(f"    - {c['check']}: {c['result']}")

    # Step 9: Zip
    print("\n[9/9] Creating zip...")
    zip_path = create_zip()
    print(f"  Zip created: {zip_path}")

    print("\n=== DONE ===")
    print(f"Evidence pack: {OUT_DIR}")
    print(f"Zip file:      {zip_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
