"""作用域级短期上下文管理。

每个群或私聊对象独立维护一个滚动窗口：
- 消息由 Store 持久化，按最近记录读取
- 群聊与私聊上下文严格隔离
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime

from bot.src.core.models import NormalizedMessage, ScopeType
from bot.src.core.ports import Store


class ContextService:
    """短期上下文读写。"""

    def __init__(
        self,
        store: Store,
        *,
        max_messages: int = 1_000,
        max_tokens: int = 20_000,
        ttl_seconds: int = 21_600,
    ) -> None:
        self._store = store
        self._max_messages = max_messages
        self._max_tokens = max_tokens
        self._ttl_seconds = ttl_seconds

    async def append(self, message: NormalizedMessage) -> None:
        """将消息追加到对应作用域的上下文窗口。"""
        await self._store.append_context(message)

    async def append_bot_reply(
        self,
        trigger: NormalizedMessage,
        text: str,
        *,
        message_id: str | None = None,
        reply_to: str | None = None,
    ) -> None:
        """将成功发送的机器人回复写入同一线性上下文。"""
        await self.append(
            NormalizedMessage(
                message_id=message_id or f"bot-{uuid.uuid4().hex}",
                sender_id="bot",
                sender_alias="bot",
                scope_type=trigger.scope_type,
                scope_id=trigger.scope_id,
                text=text,
                message_type="text",
                reply_to=reply_to,
                is_at_bot=False,
                created_at=datetime.now(UTC),
            )
        )

    async def get_recent(
        self,
        scope_id: str,
        *,
        scope_type: ScopeType,
        limit: int | None = None,
    ) -> list[NormalizedMessage]:
        """获取最近 N 条上下文（用于构造 LLM 提示）。"""
        messages = await self._store.get_context(
            self.scope_key(scope_type, scope_id), limit=limit or self._max_messages
        )
        if self._ttl_seconds > 0:
            cutoff = datetime.now(UTC).timestamp() - self._ttl_seconds
            messages = [message for message in messages if message.created_at.timestamp() >= cutoff]
        return self._within_token_budget(messages)

    def _within_token_budget(
        self, messages: list[NormalizedMessage]
    ) -> list[NormalizedMessage]:
        """从最新消息向前取满近似 token 预算，保持线性顺序。"""
        selected: list[NormalizedMessage] = []
        remaining = self._max_tokens
        for message in reversed(messages):
            cost = self.estimate_message_tokens(message)
            if selected and cost > remaining:
                break
            selected.append(message)
            remaining -= cost
        return list(reversed(selected))

    @staticmethod
    def estimate_message_tokens(message: NormalizedMessage) -> int:
        """保守估算中英文混合文本 token 数，避免依赖特定模型 tokenizer。"""
        ascii_chars = sum(character.isascii() for character in message.text)
        non_ascii_chars = len(message.text) - ascii_chars
        return max(1, non_ascii_chars + math.ceil(ascii_chars / 4) + 4)

    @staticmethod
    def scope_key(scope_type: ScopeType, scope_id: str) -> str:
        """为短期上下文生成不可冲突的群聊/私聊作用域键。"""
        return f"{scope_type.value}:{scope_id}"
