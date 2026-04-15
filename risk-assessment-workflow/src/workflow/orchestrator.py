"""Workflow orchestrator — MAF SequentialBuilder pipeline."""

import json
import logging
from typing import Any

from agent_framework.orchestrations import SequentialBuilder

from src.agents.base_agent import strip_code_fence
from src.config import Config
from src.errors import AgentInvocationError, InvalidClientIdError, WorkflowError
from src.models.input import CLIENT_ID_PATTERN, WorkflowInput
from src.models.output import RiskAssessment, SummaryOutput, WorkflowResult
from src.workflow.context import build_workflow_result

logger = logging.getLogger(__name__)


class RiskAssessmentWorkflow:
    """Orchestrates the sequential CategorizeRisk → Summarize pipeline.

    Uses MAF ``SequentialBuilder`` to chain pre-deployed prompt agents in
    Azure AI Foundry v2.  The builder passes only agent responses between
    stages (``chain_only_agent_responses=True``).
    """

    def __init__(
        self,
        categorize_agent: Any,
        summarize_agent: Any,
        config: Config | None = None,
    ):
        self.config = config or Config()
        self._categorize_agent = categorize_agent
        self._summarize_agent = summarize_agent

    async def execute(self, client_id: str) -> WorkflowResult:
        """Run the full risk assessment workflow.

        A fresh ``SequentialBuilder`` workflow is created per call to
        avoid conversation state leaking between invocations.

        Raises:
            InvalidClientIdError: If client_id format is wrong.
            WorkflowError: On any agent or handoff failure.
        """
        if not CLIENT_ID_PATTERN.match(client_id):
            raise InvalidClientIdError(client_id)
        validated = WorkflowInput(client_id=client_id)

        logger.info(f"[WORKFLOW] Starting for client: {validated.client_id}")

        prompt = (
            f"Evaluate the risk profile for Client ID: {validated.client_id}. "
            "Query the knowledge base filtered by this Client ID, "
            "apply all risk assessment rules, and return your assessment "
            "as JSON matching this schema: "
            '{"client_id": str, "risk_score": "Low|Medium|High", '
            '"weighted_score": int, "discrepancy_count": int, '
            '"search_results": [...], "rule_evaluations": [...], "reasoning": str}'
        )

        # Build a fresh workflow per call to avoid state leakage
        workflow = SequentialBuilder(
            participants=[self._categorize_agent, self._summarize_agent],
            chain_only_agent_responses=True,
        ).build()

        logger.info("[WORKFLOW] Running SequentialBuilder pipeline")
        try:
            result = await workflow.run(prompt)
        except Exception as e:
            raise WorkflowError(f"SequentialBuilder execution failed: {e}") from e

        # Parse outputs — find assistant messages by role
        outputs = result.get_outputs()
        assistant_messages = self._extract_assistant_messages(outputs)

        if len(assistant_messages) < 2:
            raise WorkflowError(
                f"Expected 2 assistant responses, got {len(assistant_messages)}"
            )

        # Stage 1: Parse CategorizeRiskAgent response
        assessment = self._parse_assessment(
            assistant_messages[0], validated.client_id
        )
        logger.info(
            f"[WORKFLOW] CategorizeRiskAgent: risk={assessment.risk_score} "
            f"weighted={assessment.weighted_score}"
        )

        # Stage 2: Parse SummarizeAgent response
        summary = self._parse_summary(
            assistant_messages[1], assessment
        )
        logger.info(
            f"[WORKFLOW] SummarizeAgent: urgency={summary.urgency_level}"
        )

        result_out = build_workflow_result(assessment, summary)
        logger.info(
            f"[WORKFLOW] Completed for client={result_out.client_id} "
            f"risk={result_out.risk_score}"
        )
        return result_out

    @staticmethod
    def _extract_assistant_messages(outputs: list) -> list[str]:
        """Extract assistant message texts from workflow outputs."""
        texts: list[str] = []
        for item in outputs:
            if isinstance(item, list):
                for msg in item:
                    if hasattr(msg, "role") and msg.role == "assistant":
                        texts.append(msg.text)
            elif hasattr(item, "role") and item.role == "assistant":
                texts.append(item.text)
        return texts

    @staticmethod
    def _parse_assessment(raw_text: str, client_id: str) -> RiskAssessment:
        """Parse and validate CategorizeRiskAgent JSON output."""
        try:
            data = json.loads(strip_code_fence(raw_text))
            assessment = RiskAssessment.model_validate(data)
        except (json.JSONDecodeError, Exception) as e:
            raise AgentInvocationError(
                "CategorizeRiskAgent",
                f"Failed to parse assessment: {e}",
            ) from e

        if assessment.client_id != client_id:
            raise AgentInvocationError(
                "CategorizeRiskAgent",
                f"client_id mismatch: expected {client_id}, "
                f"got {assessment.client_id}",
            )
        return assessment

    @staticmethod
    def _parse_summary(
        raw_text: str, assessment: RiskAssessment
    ) -> SummaryOutput:
        """Parse and validate SummarizeAgent JSON output."""
        try:
            data = json.loads(strip_code_fence(raw_text))
            summary = SummaryOutput.model_validate(data)
        except (json.JSONDecodeError, Exception) as e:
            raise AgentInvocationError(
                "SummarizeAgent",
                f"Failed to parse summary: {e}",
            ) from e

        # Cross-stage consistency checks
        if summary.client_id != assessment.client_id:
            logger.warning(
                f"[WORKFLOW] Summary client_id mismatch: "
                f"'{summary.client_id}' vs '{assessment.client_id}'. Correcting."
            )
            summary.client_id = assessment.client_id

        if summary.risk_score != assessment.risk_score:
            logger.warning(
                f"[WORKFLOW] Summary risk_score='{summary.risk_score}' "
                f"differs from assessment '{assessment.risk_score}'. Correcting."
            )
            summary.risk_score = assessment.risk_score

        return summary
