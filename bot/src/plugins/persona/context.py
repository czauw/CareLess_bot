"""群级短期上下文管理。

每个群独立维护一个滚动窗口：
- 默认 30 条消息或 20 分钟，先到者淘汰
- 群聊与私聊上下文隔离
"""

from __future__ import annotations

from bot.src.core.models import NormalizedMessage, ScopeType
from bot.src.core.ports import Store


class ContextService:
    """短期上下文读写。"""

    def __init__(
        self,
        store: Store,
        *,
        max_messages: int = 30,
        ttl_seconds: int = 1200,
    ) -> None:
        self._store = store
        self._max_messages = max_messages
        self._ttl_seconds = ttl_seconds

    async def append(self, message: NormalizedMessage) -> None:
        """将消息追加到对应群的上下文窗口。"""
        await self._store.append_context(message)

    async def get_recent(
        self,
        scope_id: str,
        *,
        scope_type: ScopeType,
        limit: int | None = None,
    ) -> list[NormalizedMessage]:
        """获取最近 N 条上下文（用于构造 LLM 提示）。"""
        return await self._store.get_context(
            self.scope_key(scope_type, scope_id), limit=limit or self._max_messages
        )

    @staticmethod
    def scope_key(scope_type: ScopeType, scope_id: str) -> str:
        """为短期上下文生成不可冲突的群聊/私聊作用域键。"""
        return f"{scope_type.value}:{scope_id}"
