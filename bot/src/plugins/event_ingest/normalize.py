"""事件规范化 —— 将 OneBot 事件转为 NormalizedMessage。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bot.src.core.models import NormalizedMessage, ScopeType


def _segments(event: dict[str, Any]) -> list[dict[str, Any]]:
    value = event.get("message_segments")
    if not isinstance(value, list):
        return []
    return [segment for segment in value if isinstance(segment, dict)]


def _display_text(segments: list[dict[str, Any]], fallback: str) -> str:
    """把 OneBot 消息段转成不会假装理解媒体内容的提示词文本。"""
    parts: list[str] = []
    labels = {
        "image": "[图片，内容未知]",
        "face": "[表情]",
        "record": "[语音，内容未知]",
        "video": "[视频，内容未知]",
        "file": "[文件，内容未知]",
        "json": "[卡片消息]",
        "xml": "[卡片消息]",
        "markdown": "[Markdown消息]",
    }
    for segment in segments:
        kind = str(segment.get("type", ""))
        data = segment.get("data") if isinstance(segment.get("data"), dict) else {}
        if kind == "text":
            parts.append(str(data.get("text", "")))
        elif kind == "at":
            parts.append(f"@{data.get('qq', '')}")
        elif kind == "reply":
            continue
        elif kind in labels:
            parts.append(labels[kind])
        elif kind:
            parts.append(f"[{kind}消息]")
    rendered = "".join(parts).strip()
    return rendered or fallback


def _message_type(segments: list[dict[str, Any]], fallback: str) -> str:
    kinds = {str(segment.get("type", "")) for segment in segments} - {"", "reply", "at"}
    if len(kinds) == 1:
        return next(iter(kinds))
    return "mixed" if kinds else fallback


def normalize_group_message(
    event: dict[str, Any],
    bot_qq_id: str = "",
    *,
    is_to_me: bool = False,
) -> NormalizedMessage:
    """将 OneBot v11 群消息事件规范化为 NormalizedMessage。"""
    sender = event.get("sender", {})
    raw_message = str(event.get("raw_message", "") or event.get("message", ""))
    message_id = str(event.get("message_id", ""))
    segments = _segments(event)
    at_user_ids = frozenset(
        str(segment.get("data", {}).get("qq", ""))
        for segment in segments
        if segment.get("type") == "at" and isinstance(segment.get("data"), dict)
    ) - {""}
    reply_to = next(
        (
            str(segment.get("data", {}).get("id", ""))
            for segment in segments
            if segment.get("type") == "reply" and isinstance(segment.get("data"), dict)
        ),
        None,
    )
    # is_to_me 由 NoneBot 在移除机器人 @ 段前计算，可防止适配器预处理造成漏判。
    is_at_bot = is_to_me or bool(bot_qq_id and bot_qq_id in at_user_ids)

    return NormalizedMessage(
        message_id=message_id,
        sender_id=str(event.get("user_id", "")),
        sender_alias=sender.get("card") or sender.get("nickname", ""),
        scope_type=ScopeType.GROUP,
        scope_id=str(event.get("group_id", "")),
        text=_display_text(segments, raw_message),
        message_type=_message_type(segments, str(event.get("message_type", "text"))),
        reply_to=reply_to or None,
        is_at_bot=is_at_bot,
        created_at=datetime.now(UTC),
        at_user_ids=at_user_ids,
    )


def normalize_private_message(
    event: dict[str, Any], bot_qq_id: str = ""
) -> NormalizedMessage:
    """将 OneBot v11 私聊消息事件规范化为 NormalizedMessage。"""
    sender = event.get("sender", {})
    raw_message = str(event.get("raw_message", "") or event.get("message", ""))
    sender_id = str(event.get("user_id", ""))
    segments = _segments(event)

    return NormalizedMessage(
        message_id=str(event.get("message_id", "")),
        sender_id=sender_id,
        sender_alias=sender.get("nickname", ""),
        scope_type=ScopeType.PRIVATE,
        scope_id=sender_id,  # 私聊作用域 = sender_id
        text=_display_text(segments, raw_message),
        message_type=_message_type(segments, str(event.get("message_type", "text"))),
        reply_to=next(
            (
                str(segment.get("data", {}).get("id", ""))
                for segment in segments
                if segment.get("type") == "reply" and isinstance(segment.get("data"), dict)
            ),
            None,
        ),
        is_at_bot=True,  # 私聊中每条消息都视为"对话"
        created_at=datetime.now(UTC),
    )
