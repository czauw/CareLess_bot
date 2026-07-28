"""PersonaGate 门控更多边界测试。"""

from __future__ import annotations

import random
from datetime import UTC, datetime

from bot.src.core.models import NormalizedMessage, ScopeType, TriggerType
from bot.src.plugins.persona.gate import PersonaGate


def _group_msg(text: str, sender_id: str = "10001", *, is_at_bot: bool = False) -> NormalizedMessage:
    return NormalizedMessage(
        message_id=f"msg-{text}",
        sender_id=sender_id,
        sender_alias="tester",
        scope_type=ScopeType.GROUP,
        scope_id="20001",
        text=text,
        message_type="text",
        reply_to=None,
        is_at_bot=is_at_bot,
        created_at=datetime.now(UTC),
    )


def _private_msg(text: str, sender_id: str = "10001") -> NormalizedMessage:
    return NormalizedMessage(
        message_id=f"msg-{text}",
        sender_id=sender_id,
        sender_alias="tester",
        scope_type=ScopeType.PRIVATE,
        scope_id="10001",
        text=text,
        message_type="text",
        reply_to=None,
        is_at_bot=True,
        created_at=datetime.now(UTC),
    )


def test_hard_trigger_via_at() -> None:
    gate = PersonaGate(hard_trigger_enabled=True)
    msg = _group_msg("@bot 在吗", is_at_bot=True)
    result = gate.evaluate(msg)
    assert result.should_reply is True
    assert result.trigger_type == TriggerType.HARD


def test_hard_trigger_via_private() -> None:
    gate = PersonaGate(hard_trigger_enabled=True)
    msg = _private_msg("私聊")
    result = gate.evaluate(msg)
    assert result.should_reply is True
    assert result.trigger_type == TriggerType.HARD


def test_soft_trigger_blocks_during_cooldown() -> None:
    gate = PersonaGate(
        active_probability=1.0,
        group_cooldown_seconds=60,
        user_cooldown_seconds=60,
        soft_trigger_enabled=True,
        quiet_start="00:00",
        quiet_end="00:00",
    )
    msg = _group_msg("测试", sender_id="10001")
    gate.evaluate(msg)
    gate.record_reply(msg)
    second = gate.evaluate(_group_msg("测试2", sender_id="10001"))
    assert not second.should_reply
    assert second.reason == "回复冷却中"


def test_quiet_hours_blocks_soft_trigger() -> None:
    # 设置全天静默
    gate = PersonaGate(
        active_probability=1.0,
        soft_trigger_enabled=True,
        quiet_start="00:00",
        quiet_end="23:59",
    )
    msg = _group_msg("测试")
    result = gate.evaluate(msg)
    assert not result.should_reply
    assert result.reason == "夜间静默"


def test_quiet_hours_allows_hard_trigger() -> None:
    gate = PersonaGate(
        hard_trigger_enabled=True,
        quiet_start="00:00",
        quiet_end="23:59",
    )
    msg = _group_msg("hi", is_at_bot=True)
    result = gate.evaluate(msg)
    assert result.should_reply is True


def test_hourly_quota_exhausted() -> None:
    gate = PersonaGate(
        active_probability=1.0,
        max_active_replies_per_hour=1,
        group_cooldown_seconds=0,
        user_cooldown_seconds=0,
        soft_trigger_enabled=True,
        quiet_start="00:00",
        quiet_end="00:00",
    )
    msg1 = _group_msg("test1")
    gate.evaluate(msg1)
    gate.record_reply(msg1)
    msg2 = _group_msg("test2")
    result = gate.evaluate(msg2)
    assert not result.should_reply
    assert result.reason == "每小时额度耗尽"


def test_probability_zero_never_triggers() -> None:
    gate = PersonaGate(
        active_probability=0.0,
        soft_trigger_enabled=True,
        quiet_start="00:00",
        quiet_end="00:00",
    )
    msg = _group_msg("test")
    result = gate.evaluate(msg)
    assert not result.should_reply
    assert result.reason == "未抽中"


def test_probability_one_always_triggers() -> None:
    gate = PersonaGate(
        active_probability=1.0,
        soft_trigger_enabled=True,
        quiet_start="00:00",
        quiet_end="00:00",
    )
    msg = _group_msg("test")
    result = gate.evaluate(msg)
    assert result.should_reply is True
    assert result.trigger_type == TriggerType.SOFT


def test_hard_trigger_disabled() -> None:
    gate = PersonaGate(hard_trigger_enabled=False)
    msg = _group_msg("hi", is_at_bot=True)
    result = gate.evaluate(msg)
    assert not result.should_reply
    assert result.reason == "硬触发已关闭"


def test_soft_trigger_disabled() -> None:
    gate = PersonaGate(soft_trigger_enabled=False, quiet_start="00:00", quiet_end="00:00")
    msg = _group_msg("test")
    result = gate.evaluate(msg)
    assert not result.should_reply
    assert result.reason == "软触发已关闭"


def test_is_hard_trigger_for_private() -> None:
    gate = PersonaGate()
    assert gate.is_hard_trigger(_private_msg("hi")) is True


def test_is_quiet_hours_when_start_equals_end() -> None:
    gate = PersonaGate(quiet_start="00:00", quiet_end="00:00")
    assert gate.is_quiet_hours() is False


def test_record_reply_resets_cooldown() -> None:
    gate = PersonaGate(
        active_probability=1.0,
        group_cooldown_seconds=0,
        user_cooldown_seconds=0,
        soft_trigger_enabled=True,
        quiet_start="00:00",
        quiet_end="00:00",
    )
    msg = _group_msg("test")
    assert gate.evaluate(msg).should_reply
    gate.record_reply(msg)
    assert gate.evaluate(msg).should_reply  # cooldown=0
