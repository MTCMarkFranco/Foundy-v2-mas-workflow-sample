"""SummarizeAgent wrapper with structured output parsing."""

import json
import logging
from typing import Any

from src.agents.base_agent import HostedAgentInvoker
from src.errors import AgentInvocationError
from src.models.output import RiskAssessment, SummaryOutput

logger = logging.getLogger(__name__)


class SummarizeAgentWrapper:
    """Wraps the SummarizeAgent hosted in Foundry v2.

    Receives the validated RiskAssessment from the categorize stage,
    passes structured context to the hosted agent, and parses the
    summary response.
    """

    def __init__(self, openai_client: Any, agent_name: str = "SummarizeAgent", version: str = "1"):
        self._invoker = HostedAgentInvoker(openai_client, agent_name, version)

    def summarize(self, assessment: RiskAssessment) -> SummaryOutput:
        """Generate a human-readable summary from a risk assessment.

        Raises:
            AgentInvocationError: On invocation or parsing failure.
        """
        # Pass only the validated structured data — no raw text
        context_json = assessment.model_dump_json(indent=2)

        prompt = (
            "Generate a professional risk assessment summary.\n\n"
            f"Risk Assessment Results:\n{context_json}\n\n"
            "Return your response as JSON matching this schema: "
            '{"client_id": str, "risk_score": str, '
            '"summary_markdown": str, "summary_plain_text": str, '
            '"key_findings": [str], "recommendations": [str], '
            '"urgency_level": "routine|elevated|immediate", '
            '"generated_timestamp": str}'
        )

        data = self._invoker.invoke_json(prompt)

        try:
            summary = SummaryOutput.model_validate(data)
        except Exception as e:
            raise AgentInvocationError(
                self._invoker.agent_name,
                f"Response does not match SummaryOutput schema: {e}",
            ) from e

        # Ensure consistency: summary risk_score must match assessment
        if summary.risk_score != assessment.risk_score:
            logger.warning(
                f"[AGENT:{self._invoker.agent_name}] Summary risk_score="
                f"'{summary.risk_score}' differs from assessment "
                f"'{assessment.risk_score}'. Overriding with assessment value."
            )
            summary.risk_score = assessment.risk_score

        logger.info(
            f"[AGENT:{self._invoker.agent_name}] Summary generated for "
            f"client={assessment.client_id} urgency={summary.urgency_level}"
        )
        return summary
