"""RateLimitService 与 _Bucket 限流测试。"""

from __future__ import annotations

import time

from bot.src.core.services.rate_limit_service import RateLimitService, _Bucket


def test_bucket_allows_up_to_max_count() -> None:
    bucket = _Bucket(window_seconds=60, max_count=3)
    assert bucket.allow() is True
    assert bucket.allow() is True
    assert bucket.allow() is True


def test_bucket_blocks_after_max_count() -> None:
    bucket = _Bucket(window_seconds=60, max_count=2)
    assert bucket.allow() is True
    assert bucket.allow() is True
    assert bucket.allow() is False


def test_bucket_count_reflects_window() -> None:
    bucket = _Bucket(window_seconds=60, max_count=10)
    assert bucket.count == 0
    bucket.allow()
    bucket.allow()
    assert bucket.count == 2


def test_rate_limit_check_and_consume() -> None:
    svc = RateLimitService()
    assert svc.check_and_consume("test", "key1", window_seconds=60, max_count=2) is True
    assert svc.check_and_consume("test", "key1", window_seconds=60, max_count=2) is True
    assert svc.check_and_consume("test", "key1", window_seconds=60, max_count=2) is False


def test_rate_limit_remaining() -> None:
    svc = RateLimitService()
    assert svc.remaining("test", "key1", window_seconds=60, max_count=2) == 2
    svc.check_and_consume("test", "key1", window_seconds=60, max_count=2)
    assert svc.remaining("test", "key1", window_seconds=60, max_count=2) == 1


def test_rate_limit_reset() -> None:
    svc = RateLimitService()
    svc.check_and_consume("test", "key1", window_seconds=60, max_count=2)
    svc.reset("test", "key1")
    assert svc.remaining("test", "key1", window_seconds=60, max_count=2) == 2


def test_rate_limit_scoped_independence() -> None:
    svc = RateLimitService()
    svc.check_and_consume("scope_a", "key1", window_seconds=60, max_count=1)
    assert svc.check_and_consume("scope_b", "key1", window_seconds=60, max_count=1) is True


def test_bucket_remaining_unknown_key() -> None:
    svc = RateLimitService()
    assert svc.remaining("unknown", "x", window_seconds=60, max_count=5) == 5
