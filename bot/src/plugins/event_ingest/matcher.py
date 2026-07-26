"""OneBot 消息统一入口。

命令在此处优先处理，其他文本只进入短期上下文和人格门控。
"""

from __future__ import annotations

import logging
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
logger = logging.getLogger(__name__)


def _event_dict(event: MessageEvent) -> dict[str, Any]:
    return {
        "message_id": event.message_id,
        "user_id": event.user_id,
        "group_id": getattr(event, "group_id", ""),
        "sender": event.sender.model_dump(),
        # NoneBot 2.5 的 MessageEvent 不再提供 get_raw_message()；
        # Message 的字符串表示保留 CQ 码，供 @ 识别与上下文使用。
        "raw_message": str(event.get_message()),
        "message_type": event.message_type,
    }


def _mask_sender_id(sender_id: str) -> str:
    """日志中仅保留 QQ 号后四位。"""
    return f"***{sender_id[-4:]}" if len(sender_id) >= 4 else "***"


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
    if not runtime.config.bot_enabled:
        return
    if runtime.config.bot_qq_id and str(event.user_id) == runtime.config.bot_qq_id:
        return

    raw_event = _event_dict(event)
    message = (
        normalize_group_message(raw_event, runtime.config.bot_qq_id)
        if isinstance(event, GroupMessageEvent)
        else normalize_private_message(raw_event, runtime.config.bot_qq_id)
    )
    logger.info(
        "收到 OneBot 消息 scope=%s:%s sender=%s at_bot=%s message_id=%s",
        message.scope_type.value,
        message.scope_id,
        _mask_sender_id(message.sender_id),
        message.is_at_bot,
        message.message_id,
    )
    if not message.message_id or await is_duplicate(runtime.store, message.message_id):
        logger.debug("消息已去重或缺少 message_id，忽略处理")
        return
    # 所有私聊、群聊入站消息均持久化；上下文读取由 Store 按作用域完成。
    await runtime.store.record_chat_message(message)

    try:
        runtime.command_handler._parser.parse(message.text)
    except CommandParseError:
        if message.text.strip().startswith("/"):
            if (
                runtime.config.admin_commands_enabled
                and runtime.auth_service.is_whitelisted(message.sender_id)
            ):
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
    if not runtime.config.persona_enabled:
        return
    is_admin = runtime.auth_service.is_whitelisted(message.sender_id)
    # 群消息持续进入线性上下文，使软触发能参考触发前的实际聊天。
    context_appended = False
    if runtime.config.persona_context_enabled and message.scope_type == ScopeType.GROUP:
        await runtime.context_service.append(message)
        context_appended = True

    record_gate_reply = False
    group_conversation_reply = False

    if is_admin:
        # 管理员只在 @ 或私聊时即时触发；默认绕过群白名单和冷却。
        if not (message.is_at_bot or message.scope_type == ScopeType.PRIVATE):
            return
        if not runtime.config.persona_hard_trigger_enabled:
            return
        if (
            message.scope_type == ScopeType.GROUP
            and not runtime.config.admin_bypass_group_allowlist
            and runtime.config.allowed_group_ids
            and message.scope_id not in runtime.config.allowed_group_ids
        ):
            return
        if not runtime.config.admin_bypass_cooldowns:
            decision = runtime.persona_gate.evaluate(message)
            if not decision.should_reply:
                return
            record_gate_reply = True
    elif message.scope_type == ScopeType.PRIVATE:
        if not runtime.config.guest_private_reply_enabled:
            return
        decision = runtime.persona_gate.evaluate(message)
        if not decision.should_reply:
            return
        record_gate_reply = True
    else:
        allowed_groups = runtime.config.allowed_group_ids
        if allowed_groups and message.scope_id not in allowed_groups:
            return
        if message.is_at_bot and not runtime.config.persona_hard_trigger_enabled:
            return

        conversation = await runtime.group_conversation_service.evaluate(message)
        if conversation.should_reply:
            # 普通成员的 @ 和后续短会话是显式会话，不依赖随机插话开关。
            if not runtime.config.persona_hard_trigger_enabled:
                return
            group_conversation_reply = True
        elif message.is_at_bot:
            # 被群级回复或艾特冷却拦截的 @ 不能回退成随机触发。
            return
        else:
            # 不在短会话中的普通群消息才参与主动回复抽样。
            decision = runtime.persona_gate.evaluate(message)
            if not decision.should_reply:
                return
            record_gate_reply = True

    if runtime.config.persona_context_enabled and not context_appended:
        await runtime.context_service.append(message)
    async def generate_and_send() -> None:
        # 延迟结束后再读取数据库上下文，使等待期内的新消息也进入本次回复参考。
        context = (
            await runtime.context_service.get_recent(
                message.scope_id,
                scope_type=message.scope_type,
            )
            if runtime.config.persona_context_enabled
            else [message]
        )
        if not context:
            context = [message]
        responses = await runtime.responder.generate(message, context)
        if not responses:
            logger.warning("人格回复未生成 scope=%s:%s", message.scope_type.value, message.scope_id)
            return

        sent_count = 0
        for index, response in enumerate(responses):
            try:
                await _send(bot, event, response)
            except Exception:
                logger.exception("人格回复发送失败 scope=%s:%s", message.scope_type.value, message.scope_id)
                break
            sent_count += 1
            if runtime.config.persona_context_enabled:
                await runtime.context_service.append_bot_reply(message, response)
            if index + 1 < len(responses):
                await runtime.persona_reply_scheduler.wait_before_followup()

        if not sent_count:
            return
        logger.info(
            "人格回复已发送 scope=%s:%s messages=%s",
            message.scope_type.value,
            message.scope_id,
            sent_count,
        )
        # 多条实际消息仍是一轮逻辑回复，只消耗一次会话额度或冷却记录。
        if group_conversation_reply:
            await runtime.group_conversation_service.record_reply(message)
        elif record_gate_reply:
            runtime.persona_gate.record_reply(message)

    scope_key = runtime.context_service.scope_key(message.scope_type, message.scope_id)
    if runtime.persona_reply_scheduler.schedule(scope_key, generate_and_send):
        logger.debug("人格回复已安排 scope=%s", scope_key)
