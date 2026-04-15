"""Tests for the workflow orchestrator using MAF SequentialBuilder."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.errors import AgentInvocationError, InvalidClientIdError, WorkflowError
from src.workflow.orchestrator import RiskAssessmentWorkflow


# ── Helpers ──────────────────────────────────────────────────────────

def _make_message(role: str, text: str):
    """Create a mock Message-like object."""
    return SimpleNamespace(role=role, text=text)


def _make_workflow_run_result(categorize_json: dict, summary_json: dict):
    """Create a mock WorkflowRunResult with get_outputs() returning messages."""
    messages = [
        _make_message("user", "Evaluate risk..."),
        _make_message("assistant", json.dumps(categorize_json)),
        _make_message("assistant", json.dumps(summary_json)),
    ]
    result = MagicMock()
    result.get_outputs.return_value = [messages]
    return result


# Sample agent responses for each test client
SAMPLE_CATEGORIZE_RESPONSES = {
    "CLT-10001": {
        "client_id": "CLT-10001",
        "risk_score": "Low",
        "weighted_score": 0,
        "discrepancy_count": 0,
        "search_results": [],
        "rule_evaluations": [
            {"rule_id": "C1", "rule_name": "Compliance docs", "passed": True,
             "severity": "Critical", "details": "All present"},
        ],
        "reasoning": "All documents current, no risk flags.",
    },
    "CLT-20002": {
        "client_id": "CLT-20002",
        "risk_score": "Medium",
        "weighted_score": 3,
        "discrepancy_count": 2,
        "search_results": [],
        "rule_evaluations": [
            {"rule_id": "D4", "rule_name": "Stale data", "passed": False,
             "severity": "Major", "details": "Ownership change pending"},
            {"rule_id": "C2", "rule_name": "Dates current", "passed": False,
             "severity": "Minor", "details": "ISO cert expiring soon"},
        ],
        "reasoning": "Pending ownership change and expiring certification.",
    },
    "CLT-30003": {
        "client_id": "CLT-30003",
        "risk_score": "High",
        "weighted_score": 10,
        "discrepancy_count": 4,
        "search_results": [],
        "rule_evaluations": [
            {"rule_id": "C1", "rule_name": "Compliance docs", "passed": False,
             "severity": "Critical", "details": "KYC expired"},
            {"rule_id": "C5", "rule_name": "Watchlist", "passed": False,
             "severity": "Critical", "details": "Regulatory investigation"},
        ],
        "reasoning": "Critical compliance issues.",
    },
    "CLT-40004": {
        "client_id": "CLT-40004",
        "risk_score": "Low",
        "weighted_score": 1,
        "discrepancy_count": 1,
        "search_results": [],
        "rule_evaluations": [
            {"rule_id": "D1", "rule_name": "Revenue flag", "passed": False,
             "severity": "Minor", "details": "Revenue decline noted"},
        ],
        "reasoning": "Minor revenue decline within threshold.",
    },
    "CLT-50005": {
        "client_id": "CLT-50005",
        "risk_score": "High",
        "weighted_score": 11,
        "discrepancy_count": 4,
        "search_results": [],
        "rule_evaluations": [
            {"rule_id": "C5", "rule_name": "Jurisdiction risk", "passed": False,
             "severity": "Critical", "details": "High-risk jurisdiction"},
            {"rule_id": "D5", "rule_name": "Transaction pattern", "passed": False,
             "severity": "Critical", "details": "Unusual transactions"},
        ],
        "reasoning": "High-risk jurisdiction, unusual transactions.",
    },
}

SAMPLE_SUMMARY = {
    "client_id": "CLT-10001",
    "risk_score": "Low",
    "summary_markdown": "## Risk Assessment\n\n**Risk**: Low",
    "summary_plain_text": "Risk Assessment - Low Risk",
    "key_findings": ["All compliance current"],
    "recommendations": ["Standard review cycle"],
    "urgency_level": "routine",
    "generated_timestamp": "2026-04-15T00:00:00Z",
}


def _patch_sequential_builder(categorize_json: dict, summary_json: dict):
    """Return a patch context manager that mocks SequentialBuilder."""
    mock_result = _make_workflow_run_result(categorize_json, summary_json)

    mock_workflow = AsyncMock()
    mock_workflow.run = AsyncMock(return_value=mock_result)

    mock_builder = MagicMock()
    mock_builder.return_value.build.return_value = mock_workflow

    return patch(
        "src.workflow.orchestrator.SequentialBuilder", mock_builder
    )


# ── Workflow tests ───────────────────────────────────────────────────

class TestRiskAssessmentWorkflow:
    @pytest.mark.asyncio
    async def test_execute_low_risk_client(self):
        cat = SAMPLE_CATEGORIZE_RESPONSES["CLT-10001"]
        summary = {**SAMPLE_SUMMARY, "client_id": "CLT-10001", "risk_score": "Low"}

        with _patch_sequential_builder(cat, summary):
            wf = RiskAssessmentWorkflow(MagicMock(), MagicMock())
            result = await wf.execute("CLT-10001")

        assert result.client_id == "CLT-10001"
        assert result.risk_score == "Low"
        assert result.summary.urgency_level == "routine"

    @pytest.mark.asyncio
    async def test_execute_medium_risk_client(self):
        cat = SAMPLE_CATEGORIZE_RESPONSES["CLT-20002"]
        summary = {**SAMPLE_SUMMARY, "client_id": "CLT-20002",
                    "risk_score": "Medium", "urgency_level": "elevated"}

        with _patch_sequential_builder(cat, summary):
            wf = RiskAssessmentWorkflow(MagicMock(), MagicMock())
            result = await wf.execute("CLT-20002")

        assert result.client_id == "CLT-20002"
        assert result.risk_score == "Medium"

    @pytest.mark.asyncio
    async def test_execute_high_risk_client(self):
        cat = SAMPLE_CATEGORIZE_RESPONSES["CLT-30003"]
        summary = {**SAMPLE_SUMMARY, "client_id": "CLT-30003",
                    "risk_score": "High", "urgency_level": "immediate"}

        with _patch_sequential_builder(cat, summary):
            wf = RiskAssessmentWorkflow(MagicMock(), MagicMock())
            result = await wf.execute("CLT-30003")

        assert result.client_id == "CLT-30003"
        assert result.risk_score == "High"

    @pytest.mark.asyncio
    async def test_invalid_client_id_raises(self):
        wf = RiskAssessmentWorkflow(MagicMock(), MagicMock())
        with pytest.raises(InvalidClientIdError):
            await wf.execute("INVALID")

    @pytest.mark.asyncio
    async def test_invalid_client_id_empty(self):
        wf = RiskAssessmentWorkflow(MagicMock(), MagicMock())
        with pytest.raises(InvalidClientIdError):
            await wf.execute("")

    @pytest.mark.asyncio
    async def test_builds_fresh_workflow_per_call(self):
        """Verify SequentialBuilder is called each time (no state leakage)."""
        cat = SAMPLE_CATEGORIZE_RESPONSES["CLT-10001"]
        summary = {**SAMPLE_SUMMARY}

        with _patch_sequential_builder(cat, summary) as mock_builder:
            wf = RiskAssessmentWorkflow(MagicMock(), MagicMock())
            await wf.execute("CLT-10001")
            await wf.execute("CLT-10001")

            assert mock_builder.call_count == 2

    @pytest.mark.asyncio
    async def test_chain_only_agent_responses_enabled(self):
        """Verify SequentialBuilder is created with chain_only_agent_responses=True."""
        cat = SAMPLE_CATEGORIZE_RESPONSES["CLT-10001"]
        summary = {**SAMPLE_SUMMARY}

        with _patch_sequential_builder(cat, summary) as mock_builder:
            wf = RiskAssessmentWorkflow(MagicMock(), MagicMock())
            await wf.execute("CLT-10001")

            call_kwargs = mock_builder.call_args[1]
            assert call_kwargs["chain_only_agent_responses"] is True

    @pytest.mark.asyncio
    async def test_summary_risk_score_corrected_to_match_assessment(self):
        """If summarizer returns wrong risk_score, it's corrected."""
        cat = SAMPLE_CATEGORIZE_RESPONSES["CLT-10001"]  # risk_score: Low
        summary = {**SAMPLE_SUMMARY, "risk_score": "High"}  # Wrong!

        with _patch_sequential_builder(cat, summary):
            wf = RiskAssessmentWorkflow(MagicMock(), MagicMock())
            result = await wf.execute("CLT-10001")

        assert result.risk_score == "Low"  # Corrected by consistency check
        assert result.summary.risk_score == "Low"

    @pytest.mark.asyncio
    async def test_insufficient_outputs_raises(self):
        """If workflow returns fewer than 2 assistant messages, raise."""
        messages = [_make_message("user", "test")]
        mock_result = MagicMock()
        mock_result.get_outputs.return_value = [messages]

        mock_workflow = AsyncMock()
        mock_workflow.run = AsyncMock(return_value=mock_result)

        mock_builder = MagicMock()
        mock_builder.return_value.build.return_value = mock_workflow

        with patch("src.workflow.orchestrator.SequentialBuilder", mock_builder):
            wf = RiskAssessmentWorkflow(MagicMock(), MagicMock())
            with pytest.raises(WorkflowError, match="Expected 2 assistant"):
                await wf.execute("CLT-10001")

    @pytest.mark.asyncio
    async def test_invalid_assessment_json_raises(self):
        """If CategorizeRiskAgent returns invalid JSON, raise."""
        messages = [
            _make_message("user", "test"),
            _make_message("assistant", "not json"),
            _make_message("assistant", json.dumps(SAMPLE_SUMMARY)),
        ]
        mock_result = MagicMock()
        mock_result.get_outputs.return_value = [messages]

        mock_workflow = AsyncMock()
        mock_workflow.run = AsyncMock(return_value=mock_result)

        mock_builder = MagicMock()
        mock_builder.return_value.build.return_value = mock_workflow

        with patch("src.workflow.orchestrator.SequentialBuilder", mock_builder):
            wf = RiskAssessmentWorkflow(MagicMock(), MagicMock())
            with pytest.raises(AgentInvocationError, match="CategorizeRiskAgent"):
                await wf.execute("CLT-10001")

    @pytest.mark.asyncio
    async def test_client_id_mismatch_raises(self):
        """If assessment client_id doesn't match input, raise."""
        cat = {**SAMPLE_CATEGORIZE_RESPONSES["CLT-10001"], "client_id": "CLT-99999"}
        summary = {**SAMPLE_SUMMARY}

        with _patch_sequential_builder(cat, summary):
            wf = RiskAssessmentWorkflow(MagicMock(), MagicMock())
            with pytest.raises(AgentInvocationError, match="client_id mismatch"):
                await wf.execute("CLT-10001")


# ── Golden fixture tests (all 5 sample clients) ─────────────────────

class TestGoldenFixtures:
    """Validate risk scoring matches model output (no local override)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("client_id,expected_risk", [
        ("CLT-10001", "Low"),
        ("CLT-20002", "Medium"),
        ("CLT-30003", "High"),
        ("CLT-40004", "Low"),
        ("CLT-50005", "High"),
    ])
    async def test_risk_score_matches_expected(self, client_id, expected_risk):
        cat = SAMPLE_CATEGORIZE_RESPONSES[client_id]
        summary = {**SAMPLE_SUMMARY, "client_id": client_id,
                    "risk_score": expected_risk}

        with _patch_sequential_builder(cat, summary):
            wf = RiskAssessmentWorkflow(MagicMock(), MagicMock())
            result = await wf.execute(client_id)

        assert result.risk_score == expected_risk
