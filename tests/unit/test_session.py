"""GroupConversationService 短会话更多边界测试。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from bot.src.adapters.memory_store import MemoryStore
from bot.src.core.models import NormalizedMessage, ScopeType
from bot.src.plugins.persona.session import (
    GroupConversationService,
    PersonaCooldown,
    PersonaSession,
)


def _group_msg(text: str, sender_id: str = "10001", scope_id: str = "20001", *, is_at_bot: bool = False) -> NormalizedMessage:
    return NormalizedMessage(
        message_id=f"msg-{text}",
        sender_id=sender_id,
        sender_alias="tester",
        scope_type=ScopeType.GROUP,
        scope_id=scope_id,
        text=text,
        message_type="text",
        reply_to=None,
        is_at_bot=is_at_bot,
        created_at=datetime.now(UTC),
    )


def make_service(store: MemoryStore) -> GroupConversationService:
    return GroupConversationService(
        store,
        max_replies=2,
        session_ttl_seconds=60,
        reply_cooldown_seconds=60,
        mention_cooldown_seconds=120,
    )


@pytest.mark.asyncio
async def test_private_message_rejected() -> None:
    store = MemoryStore()
    svc = make_service(store)
    msg = NormalizedMessage(
        message_id="m1",
        sender_id="10001",
        sender_alias="tester",
        scope_type=ScopeType.PRIVATE,
        scope_id="10001",
        text="私聊",
        message_type="text",
        reply_to=None,
        is_at_bot=True,
        created_at=datetime.now(UTC),
    )
    decision = await svc.evaluate(msg)
    assert decision.should_reply is False
    assert "私聊" in decision.reason


@pytest.mark.asyncio
async def test_mention_cooldown() -> None:
    store = MemoryStore()
    svc = make_service(store)
    msg = _group_msg("hi", is_at_bot=True)
    assert (await svc.evaluate(msg)).should_reply
    await svc.record_reply(msg)
    msg2 = _group_msg("hi again", sender_id="10002", is_at_bot=True)
    decision = await svc.evaluate(msg2)
    assert not decision.should_reply
    assert "冷却" in decision.reason


@pytest.mark.asyncio
async def test_record_reply_depletes_session() -> None:
    store = MemoryStore()
    svc = make_service(store)
    msg1 = _group_msg("在吗", sender_id="10001", is_at_bot=True)
    assert (await svc.evaluate(msg1)).should_reply
    await svc.record_reply(msg1)
    # 同一用户续聊
    msg2 = _group_msg("继续", sender_id="10001")
    assert (await svc.evaluate(msg2)).should_reply
    await svc.record_reply(msg2)
    # 用完次数
    msg3 = _group_msg("再来", sender_id="10001")
    assert not (await svc.evaluate(msg3)).should_reply


@pytest.mark.asyncio
async def test_session_expiry() -> None:
    store = MemoryStore()
    svc = GroupConversationService(store, max_replies=2, session_ttl_seconds=0)
    msg = _group_msg("hi", is_at_bot=True)
    assert (await svc.evaluate(msg)).should_reply
    # 立即过期
    msg2 = _group_msg("继续", sender_id="10001")
    decision = await svc.evaluate(msg2)
    assert decision.should_reply is False
