"""Tests for the base HostedAgentInvoker and agent-specific wrappers."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.agents.base_agent import HostedAgentInvoker
from src.agents.categorize_agent import (
    CategorizeRiskAgentWrapper,
    compute_risk_score,
)
from src.agents.summarize_agent import SummarizeAgentWrapper
from src.errors import AgentInvocationError
from src.models.output import RiskAssessment, RuleEvaluation


# ── Helpers ──────────────────────────────────────────────────────────

def _mock_openai_client(response_text: str) -> MagicMock:
    """Create a mock openai client that returns the given text."""
    client = MagicMock()
    response = SimpleNamespace(output_text=response_text)
    client.responses.create.return_value = response
    return client


# ── HostedAgentInvoker ───────────────────────────────────────────────

class TestHostedAgentInvoker:
    def test_invoke_returns_text(self):
        client = _mock_openai_client("hello")
        invoker = HostedAgentInvoker(client, "TestAgent", "1")
        assert invoker.invoke("msg") == "hello"

    def test_invoke_sends_agent_reference(self):
        client = _mock_openai_client("ok")
        invoker = HostedAgentInvoker(client, "MyAgent", "2")
        invoker.invoke("test")
        call_kwargs = client.responses.create.call_args
        extra = call_kwargs.kwargs["extra_body"]["agent_reference"]
        assert extra["name"] == "MyAgent"
        assert extra["version"] == "2"
        assert extra["type"] == "agent_reference"

    def test_invoke_json_parses_json(self):
        payload = {"client_id": "CLT-10001", "risk_score": "Low"}
        client = _mock_openai_client(json.dumps(payload))
        invoker = HostedAgentInvoker(client, "A", "1")
        assert invoker.invoke_json("x") == payload

    def test_invoke_json_strips_code_fence(self):
        payload = {"key": "value"}
        fenced = f"```json\n{json.dumps(payload)}\n```"
        client = _mock_openai_client(fenced)
        invoker = HostedAgentInvoker(client, "A", "1")
        assert invoker.invoke_json("x") == payload

    def test_invoke_json_raises_on_invalid_json(self):
        client = _mock_openai_client("not json at all")
        invoker = HostedAgentInvoker(client, "A", "1")
        with pytest.raises(AgentInvocationError, match="not valid JSON"):
            invoker.invoke_json("x")

    def test_invoke_wraps_unexpected_errors(self):
        client = MagicMock()
        client.responses.create.side_effect = RuntimeError("boom")
        invoker = HostedAgentInvoker(client, "A", "1")
        with pytest.raises(AgentInvocationError, match="boom"):
            invoker.invoke("x")


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
        # 1 Critical (3) + 1 Major (2) = 5 → Medium
        evals = [
            RuleEvaluation(rule_id="R1", rule_name="R1", passed=False, severity="Critical"),
            RuleEvaluation(rule_id="R2", rule_name="R2", passed=False, severity="Major"),
        ]
        level, weighted, _ = compute_risk_score(evals)
        assert level == "Medium"
        assert weighted == 5

    def test_boundary_six_is_high(self):
        # 2 Critical (6) → High
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


# ── CategorizeRiskAgentWrapper ───────────────────────────────────────

class TestCategorizeRiskAgentWrapper:
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

    def test_evaluate_low_risk(self):
        client = _mock_openai_client(self._make_response())
        wrapper = CategorizeRiskAgentWrapper(client)
        result = wrapper.evaluate("CLT-10001")
        assert result.client_id == "CLT-10001"
        assert result.risk_score == "Low"

    def test_evaluate_recomputes_score_locally(self):
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
        client = _mock_openai_client(json.dumps(data))
        wrapper = CategorizeRiskAgentWrapper(client)
        result = wrapper.evaluate("CLT-30003")
        assert result.risk_score == "High"  # Locally corrected
        assert result.weighted_score == 6
        assert result.discrepancy_count == 2

    def test_evaluate_invalid_json_raises(self):
        client = _mock_openai_client("not json")
        wrapper = CategorizeRiskAgentWrapper(client)
        with pytest.raises(AgentInvocationError):
            wrapper.evaluate("CLT-10001")

    def test_evaluate_missing_fields_raises(self):
        client = _mock_openai_client(json.dumps({"wrong": "schema"}))
        wrapper = CategorizeRiskAgentWrapper(client)
        with pytest.raises(AgentInvocationError, match="schema"):
            wrapper.evaluate("CLT-10001")


# ── SummarizeAgentWrapper ────────────────────────────────────────────

class TestSummarizeAgentWrapper:
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

    def test_summarize_returns_summary(self):
        client = _mock_openai_client(self._make_summary_response())
        wrapper = SummarizeAgentWrapper(client)
        assessment = RiskAssessment(client_id="CLT-10001", risk_score="Low")
        result = wrapper.summarize(assessment)
        assert result.client_id == "CLT-10001"
        assert result.urgency_level == "routine"

    def test_summarize_overrides_mismatched_score(self):
        """If summarizer returns wrong risk_score, it's corrected."""
        client = _mock_openai_client(
            self._make_summary_response(risk_score="High")
        )
        wrapper = SummarizeAgentWrapper(client)
        assessment = RiskAssessment(client_id="CLT-10001", risk_score="Low")
        result = wrapper.summarize(assessment)
        assert result.risk_score == "Low"  # Corrected to match assessment

    def test_summarize_invalid_json_raises(self):
        client = _mock_openai_client("not json")
        wrapper = SummarizeAgentWrapper(client)
        assessment = RiskAssessment(client_id="CLT-10001", risk_score="Low")
        with pytest.raises(AgentInvocationError):
            wrapper.summarize(assessment)
