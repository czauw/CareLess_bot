from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from bot.src.adapters.memory_store import MemoryStore
from bot.src.adapters.mock_ops_gateway import MockOpsGateway
from bot.src.core.models import NormalizedMessage, ScopeType
from bot.src.core.runtime import Runtime, get_runtime, init_runtime
from bot.src.core.services.approval_service import ApprovalService
from bot.src.core.services.audit_service import AuditService
from bot.src.core.services.auth_service import AuthService
from bot.src.core.services.job_service import JobService
from bot.src.core.services.rate_limit_service import RateLimitService
from bot.src.plugins.admin_command.handler import CommandHandler
from bot.src.plugins.admin_command.parser import CommandParser
from bot.src.plugins.persona.context import ContextService
from bot.src.plugins.persona.gate import PersonaGate
from bot.src.plugins.persona.responder import Responder


def make_handler() -> CommandHandler:
    store = MemoryStore()
    gateway = MockOpsGateway(default_delay=0)
    gateway.register_server("survival", "生存服")
    runtime = Runtime.create()
    runtime.config = SimpleNamespace(
        admin_commands_enabled=True,
        ops_enabled=True,
        ops_read_enabled=True,
        ops_write_enabled=True,
        ops_r1_requires_approval=False,
        ops_max_log_lines=100,
    )
    runtime.store = store
    runtime.ops_gateway = gateway
    runtime.auth_service = AuthService({"10001"})
    runtime.approval_service = ApprovalService(store, ttl_seconds=60)
    runtime.job_service = JobService(store)
    runtime.audit_service = AuditService(store)
    runtime.rate_limit_service = RateLimitService()
    runtime.server_targets = {
        "survival": type(
            "Target", (), {"enabled": True, "capabilities": frozenset({"status", "start", "stop"})}
        )()
    }
    init_runtime(runtime)
    return CommandHandler(CommandParser({"生存服": "survival"}), gateway, store)


def test_read_only_command_executes_for_whitelisted_user() -> None:
    handler = make_handler()

    response = asyncio.run(
        handler.handle("10001", ScopeType.GROUP, "20001", "/服 状态 生存服")
    )

    assert "survival" in response
    assert "离线" in response
    operation_events = [
        event for event in get_runtime().store.audit_events if event.event_type == "operation"
    ]
    assert [event.decision for event in operation_events] == ["started", "succeeded"]
    assert all(event.risk_level == "R0" for event in operation_events)


def test_stop_requires_same_actor_and_scope_to_confirm() -> None:
    handler = make_handler()
    pending = asyncio.run(
        handler.handle("10001", ScopeType.GROUP, "20001", "/服 停止 生存服")
    )
    code = pending.split("确认码: ", 1)[1].split("\n", 1)[0]

    wrong_scope = asyncio.run(
        handler.handle("10001", ScopeType.PRIVATE, "20001", f"/确认 {code}")
    )
    assert "无效" in wrong_scope

    completed = asyncio.run(
        handler.handle("10001", ScopeType.GROUP, "20001", f"/确认 {code}")
    )
    assert "已处于离线状态" in completed

    audit_events = get_runtime().store.audit_events
    operation_events = [event for event in audit_events if event.event_type == "operation"]
    assert [event.decision for event in operation_events] == [
        "approval_requested",
        "approval_confirmed",
        "succeeded",
    ]
    assert all(event.actor == "***0001" for event in operation_events)
    assert all(event.operation_id for event in operation_events)


def test_parser_rejects_invalid_log_tail_argument() -> None:
    parser = CommandParser({"生存服": "survival"})
    with pytest.raises(Exception, match="日志行数必须是数字"):
        parser.parse("/服 日志 生存服 十行")


def _message(
    scope_type: ScopeType,
    scope_id: str,
    text: str,
    *,
    sender_id: str = "10001",
    is_at_bot: bool = False,
) -> NormalizedMessage:
    return NormalizedMessage(
        message_id=f"{scope_type.value}-{scope_id}-{text}",
        sender_id=sender_id,
        sender_alias="测试用户",
        scope_type=scope_type,
        scope_id=scope_id,
        text=text,
        message_type="text",
        reply_to=None,
        is_at_bot=is_at_bot,
        created_at=datetime.now(UTC),
    )


def test_context_does_not_mix_group_and_private_with_same_id() -> None:
    async def run() -> tuple[list[NormalizedMessage], list[NormalizedMessage]]:
        context = ContextService(MemoryStore())
        await context.append(_message(ScopeType.GROUP, "10001", "群消息"))
        await context.append(_message(ScopeType.PRIVATE, "10001", "私聊消息"))
        return (
            await context.get_recent("10001", scope_type=ScopeType.GROUP),
            await context.get_recent("10001", scope_type=ScopeType.PRIVATE),
        )

    group, private = asyncio.run(run())
    assert [message.text for message in group] == ["群消息"]
    assert [message.text for message in private] == ["私聊消息"]


def test_responder_rejects_reply_over_configured_length() -> None:
    class LongReplyLlm:
        async def chat(self, **_: object) -> str:
            return "过长回复" * 10

    response = asyncio.run(
        Responder(LongReplyLlm(), max_reply_length=8).generate(
            _message(ScopeType.GROUP, "20001", "测试"),
            [_message(ScopeType.GROUP, "20001", "测试")],
        )
    )
    assert response is None


def test_ops_write_switch_blocks_state_changing_commands() -> None:
    handler = make_handler()
    get_runtime().config.ops_write_enabled = False

    response = asyncio.run(
        handler.handle("10001", ScopeType.GROUP, "20001", "/服 停止 生存服")
    )

    assert response == "服务器操作功能当前未启用。"


def test_r1_confirmation_switch_requires_approval() -> None:
    handler = make_handler()
    get_runtime().config.ops_r1_requires_approval = True

    response = asyncio.run(
        handler.handle("10001", ScopeType.GROUP, "20001", "/服 启动 生存服")
    )

    assert "高风险操作确认" in response


def test_hard_trigger_switch_disables_private_reply() -> None:
    gate = PersonaGate(hard_trigger_enabled=False)

    result = gate.evaluate(_message(ScopeType.PRIVATE, "10001", "在吗"))

    assert not result.should_reply
    assert result.reason == "硬触发已关闭"


def test_guest_conversation_has_two_replies_and_group_cooldowns() -> None:
    from bot.src.plugins.persona.session import GroupConversationService

    service = GroupConversationService(max_replies=2, reply_cooldown_seconds=60, mention_cooldown_seconds=60)
    first = _message(ScopeType.GROUP, "20001", "机器人 在吗", sender_id="200", is_at_bot=True)
    assert service.evaluate(first).should_reply
    service.record_reply(first)

    follow_up = _message(ScopeType.GROUP, "20001", "我刚才说的是那个", sender_id="200")
    assert service.evaluate(follow_up).should_reply
    service.record_reply(follow_up)

    blocked = _message(ScopeType.GROUP, "20001", "机器人 继续", sender_id="200", is_at_bot=True)
    assert service.evaluate(blocked).reason == "群艾特冷却中"

    other_group = _message(ScopeType.GROUP, "20002", "机器人 在吗", sender_id="200", is_at_bot=True)
    assert service.evaluate(other_group).should_reply


def test_responder_removes_punctuation_and_uses_exact_cache() -> None:
    class CountingLlm:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, **_: object) -> str:
            self.calls += 1
            return "嘿 你急了啊。"

    llm = CountingLlm()
    responder = Responder(llm, max_reply_length=20, cache_ttl_seconds=60)
    trigger = _message(ScopeType.GROUP, "20001", "别急", is_at_bot=True)

    first = asyncio.run(responder.generate(trigger, [trigger]))
    second = asyncio.run(responder.generate(trigger, [trigger]))

    assert first == "嘿 你急了啊"
    assert second == first
    assert llm.calls == 1


def test_context_respects_token_budget_and_keeps_latest_messages() -> None:
    async def run() -> list[NormalizedMessage]:
        context = ContextService(MemoryStore(), max_messages=10, max_tokens=12)
        await context.append(_message(ScopeType.GROUP, "20001", "第一条消息很长很长"))
        await context.append(_message(ScopeType.GROUP, "20001", "第二条"))
        return await context.get_recent("20001", scope_type=ScopeType.GROUP)

    messages = asyncio.run(run())
    assert [message.text for message in messages] == ["第二条"]
