"""Output models for agent responses and workflow results."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# --- Token Usage ---

class TokenUsage(BaseModel):
    """Token consumption metrics for a single agent invocation."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class AgentStageMetrics(BaseModel):
    """Metrics captured from a single agent stage execution."""

    agent_name: str
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    reasoning: str = ""
    duration_seconds: float = 0.0


# --- CategorizeRiskAgent output ---

class SearchResult(BaseModel):
    """A single search result from AI Search."""

    document_id: str
    relevance_score: float = 0.0
    content_summary: str = ""
    fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("relevance_score", mode="before")
    @classmethod
    def coerce_relevance(cls, v: Any) -> float:
        if v is None or v == "":
            return 0.0
        try:
            return float(v)
        except (ValueError, TypeError):
            return 0.0


class RuleEvaluation(BaseModel):
    """Result of evaluating a single risk rule."""

    rule_id: str
    rule_name: str
    passed: bool
    severity: str = "Minor"  # Critical | Major | Minor
    details: str = ""


class RiskAssessment(BaseModel):
    """Structured output from CategorizeRiskAgent."""

    client_id: str
    risk_score: str  # Low | Medium | High
    weighted_score: int = 0
    discrepancy_count: int = 0
    search_results: list[SearchResult] = Field(default_factory=list)
    rule_evaluations: list[RuleEvaluation] = Field(default_factory=list)
    reasoning: str = ""


# --- SummarizeAgent output ---

class SummaryOutput(BaseModel):
    """Structured output from SummarizeAgent."""

    client_id: str
    risk_score: str
    summary_markdown: str = ""
    summary_plain_text: str = ""
    key_findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    urgency_level: str = "routine"  # routine | elevated | immediate
    generated_timestamp: Optional[str] = None


# --- Final workflow result ---

class WorkflowResult(BaseModel):
    """Consolidated result from the full workflow."""

    client_id: str
    risk_score: str
    risk_assessment: RiskAssessment
    summary: SummaryOutput
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    stage_metrics: list[AgentStageMetrics] = Field(default_factory=list)

    @property
    def total_token_usage(self) -> TokenUsage:
        """Aggregate token usage across all agent stages."""
        return TokenUsage(
            prompt_tokens=sum(m.token_usage.prompt_tokens for m in self.stage_metrics),
            completion_tokens=sum(m.token_usage.completion_tokens for m in self.stage_metrics),
            total_tokens=sum(m.token_usage.total_tokens for m in self.stage_metrics),
        )
