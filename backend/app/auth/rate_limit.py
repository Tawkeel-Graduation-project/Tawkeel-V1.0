"""Thread-safe, bounded in-memory login rate limiting."""

import heapq
import math
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import islice
from threading import Lock
from typing import Callable, Protocol

from app.core.config import get_settings


class RateLimiter(Protocol):
    """Operations needed by the login endpoint."""

    def reserve_attempt(self, ip_key: str, email_key: str) -> "ReserveAttemptResult":
        """Atomically check and reserve one attempt against both keys."""

    def complete_failure(self, reservation: "RateLimitReservation") -> None:
        """Keep a reservation as a counted failure."""

    def complete_success(self, reservation: "RateLimitReservation") -> None:
        """Release the IP reservation and reset the email failure history."""

    def retry_after(self, key: str) -> int | None:
        """Return seconds until a blocked key is allowed again, if blocked."""

    def record_failure(self, key: str) -> None:
        """Record one failed login for a key."""

    def reset(self, key: str) -> None:
        """Clear failures for a key."""


@dataclass
class _FailureState:
    failures: deque[float] = field(default_factory=deque)
    reservations: dict[int, float] = field(default_factory=dict)
    last_activity: float = 0.0
    blocked_until: float | None = None


@dataclass(frozen=True)
class RateLimitReservation:
    """One provisional attempt reserved under the limiter lock."""

    ip_key: str
    email_key: str
    reservation_id: int
    timestamp: float


@dataclass(frozen=True)
class ReserveAttemptResult:
    """Either a reservation or the retry delay for a blocked attempt."""

    reservation: RateLimitReservation | None = None
    retry_after: int | None = None


class InMemoryRateLimiter:
    """Sliding-window limiter with bounded keys and injectable monotonic clock.

    Each key retains at most its configured threshold. With configuration
    bounds of 100 failures and 10,000 keys, at most one million timestamps are
    retained. At capacity, the least recently active non-blocked key is evicted.
    If every tracked key is blocked, new keys fail closed until a block expires.
    """

    def __init__(
        self,
        *,
        max_failures_per_ip: int = 20,
        max_failures_per_email: int = 5,
        window_seconds: int = 900,
        max_tracked_keys: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_failures_per_ip < 1 or max_failures_per_email < 1:
            raise ValueError("failure limits must be positive")
        if window_seconds < 1 or max_tracked_keys < 1:
            raise ValueError("window and key limit must be positive")

        self.max_failures_per_ip = max_failures_per_ip
        self.max_failures_per_email = max_failures_per_email
        self.window_seconds = window_seconds
        self.max_tracked_keys = max_tracked_keys
        self._clock = clock
        self._entries: OrderedDict[str, _FailureState] = OrderedDict()
        self._evictable: OrderedDict[str, None] = OrderedDict()
        self._blocked_expirations: list[tuple[float, str]] = []
        self._lock = Lock()
        self._next_reservation_id = 0

    @property
    def tracked_key_count(self) -> int:
        """Current number of retained keys; useful for health and tests."""
        with self._lock:
            return len(self._entries)

    def _threshold(self, key: str) -> int:
        if key.startswith("ip:"):
            return self.max_failures_per_ip
        if key.startswith("email:"):
            return self.max_failures_per_email
        raise ValueError("rate-limit keys must start with 'ip:' or 'email:'")

    def _prune_state(self, state: _FailureState, now: float) -> None:
        cutoff = now - self.window_seconds
        while state.failures and state.failures[0] <= cutoff:
            state.failures.popleft()
        expired = [
            reservation_id
            for reservation_id, timestamp in state.reservations.items()
            if timestamp <= cutoff
        ]
        for reservation_id in expired:
            del state.reservations[reservation_id]

    def _maybe_prune_all(self, now: float) -> None:
        """Bound cleanup work to a small number of oldest evictable entries."""
        for key in islice(self._evictable, 16):
            state = self._entries.get(key)
            if state is None:
                self._evictable.pop(key, None)
                continue
            self._prune_state(state, now)
            if not state.failures and not state.reservations:
                self._remove_entry(key)

    def _remove_entry(self, key: str) -> None:
        self._entries.pop(key, None)
        self._evictable.pop(key, None)

    def _refresh_status(self, key: str, state: _FailureState, now: float) -> None:
        self._prune_state(state, now)
        if not state.failures and not state.reservations:
            self._remove_entry(key)
            return

        if len(state.failures) + len(state.reservations) >= self._threshold(key):
            self._evictable.pop(key, None)
            if state.blocked_until is None:
                oldest = min((*state.failures, *state.reservations.values()))
                state.blocked_until = oldest + self.window_seconds
                heapq.heappush(self._blocked_expirations, (state.blocked_until, key))
        else:
            state.blocked_until = None
            self._evictable[key] = None
            self._evictable.move_to_end(key)

    def _promote_expired_blocks(self, now: float, budget: int = 16) -> None:
        examined = 0
        while (
            self._blocked_expirations
            and self._blocked_expirations[0][0] <= now
            and examined < budget
        ):
            deadline, key = heapq.heappop(self._blocked_expirations)
            state = self._entries.get(key)
            examined += 1
            if state is None or state.blocked_until != deadline:
                continue
            self._refresh_status(key, state, now)

    def _retry_delay_for_full_store(self, now: float) -> int:
        self._promote_expired_blocks(now)
        while self._blocked_expirations:
            deadline, key = self._blocked_expirations[0]
            state = self._entries.get(key)
            if state is not None and state.blocked_until == deadline:
                return max(1, math.ceil(deadline - now))
            heapq.heappop(self._blocked_expirations)
        return 1

    def _make_room(self, number_of_new_keys: int, now: float) -> int | None:
        if number_of_new_keys > self.max_tracked_keys:
            return self._retry_delay_for_full_store(now)
        while len(self._entries) + number_of_new_keys > self.max_tracked_keys:
            if self._evictable:
                key, _ = self._evictable.popitem(last=False)
                self._entries.pop(key, None)
                continue
            self._promote_expired_blocks(now)
            if not self._evictable:
                return self._retry_delay_for_full_store(now)
        return None

    def retry_after(self, key: str) -> int | None:
        threshold = self._threshold(key)
        with self._lock:
            now = self._clock()
            self._maybe_prune_all(now)
            state = self._entries.get(key)
            if state is None:
                return None

            self._refresh_status(key, state, now)
            state = self._entries.get(key)
            if state is None:
                return None
            if not state.failures and not state.reservations:
                self._remove_entry(key)
                return None

            state.last_activity = now
            timestamps = (*state.failures, *state.reservations.values())
            if len(timestamps) < threshold:
                return None

            seconds = math.ceil(min(timestamps) + self.window_seconds - now)
            return max(1, seconds)

    def _retry_after_locked(self, key: str, now: float) -> int | None:
        state = self._entries.get(key)
        if state is None:
            return None
        self._refresh_status(key, state, now)
        state = self._entries.get(key)
        if state is None:
            return None
        state.last_activity = now
        if len(state.failures) + len(state.reservations) < self._threshold(key):
            return None
        oldest = min((*state.failures, *state.reservations.values()))
        return max(1, math.ceil(oldest + self.window_seconds - now))

    def _state_for_update(self, key: str, now: float) -> _FailureState | None:
        state = self._entries.get(key)
        if state is None:
            blocked = self._make_room(1, now)
            if blocked is not None:
                return None
            state = _FailureState(last_activity=now)
            self._entries[key] = state
        else:
            self._prune_state(state, now)
        return state

    def reserve_attempt(self, ip_key: str, email_key: str) -> ReserveAttemptResult:
        """Atomically check both limits and add a provisional timestamp to each."""
        self._threshold(ip_key)
        self._threshold(email_key)
        with self._lock:
            now = self._clock()
            self._maybe_prune_all(now)
            retry_afters = (
                self._retry_after_locked(ip_key, now),
                self._retry_after_locked(email_key, now),
            )
            active = [retry for retry in retry_afters if retry is not None]
            if active:
                return ReserveAttemptResult(retry_after=max(active))

            # Ensure both entries exist before adding either reservation.
            missing = len({ip_key, email_key} - self._entries.keys())
            full_store_retry = self._make_room(missing, now)
            if full_store_retry is not None:
                return ReserveAttemptResult(retry_after=full_store_retry)
            states = {
                key: self._state_for_update(key, now) for key in (ip_key, email_key)
            }
            self._next_reservation_id += 1
            reservation_id = self._next_reservation_id
            for key, state in states.items():
                state.reservations[reservation_id] = now
                state.last_activity = now
                self._refresh_status(key, state, now)
            reservation = RateLimitReservation(
                ip_key=ip_key,
                email_key=email_key,
                reservation_id=reservation_id,
                timestamp=now,
            )
            return ReserveAttemptResult(reservation=reservation)

    def complete_failure(self, reservation: RateLimitReservation) -> None:
        """Commit a provisional attempt as a failure in both key histories."""
        with self._lock:
            now = self._clock()
            for key in (reservation.ip_key, reservation.email_key):
                state = self._entries.get(key)
                if state is None:
                    continue
                timestamp = state.reservations.pop(reservation.reservation_id, None)
                if timestamp is not None:
                    state.failures.append(timestamp)
                    state.last_activity = now
                    self._refresh_status(key, state, now)

    def complete_success(self, reservation: RateLimitReservation) -> None:
        """Release this IP slot and clear completed email failures."""
        with self._lock:
            now = self._clock()
            ip_state = self._entries.get(reservation.ip_key)
            if ip_state is not None:
                ip_state.reservations.pop(reservation.reservation_id, None)
                if not ip_state.failures and not ip_state.reservations:
                    self._remove_entry(reservation.ip_key)
                else:
                    ip_state.last_activity = now
                    self._refresh_status(reservation.ip_key, ip_state, now)

            email_state = self._entries.get(reservation.email_key)
            if email_state is not None:
                email_state.failures.clear()
                email_state.reservations.pop(reservation.reservation_id, None)
                if not email_state.reservations:
                    self._remove_entry(reservation.email_key)
                else:
                    email_state.last_activity = now
                    self._refresh_status(reservation.email_key, email_state, now)

    def record_failure(self, key: str) -> None:
        threshold = self._threshold(key)
        with self._lock:
            now = self._clock()
            self._maybe_prune_all(now)
            state = self._state_for_update(key, now)
            if state is None:
                return

            state.failures.append(now)
            while len(state.failures) > max(0, threshold - len(state.reservations)):
                state.failures.popleft()
            state.last_activity = now
            self._refresh_status(key, state, now)

    def reset(self, key: str) -> None:
        with self._lock:
            now = self._clock()
            self._maybe_prune_all(now)
            self._remove_entry(key)


@lru_cache(maxsize=1)
def get_login_rate_limiter() -> RateLimiter:
    """Lazily create the process-local login limiter for FastAPI dependency use."""
    settings = get_settings()
    return InMemoryRateLimiter(
        max_failures_per_ip=settings.login_rate_limit_ip_max_failures,
        max_failures_per_email=settings.login_rate_limit_email_max_failures,
        window_seconds=settings.login_rate_limit_window_seconds,
        max_tracked_keys=settings.login_rate_limit_max_tracked_keys,
    )
