"""Workflow orchestrator — async sequential agent pipeline using MAF."""

import logging
from typing import Any

from src.agents.base_agent import AgentRunnable
from src.agents.categorize_agent import evaluate_risk
from src.agents.summarize_agent import summarize_risk
from src.config import Config
from src.errors import InvalidClientIdError
from src.models.input import CLIENT_ID_PATTERN, WorkflowInput
from src.models.output import WorkflowResult
from src.workflow.context import build_workflow_result

logger = logging.getLogger(__name__)


class RiskAssessmentWorkflow:
    """Orchestrates the sequential CategorizeRisk → Summarize pipeline.

    Uses Microsoft Agent Framework ``FoundryAgent`` instances to invoke
    pre-deployed prompt agents in Azure AI Foundry v2.
    """

    def __init__(
        self,
        categorize_agent: AgentRunnable,
        summarize_agent: AgentRunnable,
        config: Config | None = None,
    ):
        """
        Args:
            categorize_agent: A FoundryAgent connected to CategorizeRiskAgent.
            summarize_agent: A FoundryAgent connected to SummarizeAgent.
            config: Optional config; defaults are loaded from env.
        """
        self.config = config or Config()
        self._categorize_agent = categorize_agent
        self._summarize_agent = summarize_agent

    async def execute(self, client_id: str) -> WorkflowResult:
        """Run the full risk assessment workflow.

        Args:
            client_id: A valid client identifier (CLT-XXXXX).

        Returns:
            WorkflowResult with risk assessment and summary.

        Raises:
            InvalidClientIdError: If client_id format is wrong.
            WorkflowError: On any agent or handoff failure.
        """
        # --- Input validation ---
        if not CLIENT_ID_PATTERN.match(client_id):
            raise InvalidClientIdError(client_id)
        validated = WorkflowInput(client_id=client_id)

        logger.info(f"[WORKFLOW] Starting for client: {validated.client_id}")

        # --- Stage 1: Risk categorization (FoundryAgent) ---
        logger.info("[WORKFLOW] Stage 1: CategorizeRiskAgent")
        assessment = await evaluate_risk(
            self._categorize_agent,
            self.config.categorize_agent_name,
            validated.client_id,
        )

        # --- Stage 2: Summarization (FoundryAgent) ---
        logger.info("[WORKFLOW] Stage 2: SummarizeAgent")
        summary = await summarize_risk(
            self._summarize_agent,
            self.config.summarize_agent_name,
            assessment,
        )

        # --- Consolidate ---
        result = build_workflow_result(assessment, summary)
        logger.info(
            f"[WORKFLOW] Completed for client={result.client_id} "
            f"risk={result.risk_score}"
        )
        return result
