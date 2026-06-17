"""统一回归报告生成器

从聚合结果生成：
- regression-summary.json — 结构化JSON摘要
- regression-report.md   — 人类可读Markdown报告
- evidence.json          — 证据索引
"""

import os
import json
from datetime import datetime

from schema.stage_results import iter_public_tool_results


def generate_regression_report(
    project_name: str,
    profile: str,
    results: list[dict],
    stage_results: dict = None,
    quality_gate: dict = None,
    base_url: str = "",
    command: str = "",
    date: str = None,
    output_dir: str = None,
    project_config: dict = None,
    allure_generation: dict = None,
) -> dict:
    """生成完整的回归报告套件。

    Args:
        project_name: 项目名
        profile: 执行的profile名称
        results: 聚合后的统一TestResult列表
        stage_results: 阶段执行结果 {stage_name: {ok, tools: {tool: status}}}
        quality_gate: 质量门禁结果 {profile, passed, failures}
        base_url: 测试目标URL
        command: 执行的命令
        date: 日期字符串 (YYYY-MM-DD)，默认今天
        output_dir: 输出目录，默认 reports/<project>/<date>/
        project_config: 项目配置 dict (fittrack.yaml 内容)

    Returns:
        dict with paths to generated files
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    base_dir = output_dir or os.path.join("reports", project_name, date)
    os.makedirs(base_dir, exist_ok=True)

    # --- Compute statistics ---
    totals = {"passed": 0, "failed": 0, "skipped": 0, "blocked": 0}
    by_tool = {}
    top_failures = []

    for r in results:
        status = r.get("status", "unknown")
        tool = r.get("tool", "unknown")

        # Totals
        if status in totals:
            totals[status] += 1

        # By tool
        if tool not in by_tool:
            by_tool[tool] = {"passed": 0, "failed": 0, "skipped": 0, "blocked": 0, "total": 0}
        by_tool[tool]["total"] += 1
        if status in by_tool[tool]:
            by_tool[tool][status] += 1

        # Top failures (failed + blocked, sorted by most severe)
        if status in ("failed", "blocked"):
            top_failures.append({
                "test_name": r.get("test_name", ""),
                "status": status,
                "tool": tool,
                "error": (r.get("error") or {}).get("message", "")[:300],
                "screenshot": r.get("screenshot", ""),
                "browser": r.get("browser", ""),
            })

    # Sort failures: blocked first, then by tool
    top_failures.sort(key=lambda f: (0 if f["status"] == "blocked" else 1, f["tool"]))

    # --- Determine overall status ---
    if totals["blocked"] > 0:
        overall_status = "blocked"
    elif quality_gate and not quality_gate.get("passed", True):
        overall_status = "failed"
    elif totals["failed"] > 0:
        overall_status = "failed"
    else:
        overall_status = "passed"

    # Load explorer results if available (look in project-agnostic path)
    explorer_summary = None
    explorer_pages = []
    explorer_auth_mode = None
    explorer_path = os.path.join("reports", "ui-explorer", "explorer-results.json")
    if os.path.exists(explorer_path):
        try:
            with open(explorer_path, "r", encoding="utf-8") as f:
                explorer_data = json.load(f)
            explorer_summary = explorer_data.get("summary", {})
            explorer_pages = explorer_data.get("pages", [])
            # Runtime authMode is authoritative: it records what actually happened
            explorer_auth_mode = explorer_data.get("authMode")
        except Exception:
            pass

    # Build explorer section for summary
    explorer_section = dict(explorer_summary) if explorer_summary else {}
    if not explorer_section:
        explorer_section = {
            "routesVisited": 0, "actionsAttempted": 0,
            "issuesFound": 0, "bySeverity": {"P0": 0, "P1": 0, "P2": 0, "P3": 0},
        }

    # Detect environment blocks from stage results
    environment_blocks = _detect_environment_blocks(stage_results or {}, project_name)

    # --- Load business smoke results ---
    business_smoke = _load_business_smoke()

    # --- Read authMode ---
    auth_mode = _read_auth_mode(project_config or {}, explorer_auth_mode)

    # --- Compute verdicts ---
    verdicts = _compute_verdicts(stage_results or {}, quality_gate or {}, explorer_summary or {}, auth_mode)

    # --- Compute blockers ---
    blockers = _compute_blockers(stage_results or {}, environment_blocks, auth_mode)

    # --- Generate regression-summary.json ---
    allure_generation = allure_generation or {}
    allure_html_path = allure_generation.get("html_path") or ""
    summary = {
        "project": project_name,
        "profile": profile,
        "date": date,
        "status": overall_status,
        "command": command,
        "base_url": base_url,
        "totals": totals,
        "by_tool": by_tool,
        "explorer": explorer_section,
        "environmentBlocks": environment_blocks,
        "quality_gate": quality_gate or {},
        "verdicts": verdicts,
        "blockers": blockers,
        "authMode": auth_mode,
        "businessSmoke": business_smoke,
        "top_failures": top_failures[:20],
        "artifacts": {
            "evidence": os.path.join(base_dir, "evidence.json"),
            "markdown": os.path.join(base_dir, "regression-report.md"),
            "allure": allure_html_path,
            "allure_generation": allure_generation.get(
                "manifest_path",
                os.path.join(base_dir, "allure-generation.json"),
            ),
        },
        "allure_generation": allure_generation,
        "generated_at": datetime.now().isoformat(),
    }
    summary_path = os.path.join(base_dir, "regression-summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # --- Generate regression-report.md ---
    md = _render_markdown(
        project_name=project_name,
        profile=profile,
        date=date,
        overall_status=overall_status,
        command=command,
        base_url=base_url,
        stage_results=stage_results,
        totals=totals,
        by_tool=by_tool,
        explorer_summary=explorer_section,
        explorer_pages=explorer_pages,
        environment_blocks=environment_blocks,
        top_failures=top_failures,
        quality_gate=quality_gate,
        base_dir=base_dir,
        verdicts=verdicts,
        auth_mode=auth_mode,
        business_smoke=business_smoke,
        allure_generation=allure_generation,
    )
    md_path = os.path.join(base_dir, "regression-report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"  [REPORT] regression-summary.json -> {summary_path}")
    print(f"  [REPORT] regression-report.md    -> {md_path}")

    return {
        "summary": summary_path,
        "markdown": md_path,
        "status": overall_status,
    }


def _render_markdown(**ctx) -> str:
    """Render the regression report as Markdown."""
    project_name = ctx["project_name"]
    profile = ctx["profile"]
    date = ctx["date"]
    overall_status = ctx["overall_status"]
    command = ctx.get("command", "")
    base_url = ctx.get("base_url", "")
    stage_results = ctx.get("stage_results") or {}
    totals = ctx.get("totals", {})
    by_tool = ctx.get("by_tool", {})
    explorer_summary = ctx.get("explorer_summary")
    top_failures = ctx.get("top_failures", [])
    base_dir = ctx["base_dir"]
    allure_generation = ctx.get("allure_generation") or {}

    status_icon = {"passed": "PASS", "failed": "FAIL", "blocked": "BLOCKED"}
    icon = status_icon.get(overall_status, "UNKNOWN")
    quality_gate = ctx.get("quality_gate") or {}
    gate_passed = quality_gate.get("passed", None)
    gate_profile = quality_gate.get("profile", "")

    lines = [
        f"# Regression Report: {project_name}",
        "",
        f"## Conclusion: **{icon}**",
        "",
        f"| Item | Value |",
        f"|------|-------|",
        f"| Project | {project_name} |",
        f"| Profile | {profile} |",
        f"| Date | {date} |",
    ]
    if command:
        lines.append(f"| Command | `{command}` |")
    if base_url:
        lines.append(f"| Base URL | {base_url} |")
    lines.append(f"| Overall Status | {icon} |")
    auth_mode = ctx.get("auth_mode", "real")
    lines.append(f"| Auth Mode | {auth_mode} |")
    if auth_mode == "injected":
        lines.append("")
        lines.append("> **Warning**: Injected auth used; backend authentication not verified.")
        lines.append("")
    if gate_passed is not None:
        gate_label = "PASS" if gate_passed else "BLOCKED"
        lines.append(f"| Quality Gate ({gate_profile}) | {gate_label} |")
    if gate_passed and overall_status != "passed":
        lines.append(f"| Gate vs Overall | Gate passes but overall {overall_status} — see details below |")
    lines.append(f"| Total Results | {totals.get('passed',0)+totals.get('failed',0)} (P:{totals.get('passed',0)} F:{totals.get('failed',0)} S:{totals.get('skipped',0)} B:{totals.get('blocked',0)}) |")
    lines.append("")

    # --- Stage Results ---
    if stage_results:
        lines.append("## Stage Results")
        lines.append("")
        lines.append("| Stage | Status | Tools | Passed | Failed | Skipped | Blocked |")
        lines.append("|-------|--------|-------|--------|--------|---------|---------|")
        for stage_name, sr in stage_results.items():
            ok = sr.get("ok", True)
            stage_items = list(iter_public_tool_results({stage_name: sr}))
            tool_names = [item["tool"] for item in stage_items]
            status_str = "OK" if ok else "FAIL"

            # Count tool statuses
            p = sum(1 for item in stage_items if item["status"] == "passed")
            f = sum(1 for item in stage_items if item["status"] == "failed")
            s = sum(1 for item in stage_items if item["status"] == "skipped")
            b = sum(1 for item in stage_items if item["status"] == "blocked")

            lines.append(f"| {stage_name} | {status_str} | {', '.join(tool_names)} | {p} | {f} | {s} | {b} |")
        lines.append("")

    # --- Totals ---
    lines.append("## Results Summary")
    lines.append("")
    lines.append(f"| Status | Count |")
    lines.append(f"|--------|-------|")
    for status in ("passed", "failed", "skipped", "blocked"):
        lines.append(f"| {status} | {totals.get(status, 0)} |")
    lines.append("")

    # --- By Tool ---
    if by_tool:
        lines.append("### By Tool")
        lines.append("")
        lines.append("| Tool | Total | Passed | Failed | Skipped | Blocked |")
        lines.append("|------|-------|--------|--------|---------|---------|")
        for tool, counts in sorted(by_tool.items()):
            lines.append(
                f"| {tool} | {counts['total']} | {counts['passed']} | "
                f"{counts['failed']} | {counts['skipped']} | {counts['blocked']} |"
            )
        lines.append("")

    # --- UI Explorer ---
    explorer_summary = ctx.get("explorer_summary")
    explorer_pages = ctx.get("explorer_pages") or []
    if explorer_summary:
        lines.append("## UI Explorer Summary")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Routes Visited | {explorer_summary.get('routesVisited', 0)} |")
        lines.append(f"| Actions Attempted | {explorer_summary.get('actionsAttempted', 0)} |")
        lines.append(f"| Issues Found | {explorer_summary.get('issuesFound', 0)} |")
        by_sev = explorer_summary.get("bySeverity", {})
        if by_sev:
            sev_str = " | ".join(f"{k}:{v}" for k, v in sorted(by_sev.items()))
            lines.append(f"| By Severity | {sev_str} |")
        lines.append("")

    # --- UI Explorer Findings (per-page issues) ---
    all_explorer_issues = []
    for page_entry in explorer_pages:
        for issue in (page_entry.get("issues") or []):
            all_explorer_issues.append({
                **issue,
                "route": page_entry.get("route", ""),
            })
    if all_explorer_issues:
        lines.append("## UI Explorer Findings")
        lines.append("")
        lines.append("| Severity | Route | Title | Repro Steps | Evidence |")
        lines.append("|----------|-------|-------|-------------|----------|")
        for fi in all_explorer_issues[:20]:
            sev = fi.get("severity", "P3")
            route = fi.get("route", "")
            title = fi.get("title", "")[:80]
            steps = "; ".join((fi.get("reproSteps") or [])[:2])
            ev = ""
            if fi.get("screenshot"):
                ev += f"[shot]({fi['screenshot']}) "
            if fi.get("consoleErrors"):
                ev += f"console({len(fi['consoleErrors'])}) "
            lines.append(f"| {sev} | {route} | {title} | {steps[:120]} | {ev.strip()} |")
        if len(all_explorer_issues) > 20:
            lines.append(f"| ... | | *{len(all_explorer_issues) - 20} more issues* | | |")
        lines.append("")

    # --- Business Smoke ---
    business_smoke = ctx.get("business_smoke") or {}
    exercise_smoke = business_smoke.get("exercise") if isinstance(business_smoke, dict) else None
    if exercise_smoke:
        ex_status = exercise_smoke.get("status", "NOT_RUN")
        ex_flow_details = exercise_smoke.get("flowDetails", {})
        lines.append("## Business Smoke: Exercise")
        lines.append("")
        if ex_status == "NOT_RUN":
            lines.append("Business smoke not yet executed. Run: `npx playwright test tests/h5/exercise-smoke.spec.js`")
        else:
            lines.append("| Flow | Status | Duration | Assertions | Evidence | Notes |")
            lines.append("|------|--------|----------|------------|----------|-------|")
            for flow_name in ("list", "search", "create", "edit", "validation", "apiFailure"):
                fd = ex_flow_details.get(flow_name, {})
                f_status = fd.get("status", "NOT_RUN")
                # Duration
                duration_ms = fd.get("durationMs", 0)
                duration_str = f"{duration_ms / 1000:.1f}s" if duration_ms else ""
                # Assertions
                assertions = fd.get("assertions", {})
                if assertions:
                    assertions_str = f"{assertions.get('passed', 0)}/{assertions.get('total', 0)} passed"
                else:
                    assertions_str = ""
                # Evidence
                evidence_list = fd.get("evidence", [])
                if evidence_list:
                    evidence_str = ", ".join(str(e) for e in evidence_list)
                else:
                    evidence_str = ""
                # Notes (error or manual notes)
                notes = fd.get("error", "").strip()
                lines.append(f"| {flow_name} | {f_status} | {duration_str} | {assertions_str} | {evidence_str} | {notes} |")
        lines.append("")

    # --- Environment Blocks ---
    env_blocks = ctx.get("environment_blocks") or []
    if env_blocks:
        lines.append("## Environment Blocks")
        lines.append("")
        lines.append("| Tool | Required | Status | Reason | Suggested Fix |")
        lines.append("|------|----------|--------|--------|---------------|")
        for eb in env_blocks:
            lines.append(
                f"| {eb.get('tool', '')} | {eb.get('required', False)} | "
                f"{eb.get('status', '')} | {eb.get('reason', '')} | {eb.get('fix', '')} |"
            )
        lines.append("")

    # --- Top Failures ---
    if top_failures:
        lines.append("## Top Failures")
        lines.append("")
        limited = top_failures[:10]
        for i, tf in enumerate(limited, 1):
            lines.append(f"### {i}. [{tf['status'].upper()}] {tf['test_name']}")
            lines.append(f"- **Tool**: {tf['tool']}")
            if tf.get("browser"):
                lines.append(f"- **Browser**: {tf['browser']}")
            if tf.get("error"):
                lines.append(f"- **Error**: {tf['error']}")
            if tf.get("screenshot"):
                lines.append(f"- **Screenshot**: `{tf['screenshot']}`")
            lines.append("")

    # --- Quality Gate ---
    if quality_gate:
        lines.append("## Quality Gate")
        lines.append("")
        lines.append(f"- **Profile**: {quality_gate.get('profile', 'N/A')}")
        gate_passed = quality_gate.get("passed", False)
        lines.append(f"- **Passed**: {gate_passed}")
        failures = quality_gate.get("failures", [])
        if failures:
            lines.append("- **Failures**:")
            for f in failures:
                lines.append(f"  - {f}")
        # Clarify divergence
        if gate_passed and overall_status == "failed":
            lines.append("")
            lines.append("> Note: Gate thresholds are met, but individual test failures exist. "
                         "Overall status is FAIL due to specific failing tests — see Top Failures below.")
        elif gate_passed and overall_status == "blocked":
            lines.append("")
            lines.append("> Note: Gate thresholds are met, but required tools are blocked. "
                         "Overall status is BLOCKED — see Environment Blocks below.")
        lines.append("")

    # --- Artifacts ---
    lines.append("## Evidence & Artifacts")
    lines.append("")
    lines.append(f"- Evidence JSON: `{base_dir}/evidence.json`")
    lines.append(f"- Regression Summary: `{base_dir}/regression-summary.json`")
    if allure_generation.get("status") == "PASS" and allure_generation.get("html_path"):
        lines.append(f"- Allure Report: `{allure_generation['html_path']}`")
    elif allure_generation:
        lines.append(
            f"- Allure HTML: `{allure_generation.get('status')}` "
            f"({allure_generation.get('reason', '')})"
        )
        lines.append(f"- Allure Generation Manifest: `{allure_generation.get('manifest_path', '')}`")
    else:
        lines.append(f"- Allure Report: `{base_dir}/allure-report/index.html`")
    lines.append(f"- Playwright Results: `reports/playwright-results.json`")
    lines.append(f"- Playwright Traces: `test-results/`")
    lines.append("")

    # --- Known Gaps ---
    lines.append("## Known Gaps")
    lines.append("")
    lines.append("- Playwright UI tests require FitTrack H5 admin running on localhost:5190")
    lines.append("- Explorer test requires the target pages to be accessible")
    lines.append("- MiniApp E2E tests require WeChat DevTools and miniprogram-automator")
    lines.append("- Maestro tests require Android emulator/device with APK installed")
    lines.append("- Sentry/Bugly monitors require API keys configured in .env")
    lines.append("")

    return "\n".join(lines)


def _compute_verdicts(stage_results: dict, quality_gate: dict, explorer_summary: dict,
                     auth_mode: str = "real") -> dict:
    """Derive machine-readable verdicts from stage_results, quality_gate, and auth_mode.

    Returns:
        dict with keys: implementation, runtimeExplorer, runtimeFullPipeline, codeReview
    """
    verdicts = {}

    # implementation: all non-h5_ui stages are ok → PASS, else BLOCKED
    non_h5_stages = {k: v for k, v in stage_results.items() if k != "h5_ui"}
    if non_h5_stages and all(sr.get("ok", True) for sr in non_h5_stages.values()):
        verdicts["implementation"] = "PASS"
    else:
        verdicts["implementation"] = "BLOCKED" if non_h5_stages else "PASS"

    # runtimeExplorer: h5_ui stage ok AND explorer has routesVisited > 0 → PASS
    h5_ui = stage_results.get("h5_ui", {})
    if h5_ui.get("ok", True) and explorer_summary.get("routesVisited", 0) > 0:
        verdicts["runtimeExplorer"] = "PASS"
    else:
        verdicts["runtimeExplorer"] = "BLOCKED"

    # runtimeFullPipeline: all stages ok AND gate passed AND auth is real → PASS
    # Injected auth means backend is unavailable → BLOCKED regardless of stages
    if auth_mode == "injected":
        verdicts["runtimeFullPipeline"] = "BLOCKED"
    else:
        all_stages_ok = all(sr.get("ok", True) for sr in stage_results.values()) if stage_results else True
        gate_passed = quality_gate.get("passed", True)
        if all_stages_ok and gate_passed:
            verdicts["runtimeFullPipeline"] = "PASS"
        else:
            verdicts["runtimeFullPipeline"] = "BLOCKED"

    # codeReview: from _code_review config or default PASS
    verdicts["codeReview"] = "PASS"

    return verdicts


def _compute_blockers(stage_results: dict, environment_blocks: list,
                     auth_mode: str = "real") -> list[dict]:
    """Generate blockers list from stage_results, environment_blocks, and auth_mode.

    Returns:
        list of blocker dicts with type, reason, recommendation
    """
    blockers = []

    # When auth is injected, the backend is unavailable → add top-priority blocker
    if auth_mode == "injected":
        blockers.append({
            "type": "backend_unavailable",
            "reason": "No local backend; using injected auth and API mocks for frontend exploration",
            "recommendation": "Start real backend or WeChat Cloud Functions integration",
        })

    # From stage_results: collect tools with blocked status
    for item in iter_public_tool_results(stage_results):
        if item["status"] != "blocked":
            continue
        detail = item.get("detail", {})
        reason = ""
        if isinstance(detail, dict):
            reason = detail.get("reason", detail.get("error", ""))
        blockers.append({
            "type": "tool_blocked",
            "reason": reason or f"Tool '{item['tool']}' blocked in stage '{item['stage']}'",
            "recommendation": f"Check {item['tool']} availability and re-run stage '{item['stage']}'",
        })

    # From environment_blocks: generate auth_guard type for missing backends
    for eb in environment_blocks:
        if eb.get("status") == "blocked":
            blockers.append({
                "type": "env_blocked",
                "reason": eb.get("reason", f"Tool {eb.get('tool', '')} environment not available"),
                "recommendation": eb.get("fix", "Check environment setup"),
            })

    return blockers


def _read_auth_mode(project_config: dict, explorer_auth_mode: str = None) -> str:
    """Read authMode with priority: explorer runtime > project_config > default 'real'.

    Explorer runtime data is authoritative — it records what ACTUALLY happened.
    Project config tells us what was configured.
    """
    if explorer_auth_mode:
        return explorer_auth_mode
    playwright_cfg = project_config.get("playwright", {})
    explorer_cfg = playwright_cfg.get("explorer", {})
    return explorer_cfg.get("authMode", "real")


def _load_business_smoke() -> dict:
    """Load business smoke results from reports/business-smoke/exercise-results.json.

    Returns a dict with the exercise smoke structure including summary, authMode,
    and per-flow details (durationMs, evidence, assertions counts, error notes).
    If the file does not exist, all flows default to NOT_RUN.
    """
    smoke_path = os.path.join("reports", "business-smoke", "exercise-results.json")
    default_flow_names = ["list", "search", "create", "edit", "validation", "apiFailure"]
    default_flows = {name: "NOT_RUN" for name in default_flow_names}
    default = {
        "exercise": {
            "status": "NOT_RUN",
            "flows": dict(default_flows),
            "issues": [],
        }
    }

    if not os.path.exists(smoke_path):
        return default

    try:
        with open(smoke_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return default

    flows_raw = data.get("flows", [])
    flows = {}
    flow_details = {}
    has_fail = False
    has_blocked = False

    for f_entry in flows_raw:
        flow_name = f_entry.get("flow", "")
        flow_status = f_entry.get("status", "NOT_RUN")
        flows[flow_name] = flow_status

        # Collect per-flow details
        details = {
            "status": flow_status,
            "durationMs": f_entry.get("durationMs", 0),
            "evidence": f_entry.get("evidence", []),
            "error": f_entry.get("error", ""),
        }
        # Count assertions passed/failed
        assertions = f_entry.get("assertions", [])
        if assertions:
            passed_assertions = sum(1 for a in assertions if a.get("passed", True))
            failed_assertions = len(assertions) - passed_assertions
            details["assertions"] = {
                "total": len(assertions),
                "passed": passed_assertions,
                "failed": failed_assertions,
            }
        else:
            details["assertions"] = {"total": 0, "passed": 0, "failed": 0}
        flow_details[flow_name] = details

        if flow_status == "FAIL":
            has_fail = True
        elif flow_status == "BLOCKED":
            has_blocked = True

    # Fill missing flows with NOT_RUN
    for key in default_flow_names:
        if key not in flows:
            flows[key] = "NOT_RUN"
            flow_details[key] = {
                "status": "NOT_RUN",
                "durationMs": 0,
                "evidence": [],
                "error": "",
                "assertions": {"total": 0, "passed": 0, "failed": 0},
            }

    # Derive overall exercise status
    if has_fail:
        overall = "FAIL"
    elif has_blocked:
        overall = "BLOCKED"
    elif all(v == "NOT_RUN" for v in flows.values()):
        overall = "NOT_RUN"
    else:
        overall = "PASS"

    result = {
        "exercise": {
            "status": overall,
            "flows": flows,
            "flowDetails": flow_details,
            "summary": data.get("summary", {}),
            "authMode": data.get("authMode", ""),
            "issues": data.get("issues", []),
        }
    }
    return result


def _detect_environment_blocks(stage_results: dict, project_name: str) -> list[dict]:
    """Detect tools that were blocked or skipped due to environment issues."""
    blocks = []

    tool_deps = {
        "playwright": {"fix": "Install: npm init playwright && npx playwright install"},
        "maestro": {"fix": "Install Maestro and connect Android device/emulator"},
        "airtest": {"fix": "Install Airtest IDE and connect device"},
        "miniprogram-automator": {"fix": "Open WeChat DevTools and enable automator port 9420"},
        "wetest": {"fix": "Configure WeTest cloud device pool"},
        "metersphere": {"fix": "Configure MeterSphere API endpoint"},
    }

    for item in iter_public_tool_results(stage_results):
        status = item["status"]
        if status not in ("blocked", "skipped"):
            continue
        detail = item.get("detail", {})
        reason = ""
        if isinstance(detail, dict):
            reason = detail.get("reason", detail.get("error", ""))
        deps = tool_deps.get(item["tool"], {"fix": "Check tool installation and configuration"})
        blocks.append({
            "tool": item["tool"],
            "stage": item["stage"],
            "required": status == "blocked",
            "status": status,
            "reason": reason,
            "fix": deps.get("fix", ""),
        })

    return blocks
