"""Tests for resilience primitives: circuit breaker, async retry, concurrency limiter."""

import asyncio
import time

import pytest

from src.errors import CircuitOpenError, WorkflowTimeoutError
from src.resilience import CircuitBreaker, ConcurrencyLimiter, async_retry_with_backoff


# ── Circuit Breaker ─────────────────────────────────────────────────

class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(failure_threshold=3)
        assert cb.state == CircuitBreaker.CLOSED
        assert not cb.is_open

    def test_stays_closed_below_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED

    def test_opens_at_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_seconds=60.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        assert cb.is_open

    def test_check_raises_when_open(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_seconds=60.0)
        cb.record_failure()
        with pytest.raises(CircuitOpenError):
            cb.check()

    def test_success_resets_failures(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED
        # Should tolerate more failures now
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED

    def test_half_open_after_recovery(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_seconds=0.1)
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        time.sleep(0.15)
        assert cb.state == CircuitBreaker.HALF_OPEN

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_seconds=0.1)
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitBreaker.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_seconds=0.1)
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitBreaker.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

    def test_reset_clears_state(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        assert cb.is_open
        cb.reset()
        assert cb.state == CircuitBreaker.CLOSED

    def test_recovery_remaining_decreases(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_seconds=1.0)
        cb.record_failure()
        remaining = cb.recovery_remaining
        assert 0.0 < remaining <= 1.0


# ── Async Retry ─────────────────────────────────────────────────────

class TestAsyncRetry:
    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        call_count = 0

        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await async_retry_with_backoff(succeed, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_transient_error(self):
        call_count = 0

        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "ok"

        result = await async_retry_with_backoff(
            fail_then_succeed, max_retries=3, base_delay=0.01
        )
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        async def always_fail():
            raise TimeoutError("always")

        with pytest.raises(TimeoutError, match="always"):
            await async_retry_with_backoff(
                always_fail, max_retries=3, base_delay=0.01
            )

    @pytest.mark.asyncio
    async def test_no_retry_on_non_transient_error(self):
        call_count = 0

        async def bad_input():
            nonlocal call_count
            call_count += 1
            raise ValueError("bad input")

        with pytest.raises(ValueError, match="bad input"):
            await async_retry_with_backoff(
                bad_input, max_retries=3, base_delay=0.01
            )
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_respects_deadline(self):
        call_count = 0

        async def slow_fail():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            raise ConnectionError("slow")

        start = time.monotonic()
        with pytest.raises((ConnectionError, asyncio.TimeoutError)):
            await async_retry_with_backoff(
                slow_fail, max_retries=10, base_delay=0.01, deadline=0.2
            )
        elapsed = time.monotonic() - start
        assert elapsed < 1.0  # Should not take 10 retries worth of time

    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_seconds=60.0)

        async def always_fail():
            raise ConnectionError("fail")

        with pytest.raises(ConnectionError):
            await async_retry_with_backoff(
                always_fail, max_retries=2, base_delay=0.01, circuit_breaker=cb
            )

        assert cb.state == CircuitBreaker.OPEN

        # Next call should be rejected by breaker
        async def should_not_run():
            raise AssertionError("should not be called")

        with pytest.raises(CircuitOpenError):
            await async_retry_with_backoff(
                should_not_run, max_retries=3, base_delay=0.01, circuit_breaker=cb
            )


# ── Concurrency Limiter ─────────────────────────────────────────────

class TestConcurrencyLimiter:
    @pytest.mark.asyncio
    async def test_acquire_and_release(self):
        limiter = ConcurrencyLimiter(max_concurrent=2, acquire_timeout=1.0)
        assert await limiter.acquire()
        assert await limiter.acquire()
        limiter.release()
        limiter.release()

    @pytest.mark.asyncio
    async def test_rejects_when_full(self):
        limiter = ConcurrencyLimiter(max_concurrent=1, acquire_timeout=0.1)
        assert await limiter.acquire()
        # Second acquire should fail
        acquired = await limiter.acquire()
        assert not acquired
        limiter.release()


# ── Typed Exceptions ────────────────────────────────────────────────

class TestResilienceExceptions:
    def test_workflow_timeout_error(self):
        err = WorkflowTimeoutError(30.0, "CLT-10001")
        assert "30" in str(err)
        assert "CLT-10001" in str(err)
        assert err.timeout_seconds == 30.0
        assert err.client_id == "CLT-10001"

    def test_circuit_open_error(self):
        err = CircuitOpenError(15.0)
        assert "15.0" in str(err)
        assert err.recovery_remaining == 15.0
