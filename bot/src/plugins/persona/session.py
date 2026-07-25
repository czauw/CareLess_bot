"""普通群成员的短会话与群级冷却。

一次 @ 只允许机器人发送一条消息。成功回复后，发起人可在会话有效期内
自然接话，机器人最多再回复一次；两类冷却均按群独立维护。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from bot.src.core.models import NormalizedMessage, ScopeType


@dataclass
class _Conversation:
    actor_id: str
    remaining_replies: int
    expires_at: float


@dataclass(frozen=True)
class ConversationDecision:
    should_reply: bool
    reason: str


class GroupConversationService:
    """维护普通成员的群级短会话、回复冷却和艾特冷却。"""

    def __init__(
        self,
        *,
        max_replies: int = 2,
        session_ttl_seconds: int = 300,
        reply_cooldown_seconds: int = 120,
        mention_cooldown_seconds: int = 300,
    ) -> None:
        self._max_replies = max_replies
        self._session_ttl = session_ttl_seconds
        self._reply_cooldown = reply_cooldown_seconds
        self._mention_cooldown = mention_cooldown_seconds
        self._conversations: dict[str, _Conversation] = {}
        self._reply_blocked_until: dict[str, float] = {}
        self._mention_blocked_until: dict[str, float] = {}

    def evaluate(self, message: NormalizedMessage) -> ConversationDecision:
        """判断普通成员消息是否开启或延续短会话。"""
        if message.scope_type != ScopeType.GROUP:
            return ConversationDecision(False, "普通成员私聊未启用")

        now = time.monotonic()
        scope_id = message.scope_id
        conversation = self._active_conversation(scope_id, now)
        if conversation and conversation.actor_id == message.sender_id:
            return ConversationDecision(True, "短会话续聊")

        if not message.is_at_bot:
            return ConversationDecision(False, "未艾特机器人")
        if now < self._mention_blocked_until.get(scope_id, 0):
            return ConversationDecision(False, "群艾特冷却中")
        if now < self._reply_blocked_until.get(scope_id, 0):
            return ConversationDecision(False, "群回复冷却中")

        self._conversations[scope_id] = _Conversation(
            actor_id=message.sender_id,
            remaining_replies=self._max_replies,
            expires_at=now + self._session_ttl,
        )
        return ConversationDecision(True, "艾特开启短会话")

    def record_reply(self, message: NormalizedMessage) -> None:
        """仅在发送成功后扣减会话次数并启动群级冷却。"""
        now = time.monotonic()
        scope_id = message.scope_id
        conversation = self._active_conversation(scope_id, now)
        if conversation and conversation.actor_id == message.sender_id:
            conversation.remaining_replies -= 1
            if conversation.remaining_replies <= 0:
                self._conversations.pop(scope_id, None)
        self._reply_blocked_until[scope_id] = now + self._reply_cooldown
        self._mention_blocked_until[scope_id] = now + self._mention_cooldown

    def _active_conversation(self, scope_id: str, now: float) -> _Conversation | None:
        conversation = self._conversations.get(scope_id)
        if conversation is None:
            return None
        if now >= conversation.expires_at or conversation.remaining_replies <= 0:
            self._conversations.pop(scope_id, None)
            return None
        return conversation
