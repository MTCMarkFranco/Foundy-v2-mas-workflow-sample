"""Workflow orchestrator — sequential agent pipeline."""

import logging
from typing import Any

from src.agents.categorize_agent import CategorizeRiskAgentWrapper
from src.agents.summarize_agent import SummarizeAgentWrapper
from src.config import Config
from src.errors import InvalidClientIdError, WorkflowError
from src.models.input import CLIENT_ID_PATTERN, WorkflowInput
from src.models.output import WorkflowResult
from src.workflow.context import build_workflow_result

logger = logging.getLogger(__name__)


class RiskAssessmentWorkflow:
    """Orchestrates the sequential CategorizeRisk → Summarize pipeline.

    Uses the Foundry v2 ``azure-ai-projects`` SDK to call pre-deployed
    hosted agents.
    """

    def __init__(self, project_client: Any, config: Config | None = None):
        """
        Args:
            project_client: An ``AIProjectClient`` instance (or mock).
            config: Optional config; defaults are loaded from env.
        """
        self.config = config or Config()
        openai_client = project_client.get_openai_client()

        # One wrapper (and implicitly one openai_client ref) per agent
        self._categorize = CategorizeRiskAgentWrapper(
            openai_client,
            agent_name=self.config.categorize_agent_name,
            version=self.config.categorize_agent_version,
        )
        self._summarize = SummarizeAgentWrapper(
            openai_client,
            agent_name=self.config.summarize_agent_name,
            version=self.config.summarize_agent_version,
        )

    def execute(self, client_id: str) -> WorkflowResult:
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

        # --- Stage 1: Risk categorization ---
        logger.info("[WORKFLOW] Stage 1: CategorizeRiskAgent")
        assessment = self._categorize.evaluate(validated.client_id)

        # --- Stage 2: Summarization ---
        logger.info("[WORKFLOW] Stage 2: SummarizeAgent")
        summary = self._summarize.summarize(assessment)

        # --- Consolidate ---
        result = build_workflow_result(assessment, summary)
        logger.info(
            f"[WORKFLOW] Completed for client={result.client_id} "
            f"risk={result.risk_score}"
        )
        return result
