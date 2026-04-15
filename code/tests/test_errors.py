"""Tests for error handling and retry logic."""

import time
from unittest.mock import MagicMock, patch

import pytest

from src.errors import (
    AgentInvocationError,
    ClientNotFoundError,
    ContextHandoffError,
    InvalidClientIdError,
    WorkflowError,
    retry_with_backoff,
)


class TestExceptionHierarchy:
    def test_all_errors_are_workflow_errors(self):
        assert issubclass(AgentInvocationError, WorkflowError)
        assert issubclass(ContextHandoffError, WorkflowError)
        assert issubclass(ClientNotFoundError, WorkflowError)
        assert issubclass(InvalidClientIdError, WorkflowError)

    def test_agent_invocation_error_includes_name(self):
        e = AgentInvocationError("MyAgent", "timeout")
        assert "MyAgent" in str(e)
        assert "timeout" in str(e)
        assert e.agent_name == "MyAgent"

    def test_client_not_found_error(self):
        e = ClientNotFoundError("CLT-99999")
        assert "CLT-99999" in str(e)
        assert e.client_id == "CLT-99999"

    def test_invalid_client_id_error(self):
        e = InvalidClientIdError("BAD")
        assert "BAD" in str(e)
        assert "CLT-XXXXX" in str(e)


class TestRetryWithBackoff:
    def test_succeeds_first_try(self):
        @retry_with_backoff(max_retries=3, base_delay=0.01)
        def success():
            return "ok"
        assert success() == "ok"

    def test_retries_on_connection_error(self):
        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=0.01)
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("network down")
            return "recovered"

        assert flaky() == "recovered"
        assert call_count == 3

    def test_raises_after_max_retries(self):
        @retry_with_backoff(max_retries=2, base_delay=0.01)
        def always_fails():
            raise TimeoutError("timeout")

        with pytest.raises(TimeoutError):
            always_fails()

    def test_does_not_retry_non_transient_errors(self):
        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=0.01)
        def value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("bad input")

        with pytest.raises(ValueError):
            value_error()
        assert call_count == 1  # No retries

    def test_does_not_retry_runtime_errors(self):
        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=0.01)
        def runtime_error():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("logic error")

        with pytest.raises(RuntimeError):
            runtime_error()
        assert call_count == 1
