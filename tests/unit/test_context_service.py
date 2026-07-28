"""ContextService 短期上下文更多边界测试。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from bot.src.adapters.memory_store import MemoryStore
from bot.src.core.models import NormalizedMessage, ScopeType
from bot.src.plugins.persona.context import ContextService


def _message(text: str, scope_type: ScopeType = ScopeType.GROUP, scope_id: str = "20001", **kwargs: object) -> NormalizedMessage:
    defaults = {
        "message_id": f"msg-{text}",
        "sender_id": "10001",
        "sender_alias": "tester",
        "scope_type": scope_type,
        "scope_id": scope_id,
        "text": text,
        "message_type": "text",
        "reply_to": None,
        "is_at_bot": False,
        "created_at": datetime.now(UTC),
    }
    defaults.update(kwargs)
    return NormalizedMessage(**defaults)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_append_bot_reply() -> None:
    store = MemoryStore()
    ctx = ContextService(store, max_messages=10)
    trigger = _message("用户消息")
    await ctx.append_bot_reply(trigger, "bot 回复", message_id="bot-1")
    messages = await ctx.get_recent("20001", scope_type=ScopeType.GROUP)
    # append_bot_reply 把 bot 消息写入上下文；store 里至少有一条
    assert len(messages) >= 1
    bot_texts = [m.text for m in messages if m.sender_id == "bot"]
    assert "bot 回复" in bot_texts


def test_scope_key_group() -> None:
    assert ContextService.scope_key(ScopeType.GROUP, "20001") == "group:20001"


def test_scope_key_private() -> None:
    assert ContextService.scope_key(ScopeType.PRIVATE, "10001") == "private:10001"


def test_estimate_message_tokens_chinese() -> None:
    msg = _message("你好世界")
    tokens = ContextService.estimate_message_tokens(msg)
    assert tokens > 0


def test_estimate_message_tokens_english() -> None:
    msg = _message("hello world")
    tokens = ContextService.estimate_message_tokens(msg)
    assert tokens > 0


def test_estimate_message_tokens_mixed() -> None:
    msg = _message("hello 世界 test")
    tokens = ContextService.estimate_message_tokens(msg)
    assert tokens > 0
    # 中文字符权重不低于英文
    msg_cn = _message("你好")
    msg_en = _message("hello")
    assert ContextService.estimate_message_tokens(msg_cn) >= ContextService.estimate_message_tokens(msg_en)


@pytest.mark.asyncio
async def test_get_recent_ttl_filter() -> None:
    store = MemoryStore()
    ctx = ContextService(store, max_messages=10, ttl_seconds=1)
    await ctx.append(_message("new"))
    await ctx.append(
        _message("old", created_at=datetime.now(UTC) - timedelta(seconds=9999))
    )
    messages = await ctx.get_recent("20001", scope_type=ScopeType.GROUP)
    # TTL 过滤后会至少保留 new
    texts = [m.text for m in messages]
    assert "new" in texts


@pytest.mark.asyncio
async def test_get_recent_respects_limit() -> None:
    store = MemoryStore()
    ctx = ContextService(store, max_messages=100)
    for i in range(10):
        await ctx.append(_message(f"msg-{i}"))
    messages = await ctx.get_recent("20001", scope_type=ScopeType.GROUP, limit=3)
    assert len(messages) == 3
    assert messages[-1].text == "msg-9"


@pytest.mark.asyncio
async def test_scope_isolation_group_vs_private() -> None:
    store = MemoryStore()
    ctx = ContextService(store)
    await ctx.append(_message("group-msg", scope_type=ScopeType.GROUP, scope_id="20001"))
    await ctx.append(_message("private-msg", scope_type=ScopeType.PRIVATE, scope_id="10001"))
    group = await ctx.get_recent("20001", scope_type=ScopeType.GROUP)
    private = await ctx.get_recent("10001", scope_type=ScopeType.PRIVATE)
    assert [m.text for m in group] == ["group-msg"]
    assert [m.text for m in private] == ["private-msg"]


@pytest.mark.asyncio
async def test_token_budget_keeps_latest_messages() -> None:
    store = MemoryStore()
    ctx = ContextService(store, max_messages=10, max_tokens=10)
    await ctx.append(_message("很长很长很长很长很长很长很长很长"))
    await ctx.append(_message("短"))
    messages = await ctx.get_recent("20001", scope_type=ScopeType.GROUP)
    assert [m.text for m in messages] == ["短"]
