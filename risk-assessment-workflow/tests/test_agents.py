"""Tests for the async agent helpers and agent-specific functions."""

import json
from unittest.mock import AsyncMock

import pytest

from src.agents.base_agent import invoke_agent, invoke_agent_json, strip_code_fence
from src.agents.categorize_agent import (
    compute_risk_score,
    evaluate_risk,
)
from src.agents.summarize_agent import summarize_risk
from src.errors import AgentInvocationError
from src.models.output import RiskAssessment, RuleEvaluation


# ── Helpers ──────────────────────────────────────────────────────────

def _mock_agent(response_text: str) -> AsyncMock:
    """Create a mock agent whose run() returns the given text."""
    agent = AsyncMock()
    agent.run.return_value = response_text
    return agent


# ── invoke_agent / invoke_agent_json ─────────────────────────────────

class TestInvokeAgent:
    @pytest.mark.asyncio
    async def test_invoke_returns_text(self):
        agent = _mock_agent("hello")
        result = await invoke_agent(agent, "TestAgent", "msg")
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_invoke_calls_agent_run(self):
        agent = _mock_agent("ok")
        await invoke_agent(agent, "MyAgent", "test prompt")
        agent.run.assert_awaited_once_with("test prompt")

    @pytest.mark.asyncio
    async def test_invoke_json_parses_json(self):
        payload = {"client_id": "CLT-10001", "risk_score": "Low"}
        agent = _mock_agent(json.dumps(payload))
        result = await invoke_agent_json(agent, "A", "x")
        assert result == payload

    @pytest.mark.asyncio
    async def test_invoke_json_strips_code_fence(self):
        payload = {"key": "value"}
        fenced = f"```json\n{json.dumps(payload)}\n```"
        agent = _mock_agent(fenced)
        result = await invoke_agent_json(agent, "A", "x")
        assert result == payload

    @pytest.mark.asyncio
    async def test_invoke_json_raises_on_invalid_json(self):
        agent = _mock_agent("not json at all")
        with pytest.raises(AgentInvocationError, match="not valid JSON"):
            await invoke_agent_json(agent, "A", "x")

    @pytest.mark.asyncio
    async def test_invoke_wraps_unexpected_errors(self):
        agent = AsyncMock()
        agent.run.side_effect = RuntimeError("boom")
        with pytest.raises(AgentInvocationError, match="boom"):
            await invoke_agent(agent, "A", "x")


class TestStripCodeFence:
    def test_plain_json(self):
        assert strip_code_fence('{"a": 1}') == '{"a": 1}'

    def test_fenced_json(self):
        assert strip_code_fence('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_fenced_no_lang(self):
        assert strip_code_fence('```\n{"a": 1}\n```') == '{"a": 1}'


# ── compute_risk_score ───────────────────────────────────────────────

class TestComputeRiskScore:
    def test_no_failures_is_low(self):
        evals = [
            RuleEvaluation(rule_id="R1", rule_name="R1", passed=True, severity="Critical"),
        ]
        level, weighted, count = compute_risk_score(evals)
        assert level == "Low"
        assert weighted == 0
        assert count == 0

    def test_minor_failures_is_medium(self):
        evals = [
            RuleEvaluation(rule_id="R1", rule_name="R1", passed=False, severity="Minor"),
            RuleEvaluation(rule_id="R2", rule_name="R2", passed=False, severity="Major"),
        ]
        level, weighted, count = compute_risk_score(evals)
        assert level == "Medium"  # 1 + 2 = 3
        assert weighted == 3
        assert count == 2

    def test_boundary_five_is_medium(self):
        evals = [
            RuleEvaluation(rule_id="R1", rule_name="R1", passed=False, severity="Critical"),
            RuleEvaluation(rule_id="R2", rule_name="R2", passed=False, severity="Major"),
        ]
        level, weighted, _ = compute_risk_score(evals)
        assert level == "Medium"
        assert weighted == 5

    def test_boundary_six_is_high(self):
        evals = [
            RuleEvaluation(rule_id="R1", rule_name="R1", passed=False, severity="Critical"),
            RuleEvaluation(rule_id="R2", rule_name="R2", passed=False, severity="Critical"),
        ]
        level, weighted, _ = compute_risk_score(evals)
        assert level == "High"
        assert weighted == 6

    def test_empty_evaluations_is_low(self):
        level, weighted, count = compute_risk_score([])
        assert level == "Low"
        assert weighted == 0
        assert count == 0


# ── evaluate_risk ────────────────────────────────────────────────────

class TestEvaluateRisk:
    def _make_response(self, **overrides) -> str:
        data = {
            "client_id": "CLT-10001",
            "risk_score": "Low",
            "weighted_score": 0,
            "discrepancy_count": 0,
            "search_results": [],
            "rule_evaluations": [],
            "reasoning": "All clear.",
        }
        data.update(overrides)
        return json.dumps(data)

    @pytest.mark.asyncio
    async def test_evaluate_low_risk(self):
        agent = _mock_agent(self._make_response())
        result = await evaluate_risk(agent, "CategorizeRiskAgent", "CLT-10001")
        assert result.client_id == "CLT-10001"
        assert result.risk_score == "Low"

    @pytest.mark.asyncio
    async def test_evaluate_recomputes_score_locally(self):
        """If model says Low but rules say High, local computation wins."""
        data = {
            "client_id": "CLT-30003",
            "risk_score": "Low",  # Model is wrong
            "weighted_score": 0,
            "discrepancy_count": 0,
            "search_results": [],
            "rule_evaluations": [
                {"rule_id": "C1", "rule_name": "KYC", "passed": False,
                 "severity": "Critical", "details": "expired"},
                {"rule_id": "C5", "rule_name": "Watchlist", "passed": False,
                 "severity": "Critical", "details": "flagged"},
            ],
            "reasoning": "Issues found.",
        }
        agent = _mock_agent(json.dumps(data))
        result = await evaluate_risk(agent, "CategorizeRiskAgent", "CLT-30003")
        assert result.risk_score == "High"  # Locally corrected
        assert result.weighted_score == 6
        assert result.discrepancy_count == 2

    @pytest.mark.asyncio
    async def test_evaluate_invalid_json_raises(self):
        agent = _mock_agent("not json")
        with pytest.raises(AgentInvocationError):
            await evaluate_risk(agent, "CategorizeRiskAgent", "CLT-10001")

    @pytest.mark.asyncio
    async def test_evaluate_missing_fields_raises(self):
        agent = _mock_agent(json.dumps({"wrong": "schema"}))
        with pytest.raises(AgentInvocationError, match="schema"):
            await evaluate_risk(agent, "CategorizeRiskAgent", "CLT-10001")


# ── summarize_risk ───────────────────────────────────────────────────

class TestSummarizeRisk:
    def _make_summary_response(self, **overrides) -> str:
        data = {
            "client_id": "CLT-10001",
            "risk_score": "Low",
            "summary_markdown": "## Low Risk",
            "summary_plain_text": "Low Risk",
            "key_findings": ["All clear"],
            "recommendations": ["Standard review"],
            "urgency_level": "routine",
            "generated_timestamp": "2026-04-15T00:00:00Z",
        }
        data.update(overrides)
        return json.dumps(data)

    @pytest.mark.asyncio
    async def test_summarize_returns_summary(self):
        agent = _mock_agent(self._make_summary_response())
        assessment = RiskAssessment(client_id="CLT-10001", risk_score="Low")
        result = await summarize_risk(agent, "SummarizeAgent", assessment)
        assert result.client_id == "CLT-10001"
        assert result.urgency_level == "routine"

    @pytest.mark.asyncio
    async def test_summarize_overrides_mismatched_score(self):
        """If summarizer returns wrong risk_score, it's corrected."""
        agent = _mock_agent(
            self._make_summary_response(risk_score="High")
        )
        assessment = RiskAssessment(client_id="CLT-10001", risk_score="Low")
        result = await summarize_risk(agent, "SummarizeAgent", assessment)
        assert result.risk_score == "Low"  # Corrected to match assessment

    @pytest.mark.asyncio
    async def test_summarize_invalid_json_raises(self):
        agent = _mock_agent("not json")
        assessment = RiskAssessment(client_id="CLT-10001", risk_score="Low")
        with pytest.raises(AgentInvocationError):
            await summarize_risk(agent, "SummarizeAgent", assessment)
