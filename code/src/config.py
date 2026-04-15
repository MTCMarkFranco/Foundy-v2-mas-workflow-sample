"""Configuration module for the Risk Assessment Workflow."""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# override=False so Foundry runtime env vars take precedence over .env
load_dotenv(override=False)


@dataclass
class Config:
    """Workflow configuration loaded from environment variables."""

    foundry_endpoint: str = field(
        default_factory=lambda: os.getenv(
            "FOUNDRY_ENDPOINT",
            "https://foundry-cc-canada.services.ai.azure.com/api/projects/dev",
        )
    )

    categorize_agent_name: str = field(
        default_factory=lambda: os.getenv("CATEGORIZE_AGENT_NAME", "CategorizeRiskAgent")
    )
    categorize_agent_version: str = field(
        default_factory=lambda: os.getenv("CATEGORIZE_AGENT_VERSION", "1")
    )

    summarize_agent_name: str = field(
        default_factory=lambda: os.getenv("SUMMARIZE_AGENT_NAME", "SummarizeAgent")
    )
    summarize_agent_version: str = field(
        default_factory=lambda: os.getenv("SUMMARIZE_AGENT_VERSION", "1")
    )

    timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("WORKFLOW_TIMEOUT_SECONDS", "60"))
    )
    retry_count: int = field(
        default_factory=lambda: int(os.getenv("RETRY_COUNT", "3"))
    )
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO")
    )
