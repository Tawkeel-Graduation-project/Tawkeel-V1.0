"""Unit tests for the bounded sliding-window login limiter."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException, Request, Response

from app.auth import router
from app.auth.rate_limit import InMemoryRateLimiter
from app.auth.schemas import UserLogin


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_limits_only_at_threshold_and_releases_after_window() -> None:
    clock = FakeClock()
    limiter = InMemoryRateLimiter(
        max_failures_per_ip=3, max_failures_per_email=2, window_seconds=10, clock=clock
    )
    limiter.record_failure("email:a@example.com")
    assert limiter.retry_after("email:a@example.com") is None
    limiter.record_failure("email:a@example.com")
    assert limiter.retry_after("email:a@example.com") == 10
    clock.now += 10
    assert limiter.retry_after("email:a@example.com") is None


def test_sliding_window_and_retry_after_rounds_up() -> None:
    clock = FakeClock()
    limiter = InMemoryRateLimiter(max_failures_per_ip=2, window_seconds=10, clock=clock)
    limiter.record_failure("ip:1.2.3.4")
    clock.now += 2.25
    limiter.record_failure("ip:1.2.3.4")
    assert limiter.retry_after("ip:1.2.3.4") == 8
    clock.now += 7.65
    assert limiter.retry_after("ip:1.2.3.4") == 1
    clock.now += 0.35
    assert limiter.retry_after("ip:1.2.3.4") is None


def test_keys_are_independent_and_reset_is_per_key() -> None:
    limiter = InMemoryRateLimiter(max_failures_per_ip=2, max_failures_per_email=2)
    limiter.record_failure("email:a@example.com")
    limiter.record_failure("email:a@example.com")
    limiter.record_failure("email:b@example.com")
    limiter.record_failure("ip:1.2.3.4")
    assert limiter.retry_after("email:a@example.com") is not None
    limiter.reset("email:a@example.com")
    assert limiter.retry_after("email:a@example.com") is None
    assert limiter.retry_after("email:b@example.com") is None
    assert limiter.retry_after("ip:1.2.3.4") is None


def test_retry_after_is_at_least_one_second() -> None:
    clock = FakeClock()
    limiter = InMemoryRateLimiter(
        max_failures_per_email=1, window_seconds=1, clock=clock
    )
    limiter.record_failure("email:a@example.com")
    clock.now += 0.999
    assert limiter.retry_after("email:a@example.com") == 1


def test_key_store_is_bounded_and_evicts_oldest_evictable_key() -> None:
    clock = FakeClock()
    limiter = InMemoryRateLimiter(
        max_failures_per_email=3,
        max_tracked_keys=4,
        window_seconds=1000,
        clock=clock,
    )
    for i in range(100):
        clock.now += 1
        limiter.record_failure(f"email:user{i}@example.com")
    assert limiter.tracked_key_count == 4
    assert limiter.retry_after("email:user0@example.com") is None
    assert limiter.retry_after("email:user99@example.com") is None
    assert limiter.retry_after("email:user98@example.com") is None
    assert limiter.retry_after("email:user97@example.com") is None


def test_active_block_survives_pressure_from_new_keys() -> None:
    limiter = InMemoryRateLimiter(
        max_failures_per_email=2, max_tracked_keys=3, window_seconds=100
    )
    limiter.record_failure("email:blocked@example.com")
    limiter.record_failure("email:blocked@example.com")
    limiter.record_failure("email:evictable1@example.com")
    limiter.record_failure("email:evictable2@example.com")
    limiter.record_failure("email:new@example.com")

    assert limiter.retry_after("email:blocked@example.com") is not None
    assert limiter.retry_after("email:evictable1@example.com") is None
    assert limiter.retry_after("email:evictable2@example.com") is None
    assert limiter.tracked_key_count == 3


def test_full_all_blocked_store_fails_closed_for_new_keys() -> None:
    limiter = InMemoryRateLimiter(
        max_failures_per_ip=1,
        max_failures_per_email=1,
        max_tracked_keys=2,
        window_seconds=100,
    )
    limiter.record_failure("email:blocked1@example.com")
    limiter.record_failure("email:blocked2@example.com")

    result = limiter.reserve_attempt("ip:new", "email:new@example.com")

    assert result.reservation is None
    assert result.retry_after is not None
    assert limiter.retry_after("email:blocked1@example.com") is not None
    assert limiter.retry_after("email:blocked2@example.com") is not None
    assert limiter.tracked_key_count == 2


def test_expired_entries_are_pruned_and_key_format_is_checked() -> None:
    clock = FakeClock()
    limiter = InMemoryRateLimiter(window_seconds=2, clock=clock)
    limiter.record_failure("email:a@example.com")
    clock.now += 3
    limiter.record_failure("email:b@example.com")
    assert limiter.tracked_key_count == 1
    with pytest.raises(ValueError):
        limiter.record_failure("other:key")


def test_concurrent_failure_updates_are_thread_safe() -> None:
    limiter = InMemoryRateLimiter(max_failures_per_email=40)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(
            pool.map(lambda _: limiter.record_failure("email:a@example.com"), range(40))
        )
    assert limiter.retry_after("email:a@example.com") is not None
    assert limiter.tracked_key_count == 1
    assert len(limiter._entries["email:a@example.com"].failures) == 40


@pytest.mark.parametrize("limited_key", ["email", "ip"])
def test_atomic_reservations_admit_exactly_the_limit_under_concurrency(
    limited_key: str,
) -> None:
    limiter = InMemoryRateLimiter(
        max_failures_per_ip=5 if limited_key == "ip" else 100,
        max_failures_per_email=5 if limited_key == "email" else 100,
        max_tracked_keys=1000,
    )

    def reserve(index: int) -> bool:
        ip_key = "ip:shared" if limited_key == "ip" else f"ip:{index}"
        email_key = (
            "email:shared@example.com"
            if limited_key == "email"
            else f"email:user{index}@example.com"
        )
        decision = limiter.reserve_attempt(ip_key, email_key)
        if decision.reservation is None:
            return False
        limiter.complete_failure(decision.reservation)
        return True

    with ThreadPoolExecutor(max_workers=50) as pool:
        allowed = list(pool.map(reserve, range(50)))

    assert sum(allowed) == 5


@pytest.mark.parametrize("count", [5, 15])
def test_parallel_success_reservations_are_released(count: int) -> None:
    limiter = InMemoryRateLimiter(max_failures_per_ip=20, max_failures_per_email=5)
    reservations = []
    with ThreadPoolExecutor(max_workers=count) as pool:
        results = list(
            pool.map(
                lambda index: limiter.reserve_attempt(
                    "ip:shared", f"email:user{index}@example.com"
                ),
                range(count),
            )
        )
    for result in results:
        assert result.reservation is not None
        reservations.append(result.reservation)
    with ThreadPoolExecutor(max_workers=count) as pool:
        list(pool.map(limiter.complete_success, reservations))

    assert limiter.retry_after("ip:shared") is None
    assert limiter.tracked_key_count == 0


def test_exception_completion_keeps_reservation_as_failure() -> None:
    limiter = InMemoryRateLimiter(max_failures_per_ip=1, max_failures_per_email=1)
    result = limiter.reserve_attempt("ip:127.0.0.1", "email:fail@example.com")
    assert result.reservation is not None
    limiter.complete_failure(result.reservation)

    blocked = limiter.reserve_attempt("ip:127.0.0.1", "email:fail@example.com")
    assert blocked.reservation is None
    assert blocked.retry_after == 900


def test_blocked_reservations_do_not_change_original_expiry() -> None:
    clock = FakeClock()
    limiter = InMemoryRateLimiter(
        max_failures_per_ip=1, max_failures_per_email=1, window_seconds=10, clock=clock
    )
    first = limiter.reserve_attempt("ip:127.0.0.1", "email:blocked@example.com")
    assert first.reservation is not None
    limiter.complete_failure(first.reservation)
    for _ in range(9):
        clock.now += 1
        blocked = limiter.reserve_attempt("ip:127.0.0.1", "email:blocked@example.com")
        assert blocked.reservation is None
    clock.now = 110
    allowed = limiter.reserve_attempt("ip:127.0.0.1", "email:blocked@example.com")
    assert allowed.reservation is not None


def test_router_canonicalizes_limiter_key_for_unvalidated_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = InMemoryRateLimiter(max_failures_per_email=1, max_failures_per_ip=10)

    def bad_credentials(_db, _payload):
        raise HTTPException(status_code=401)

    monkeypatch.setattr(router, "authenticate_user", bad_credentials)
    request = Request({"type": "http", "client": ("127.0.0.1", 1), "headers": []})
    payload = UserLogin.model_construct(email="Raw@xn--bcher-kva.com", password="wrong")

    with pytest.raises(HTTPException) as error:
        router.login(payload, request, Response(), None, limiter)

    assert error.value.status_code == 401
    assert limiter.retry_after("email:raw@bücher.com") is not None
    assert limiter.retry_after("email:raw@xn--bcher-kva.com") is None
