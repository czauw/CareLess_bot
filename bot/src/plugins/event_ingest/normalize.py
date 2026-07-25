"""事件规范化 —— 将 OneBot 事件转为 NormalizedMessage。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bot.src.core.models import NormalizedMessage, ScopeType


def normalize_group_message(event: dict[str, Any], bot_qq_id: str = "") -> NormalizedMessage:
    """将 OneBot v11 群消息事件规范化为 NormalizedMessage。"""
    sender = event.get("sender", {})
    raw_message = str(event.get("raw_message", "") or event.get("message", ""))
    message_id = str(event.get("message_id", ""))

    # 检查是否 @ 了机器人
    is_at_bot = False
    if bot_qq_id:
        is_at_bot = f"[CQ:at,qq={bot_qq_id}]" in raw_message

    return NormalizedMessage(
        message_id=message_id,
        sender_id=str(event.get("user_id", "")),
        sender_alias=sender.get("card") or sender.get("nickname", ""),
        scope_type=ScopeType.GROUP,
        scope_id=str(event.get("group_id", "")),
        text=raw_message,
        message_type=str(event.get("message_type", "text")),
        reply_to=None,  # 从事件中提取 reply 关系（按需）
        is_at_bot=is_at_bot,
        created_at=datetime.utcnow(),
    )


def normalize_private_message(
    event: dict[str, Any], bot_qq_id: str = ""
) -> NormalizedMessage:
    """将 OneBot v11 私聊消息事件规范化为 NormalizedMessage。"""
    sender = event.get("sender", {})
    raw_message = str(event.get("raw_message", "") or event.get("message", ""))
    sender_id = str(event.get("user_id", ""))

    return NormalizedMessage(
        message_id=str(event.get("message_id", "")),
        sender_id=sender_id,
        sender_alias=sender.get("nickname", ""),
        scope_type=ScopeType.PRIVATE,
        scope_id=sender_id,  # 私聊作用域 = sender_id
        text=raw_message,
        message_type=str(event.get("message_type", "text")),
        reply_to=None,
        is_at_bot=True,  # 私聊中每条消息都视为"对话"
        created_at=datetime.utcnow(),
    )
