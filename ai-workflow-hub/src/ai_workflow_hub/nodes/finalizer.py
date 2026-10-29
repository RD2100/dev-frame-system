"""Finalizer 节点 — 100% 确定性报告生成.

不调用任何模型。从 state.json + diff + test output + review data 拼接结构化报告。
报告格式为 machine-readable（结构化区块），供 @go Auditor 消费。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config_loader import _hub_dir
from ..run_store import save_run_file, save_run_json
from ..run_governance import render_full_governance_md, summarize_run_governance


def finalizer_node(state: dict[str, Any]) -> dict[str, Any]:
    """执行终结节点 — 100% 确定性，不调用任何模型.

    生成 final-report.md（machine-readable 结构化格式），设置最终 status。
    """
    run_dir = state.get("run_dir", "")
    status = state.get("status", "passed")

    # 根据当前状态确定最终 status
    review_result = state.get("review_result", "")
    if review_result == "blocked":
        status = "blocked"
    elif state.get("human_required"):
        status = "human_required"
    elif review_result == "pass":
        status = "passed"
    elif review_result == "fail":
        status = "failed"

    from datetime import datetime, timezone
    state["status"] = status
    state["updated_at"] = datetime.now(timezone.utc).isoformat()

    # --- P0 issue blocking ---
    from ..issue_ledger import unresolved_p0_count
    p0_count = unresolved_p0_count(run_dir)
    if p0_count > 0:
        status = "blocked"
        state["status"] = "blocked"
        state["review_result"] = "blocked"
        state["human_required"] = True
        state["error_message"] = f"Reviewer found {p0_count} unresolved P0 issue(s)"

    # --- 100% deterministic report — no model calls ---
    report = _generate_deterministic_report(state)

    save_run_file(run_dir, "final-report.md", report)
    save_run_json(run_dir, "state.json", state)
    _write_failure_analysis_if_needed(state)

    return {
        "status": status,
        "updated_at": state["updated_at"],
        "backend_calls": {
            "finalizer": {
                "backend": "local_template",
                "model": "deterministic",
                "exit_code": 0,
                "stdout_log": str(Path(run_dir) / "final-report.md"),
                "stderr_log": "",
                "trusted_for_status": True,
            }
        },
    }


def _generate_deterministic_report(state: dict[str, Any]) -> str:
    """确定性报告 — machine-readable 结构化区块格式.

    报告结构:
    - RUN INFO   (元数据)
    - PLAN       (计划摘要)
    - CHANGES    (变更文件 + diff 行数)
    - REVIEW     (审核裁定 + blocking fixes)
    - TESTS      (测试结果)
    - SAFETY     (安全检查)
    - BACKEND    (后端调用审计)
    - EVIDENCE   (证据文件路径)
    - VERDICT    (最终裁定)
    """
    bc_table = _render_backend_calls(state.get("backend_calls", {}))
    changed = state.get("changed_files", [])
    changed_status = state.get("changed_files_status", {})
    status_lines = []
    for f in changed:
        st = changed_status.get(f, "M")
        status_lines.append(f"- `{f}` ({st})")

    sections = []

    # RUN INFO
    sections.append(f"""\
# Final Report (deterministic)

## RUN INFO
- **Run ID**: {state.get("run_id", "")}
- **Project**: {state.get("project_name", "")} ({state.get("project_id", "")})
- **Task**: {state.get("task_title", "")} ({state.get("task_id", "")})
- **Risk**: {state.get("task_risk", "medium")}
- **Mode**: {'dry-run' if state.get("dry_run", True) else 'apply'}
- **Status**: {state.get("status", "unknown")}
- **Branch**: {state.get("current_branch", "")}
- **Started**: {state.get("created_at", "")}
- **Completed**: {state.get("updated_at", "")}
- **Isolation**: {state.get("isolation_mode", "branch")}
- **Fix Rounds**: {state.get("fix_round", 0)}/{state.get("max_fix_rounds", 3)}""")

    # PLAN
    plan = state.get("plan", "No plan available.")
    sections.append(f"""\
## PLAN
{plan[:3000]}""")

    # CHANGES
    sections.append(f"""\
## CHANGES
- **Files Changed**: {len(changed)}
- **Diff Lines**: {state.get("diff_line_count", 0)}
- **File List**:
{chr(10).join(status_lines) if status_lines else '- (none)'}

### Allowed Files
{chr(10).join(f'- `{f}`' for f in state.get("allowed_files", [])) or '- (none)'}

### Forbidden Files
{chr(10).join(f'- `{f}`' for f in state.get("forbidden_files", [])) or '- (none)'}""")

    # REVIEW
    sections.append(f"""\
## REVIEW
- **Verdict**: {state.get("review_result", "")}
- **Summary**: {state.get("review_summary", "")}

### Blocking Fixes
{chr(10).join(f'- {f}' for f in state.get("next_fixes", [])) or '- (none)'}

### Allowed Fix Files
{chr(10).join(f'- `{f}`' for f in state.get("allowed_fix_files", [])) or '- (none)'}""")

    # TESTS
    sections.append(f"""\
## TESTS
- **Exit Code**: {state.get("test_exit_code", -1)}
- **Test Commands**:
  ```json
  {_format_json(state.get("test_commands", {}))}
  ```

### Test Output (first 2000 chars)
```
{state.get("test_output", "")[:2000]}
```""")

    # SAFETY
    sections.append(f"""\
## SAFETY
- **Dangerous Change**: {state.get("dangerous_change", False)}
- **Human Required**: {state.get("human_required", False)}
- **Safety Overall**: {state.get("safety_overall", "")}
- **Forbidden Paths Touched**: {state.get("forbidden_paths_touched", [])}
- **Protected Tests**: {state.get("protected_tests", [])}
- **Error Message**: {state.get("error_message", "")[:500]}""")

    # RUN / ISSUE GOVERNANCE
    governance_summary = summarize_run_governance(state.get("run_dir", ""), state=state)
    sections.append(render_full_governance_md(governance_summary))

    # BACKEND
    sections.append(f"""\
## BACKEND CALLS
{bc_table}""")

    # EVIDENCE
    sections.append(f"""\
## EVIDENCE
- **Run Directory**: {state.get("run_dir", "")}
- **Workflow File**: {state.get("workflow_file", "")}
- **Executed Nodes**: {state.get("executed_nodes", [])}
- **Cleanup Success**: {state.get("cleanup_success", True)}""")

    # VERDICT
    verdict_detail = _build_verdict(state)
    sections.append(f"""\
## VERDICT
- **Final Status**: {state.get("status", "unknown")}
- **Deterministic Report**: True (no model interpretation)
{verdict_detail}""")

    return "\n\n".join(sections)


def _render_backend_calls(backend_calls: dict) -> str:
    """渲染 backend_calls 表格."""
    if not backend_calls:
        return "No backend calls recorded."
    lines = ["| Node | Backend | Model | Exit Code | Duration(s) | Timeout |",
             "|------|---------|-------|-----------|-------------|---------|"]
    for node, info in backend_calls.items():
        if isinstance(info, dict):
            lines.append(
                f"| {node} | {info.get('backend', '?')} | {info.get('model', '?')} | "
                f"{info.get('exit_code', '?')} | {info.get('duration_seconds', '?')} | "
                f"{info.get('timed_out', False)} |")
    return "\n".join(lines)


def _format_json(data: dict) -> str:
    import json
    return json.dumps(data, indent=2, ensure_ascii=False)


def _build_verdict(state: dict[str, Any]) -> str:
    """构建 verdict 详情."""
    status = state.get("status", "unknown")
    lines = []
    if status == "passed":
        lines.append("- All gates passed.")
    elif status == "failed":
        lines.append(f"- Failure: {state.get('error_message', '')[:200]}")
        lines.append(f"- Test exit code: {state.get('test_exit_code', -1)}")
        lines.append(f"- Fix rounds used: {state.get('fix_round', 0)}/{state.get('max_fix_rounds', 3)}")
    elif status == "blocked":
        lines.append(f"- Blocked: {state.get('review_result', '')}")
        lines.append(f"- Blocking fixes: {state.get('next_fixes', [])}")
    elif status == "human_required":
        lines.append("- Human gate required.")
        lines.append(f"- Reason: dangerous={state.get('dangerous_change', False)}, human_required={state.get('human_required', False)}")
    elif status == "pending":
        lines.append("- Workflow did not complete.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Failure analysis
# ---------------------------------------------------------------------------

def _write_failure_analysis_if_needed(state: dict[str, Any]) -> bool:
    """终态 failed/blocked/human_required 时生成 failure-analysis.md."""
    status = state.get("status", "")
    if status not in ("failed", "blocked", "human_required"):
        return False

    content = build_failure_analysis(state)
    run_dir = state.get("run_dir", "")
    if run_dir:
        save_run_file(run_dir, "failure-analysis.md", content)
        return True
    return False


def build_failure_analysis(state: dict[str, Any]) -> str:
    """生成 failure-analysis.md."""
    status = state.get("status", "unknown")
    blocking_node = _infer_blocking_node(state)
    bc_table = _render_backend_calls_full(state.get("backend_calls", {}))
    next_action = _recommend_next_action(state, blocking_node)

    governance_summary = summarize_run_governance(state.get("run_dir", ""), state=state)
    gov_lines = render_full_governance_md(governance_summary).replace(
        "## RUN GOVERNANCE",
        "## Run Governance",
        1,
    ).replace(
        "## ISSUE LEDGER",
        "## Governance Summary",
        1,
    )

    return f"""# Failure Analysis

## Summary
- **Status**: {status}
- **Review Result**: {state.get("review_result", "")}
- **Human Required**: {state.get("human_required", False)}
- **Error Message**: {state.get("error_message", "")[:200]}
- **Run ID**: {state.get("run_id", "")}
- **Task**: {state.get("task_title", "")} ({state.get("task_id", "")})
- **Project**: {state.get("project_name", "")}

## Likely Blocking Node
- **Node**: {blocking_node}
- **Reason**: {_blocking_reason(state, blocking_node)}

## Backend Calls
{bc_table}

## Diff State
- **Changed Files**: {len(state.get("changed_files", []))}
- **Diff Lines**: {state.get("diff_line_count", 0)}

## Test State
- **Test Exit Code**: {state.get("test_exit_code", -1)}

## Review State
- **Review Summary**: {state.get("review_summary", "")}
- **Next Fixes**: {', '.join(state.get("next_fixes", [])) or 'none'}

## Safety / Human Gate
- **Dangerous Change**: {state.get("dangerous_change", False)}
- **Human Required**: {state.get("human_required", False)}

## Recommended Next Action
{next_action}

{gov_lines}

## Evidence Files
All evidence in: {state.get("run_dir", "")}
"""


def _infer_blocking_node(state: dict[str, Any]) -> str:
    """推断阻塞节点."""
    err = state.get("error_message", "")
    if err and "timeout" in err.lower():
        bc = state.get("backend_calls", {})
        for node in ["executor", "fixer"]:
            info = bc.get(node, {})
            if isinstance(info, dict) and info.get("timed_out"):
                return node
        return "executor"

    if state.get("human_required"):
        return "human_gate"
    if state.get("fix_round", 0) >= state.get("max_fix_rounds", 3):
        return "fixer"
    if state.get("test_exit_code", 0) not in (0, -1):
        return "tester"
    if err:
        bc = state.get("backend_calls", {})
        for node in ["executor", "fixer"]:
            info = bc.get(node, {})
            if isinstance(info, dict) and info.get("exit_code", 0) != 0:
                return node
        return "executor"
    return "unknown"


def _blocking_reason(state: dict[str, Any], node: str) -> str:
    reasons = {
        "executor": "executor failed or timed out",
        "fixer": "fixer exhausted max rounds",
        "human_gate": "human review required",
        "tester": "tests failed",
        "unknown": "blocking reason unclear",
    }
    return reasons.get(node, reasons["unknown"])


def _render_backend_calls_full(backend_calls: dict) -> str:
    if not backend_calls:
        return "No backend calls."
    lines = ["| Node | Backend | Model | Exit | Timeout | Dur(s) |",
             "|------|---------|-------|------|---------|--------|"]
    for node, info in backend_calls.items():
        if isinstance(info, dict):
            lines.append(
                f"| {node} | {info.get('backend','?')} | {info.get('model','?')} | "
                f"{info.get('exit_code','?')} | {info.get('timed_out',False)} | "
                f"{info.get('duration_seconds','?')} |")
    return "\n".join(lines)


def _recommend_next_action(state: dict[str, Any], node: str) -> str:
    actions = {
        "executor": "- Check OpenCode stdout/stderr logs\n- Verify API key and model availability\n- Retry with different model via OPENCODE_MODEL_OVERRIDE",
        "fixer": "- Check fix rounds exhausted -- task may need human intervention\n- Review diff changes and fix manually\n- Re-run apply after manual fix",
        "human_gate": "- Review human-gate.md\n- Approve: re-run with --apply\n- Reject: discard run",
        "tester": "- Check test-output.md for failures\n- Fix failing tests\n- Re-run apply",
        "unknown": "- Inspect all log files in run directory\n- Check state.json for details",
    }
    return actions.get(node, actions["unknown"])
