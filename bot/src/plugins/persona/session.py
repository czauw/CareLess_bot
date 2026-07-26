"""普通群成员的短会话与群级冷却。

一次 @ 只允许机器人发送一条消息。成功回复后，发起人可在会话有效期内
自然接话，机器人最多再回复一次；两类冷却均按群独立维护。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from bot.src.core.models import NormalizedMessage, ScopeType


@dataclass
class PersonaSession:
    actor_id: str
    remaining_replies: int
    expires_at: datetime


@dataclass(frozen=True)
class ConversationDecision:
    should_reply: bool
    reason: str


@dataclass(frozen=True)
class PersonaCooldown:
    reply_blocked_until: datetime | None
    mention_blocked_until: datetime | None


class PersonaStateStore(Protocol):
    """短会话和群级冷却的可替换存储端口。"""

    async def get_persona_session(self, group_id: str) -> PersonaSession | None: ...

    async def save_persona_session(self, group_id: str, session: PersonaSession) -> None: ...

    async def delete_persona_session(self, group_id: str) -> None: ...

    async def get_persona_cooldown(self, group_id: str) -> PersonaCooldown: ...

    async def save_persona_cooldown(self, group_id: str, cooldown: PersonaCooldown) -> None: ...


class GroupConversationService:
    """维护普通成员的群级短会话、回复冷却和艾特冷却。"""

    def __init__(
        self,
        store: PersonaStateStore,
        *,
        max_replies: int = 2,
        session_ttl_seconds: int = 300,
        reply_cooldown_seconds: int = 120,
        mention_cooldown_seconds: int = 300,
    ) -> None:
        self._store = store
        self._max_replies = max_replies
        self._session_ttl = session_ttl_seconds
        self._reply_cooldown = reply_cooldown_seconds
        self._mention_cooldown = mention_cooldown_seconds

    async def evaluate(self, message: NormalizedMessage) -> ConversationDecision:
        """判断普通成员消息是否开启或延续短会话。"""
        if message.scope_type != ScopeType.GROUP:
            return ConversationDecision(False, "普通成员私聊未启用")

        now = datetime.now(UTC)
        scope_id = message.scope_id
        conversation = await self._active_conversation(scope_id, now)
        if conversation and conversation.actor_id == message.sender_id:
            return ConversationDecision(True, "短会话续聊")

        if not message.is_at_bot:
            return ConversationDecision(False, "未艾特机器人")
        cooldown = await self._store.get_persona_cooldown(scope_id)
        if cooldown.mention_blocked_until and now < cooldown.mention_blocked_until:
            return ConversationDecision(False, "群艾特冷却中")
        if cooldown.reply_blocked_until and now < cooldown.reply_blocked_until:
            return ConversationDecision(False, "群回复冷却中")

        await self._store.save_persona_session(scope_id, PersonaSession(
            actor_id=message.sender_id,
            remaining_replies=self._max_replies,
            expires_at=now + timedelta(seconds=self._session_ttl),
        ))
        return ConversationDecision(True, "艾特开启短会话")

    async def record_reply(self, message: NormalizedMessage) -> None:
        """仅在发送成功后扣减会话次数并启动群级冷却。"""
        now = datetime.now(UTC)
        scope_id = message.scope_id
        conversation = await self._active_conversation(scope_id, now)
        if conversation and conversation.actor_id == message.sender_id:
            conversation.remaining_replies -= 1
            if conversation.remaining_replies <= 0:
                await self._store.delete_persona_session(scope_id)
            else:
                await self._store.save_persona_session(scope_id, conversation)
        await self._store.save_persona_cooldown(
            scope_id,
            PersonaCooldown(
                reply_blocked_until=now + timedelta(seconds=self._reply_cooldown),
                mention_blocked_until=now + timedelta(seconds=self._mention_cooldown),
            ),
        )

    async def _active_conversation(
        self, scope_id: str, now: datetime
    ) -> PersonaSession | None:
        conversation = await self._store.get_persona_session(scope_id)
        if conversation is None:
            return None
        if now >= conversation.expires_at or conversation.remaining_replies <= 0:
            await self._store.delete_persona_session(scope_id)
            return None
        return conversation
