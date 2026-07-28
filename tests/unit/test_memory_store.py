"""MemoryStore 内存存储全部方法测试。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from bot.src.adapters.memory_store import MemoryStore
from bot.src.core.models import (
    ActionType,
    AuditEvent,
    NormalizedMessage,
    OperationJob,
    OperationRequest,
    OperationState,
    RiskLevel,
    ScopeType,
)
from bot.src.plugins.persona.session import PersonaCooldown, PersonaSession


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
async def test_claim_message_first_and_second() -> None:
    store = MemoryStore()
    assert await store.claim_message("m1") is True
    assert await store.claim_message("m1") is False


@pytest.mark.asyncio
async def test_append_and_get_context() -> None:
    store = MemoryStore(context_max_messages=10)
    key = "group:20001"
    await store.append_context(_message("hello"))
    await store.append_context(_message("world"))
    ctx = await store.get_context(key, limit=10)
    assert [m.text for m in ctx] == ["hello", "world"]


@pytest.mark.asyncio
async def test_context_respects_max_count() -> None:
    store = MemoryStore(context_max_messages=3)
    key = "group:20001"
    for i in range(5):
        await store.append_context(_message(f"msg-{i}"))
    ctx = await store.get_context(key, limit=10)
    assert [m.text for m in ctx] == ["msg-2", "msg-3", "msg-4"]


@pytest.mark.asyncio
async def test_context_eviction_by_time() -> None:
    store = MemoryStore(context_max_messages=10, context_ttl_seconds=1)
    key = "group:20001"
    old = _message("old", created_at=datetime.now(UTC) - timedelta(seconds=9999))
    await store.append_context(old)
    ctx = await store.get_context(key, limit=10)
    assert len(ctx) == 0


@pytest.mark.asyncio
async def test_is_bot_message() -> None:
    store = MemoryStore()
    key = "group:20001"
    bot_msg = _message("bot reply", sender_id="bot", message_id="bot-1")
    await store.append_context(bot_msg)
    assert await store.is_bot_message(key, "bot-1") is True
    assert await store.is_bot_message(key, "nonexistent") is False
    assert await store.is_bot_message("unknown_scope", "bot-1") is False


@pytest.mark.asyncio
async def test_save_and_get_job() -> None:
    store = MemoryStore()
    req = OperationRequest(
        operation_id="op-1",
        actor_qq_id="10001",
        scope_type=ScopeType.GROUP,
        scope_id="20001",
        action=ActionType.START,
        server_id="survival",
        risk_level=RiskLevel.R1,
    )
    job = OperationJob(operation_id="op-1", request=req)
    await store.save_job(job)
    assert (await store.get_job("op-1")) is not None
    assert await store.get_job("nonexistent") is None


@pytest.mark.asyncio
async def test_find_pending_approval() -> None:
    store = MemoryStore()
    req = OperationRequest(
        operation_id="op-1",
        actor_qq_id="10001",
        scope_type=ScopeType.GROUP,
        scope_id="20001",
        action=ActionType.STOP,
        server_id="survival",
        risk_level=RiskLevel.R2,
    )
    job = OperationJob(
        operation_id="op-1",
        request=req,
        state=OperationState.PENDING_APPROVAL,
        approval_code_hash="abc123",
    )
    await store.save_job(job)
    found = await store.find_pending_approval(ScopeType.GROUP, "20001", "abc123")
    assert found is not None
    assert found.operation_id == "op-1"
    not_found = await store.find_pending_approval(ScopeType.GROUP, "20001", "wrong")
    assert not_found is None


@pytest.mark.asyncio
async def test_find_active_job_for_server() -> None:
    store = MemoryStore()
    req = OperationRequest(
        operation_id="op-1",
        actor_qq_id="10001",
        scope_type=ScopeType.GROUP,
        scope_id="20001",
        action=ActionType.STOP,
        server_id="survival",
        risk_level=RiskLevel.R2,
    )
    job = OperationJob(operation_id="op-1", request=req, state=OperationState.RUNNING)
    await store.save_job(job)
    assert await store.find_active_job_for_server("survival") is not None
    assert await store.find_active_job_for_server("other") is None


@pytest.mark.asyncio
async def test_append_audit_and_snapshot() -> None:
    store = MemoryStore()
    event = AuditEvent(
        event_type="operation",
        actor="***0001",
        scope="group:20001",
        decision="started",
        reason=None,
        correlation_id="c1",
    )
    await store.append_audit(event)
    assert len(store.audit_events) == 1
    assert store.audit_events[0].event_type == "operation"


@pytest.mark.asyncio
async def test_persona_session_crud() -> None:
    store = MemoryStore()
    session = PersonaSession(actor_id="10001", remaining_replies=2, expires_at=datetime.now(UTC) + timedelta(seconds=60))
    await store.save_persona_session("20001", session)
    assert (await store.get_persona_session("20001")) is not None
    await store.delete_persona_session("20001")
    assert await store.get_persona_session("20001") is None


@pytest.mark.asyncio
async def test_persona_cooldown_default_and_update() -> None:
    store = MemoryStore()
    cooldown = await store.get_persona_cooldown("20001")
    assert cooldown.reply_blocked_until is None
    assert cooldown.mention_blocked_until is None
    now = datetime.now(UTC)
    new_cd = PersonaCooldown(
        reply_blocked_until=now + timedelta(seconds=60),
        mention_blocked_until=now + timedelta(seconds=120),
    )
    await store.save_persona_cooldown("20001", new_cd)
    updated = await store.get_persona_cooldown("20001")
    assert updated.reply_blocked_until is not None
    assert updated.mention_blocked_until is not None


def test_clear_all_data() -> None:
    store = MemoryStore()
    store._dedup["x"] = True
    store._audit_log.append(AuditEvent(
        event_type="test", actor="x", scope="x", decision="x", reason=None, correlation_id="x",
    ))
    store.clear()
    assert len(store._dedup) == 0
    assert len(store.audit_events) == 0


@pytest.mark.asyncio
async def test_record_chat_message_is_noop() -> None:
    store = MemoryStore()
    result = await store.record_chat_message(_message("test"))
    assert result is None


@pytest.mark.asyncio
async def test_scope_isolation() -> None:
    store = MemoryStore(context_max_messages=10)
    await store.append_context(_message("group-msg", scope_type=ScopeType.GROUP, scope_id="20001"))
    await store.append_context(_message("private-msg", scope_type=ScopeType.PRIVATE, scope_id="10001"))
    group_ctx = await store.get_context("group:20001", limit=10)
    private_ctx = await store.get_context("private:10001", limit=10)
    assert [m.text for m in group_ctx] == ["group-msg"]
    assert [m.text for m in private_ctx] == ["private-msg"]
