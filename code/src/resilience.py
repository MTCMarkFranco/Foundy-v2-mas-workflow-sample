"""Resilience primitives: circuit breaker, async retry, concurrency limiter.

These components implement the Actor Pattern's execution-safety layer,
protecting the workflow from cascading failures, unbounded waits, and
uncontrolled concurrency when calling hosted LLM agents.
"""

import asyncio
import functools
import logging
import time
from typing import Any, Callable, TypeVar

from src.errors import CircuitOpenError

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Transient errors worth retrying — NOT validation / parse / logic errors
TRANSIENT_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    asyncio.TimeoutError,
    OSError,
)


# ── Circuit Breaker ─────────────────────────────────────────────────

class CircuitBreaker:
    """Tracks consecutive transient failures and opens to prevent cascading damage.

    States:
        CLOSED  — requests flow normally
        OPEN    — requests rejected immediately (CircuitOpenError)
        HALF-OPEN — one probe request allowed; success closes, failure re-opens
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 3, recovery_seconds: float = 30.0):
        self._failure_threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        self._failure_count = 0
        self._state = self.CLOSED
        self._opened_at: float | None = None
        self._half_open_in_flight = False

    @property
    def state(self) -> str:
        if self._state == self.OPEN:
            elapsed = time.monotonic() - (self._opened_at or 0)
            if elapsed >= self._recovery_seconds:
                return self.HALF_OPEN
        return self._state

    @property
    def is_open(self) -> bool:
        return self.state == self.OPEN

    @property
    def recovery_remaining(self) -> float:
        if self._state != self.OPEN or self._opened_at is None:
            return 0.0
        return max(0.0, self._recovery_seconds - (time.monotonic() - self._opened_at))

    def check(self) -> None:
        """Raise CircuitOpenError if the breaker is open."""
        current = self.state
        if current == self.OPEN:
            logger.warning(
                "[CIRCUIT-BREAKER] OPEN — rejecting request. "
                f"Recovery in {self.recovery_remaining:.1f}s"
            )
            raise CircuitOpenError(self.recovery_remaining)
        if current == self.HALF_OPEN and self._half_open_in_flight:
            raise CircuitOpenError(0.0)
        if current == self.HALF_OPEN:
            self._half_open_in_flight = True
            logger.info("[CIRCUIT-BREAKER] HALF-OPEN — allowing probe request")

    def record_success(self) -> None:
        """Reset on success."""
        prev = self._state
        self._failure_count = 0
        self._state = self.CLOSED
        self._opened_at = None
        self._half_open_in_flight = False
        if prev != self.CLOSED:
            logger.info(f"[CIRCUIT-BREAKER] {prev} → CLOSED (success)")

    def record_failure(self) -> None:
        """Increment failures; open breaker if threshold exceeded."""
        self._failure_count += 1
        self._half_open_in_flight = False
        if self._failure_count >= self._failure_threshold:
            prev = self._state
            self._state = self.OPEN
            self._opened_at = time.monotonic()
            if prev != self.OPEN:
                logger.warning(
                    f"[CIRCUIT-BREAKER] {prev} → OPEN after "
                    f"{self._failure_count} consecutive failures"
                )

    def reset(self) -> None:
        """Force reset to closed state."""
        self._failure_count = 0
        self._state = self.CLOSED
        self._opened_at = None
        self._half_open_in_flight = False


# ── Async Retry with Backoff ────────────────────────────────────────

async def async_retry_with_backoff(
    coro_func: Callable[..., Any],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 1.0,
    deadline: float | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    **kwargs: Any,
) -> Any:
    """Execute an async callable with exponential backoff on transient failures.

    Only retries on transient errors (connection, timeout, OS-level).
    Non-transient errors (validation, parsing) propagate immediately.

    Args:
        coro_func: Async callable to execute.
        max_retries: Maximum number of attempts.
        base_delay: Initial delay in seconds (doubles each retry).
        deadline: Total time budget in seconds across all attempts.
        circuit_breaker: Optional circuit breaker to check/update.
    """
    start = time.monotonic()
    last_exception: Exception | None = None

    for attempt in range(max_retries):
        # Respect total deadline
        if deadline is not None:
            elapsed = time.monotonic() - start
            remaining = deadline - elapsed
            if remaining <= 0:
                raise last_exception or asyncio.TimeoutError(
                    f"Deadline of {deadline}s exceeded after {attempt} attempts"
                )

        # Check circuit breaker before each attempt
        if circuit_breaker is not None:
            circuit_breaker.check()

        try:
            result = await coro_func(*args, **kwargs)
            if circuit_breaker is not None:
                circuit_breaker.record_success()
            return result

        except TRANSIENT_EXCEPTIONS as e:
            last_exception = e
            if circuit_breaker is not None:
                circuit_breaker.record_failure()

            if attempt == max_retries - 1:
                raise

            delay = base_delay * (2 ** attempt)

            # Don't sleep past the deadline
            if deadline is not None:
                remaining = deadline - (time.monotonic() - start)
                if delay >= remaining:
                    raise
                delay = min(delay, remaining - 0.1)

            logger.warning(
                f"[RETRY] Attempt {attempt + 1}/{max_retries} failed: {e}. "
                f"Retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)

    raise last_exception  # pragma: no cover


# ── Concurrency Limiter ─────────────────────────────────────────────

class ConcurrencyLimiter:
    """Semaphore-based limiter with fast-fail acquisition timeout."""

    def __init__(self, max_concurrent: int = 5, acquire_timeout: float = 5.0):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._acquire_timeout = acquire_timeout
        self._max = max_concurrent

    async def acquire(self) -> bool:
        """Try to acquire a slot within the timeout. Returns True if acquired."""
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(), timeout=self._acquire_timeout
            )
            return True
        except asyncio.TimeoutError:
            logger.warning(
                f"[CONCURRENCY] All {self._max} slots busy. "
                f"Request rejected after {self._acquire_timeout}s wait."
            )
            return False

    def release(self) -> None:
        self._semaphore.release()
