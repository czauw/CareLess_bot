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
from bot.src.plugins.persona.reply_scheduler import PersonaReplyScheduler
from bot.src.plugins.persona.responder import Responder, build_profile_prompt


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


def test_responder_does_not_apply_a_character_length_limit() -> None:
    class LongReplyLlm:
        async def chat(self, **_: object) -> str:
            return '{"messages":["overlong"]}'

    response = asyncio.run(
        Responder(LongReplyLlm()).generate(
            _message(ScopeType.GROUP, "20001", "测试"),
            [_message(ScopeType.GROUP, "20001", "测试")],
        )
    )
    assert response == ["overlong"]


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


def test_soft_trigger_records_cooldown_after_successful_reply() -> None:
    gate = PersonaGate(
        active_probability=1.0,
        group_cooldown_seconds=60,
        user_cooldown_seconds=60,
        max_active_replies_per_hour=3,
        soft_trigger_enabled=True,
    )
    message = _message(ScopeType.GROUP, "20001", "今天真热", sender_id="200")

    first = gate.evaluate(message)
    assert first.should_reply
    assert first.reason == "软触发抽中"
    gate.record_reply(message)

    blocked = gate.evaluate(message)
    assert not blocked.should_reply
    assert blocked.reason == "回复冷却中"


def test_guest_conversation_has_two_replies_and_group_cooldowns() -> None:
    from bot.src.plugins.persona.session import GroupConversationService

    async def run() -> None:
        service = GroupConversationService(
            MemoryStore(), max_replies=2, reply_cooldown_seconds=60, mention_cooldown_seconds=60
        )
        first = _message(ScopeType.GROUP, "20001", "机器人 在吗", sender_id="200", is_at_bot=True)
        assert (await service.evaluate(first)).should_reply
        await service.record_reply(first)

        follow_up = _message(ScopeType.GROUP, "20001", "我刚才说的是那个", sender_id="200")
        assert (await service.evaluate(follow_up)).should_reply
        await service.record_reply(follow_up)

        blocked = _message(ScopeType.GROUP, "20001", "机器人 继续", sender_id="200", is_at_bot=True)
        assert (await service.evaluate(blocked)).reason == "群艾特冷却中"

        other_group = _message(ScopeType.GROUP, "20002", "机器人 在吗", sender_id="200", is_at_bot=True)
        assert (await service.evaluate(other_group)).should_reply

    asyncio.run(run())


def test_responder_parses_multiple_messages_and_uses_exact_cache() -> None:
    class CountingLlm:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, **_: object) -> str:
            self.calls += 1
            return '{"messages":["first, relax!", "second message"]}'

    llm = CountingLlm()
    responder = Responder(llm, cache_ttl_seconds=60)
    trigger = _message(ScopeType.GROUP, "20001", "别急", is_at_bot=True)

    first = asyncio.run(responder.generate(trigger, [trigger]))
    second = asyncio.run(responder.generate(trigger, [trigger]))

    assert first == ["first, relax!", "second message"]
    assert second == first
    assert llm.calls == 1


def test_responder_limits_json_messages_to_three() -> None:
    class FourMessagesLlm:
        async def chat(self, **_: object) -> str:
            return '{"messages":["one","two","three","four"]}'

    response = asyncio.run(
        Responder(FourMessagesLlm()).generate(
            _message(ScopeType.PRIVATE, "10001", "test"),
            [_message(ScopeType.PRIVATE, "10001", "test")],
        )
    )
    assert response == ["one", "two", "three"]


def test_responder_appends_current_time_at_the_end_of_user_prompt() -> None:
    class CapturingLlm:
        def __init__(self) -> None:
            self.messages: list[dict[str, str]] = []

        async def chat(self, **kwargs: object) -> str:
            self.messages = kwargs["messages"]  # type: ignore[assignment,index]
            return '{"messages":["ok"]}'

    llm = CapturingLlm()
    responder = Responder(
        llm,
        timezone="Asia/Shanghai",
        now_provider=lambda: datetime(2026, 7, 26, 14, 5, tzinfo=UTC),
    )
    trigger = _message(ScopeType.PRIVATE, "10001", "test")

    assert asyncio.run(responder.generate(trigger, [trigger])) == ["ok"]
    assert llm.messages[1]["content"].endswith(
        "信息补充，现在是2026-07-26-22-05，你可能会需要它。"
    )


def test_reply_scheduler_replaces_a_waiting_scope_task() -> None:
    async def run() -> None:
        scheduler = PersonaReplyScheduler(
            enabled=False,
            min_delay_seconds=0,
            max_delay_seconds=0,
            followup_min_delay_seconds=0,
            followup_max_delay_seconds=0,
        )
        delivered: list[str] = []

        async def old() -> None:
            delivered.append("old")

        async def new() -> None:
            delivered.append("new")

        assert scheduler.schedule("private:10001", old)
        assert scheduler.schedule("private:10001", new)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert delivered == ["new"]
        await scheduler.close()

    asyncio.run(run())


def test_persona_profile_is_disabled_by_default_and_stable_when_enabled() -> None:
    disabled = {
        "enabled": False,
        "name": "阿洛",
        "traits": ["嘴硬", "热心"],
    }
    enabled = {**disabled, "enabled": True}

    assert build_profile_prompt(disabled) == ""
    prompt = build_profile_prompt(enabled)
    assert "昵称：阿洛" in prompt
    assert "性格：嘴硬、热心" in prompt


def test_context_respects_token_budget_and_keeps_latest_messages() -> None:
    async def run() -> list[NormalizedMessage]:
        context = ContextService(MemoryStore(), max_messages=10, max_tokens=12)
        await context.append(_message(ScopeType.GROUP, "20001", "第一条消息很长很长"))
        await context.append(_message(ScopeType.GROUP, "20001", "第二条"))
        return await context.get_recent("20001", scope_type=ScopeType.GROUP)

    messages = asyncio.run(run())
    assert [message.text for message in messages] == ["第二条"]
