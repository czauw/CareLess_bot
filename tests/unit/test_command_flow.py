from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from bot.src.adapters.memory_store import MemoryStore
from bot.src.adapters.mock_ops_gateway import MockOpsGateway
from bot.src.core.models import NormalizedMessage, ScopeType
from bot.src.core.runtime import Runtime, init_runtime
from bot.src.core.services.approval_service import ApprovalService
from bot.src.core.services.audit_service import AuditService
from bot.src.core.services.auth_service import AuthService
from bot.src.core.services.job_service import JobService
from bot.src.core.services.rate_limit_service import RateLimitService
from bot.src.plugins.admin_command.handler import CommandHandler
from bot.src.plugins.admin_command.parser import CommandParser
from bot.src.plugins.persona.context import ContextService
from bot.src.plugins.persona.responder import Responder


def make_handler() -> CommandHandler:
    store = MemoryStore()
    gateway = MockOpsGateway(default_delay=0)
    gateway.register_server("survival", "生存服")
    runtime = Runtime.create()
    runtime.store = store
    runtime.ops_gateway = gateway
    runtime.auth_service = AuthService({"10001"})
    runtime.approval_service = ApprovalService(store, ttl_seconds=60)
    runtime.job_service = JobService(store)
    runtime.audit_service = AuditService(store)
    runtime.rate_limit_service = RateLimitService()
    runtime.server_targets = {"survival": type("Target", (), {"capabilities": frozenset({"status", "stop"})})()}
    init_runtime(runtime)
    return CommandHandler(CommandParser({"生存服": "survival"}), gateway, store)


def test_read_only_command_executes_for_whitelisted_user() -> None:
    handler = make_handler()

    response = asyncio.run(
        handler.handle("10001", ScopeType.GROUP, "20001", "/服 状态 生存服")
    )

    assert "survival" in response
    assert "离线" in response


def test_stop_requires_same_actor_and_scope_to_confirm() -> None:
    handler = make_handler()
    pending = asyncio.run(
        handler.handle("10001", ScopeType.GROUP, "20001", "/服 停止 生存服")
    )
    code = pending.split("确认码: ", 1)[1].split("\n", 1)[0]

    wrong_scope = asyncio.run(
        handler.handle("10001", ScopeType.GROUP, "20002", f"/确认 {code}")
    )
    assert "无效" in wrong_scope

    completed = asyncio.run(
        handler.handle("10001", ScopeType.GROUP, "20001", f"/确认 {code}")
    )
    assert "已处于离线状态" in completed


def test_parser_rejects_invalid_log_tail_argument() -> None:
    parser = CommandParser({"生存服": "survival"})
    with pytest.raises(Exception, match="日志行数必须是数字"):
        parser.parse("/服 日志 生存服 十行")


def _message(scope_type: ScopeType, scope_id: str, text: str) -> NormalizedMessage:
    return NormalizedMessage(
        message_id=f"{scope_type.value}-{scope_id}-{text}",
        sender_id="10001",
        sender_alias="测试用户",
        scope_type=scope_type,
        scope_id=scope_id,
        text=text,
        message_type="text",
        reply_to=None,
        is_at_bot=False,
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
