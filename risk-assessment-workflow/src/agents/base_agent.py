"""Base agent invoker for Foundry v2 hosted agents."""

import json
import logging
from typing import Any

from src.errors import AgentInvocationError, retry_with_backoff

logger = logging.getLogger(__name__)


class HostedAgentInvoker:
    """Invokes a Foundry v2 hosted agent via the azure-ai-projects SDK.

    Each instance wraps a single hosted agent. Use one instance per agent
    to keep client state isolated.
    """

    def __init__(self, openai_client: Any, agent_name: str, version: str = "1"):
        self._openai_client = openai_client
        self.agent_name = agent_name
        self.version = version

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    def invoke(self, user_message: str) -> str:
        """Invoke the hosted agent and return the raw response text.

        Raises:
            AgentInvocationError: If the agent call fails after retries.
        """
        try:
            logger.info(f"[AGENT:{self.agent_name}] Invoking")
            response = self._openai_client.responses.create(
                input=[{"role": "user", "content": user_message}],
                extra_body={
                    "agent_reference": {
                        "name": self.agent_name,
                        "version": self.version,
                        "type": "agent_reference",
                    }
                },
            )
            text = response.output_text
            logger.info(f"[AGENT:{self.agent_name}] Response received ({len(text)} chars)")
            return text
        except (ConnectionError, TimeoutError, OSError):
            raise  # let retry_with_backoff handle these
        except Exception as e:
            raise AgentInvocationError(self.agent_name, str(e)) from e

    def invoke_json(self, user_message: str) -> dict:
        """Invoke the agent and parse the response as JSON.

        Handles cases where the model wraps JSON in a markdown code fence.

        Raises:
            AgentInvocationError: If response is not valid JSON.
        """
        raw = self.invoke(user_message)
        try:
            return json.loads(self._strip_code_fence(raw))
        except json.JSONDecodeError as e:
            raise AgentInvocationError(
                self.agent_name,
                f"Response is not valid JSON: {e}. Raw: {raw[:200]}",
            ) from e

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        """Remove markdown code fences if present."""
        stripped = text.strip()
        if stripped.startswith("```"):
            # Remove opening fence (optionally with language tag)
            first_newline = stripped.index("\n")
            stripped = stripped[first_newline + 1:]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
        return stripped.strip()
