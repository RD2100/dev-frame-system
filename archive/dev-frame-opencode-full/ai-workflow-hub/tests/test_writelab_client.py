"""test_writelab_client.py — A7 WriteLab Lite HTTP client integration tests.

Tests the Paper Domain -> WriteLab Lite HTTP integration:
  - Successful expression analysis
  - Successful paragraph diagnosis
  - Service unavailable degradation
  - Timeout handling
  - Bearer token auth headers
  - Result conversion to PaperReviewIssue[]

Uses dependency injection (_client_factory) with httpx.MockTransport
to avoid async mocking issues with unittest.mock.patch.
"""

import json
import pytest
import httpx

from ai_workflow_hub.context_layer.adapters.writelab_client import (
    WriteLabLiteClient,
    WriteLabCallResult,
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT_EXPRESSION,
    DEFAULT_TIMEOUT_DIAGNOSIS,
)


# ---------------------------------------------------------------------------
# Mock transport helper
# ---------------------------------------------------------------------------

def make_mock_transport(responses: dict[str, httpx.Response]):
    """Create a mock httpx transport that returns predefined responses.

    Args:
        responses: dict mapping "METHOD URL" to httpx.Response
    """
    def handler(request: httpx.Request) -> httpx.Response:
        key = f"{request.method} {request.url}"
        for pattern, response in responses.items():
            if pattern in key:
                return response
        return httpx.Response(404, json={"detail": "not found"})
    return httpx.MockTransport(handler)


def make_client_with_mock(
    responses: dict[str, httpx.Response],
    **kwargs,
) -> WriteLabLiteClient:
    """Create a WriteLabLiteClient backed by MockTransport.

    Uses _client_factory dependency injection so no patching is needed.
    """
    transport = make_mock_transport(responses)

    def factory(**kw):
        return httpx.AsyncClient(transport=transport)

    return WriteLabLiteClient(_client_factory=factory, **kwargs)


# Mock expression response (mimics WriteLab Lite /api/analyze/expression)
MOCK_EXPR_RESPONSE = {
    "expression_report": {
        "sentence_count": 3,
        "avg_sentence_length": 15.0,
        "abstract_noun_density": 0.2,
        "dunhao_density": 0.03,
        "template_sentence_count": 1,
        "normative_expression_count": 2,
        "ai_like_risk": "medium",
        "risks": [
            {
                "type": "句式模板",
                "severity": "medium",
                "text_span": "不是A而是B",
                "explanation": "检测到「不是而是结构」",
                "start_index": 5,
                "end_index": 15,
            }
        ],
    },
    "diagnosis": None,
}

# Mock paragraph diagnosis response
MOCK_PARA_RESPONSE = {
    "expression_report": {
        "sentence_count": 2,
        "avg_sentence_length": 20.0,
        "abstract_noun_density": 0.1,
        "dunhao_density": 0.02,
        "template_sentence_count": 0,
        "normative_expression_count": 1,
        "ai_like_risk": "low",
        "risks": [],
    },
    "diagnosis": {
        "actual_function": "抽象论述",
        "expected_function": "problem_statement",
        "function_match_score": 45,
        "main_claim": "教育政策需要系统化方法",
        "argument_chain": {
            "claim": "教育政策需要系统化方法",
            "explanation": "基于文献分析",
            "mechanism": "规则引擎无法推断",
            "evidence": "规则引擎无法推断",
            "landing": "规则引擎无法推断",
        },
        "problems": [
            {
                "type": "function_mismatch",
                "severity": "medium",
                "text_span": None,
                "explanation": "期望问题陈述，实为抽象论述",
                "revision_direction": "用具体问题替代抽象论述",
            }
        ],
        "overall_comment": "段落功能不匹配",
        "expression_report": None,
    },
}


# ===========================================================================
# TestClientConfig
# ===========================================================================
class TestClientConfig:

    def test_default_base_url(self):
        client = WriteLabLiteClient()
        assert client.base_url == DEFAULT_BASE_URL

    def test_custom_base_url(self):
        client = WriteLabLiteClient(base_url="http://localhost:9999/")
        assert client.base_url == "http://localhost:9999"  # trailing slash stripped

    def test_token_header(self):
        client = WriteLabLiteClient(token="test-token-123")
        headers = client._headers()
        assert headers["Authorization"] == "Bearer test-token-123"

    def test_no_token_header(self):
        client = WriteLabLiteClient()
        headers = client._headers()
        assert "Authorization" not in headers

    def test_default_timeouts(self):
        client = WriteLabLiteClient()
        assert client.timeout_expression == DEFAULT_TIMEOUT_EXPRESSION
        assert client.timeout_diagnosis == DEFAULT_TIMEOUT_DIAGNOSIS


# ===========================================================================
# TestAnalyzeExpression
# ===========================================================================
class TestAnalyzeExpression:

    @pytest.mark.asyncio
    async def test_successful_analysis(self):
        client = make_client_with_mock({"POST": httpx.Response(200, json=MOCK_EXPR_RESPONSE)})
        result = await client.analyze_expression(
            text="不是简单的否定，而是深层次的反思。",
            chapter="方法论",
            paragraph_index=2,
        )

        assert result.success is True
        assert len(result.issues) >= 1
        assert result.diagnosis_source == "rules_fallback"
        assert all(i["issue_id"].startswith("wl-expr-") for i in result.issues)

    @pytest.mark.asyncio
    async def test_issues_have_correct_schema(self):
        client = make_client_with_mock({"POST": httpx.Response(200, json=MOCK_EXPR_RESPONSE)})
        result = await client.analyze_expression(
            text="一方面改革，另一方面稳定。",
            chapter="引言",
            paragraph_index=0,
        )

        for issue in result.issues:
            assert "issue_id" in issue
            assert "issue_type" in issue
            assert issue["issue_type"] == "expression"
            assert "severity" in issue
            assert issue["severity"] in {"critical", "major", "minor", "info"}
            assert "blocking" in issue
            assert isinstance(issue["blocking"], bool)


# ===========================================================================
# TestDiagnoseParagraph
# ===========================================================================
class TestDiagnoseParagraph:

    @pytest.mark.asyncio
    async def test_successful_diagnosis(self):
        client = make_client_with_mock({"POST": httpx.Response(200, json=MOCK_PARA_RESPONSE)})
        result = await client.diagnose_paragraph(
            text="教育政策研究需要系统化的方法论框架。",
            expected_function="problem_statement",
            chapter="方法论",
            paragraph_index=0,
        )

        assert result.success is True
        assert len(result.issues) >= 1
        assert result.diagnosis_source == "llm"

    @pytest.mark.asyncio
    async def test_includes_paragraph_issue(self):
        client = make_client_with_mock({"POST": httpx.Response(200, json=MOCK_PARA_RESPONSE)})
        result = await client.diagnose_paragraph(
            text="应当采用混合方法进行数据分析。",
            expected_function="evidence_presentation",
            chapter="方法论",
            paragraph_index=1,
        )

        para_issues = [i for i in result.issues if i["issue_id"].startswith("wl-para-")]
        assert len(para_issues) >= 1
        pi = para_issues[0]
        assert pi["issue_type"] == "structure"  # function_mismatch
        assert pi["location"]["chapter"] == "方法论"

    @pytest.mark.asyncio
    async def test_fallback_detection(self):
        """Test that degraded/fallback responses are detected."""
        degraded_response = {
            "expression_report": MOCK_PARA_RESPONSE["expression_report"],
            "diagnosis": {
                "actual_function": "placeholder",
                "expected_function": "problem_statement",
                "function_match_score": 0,
                "main_claim": "",
                "argument_chain": {},
                "problems": [],
                "overall_comment": "规则引擎诊断（LLM 未配置）",
                "expression_report": None,
            },
        }
        client = make_client_with_mock({"POST": httpx.Response(200, json=degraded_response)})
        result = await client.diagnose_paragraph(
            text="测试文本",
            expected_function="problem_statement",
        )

        assert result.success is True
        assert result.fallback_used is True
        assert result.diagnosis_source in ("degraded", "rules_fallback")


# ===========================================================================
# TestServiceUnavailable
# ===========================================================================
class TestServiceUnavailable:

    @pytest.mark.asyncio
    async def test_connection_refused(self):
        """When WriteLab is down, client returns degraded warning issue."""
        client = WriteLabLiteClient(
            base_url="http://127.0.0.1:19999",  # nothing listening
            timeout_expression=1.0,
        )
        result = await client.analyze_expression(text="测试")

        assert result.success is False
        assert result.diagnosis_source == "unavailable"
        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue["issue_id"] == "wl-unavailable-0001"
        assert issue["blocking"] is False
        assert issue["severity"] == "info"
        assert "unavailable" in issue["evidence"].lower()

    @pytest.mark.asyncio
    async def test_degraded_is_non_blocking(self):
        """Degraded result must never block paper workflow."""
        client = WriteLabLiteClient(
            base_url="http://127.0.0.1:19999",
            timeout_expression=1.0,
        )
        result = await client.diagnose_paragraph(text="测试", expected_function="conclusion")

        assert result.success is False
        for issue in result.issues:
            assert issue["blocking"] is False

    @pytest.mark.asyncio
    async def test_http_500_degradation(self):
        """500 error from server triggers graceful degradation."""
        client = make_client_with_mock(
            {"POST": httpx.Response(500, json={"detail": "internal error"})}
        )
        result = await client.diagnose_paragraph(text="测试")

        assert result.success is False
        assert result.diagnosis_source == "unavailable"
        assert result.error is not None


# ===========================================================================
# TestIntegrationWithAdapter
# ===========================================================================
class TestIntegrationWithAdapter:

    @pytest.mark.asyncio
    async def test_issues_pass_schema_validation(self):
        """All issues from client must pass adapter schema validation."""
        from ai_workflow_hub.context_layer.adapters.writelab_adapter import validate_review_issue

        client = make_client_with_mock({"POST": httpx.Response(200, json=MOCK_PARA_RESPONSE)})
        result = await client.diagnose_paragraph(
            text="应当采用混合方法。",
            expected_function="evidence_presentation",
            chapter="方法论",
            paragraph_index=1,
        )

        for issue in result.issues:
            errors = validate_review_issue(issue)
            assert errors == [], f"Schema errors for {issue['issue_id']}: {errors}"

    @pytest.mark.asyncio
    async def test_all_issues_have_wl_prefix(self):
        client = make_client_with_mock({"POST": httpx.Response(200, json=MOCK_PARA_RESPONSE)})
        result = await client.diagnose_paragraph(
            text="一方面改革，另一方面稳定。",
            expected_function="problem_statement",
        )

        for issue in result.issues:
            assert issue["issue_id"].startswith("wl-"), f"Bad prefix: {issue['issue_id']}"


# ===========================================================================
# TestBearerToken
# ===========================================================================
class TestBearerToken:

    def test_token_included_in_headers(self):
        client = WriteLabLiteClient(token="my-secret-token")
        headers = client._headers()
        assert headers.get("Authorization") == "Bearer my-secret-token"
        assert headers.get("Content-Type") == "application/json"

    def test_no_token_when_not_set(self):
        client = WriteLabLiteClient()
        headers = client._headers()
        assert "Authorization" not in headers
