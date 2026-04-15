"""Shared async helpers for invoking Foundry agents via MAF."""

import json
import logging
from typing import Any, Protocol, runtime_checkable

from src.errors import AgentInvocationError

logger = logging.getLogger(__name__)


@runtime_checkable
class AgentRunnable(Protocol):
    """Protocol matching FoundryAgent.run() signature for testability."""

    async def run(self, input: str, **kwargs: Any) -> str: ...


async def invoke_agent(agent: AgentRunnable, agent_name: str, user_message: str) -> str:
    """Invoke a MAF agent and return the raw response text.

    Raises:
        AgentInvocationError: If the agent call fails.
    """
    try:
        logger.info(f"[AGENT:{agent_name}] Invoking")
        result = await agent.run(user_message)
        # FoundryAgent.run() returns an AgentResponse; extract .text
        text = result.text if hasattr(result, "text") else str(result)
        logger.info(f"[AGENT:{agent_name}] Response received ({len(text)} chars)")
        return text
    except (ConnectionError, TimeoutError, OSError):
        raise  # let caller handle transient errors
    except Exception as e:
        raise AgentInvocationError(agent_name, str(e)) from e


async def invoke_agent_json(agent: AgentRunnable, agent_name: str, user_message: str) -> dict:
    """Invoke an agent and parse the response as JSON.

    Handles markdown code fences wrapping the JSON.

    Raises:
        AgentInvocationError: If response is not valid JSON.
    """
    raw = await invoke_agent(agent, agent_name, user_message)
    try:
        return json.loads(strip_code_fence(raw))
    except json.JSONDecodeError as e:
        raise AgentInvocationError(
            agent_name,
            f"Response is not valid JSON: {e}. Raw: {raw[:200]}",
        ) from e


def strip_code_fence(text: str) -> str:
    """Remove markdown code fences if present."""
    stripped = text.strip()
    if stripped.startswith("```"):
        first_newline = stripped.index("\n")
        stripped = stripped[first_newline + 1:]
    if stripped.endswith("```"):
        stripped = stripped[:-3]
    return stripped.strip()
