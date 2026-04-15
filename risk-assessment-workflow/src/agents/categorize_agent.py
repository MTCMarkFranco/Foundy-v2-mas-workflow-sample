"""CategorizeRiskAgent wrapper with local risk score validation."""

import logging
from typing import Any

from src.agents.base_agent import HostedAgentInvoker
from src.errors import AgentInvocationError
from src.models.output import RiskAssessment, RuleEvaluation

logger = logging.getLogger(__name__)

# Severity weights per the scoring matrix in CATEGORIZE-RISK-AGENT.md
SEVERITY_WEIGHTS: dict[str, int] = {
    "Critical": 3,
    "Major": 2,
    "Minor": 1,
}


def compute_risk_score(rule_evaluations: list[RuleEvaluation]) -> tuple[str, int, int]:
    """Deterministically compute risk score from rule evaluations.

    Returns:
        (risk_level, weighted_score, discrepancy_count)
    """
    discrepancy_count = sum(1 for r in rule_evaluations if not r.passed)
    weighted_score = sum(
        SEVERITY_WEIGHTS.get(r.severity, 1)
        for r in rule_evaluations
        if not r.passed
    )

    if weighted_score == 0:
        risk_level = "Low"
    elif weighted_score <= 5:
        risk_level = "Medium"
    else:
        risk_level = "High"

    return risk_level, weighted_score, discrepancy_count


class CategorizeRiskAgentWrapper:
    """Wraps the CategorizeRiskAgent hosted in Foundry v2.

    Invokes the agent, parses the structured JSON response, and validates
    the risk score locally using the deterministic scoring matrix.
    """

    def __init__(self, openai_client: Any, agent_name: str = "CategorizeRiskAgent", version: str = "1"):
        self._invoker = HostedAgentInvoker(openai_client, agent_name, version)

    def evaluate(self, client_id: str) -> RiskAssessment:
        """Run risk categorization for a client.

        Raises:
            AgentInvocationError: On invocation or parsing failure.
        """
        prompt = (
            f"Evaluate the risk profile for Client ID: {client_id}. "
            "Query the knowledge base filtered by this Client ID, "
            "apply all risk assessment rules, and return your assessment "
            "as JSON matching this schema: "
            '{"client_id": str, "risk_score": "Low|Medium|High", '
            '"weighted_score": int, "discrepancy_count": int, '
            '"search_results": [...], "rule_evaluations": [...], "reasoning": str}'
        )

        data = self._invoker.invoke_json(prompt)

        try:
            assessment = RiskAssessment.model_validate(data)
        except Exception as e:
            raise AgentInvocationError(
                self._invoker.agent_name,
                f"Response does not match RiskAssessment schema: {e}",
            ) from e

        # Locally recompute the risk score for determinism
        if assessment.rule_evaluations:
            risk_level, weighted, discrepancies = compute_risk_score(
                assessment.rule_evaluations
            )
            if risk_level != assessment.risk_score:
                logger.warning(
                    f"[AGENT:{self._invoker.agent_name}] Model returned risk_score="
                    f"'{assessment.risk_score}' but local computation gives "
                    f"'{risk_level}' (weighted={weighted}). Using local value."
                )
            assessment.risk_score = risk_level
            assessment.weighted_score = weighted
            assessment.discrepancy_count = discrepancies

        logger.info(
            f"[AGENT:{self._invoker.agent_name}] client={client_id} "
            f"risk={assessment.risk_score} weighted={assessment.weighted_score}"
        )
        return assessment
