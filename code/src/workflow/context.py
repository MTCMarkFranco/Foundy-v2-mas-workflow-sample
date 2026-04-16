"""Context management for agent handoff."""

from src.models.output import (
    AgentStageMetrics,
    RiskAssessment,
    SummaryOutput,
    WorkflowResult,
)


def build_workflow_result(
    assessment: RiskAssessment,
    summary: SummaryOutput,
    stage_metrics: list[AgentStageMetrics] | None = None,
) -> WorkflowResult:
    """Consolidate agent outputs into a final workflow result."""
    return WorkflowResult(
        client_id=assessment.client_id,
        risk_score=assessment.risk_score,
        risk_assessment=assessment,
        summary=summary,
        stage_metrics=stage_metrics or [],
    )
