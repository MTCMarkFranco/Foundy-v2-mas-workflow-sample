"""Tests for data models (input validation and output schemas)."""

import pytest
from pydantic import ValidationError

from src.models.input import WorkflowInput
from src.models.output import (
    RiskAssessment,
    RuleEvaluation,
    SearchResult,
    SummaryOutput,
    WorkflowResult,
)


# ── Input validation ────────────────────────────────────────────────

class TestWorkflowInput:
    def test_valid_client_id(self):
        inp = WorkflowInput(client_id="CLT-10001")
        assert inp.client_id == "CLT-10001"

    @pytest.mark.parametrize("bad_id", [
        "", "CLT", "CLT-1", "CLT-123456", "XYZ-10001",
        "clt-10001", "CLT10001", "CLT-ABCDE",
    ])
    def test_invalid_client_ids(self, bad_id):
        with pytest.raises(ValidationError):
            WorkflowInput(client_id=bad_id)


# ── RiskAssessment model ────────────────────────────────────────────

class TestRiskAssessment:
    def test_minimal_valid(self):
        a = RiskAssessment(client_id="CLT-10001", risk_score="Low")
        assert a.weighted_score == 0
        assert a.discrepancy_count == 0
        assert a.search_results == []
        assert a.rule_evaluations == []

    def test_full_model(self):
        a = RiskAssessment(
            client_id="CLT-30003",
            risk_score="High",
            weighted_score=10,
            discrepancy_count=4,
            search_results=[
                SearchResult(document_id="DOC-1", relevance_score=0.95,
                             content_summary="summary", fields={"a": 1}),
            ],
            rule_evaluations=[
                RuleEvaluation(rule_id="C1", rule_name="Missing docs",
                               passed=False, severity="Critical",
                               details="KYC expired"),
            ],
            reasoning="Critical compliance issues.",
        )
        assert a.risk_score == "High"
        assert len(a.search_results) == 1
        assert len(a.rule_evaluations) == 1


# ── SummaryOutput model ─────────────────────────────────────────────

class TestSummaryOutput:
    def test_minimal(self):
        s = SummaryOutput(client_id="CLT-10001", risk_score="Low")
        assert s.urgency_level == "routine"
        assert s.key_findings == []

    def test_full(self):
        s = SummaryOutput(
            client_id="CLT-30003",
            risk_score="High",
            summary_markdown="# High Risk",
            summary_plain_text="High Risk",
            key_findings=["KYC expired"],
            recommendations=["Escalate"],
            urgency_level="immediate",
            generated_timestamp="2026-04-15T00:00:00Z",
        )
        assert s.urgency_level == "immediate"
        assert len(s.recommendations) == 1


# ── WorkflowResult model ────────────────────────────────────────────

class TestWorkflowResult:
    def test_construction(self):
        assessment = RiskAssessment(client_id="CLT-10001", risk_score="Low")
        summary = SummaryOutput(client_id="CLT-10001", risk_score="Low")
        result = WorkflowResult(
            client_id="CLT-10001",
            risk_score="Low",
            risk_assessment=assessment,
            summary=summary,
        )
        assert result.client_id == "CLT-10001"
        assert result.completed_at is not None
