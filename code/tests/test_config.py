"""Tests for the configuration module."""

import os
from unittest.mock import patch

from src.config import Config


class TestConfig:
    def test_defaults(self):
        config = Config()
        assert "foundry-cc-canada" in config.foundry_endpoint
        assert config.categorize_agent_name == "CategorizeRiskAgent"
        assert config.categorize_agent_version in ("1", "2")  # v2 uses semantic search
        assert config.summarize_agent_name == "SummarizeAgent"
        assert config.summarize_agent_version == "1"
        assert config.timeout_seconds == 60
        assert config.retry_count == 3

    def test_env_overrides(self):
        env = {
            "FOUNDRY_ENDPOINT": "https://custom.endpoint",
            "CATEGORIZE_AGENT_NAME": "CustomCat",
            "CATEGORIZE_AGENT_VERSION": "2",
            "SUMMARIZE_AGENT_NAME": "CustomSum",
            "SUMMARIZE_AGENT_VERSION": "3",
            "WORKFLOW_TIMEOUT_SECONDS": "120",
            "RETRY_COUNT": "5",
            "LOG_LEVEL": "DEBUG",
        }
        with patch.dict(os.environ, env):
            config = Config()
            assert config.foundry_endpoint == "https://custom.endpoint"
            assert config.categorize_agent_name == "CustomCat"
            assert config.categorize_agent_version == "2"
            assert config.summarize_agent_name == "CustomSum"
            assert config.summarize_agent_version == "3"
            assert config.timeout_seconds == 120
            assert config.retry_count == 5
            assert config.log_level == "DEBUG"
