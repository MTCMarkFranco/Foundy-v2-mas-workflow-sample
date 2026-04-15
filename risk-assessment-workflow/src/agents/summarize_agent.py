"""SummarizeAgent wrapper with structured output parsing."""

import logging

from src.agents.base_agent import AgentRunnable, invoke_agent_json
from src.errors import AgentInvocationError
from src.models.output import RiskAssessment, SummaryOutput

logger = logging.getLogger(__name__)


async def summarize_risk(
    agent: AgentRunnable,
    agent_name: str,
    assessment: RiskAssessment,
) -> SummaryOutput:
    """Generate a human-readable summary from a risk assessment.

    Args:
        agent: A FoundryAgent (or any AgentRunnable) connected to SummarizeAgent.
        agent_name: Display name for logging.
        assessment: The validated RiskAssessment from the categorize stage.

    Returns:
        A validated SummaryOutput with risk_score consistency enforced.

    Raises:
        AgentInvocationError: On invocation or parsing failure.
    """
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

    data = await invoke_agent_json(agent, agent_name, prompt)

    try:
        summary = SummaryOutput.model_validate(data)
    except Exception as e:
        raise AgentInvocationError(
            agent_name,
            f"Response does not match SummaryOutput schema: {e}",
        ) from e

    # Ensure consistency: summary risk_score must match assessment
    if summary.risk_score != assessment.risk_score:
        logger.warning(
            f"[AGENT:{agent_name}] Summary risk_score="
            f"'{summary.risk_score}' differs from assessment "
            f"'{assessment.risk_score}'. Overriding with assessment value."
        )
        summary.risk_score = assessment.risk_score

    logger.info(
        f"[AGENT:{agent_name}] Summary generated for "
        f"client={assessment.client_id} urgency={summary.urgency_level}"
    )
    return summary
