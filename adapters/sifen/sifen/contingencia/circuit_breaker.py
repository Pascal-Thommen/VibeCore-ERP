"""
Circuit Breaker implementation for SIFEN Network / Timeout Failover.
"""

import time
from typing import Callable

from .enums import CircuitState


class SifenCircuitBreakerOpenError(Exception):
    """Raised or checked when SIFEN circuit breaker is in OPEN state."""
    pass


class CircuitBreaker:
    """
    State machine protecting SIFEN operations from hanging on network timeouts.
    States:
      - CLOSED: Normal operation. Requests go to remote SIFEN portal.
      - OPEN: Network outage or repeated timeouts detected. Fail fast to offline contingency.
      - HALF_OPEN: Probe connection after recovery timeout to see if SIFEN is back online.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        time_func: Callable[[], float] = time.monotonic,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.time_func = time_func

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._last_failure_time: float | None = None
        self._last_success_time: float | None = None

    @property
    def state(self) -> CircuitState:
        """Current state of the circuit breaker, evaluating recovery timeout dynamically."""
        if self._state == CircuitState.OPEN and self._last_failure_time is not None:
            elapsed = self.time_func() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    def can_attempt(self) -> bool:
        """
        Check whether an online call to SIFEN should be attempted.
        Returns False if OPEN, True if CLOSED or HALF_OPEN.
        """
        current_state = self.state
        return current_state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self) -> None:
        """Record a successful transmission to SIFEN. Closes circuit breaker."""
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        self._last_success_time = self.time_func()

    def record_failure(self, error: Exception | str | None = None) -> None:
        """
        Record a failed transmission or timeout to SIFEN.
        Trips circuit breaker to OPEN if failure threshold is reached.
        """
        self._failure_count += 1
        self._last_failure_time = self.time_func()

        if self._state == CircuitState.HALF_OPEN or self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN

    def trip(self) -> None:
        """Manually force the circuit breaker into OPEN state."""
        self._state = CircuitState.OPEN
        self._failure_count = self.failure_threshold
        self._last_failure_time = self.time_func()

    def reset(self) -> None:
        """Manually reset the circuit breaker into CLOSED state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
