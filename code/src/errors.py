"""Custom exceptions and retry logic for the workflow."""

import functools
import logging
import time

logger = logging.getLogger(__name__)


class WorkflowError(Exception):
    """Base exception for workflow errors."""
    pass


class AgentInvocationError(WorkflowError):
    """Error invoking a hosted agent."""

    def __init__(self, agent_name: str, message: str):
        self.agent_name = agent_name
        super().__init__(f"Agent '{agent_name}' error: {message}")


class ContextHandoffError(WorkflowError):
    """Error during context handoff between agents."""
    pass


class ClientNotFoundError(WorkflowError):
    """Client ID not found in search results."""

    def __init__(self, client_id: str):
        self.client_id = client_id
        super().__init__(f"Client '{client_id}' not found")


class InvalidClientIdError(WorkflowError):
    """Invalid client ID format."""

    def __init__(self, client_id: str):
        self.client_id = client_id
        super().__init__(f"Invalid client ID format: '{client_id}'. Expected format: CLT-XXXXX")


class WorkflowTimeoutError(WorkflowError):
    """Workflow execution exceeded the configured timeout."""

    def __init__(self, timeout_seconds: float, client_id: str = ""):
        self.timeout_seconds = timeout_seconds
        self.client_id = client_id
        super().__init__(
            f"Workflow timed out after {timeout_seconds}s"
            + (f" for client '{client_id}'" if client_id else "")
        )


class CircuitOpenError(WorkflowError):
    """Circuit breaker is open — calls are being rejected to allow recovery."""

    def __init__(self, recovery_remaining: float = 0.0):
        self.recovery_remaining = recovery_remaining
        super().__init__(
            f"Circuit breaker open. Recovery in {recovery_remaining:.1f}s. "
            "System is protecting against cascading failures."
        )


def retry_with_backoff(max_retries: int = 3, base_delay: float = 1.0):
    """Decorator for retry logic with exponential backoff.

    Only retries on transient errors (connection, timeout), not on
    validation or logic errors.
    """
    # Errors considered transient and worth retrying
    transient_exceptions = (ConnectionError, TimeoutError, OSError)

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except transient_exceptions as e:
                    last_exception = e
                    if attempt == max_retries - 1:
                        raise
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"[RETRY] Attempt {attempt + 1}/{max_retries} failed: {e}. "
                        f"Retrying in {delay:.1f}s"
                    )
                    time.sleep(delay)
            raise last_exception  # pragma: no cover
        return wrapper
    return decorator
