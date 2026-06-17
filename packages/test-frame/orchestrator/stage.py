"""Stage执行器 — 单个测试阶段的执行逻辑"""

import subprocess
import json
import os
import re
import sys
import traceback
import importlib
from datetime import datetime
from schema.canonical import VALID_STATUSES
from schema.stage_results import (
    is_internal_stage_result_key as _is_internal_stage_result_key,
    iter_public_tool_results,
)


# Status constants: passed | failed | skipped | blocked
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_BLOCKED = "blocked"
STATUS_ERROR = "error"
STATUS_CANCELLED = "cancelled"

# Sensitive field patterns for redaction (case-insensitive keys and value patterns)
_SENSITIVE_KEY_PATTERNS = [
    "api_key", "api_secret", "apikey", "secret_key", "secret",
    "token", "access_token", "refresh_token", "auth_token",
    "password", "passwd", "credential",
]
_SENSITIVE_VALUE_PATTERN = re.compile(
    r'(?i)(?:api[_-]?key|token|secret|password)=([^\s,;)"\'<>]+)'
)


def _sanitize_error(obj):
    """Recursively redact sensitive fields from error detail before storage.

    Handles strings, dicts, and lists-of-dicts. Non-sensitive types pass through.
    """
    if isinstance(obj, str):
        return _SENSITIVE_VALUE_PATTERN.sub(
            lambda m: m.group(0).replace(m.group(1), "[REDACTED]"),
            obj,
        )
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]" if any(
                pattern in k.lower() for pattern in _SENSITIVE_KEY_PATTERNS
            ) else _sanitize_error(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_sanitize_error(item) for item in obj]
    return obj


# Domain note: wrapper return contract
# Wrappers currently use two different conventions:
#   1. 'passed'/'skipped' booleans (most wrappers: maestro, airtest, playwright, miniapp,
#      metersphere, wetest, pytest_api, sentry)
#   2. 'status' string key (a few wrappers, e.g., bugly)
# _derive_status handles both, preferring 'status', then 'skipped', then 'passed'.
# TODO(2026-05-29): unify all wrappers to return {'status': str, 'reason': str, ...}
# and remove the dual-convention fallback in _derive_status.
#
def _derive_status(result: dict) -> str:
    """Derive status string from wrapper result dict.

    Accepts explicit status key in VALID_STATUSES.
    Falls back to legacy passed/skipped boolean keys.
    If no status-indicating key is present, returns FAILED.
    """
    raw_status = result.get("status")

    if raw_status in VALID_STATUSES:
        return raw_status

    if result.get("skipped") is True:
        return STATUS_SKIPPED

    if result.get("passed") is True:
        return STATUS_PASSED

    return STATUS_FAILED

def _stage_results_to_gate_format(stage_results: dict) -> list[dict]:
    """Convert orchestrator _stage_results to gate_check-compatible list[dict].

    _stage_results shape:
        {stage_name: {"ok": bool, "tools": {"tool_a": "passed", "tool_b": "failed", ...}}}

    Returns flat list:
        [{"status": "passed", "tool": "tool_a", "stage": "stage_name"}, ...]
    """
    return [
        {
            "status": item["status"],
            "tool": item["tool"],
            "stage": item["stage"],
        }
        for item in iter_public_tool_results(stage_results)
    ]

def _canonical_results_to_gate_format(results: list[dict]) -> list[dict]:
    """Convert CanonicalTestResult list to gate_check-compatible flat list.

    Each result is a CanonicalTestResult. The output preserves all 6 status
    fields for future gate use, while maintaining backward compatibility with
    the current 4-status gate (evaluate ignores error/cancelled for now).

    Args:
        results: list of CanonicalTestResult dicts (from normalizers).

    Returns:
        Flat list: [{"status": "failed", "tool": "playwright", "stage": "regression", ...}, ...]
    """
    gate_items = []

    for result in results:
        summary = result.get("summary", {})
        tool = result.get("tool", {})

        gate_items.append({
            "status": result["status"],
            "tool": tool.get("name", "unknown"),
            "stage": result.get("stage", "unknown"),

            # Full 6-state counts for future gate config
            "total": summary.get("total", 0),
            "passed": summary.get("passed", 0),
            "failed": summary.get("failed", 0),
            "skipped": summary.get("skipped", 0),
            "error": summary.get("error", 0),
            "blocked": summary.get("blocked", 0),
            "cancelled": summary.get("cancelled", 0),

            "test_pass_rate": summary.get("test_pass_rate"),

            # Quality signals and issues for richer gate evaluation
            "signals": result.get("signals", []),
            "issues": result.get("issues", []),
        })

    return gate_items



def _status_ok(status: str) -> bool:
    """A stage is OK if all tools are passed or skipped (not failed or blocked)."""
    return status in (STATUS_PASSED, STATUS_SKIPPED)


class Stage:
    def __init__(self, name: str, config: dict, project_config: dict, index: int):
        self.name = name
        self.config = config
        self.project_config = project_config
        self.index = index
        self.results = {}
        self._run_id = f'run-{datetime.now().strftime("%Y%m%d-%H%M%S")}-{name}'

    def execute(self) -> bool:
        """执行stage，返回是否通过"""
        tools = self.config.get("tools", [])
        timeout = self.config.get("timeout", 300)
        retry = self.config.get("retry", 0)
        parallel = self.config.get("parallel", False)
        if parallel:
            print(f"  [WARN] 'parallel' flag is not yet implemented, tools run sequentially; set to False to suppress this warning")

        if self.name == "evidence":
            return self._run_evidence()
        elif self.name == "report":
            return self._run_report()
        elif self.name == "attribution":
            return self._run_attribution()
        elif self.name == "gate":
            return self._run_gate()

        all_ok = True
        for tool in tools:
            status = self._run_tool(tool, retry)
            self.results[tool] = status
            if not _status_ok(status):
                all_ok = False

        return all_ok

    def _run_tool(self, tool: str, retry: int) -> str:
        """通过CLI wrapper执行单个工具，返回状态字符串

        retry_on (from stage config, default 'exception'):
          - exception: retry only on exceptions
          - failed:    retry only when wrapper returns status=FAILED
          - both:      retry on both exceptions and FAILED status
        """
        wrapper_map = {
            "maestro": "cli.wrappers.maestro",
            "airtest": "cli.wrappers.airtest",
            "playwright": "cli.wrappers.playwright",
            "miniprogram-automator": "cli.wrappers.miniapp",
            "metersphere": "cli.wrappers.metersphere",
            "pytest_api": "cli.wrappers.pytest_api",
            "wetest": "cli.wrappers.wetest",
        }

        module_name = wrapper_map.get(tool)
        if module_name is None:
            print(f"  [WARN] 未知工具: {tool} → BLOCKED")
            self.results[tool] = STATUS_BLOCKED
            self.results[f"{tool}_detail"] = {
                "status": STATUS_BLOCKED,
                "reason": "unknown_tool",
                "tool": tool,
            }
            return STATUS_BLOCKED

        retry_on = self.config.get("retry_on", "exception")
        if retry_on not in ("exception", "failed", "both"):
            print(f"  [WARN] Invalid retry_on='{retry_on}', falling back to 'exception'")
            retry_on = "exception"

        for attempt in range(retry + 1):
            if attempt > 0:
                print(f"  [RETRY] {tool} 第{attempt}次重试...")

            print(f"  [{tool}] 执行中...")
            try:
                module = importlib.import_module(module_name)
                result = module.run(self.project_config)
                status = _derive_status(result)
                self.results[f"{tool}_detail"] = result
                # Normalize to CanonicalTestResult (parallel path)
                try:
                    from normalizers.wrapper import normalize_wrapper_dict
                    _ctx = {
                        "run_id": self._run_id,
                        "stage": self.name,
                        "tool_name": tool,
                        "adapter_type": "wrapper",
                        "suite_name": f"{self.name}-{tool}",
                    }
                    canonical = normalize_wrapper_dict(result, _ctx)
                    self.results[f"{tool}_canonical"] = canonical
                except Exception as _norm_err:
                    self.results[f"{tool}_canonical_error"] = str(_norm_err)

                # Retry on FAILED status when configured
                if status == STATUS_FAILED and retry_on in ("failed", "both") and attempt < retry:
                    print(f"  [{tool}] [FAIL] retrying ({attempt + 1}/{retry})...")
                    continue

                if status == STATUS_PASSED:
                    print(f"  [{tool}] [OK] passed")
                elif status == STATUS_SKIPPED:
                    print(f"  [{tool}] [SKIP] skipped: {result.get('reason', '')}")
                elif status == STATUS_BLOCKED:
                    print(f"  [{tool}] [BLOCKED] {result.get('reason', '')}")
                elif status == STATUS_FAILED:
                    failed = result.get("failed", [])
                    print(f"  [{tool}] [FAIL] failed: {failed}")
                return status

            except ImportError:
                print(f"  [{tool}] [BLOCKED] module not installed")
                self.results[f"{tool}_detail"] = {
                    "status": STATUS_BLOCKED,
                    "reason": "module_not_installed",
                    "tool": tool,
                }
                return STATUS_BLOCKED
            except Exception as e:
                print(f"  [{tool}] [FAIL] exception: {e}")
                if retry_on in ("exception", "both") and attempt < retry:
                    continue
                self.results[f"{tool}_detail"] = {
                    "status": STATUS_FAILED,
                    "error": _sanitize_error(str(e)),
                    "traceback": _sanitize_error(traceback.format_exc()),
                    "tool": tool,
                }
                return STATUS_FAILED

        return STATUS_FAILED

    def _run_evidence(self) -> bool:
        """收集证据 — 返回实际状态，失败不再静默"""
        from evidence.collector import EvidenceCollector
        try:
            collector = EvidenceCollector(self.project_config.get("project", {}).get("name"))
            collector.collect()
            return True
        except Exception as e:
            print(f"  [EVIDENCE] [FAIL] 证据收集异常: {e}")
            self.results["evidence"] = STATUS_FAILED
            self.results["evidence_detail"] = {
                "status": STATUS_FAILED,
                "error": _sanitize_error(str(e)),
                "traceback": traceback.format_exc(),
            }
            return False

    def _run_report(self) -> bool:
        """生成报告 — 返回实际状态，失败不再静默"""
        from aggregator.collector import collect_and_generate

        try:
            project_name = self.project_config.get("project", {}).get("name", "unknown")
            stage_results = self.project_config.get("_stage_results", {})
            playwright_config = self.project_config.get("playwright", {})
            base_url = playwright_config.get("base_url", "")
            profile_name = self.project_config.get("_profile", "")

            report_result = collect_and_generate(
                project_name,
                project_config=self.project_config,
                stage_results=stage_results,
                profile=profile_name,
                base_url=base_url,
            )
            report_config = self.project_config.get("report", {})
            html_required = report_config.get("html_required", True)

            if report_result.status == "PASS":
                self.results["report"] = STATUS_PASSED
            elif report_result.status == "BLOCKED":
                self.results["report"] = (
                    STATUS_BLOCKED if html_required else STATUS_SKIPPED
                )
            else:
                self.results["report"] = STATUS_FAILED
            self.results["report_detail"] = {
                "status": self.results["report"],
                "allure_status": report_result.status,
                "reason": report_result.reason,
                "manifest_path": report_result.manifest_path,
                "html_path": report_result.html_path,
                "html_required": html_required,
                "machine_readable_evidence_only": (
                    report_result.status == "BLOCKED" and not html_required
                ),
            }
            return report_result.status == "PASS" or (
                report_result.status == "BLOCKED" and not html_required
            )
        except Exception as e:
            print(f"  [REPORT] [FAIL] 报告生成异常: {e}")
            self.results["report"] = STATUS_FAILED
            self.results["report_detail"] = {
                "status": STATUS_FAILED,
                "error": _sanitize_error(str(e)),
                "traceback": traceback.format_exc(),
            }
            return False

    def _run_attribution(self) -> bool:
        """缺陷归因 — 返回实际状态，失败不再静默"""
        from attribution.engine import AttributionEngine
        try:
            engine = AttributionEngine()
            engine.generate_report(
                self.project_config.get("project", {}).get("name"),
                self.project_config.get("report", {}).get("results_dir")
            )
            return True
        except Exception as e:
            print(f"  [ATTR] [FAIL] 缺陷归因异常: {e}")
            self.results["attribution"] = STATUS_FAILED
            self.results["attribution_detail"] = {
                "status": STATUS_FAILED,
                "error": _sanitize_error(str(e)),
                "traceback": traceback.format_exc(),
            }
            return False

    def _run_gate(self) -> bool:
        """质量门禁 — 优先使用 orchestrator 执行结果，而非重新从 adapter 收集"""
        print("  [GATE] Evaluating quality gate...")
        from aggregator.collector import collect_all_results
        from orchestrator.gate import gate_check

        profile_name = self.project_config.get("_gate_profile",
                    self.project_config.get("report", {}).get("gate_profile", "pr"))
        project_name = self.project_config.get("project", {}).get("name", "unknown")

        # Primary: use orchestrator's executed stage results (单数据源)
        stage_results = self.project_config.get("_stage_results", {})
        if stage_results:
            all_results = _stage_results_to_gate_format(stage_results)
            for r in all_results:
                r["_source"] = "orchestrator"
        else:
            # Fallback: re-collect from adapters (only when no stage results exist)
            print("  [GATE] No stage results, falling back to adapter collect...")
            all_results = collect_all_results(self.project_config)
            for r in all_results:
                r["_source"] = "adapter_fallback"

        passed, report = gate_check(profile_name, project_name, all_results)

        print(report)
        return passed
