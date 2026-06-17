"""writelab_client.py — HTTP client for WriteLab Lite API (A7).

Connects to WriteLab Lite (localhost:8001 by default), calls analysis endpoints,
and converts results to PaperReviewIssue[] via the writelab_adapter.

Design:
  - Configurable base_url and Bearer token
  - Per-request timeout (default 30s for LLM diagnosis, 5s for expression-only)
  - Failure semantics: service unavailable -> degraded warning issue (non-blocking)
  - No raw text logging
  - Integrates with writelab_adapter for result conversion

Usage:
    client = WriteLabLiteClient(base_url="http://127.0.0.1:8001")
    issues = await client.diagnose_paragraph(
        text="段落文本...",
        expected_function="problem_statement",
        chapter="方法论",
        paragraph_index=0,
        runtime_authorization=runtime_authorization,
    )
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from ai_workflow_hub.context_layer.adapters.writelab_adapter import (
    convert_expression_results,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "http://127.0.0.1:8001"
DEFAULT_TIMEOUT_EXPRESSION = 5.0    # pure rules, fast
DEFAULT_TIMEOUT_DIAGNOSIS = 30.0    # may involve LLM
DEFAULT_HEALTH_TIMEOUT = 3.0
_PAPER_SENSITIVE_POLICY_EXPLICIT_ALLOW = "explicit_allow"
_PAPER_TEXT_FIELD = "paragraph_text"
_PRIVACY_GATE_REASON = "paper_sensitive_input_requires_runtime_authorization"


def _has_sensitive_input_authorization(
    runtime_authorization: dict[str, Any] | None,
    sensitive_fields: set[str],
) -> bool:
    """Check explicit RuntimeAuthorization before sending raw paper text."""
    if not isinstance(runtime_authorization, dict):
        return False
    if runtime_authorization.get("preflight_status") != "pass":
        return False
    if not runtime_authorization.get("human_gate_ref"):
        return False

    data_policy = runtime_authorization.get("data_policy")
    if not isinstance(data_policy, dict):
        return False
    if data_policy.get("paper_sensitive_input") != _PAPER_SENSITIVE_POLICY_EXPLICIT_ALLOW:
        return False
    if data_policy.get("redaction_required") is not True:
        return False

    allowed_fields = set(data_policy.get("allowed_sensitive_fields") or [])
    return sensitive_fields.issubset(allowed_fields)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class WriteLabCallResult:
    """Result of a WriteLab Lite API call."""
    success: bool
    issues: list[dict[str, Any]] = field(default_factory=list)
    diagnosis_source: str = "unknown"   # "llm" | "rules_fallback" | "degraded" | "unavailable" | "authorization_required"
    fallback_used: bool = False
    error: str | None = None
    version_info: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class WriteLabLiteClient:
    """Async HTTP client for WriteLab Lite API.

    Args:
        base_url: WriteLab Lite base URL (default: http://127.0.0.1:8001)
        token: Optional Bearer token for authentication
        timeout_expression: Timeout for expression-only detection (seconds)
        timeout_diagnosis: Timeout for paragraph diagnosis (seconds, may involve LLM)
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        token: str | None = None,
        timeout_expression: float = DEFAULT_TIMEOUT_EXPRESSION,
        timeout_diagnosis: float = DEFAULT_TIMEOUT_DIAGNOSIS,
        _client_factory: Callable[..., httpx.AsyncClient] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_expression = timeout_expression
        self.timeout_diagnosis = timeout_diagnosis
        self._version_cache: dict | None = None
        self._client_factory = _client_factory or httpx.AsyncClient

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def check_health(self) -> dict[str, Any]:
        """Check if WriteLab Lite is available.

        Returns health dict or raises on failure.
        """
        async with self._client_factory(timeout=DEFAULT_HEALTH_TIMEOUT) as client:
            resp = await client.get(f"{self.base_url}/health", headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    async def get_version(self) -> dict[str, Any]:
        """Get WriteLab Lite version info.

        Caches result for the lifetime of this client instance.
        """
        if self._version_cache is not None:
            return self._version_cache

        async with self._client_factory(timeout=DEFAULT_HEALTH_TIMEOUT) as client:
            resp = await client.get(f"{self.base_url}/version", headers=self._headers())
            resp.raise_for_status()
            self._version_cache = resp.json()
            return self._version_cache

    async def analyze_expression(
        self,
        text: str,
        chapter: str = "",
        section: str = "",
        paragraph_index: int = 0,
        runtime_authorization: dict[str, Any] | None = None,
    ) -> WriteLabCallResult:
        """Analyze expression risks only (fast, no LLM).

        Returns WriteLabCallResult with PaperReviewIssue[] in .issues.
        On failure, returns degraded result with a single warning issue.
        """
        auth_result = self._sensitive_input_authorization_result(
            text=text,
            chapter=chapter,
            section=section,
            paragraph_index=paragraph_index,
            runtime_authorization=runtime_authorization,
        )
        if auth_result is not None:
            return auth_result

        try:
            async with self._client_factory(timeout=self.timeout_expression) as client:
                resp = await client.post(
                    f"{self.base_url}/api/analyze/expression",
                    headers=self._headers(),
                    json={"paragraph": text},
                )
                resp.raise_for_status()
                data = resp.json()

            # Convert WriteLab response to adapter-compatible dicts
            report = data.get("expression_report", {})
            risks = report.get("risks", [])

            # Enrich with location info for adapter
            for i, risk in enumerate(risks):
                risk.setdefault("detection_id", f"live-{i:04d}")
                risk.setdefault("rule_id", risk.get("type", "UNKNOWN"))
                risk.setdefault("risk_level", risk.get("severity", "low"))
                risk.setdefault("chapter", chapter)
                risk.setdefault("section", section)
                risk.setdefault("paragraph_index", paragraph_index)
                risk.setdefault("rule_description", risk.get("explanation", ""))
                risk.setdefault("suggestion", "")
                risk.setdefault("matched_text", risk.get("text_span"))

            issues = convert_expression_results(risks)
            return WriteLabCallResult(
                success=True,
                issues=issues,
                diagnosis_source="rules_fallback",
                fallback_used=False,
            )

        except Exception as exc:
            logger.warning("WriteLab expression analysis failed: %s", exc)
            return self._degraded_result(str(exc))

    async def diagnose_paragraph(
        self,
        text: str,
        expected_function: str = "path_design",
        chapter: str = "",
        section: str = "",
        paragraph_index: int = 0,
        rewrite_goals: str | None = None,
        paper_context: str | None = None,
        runtime_authorization: dict[str, Any] | None = None,
    ) -> WriteLabCallResult:
        """Full paragraph diagnosis (expression + LLM paragraph diagnosis).

        Returns WriteLabCallResult with PaperReviewIssue[] in .issues.
        On failure, returns degraded result with a single warning issue.
        """
        auth_result = self._sensitive_input_authorization_result(
            text=text,
            chapter=chapter,
            section=section,
            paragraph_index=paragraph_index,
            runtime_authorization=runtime_authorization,
        )
        if auth_result is not None:
            return auth_result

        try:
            payload: dict[str, Any] = {
                "paragraph": text,
                "expected_function": expected_function,
            }
            if rewrite_goals:
                payload["rewrite_goals"] = rewrite_goals
            if paper_context:
                payload["paper_context"] = paper_context

            async with self._client_factory(timeout=self.timeout_diagnosis) as client:
                resp = await client.post(
                    f"{self.base_url}/api/analyze/paragraph-diagnosis",
                    headers=self._headers(),
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

            # Extract expression risks
            expr_report = data.get("expression_report", {})
            expr_risks = expr_report.get("risks", [])
            for i, risk in enumerate(expr_risks):
                risk.setdefault("detection_id", f"live-e{i:04d}")
                risk.setdefault("rule_id", risk.get("type", "UNKNOWN"))
                risk.setdefault("risk_level", risk.get("severity", "low"))
                risk.setdefault("chapter", chapter)
                risk.setdefault("section", section)
                risk.setdefault("paragraph_index", paragraph_index)
                risk.setdefault("rule_description", risk.get("explanation", ""))
                risk.setdefault("suggestion", "")
                risk.setdefault("matched_text", risk.get("text_span"))

            expr_issues = convert_expression_results(expr_risks)

            # Extract paragraph diagnosis
            diag = data.get("diagnosis", {})
            match_score = diag.get("function_match_score", 100)
            actual_fn = diag.get("actual_function", "")
            expected_fn = diag.get("expected_function", expected_function)

            # Determine diagnosis source from overall_comment
            comment = diag.get("overall_comment", "")
            if "降级" in comment or "LLM 未配置" in comment:
                diag_source = "rules_fallback"
                fallback_used = True
            elif "placeholder" in actual_fn:
                diag_source = "degraded"
                fallback_used = True
            else:
                diag_source = "llm"
                fallback_used = False

            # Build paragraph issue
            para_issues: list[dict[str, Any]] = []
            problems = diag.get("problems", [])
            if problems or match_score < 70:
                # Determine issue_type from problems
                issue_type = "structure"
                for p in problems:
                    if p.get("type") == "missing_evidence":
                        issue_type = "argument"
                        break

                # Confidence heuristic from match_score
                confidence = match_score / 100.0
                if confidence < 0.4:
                    severity = "major"
                elif confidence <= 0.6:
                    severity = "minor"
                else:
                    severity = "info"

                blocking = confidence < 0.4
                recommendation = ""
                if problems:
                    recommendation = problems[0].get("revision_direction", comment)
                else:
                    recommendation = comment

                para_issues.append({
                    "issue_id": f"wl-para-live-{paragraph_index:04d}",
                    "issue_type": issue_type,
                    "severity": severity,
                    "location": {
                        "chapter": chapter,
                        "section": section,
                        "paragraph_index": paragraph_index,
                    },
                    "evidence": (
                        f"段落功能不匹配: 期望={expected_fn}, 实际={actual_fn}, "
                        f"置信度={confidence:.2f}, 匹配分={match_score}"
                    ),
                    "recommendation": recommendation,
                    "blocking": blocking,
                    "human_required": False,
                })

            all_issues = expr_issues + para_issues
            return WriteLabCallResult(
                success=True,
                issues=all_issues,
                diagnosis_source=diag_source,
                fallback_used=fallback_used,
            )

        except Exception as exc:
            logger.warning("WriteLab paragraph diagnosis failed: %s", exc)
            return self._degraded_result(str(exc))

    def _sensitive_input_authorization_result(
        self,
        *,
        text: str,
        chapter: str,
        section: str,
        paragraph_index: int,
        runtime_authorization: dict[str, Any] | None,
    ) -> WriteLabCallResult | None:
        """Return a blocking privacy issue unless raw paper text is authorized."""
        if not text:
            return None
        if _has_sensitive_input_authorization(runtime_authorization, {_PAPER_TEXT_FIELD}):
            return None

        issue = {
            "issue_id": "wl-privacy-runtime-authorization-required",
            "issue_type": "privacy",
            "severity": "critical",
            "location": {
                "chapter": chapter,
                "section": section,
                "paragraph_index": paragraph_index,
            },
            "evidence": (
                "WriteLab live analysis was blocked before HTTP dispatch because "
                "raw paper text lacks explicit RuntimeAuthorization."
            ),
            "recommendation": (
                "Provide RuntimeAuthorization.data_policy.paper_sensitive_input="
                "explicit_allow with paragraph_text in allowed_sensitive_fields, "
                "redaction_required=true, and human_gate_ref before using live WriteLab."
            ),
            "blocking": True,
            "human_required": True,
        }
        return WriteLabCallResult(
            success=False,
            issues=[issue],
            diagnosis_source="authorization_required",
            fallback_used=False,
            error=_PRIVACY_GATE_REASON,
        )

    def _degraded_result(self, error_msg: str) -> WriteLabCallResult:
        """Return a degraded warning issue when WriteLab is unavailable.

        The issue is non-blocking (severity: info, blocking: false) so it
        does not stall the paper workflow.
        """
        warning_issue = {
            "issue_id": "wl-unavailable-0001",
            "issue_type": "expression",
            "severity": "info",
            "location": {"chapter": "", "section": "", "paragraph_index": 0},
            "evidence": f"WriteLab service unavailable: {error_msg[:200]}",
            "recommendation": "WriteLab diagnosis skipped; paper workflow continues without it",
            "blocking": False,
            "human_required": False,
        }
        return WriteLabCallResult(
            success=False,
            issues=[warning_issue],
            diagnosis_source="unavailable",
            fallback_used=True,
            error=error_msg,
        )
