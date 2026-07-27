"""OneBot 消息统一入口。

命令在此处优先处理，其他文本只进入短期上下文和人格门控。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Any

from nonebot import on_message
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    MessageEvent,
    PrivateMessageEvent,
)
from nonebot.matcher import Matcher

from bot.src.adapters.onebot_sender import Redactor
from bot.src.core.errors import CareLessError, CommandParseError, NotWhitelistedError
from bot.src.core.models import ScopeType
from bot.src.core.runtime import get_runtime
from bot.src.plugins.event_ingest.dedup import is_duplicate
from bot.src.plugins.event_ingest.normalize import (
    normalize_group_message,
    normalize_private_message,
)
from bot.src.plugins.persona.interaction import GroupRoute


message_router = on_message(priority=1, block=True)
logger = logging.getLogger(__name__)


def _event_dict(event: MessageEvent) -> dict[str, Any]:
    # NoneBot 会在 matcher 运行前从 event.message 移除开头/结尾的机器人 @，
    # original_message 才保留完整的引用和提及关系。
    original_message = event.original_message
    return {
        "message_id": event.message_id,
        "user_id": event.user_id,
        "group_id": getattr(event, "group_id", ""),
        "sender": event.sender.model_dump(),
        "raw_message": event.raw_message or str(original_message),
        "message_segments": [
            {"type": segment.type, "data": dict(segment.data)}
            for segment in original_message
        ],
        "message_type": event.message_type,
    }


def _mask_sender_id(sender_id: str) -> str:
    """日志中仅保留 QQ 号后四位。"""
    return f"***{sender_id[-4:]}" if len(sender_id) >= 4 else "***"


async def _send(
    bot: Bot,
    event: MessageEvent,
    text: str,
) -> str | None:
    result = await bot.send(event, Redactor.redact(text))
    if isinstance(result, Mapping) and result.get("message_id") is not None:
        return str(result["message_id"])
    return str(getattr(result, "message_id", "")) or None


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
        normalize_group_message(
            raw_event,
            runtime.config.bot_qq_id,
            is_to_me=event.is_tome(),
        )
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

    if message.scope_type == ScopeType.PRIVATE:
        if is_admin:
            if not runtime.config.persona_hard_trigger_enabled:
                return
            record_gate_reply = not runtime.config.admin_bypass_cooldowns
            if record_gate_reply and not runtime.persona_gate.evaluate(message).should_reply:
                return
        else:
            if not runtime.config.guest_private_reply_enabled:
                return
            if not runtime.persona_gate.evaluate(message).should_reply:
                return
            record_gate_reply = True
        if runtime.config.persona_context_enabled and not context_appended:
            await runtime.context_service.append(message)
        await _schedule_simple_persona_reply(
            bot,
            event,
            message,
            record_gate_reply=record_gate_reply,
        )
        return

    allowed_groups = runtime.config.allowed_group_ids
    if (
        allowed_groups
        and message.scope_id not in allowed_groups
        and not (is_admin and runtime.config.admin_bypass_group_allowlist)
    ):
        return

    scope_key = runtime.context_service.scope_key(message.scope_type, message.scope_id)
    reply_to_bot = bool(
        message.reply_to
        and await runtime.store.is_bot_message(scope_key, message.reply_to)
    )
    direct = message.is_at_bot or reply_to_bot
    if direct and not runtime.config.persona_hard_trigger_enabled:
        return

    # Null LLM 只保留明确搭话的固定降级回复，不参与随机判断或群会话推理。
    if not runtime.has_llm:
        if direct:
            await _schedule_simple_persona_reply(bot, event, message, record_gate_reply=False)
        return

    route = runtime.group_interaction_coordinator.route(
        message,
        reply_to_bot=reply_to_bot,
    )
    if route.route == GroupRoute.NONE:
        logger.debug(
            "群聊人格保持沉默 group=%s reason=%s",
            message.scope_id,
            route.reason,
        )
        return

    async def decide_and_send() -> None:
        coordinator = runtime.group_interaction_coordinator
        lease = coordinator.begin_request(route, message.scope_id)
        if lease is None:
            return
        try:
            context = (
                await runtime.context_service.get_recent(
                    message.scope_id,
                    scope_type=ScopeType.GROUP,
                    limit=runtime.config.group_context_max_messages,
                )
                if runtime.config.persona_context_enabled
                else [message]
            )
            scene = runtime.group_scene_builder.build(context or [message])
            human_count = sum(item.sender_id != "bot" for item in scene.messages)
            if route.route == GroupRoute.AMBIENT and human_count < 2:
                coordinator.record_no_reply(lease, keep_session=False)
                return
            mode = route.route.value
            ai_started = time.monotonic()
            result = await runtime.responder.generate_group_decision(mode, scene)
            latency_ms = round((time.monotonic() - ai_started) * 1000)
            if result.action != "reply" or not result.target_message_id:
                coordinator.record_no_reply(lease, keep_session=result.keep_session)
                logger.info(
                    "群聊人格决策 group=%s trigger=%s action=no_reply latency_ms=%s",
                    message.scope_id,
                    route.route.value,
                    latency_ms,
                )
                return
            target = scene.find(result.target_message_id)
            if target is None or not coordinator.may_send(lease):
                logger.info(
                    "群聊人格回复取消 group=%s trigger=%s reason=scene_changed",
                    message.scope_id,
                    route.route.value,
                )
                return
            if (
                route.route == GroupRoute.AMBIENT
                and not coordinator.user_available_for_ambient(message.scope_id, target.sender_id)
            ):
                logger.info(
                    "群聊人格回复取消 group=%s trigger=ambient reason=user_cooldown",
                    message.scope_id,
                )
                return

            sent_count = 0
            last_bot_message_id: str | None = None
            for index, response in enumerate(result.messages):
                try:
                    sent_id = await _send(bot, event, response)
                except Exception:
                    logger.exception("群聊人格回复发送失败 group=%s", message.scope_id)
                    break
                sent_count += 1
                last_bot_message_id = sent_id or last_bot_message_id
                if runtime.config.persona_context_enabled:
                    await runtime.context_service.append_bot_reply(
                        message,
                        response,
                        message_id=sent_id,
                    )
                if index + 1 < len(result.messages):
                    await runtime.persona_reply_scheduler.wait_before_followup()

            if not sent_count:
                return
            coordinator.record_reply(
                lease,
                target_user_id=target.sender_id,
                bot_message_id=last_bot_message_id,
                keep_session=result.keep_session,
                expecting_answer=result.expecting_answer,
            )
            logger.info(
                "群聊人格决策 group=%s trigger=%s action=reply target=%s messages=%s "
                "keep_session=%s latency_ms=%s",
                message.scope_id,
                route.route.value,
                result.target_message_id,
                sent_count,
                result.keep_session,
                latency_ms,
            )
        finally:
            coordinator.finish_request(lease)

    if runtime.persona_reply_scheduler.schedule(scope_key, decide_and_send):
        logger.info(
            "群聊人格判断已安排 group=%s trigger=%s reason=%s",
            message.scope_id,
            route.route.value,
            route.reason,
        )


async def _schedule_simple_persona_reply(
    bot: Bot,
    event: MessageEvent,
    message: Any,
    *,
    record_gate_reply: bool,
) -> None:
    """保留私聊、管理员与无 LLM 场景的原有简单回复路径。"""
    runtime = get_runtime()
    if (
        message.scope_type == ScopeType.PRIVATE
        and not runtime.config.guest_private_reply_enabled
        and not runtime.auth_service.is_whitelisted(message.sender_id)
    ):
        return
    async def generate_and_send() -> None:
        context = (
            await runtime.context_service.get_recent(
                message.scope_id,
                scope_type=message.scope_type,
                limit=(
                    runtime.config.private_context_max_messages
                    if message.scope_type == ScopeType.PRIVATE
                    else runtime.config.group_context_max_messages
                ),
            )
            if runtime.config.persona_context_enabled
            else [message]
        )
        responses = await runtime.responder.generate(message, context or [message])
        if not responses:
            return
        sent_count = 0
        for index, response in enumerate(responses):
            try:
                sent_id = await _send(bot, event, response)
            except Exception:
                logger.exception("人格回复发送失败 scope=%s:%s", message.scope_type.value, message.scope_id)
                break
            sent_count += 1
            if runtime.config.persona_context_enabled:
                await runtime.context_service.append_bot_reply(
                    message,
                    response,
                    message_id=sent_id,
                )
            if index + 1 < len(responses):
                await runtime.persona_reply_scheduler.wait_before_followup()
        if sent_count and record_gate_reply:
            runtime.persona_gate.record_reply(message)

    scope_key = runtime.context_service.scope_key(message.scope_type, message.scope_id)
    runtime.persona_reply_scheduler.schedule(scope_key, generate_and_send)
