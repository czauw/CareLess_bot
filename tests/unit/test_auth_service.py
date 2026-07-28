"""AuthService 白名单权限测试。"""

from __future__ import annotations

from bot.src.core.services.auth_service import AuthService


def test_whitelisted_user_passes() -> None:
    svc = AuthService({"10001", "10002"})
    assert svc.is_whitelisted("10001") is True


def test_non_whitelisted_user_fails() -> None:
    svc = AuthService({"10001"})
    assert svc.is_whitelisted("99999") is False


def test_contains_operator() -> None:
    svc = AuthService({"10001"})
    assert "10001" in svc
    assert "99999" not in svc


def test_whitelist_property_is_frozen() -> None:
    svc = AuthService({"10001", "10002"})
    whitelist = svc.whitelist
    assert isinstance(whitelist, frozenset)
    assert whitelist == frozenset({"10001", "10002"})


def test_empty_whitelist() -> None:
    svc = AuthService(set())
    assert svc.is_whitelisted("10001") is False
    assert len(svc.whitelist) == 0
