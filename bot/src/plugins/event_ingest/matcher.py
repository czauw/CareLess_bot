"""OneBot 消息统一入口。

命令在此处优先处理，其他文本只进入短期上下文和人格门控。
"""

from __future__ import annotations

from typing import Any

from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent, PrivateMessageEvent
from nonebot.matcher import Matcher

from bot.src.adapters.onebot_sender import Redactor
from bot.src.core.errors import CareLessError, CommandParseError, NotWhitelistedError
from bot.src.core.models import ScopeType
from bot.src.core.runtime import get_runtime
from bot.src.plugins.event_ingest.dedup import is_duplicate
from bot.src.plugins.event_ingest.normalize import normalize_group_message, normalize_private_message


message_router = on_message(priority=1, block=True)


def _event_dict(event: MessageEvent) -> dict[str, Any]:
    return {
        "message_id": event.message_id,
        "user_id": event.user_id,
        "group_id": getattr(event, "group_id", ""),
        "sender": event.sender.model_dump(),
        "raw_message": event.get_raw_message(),
        "message_type": event.message_type,
    }


async def _send(bot: Bot, event: MessageEvent, text: str) -> None:
    await bot.send(event, Redactor.redact(text))


@message_router.handle()
async def route_message(bot: Bot, event: MessageEvent, matcher: Matcher) -> None:
    """规范化、去重并将消息路由到命令或人格处理。"""
    if not isinstance(event, (GroupMessageEvent, PrivateMessageEvent)):
        return
    runtime = get_runtime()
    if runtime.store is None or runtime.command_handler is None:
        return
    if runtime.config.bot_qq_id and str(event.user_id) == runtime.config.bot_qq_id:
        return

    raw_event = _event_dict(event)
    message = (
        normalize_group_message(raw_event, runtime.config.bot_qq_id)
        if isinstance(event, GroupMessageEvent)
        else normalize_private_message(raw_event, runtime.config.bot_qq_id)
    )
    if not message.message_id or await is_duplicate(runtime.store, message.message_id):
        return

    try:
        runtime.command_handler._parser.parse(message.text)
    except CommandParseError:
        if message.text.strip().startswith("/"):
            if runtime.auth_service.is_whitelisted(message.sender_id):
                await _send(bot, event, runtime.command_handler.HELP_TEXT)
            return
        await _handle_persona(bot, event, message)
        return

    try:
        response = await runtime.command_handler.handle(
            message.sender_id, message.scope_type, message.scope_id, message.text
        )
    except NotWhitelistedError:
        return
    except CareLessError as error:
        response = str(error)
    await _send(bot, event, response)


async def _handle_persona(bot: Bot, event: MessageEvent, message: Any) -> None:
    runtime = get_runtime()
    if message.scope_type == ScopeType.GROUP:
        allowed_groups = runtime.config.allowed_group_ids
        if allowed_groups and message.scope_id not in allowed_groups:
            return

    await runtime.context_service.append(message)
    decision = runtime.persona_gate.evaluate(message)
    if not decision.should_reply:
        return
    context = await runtime.context_service.get_recent(
        message.scope_id,
        scope_type=message.scope_type,
    )
    response = await runtime.responder.generate(message, context)
    if response:
        await _send(bot, event, response)
        runtime.persona_gate.record_reply(message)
