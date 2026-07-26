"""MVP 内存存储实现。

提供消息去重、短期上下文、任务和审计的内存存储。
所有数据进程内保存，重启即丢失——仅用于 MVP 验证流程。
"""

from __future__ import annotations

import collections
from datetime import UTC, datetime, timedelta

from bot.src.core.models import (
    AuditEvent,
    NormalizedMessage,
    OperationJob,
    OperationState,
    ScopeType,
)
from bot.src.plugins.persona.session import PersonaCooldown, PersonaSession


class MemoryStore:
    """基于内存的存储适配器。"""

    def __init__(
        self,
        context_max_messages: int = 30,
        context_ttl_seconds: int = 1200,
    ) -> None:
        self._context_max = context_max_messages
        self._context_ttl = context_ttl_seconds

        # message_id -> True（已处理）
        self._dedup: dict[str, bool] = {}

        # scope_id -> deque[NormalizedMessage]
        self._contexts: dict[str, collections.deque[NormalizedMessage]] = (
            collections.defaultdict(collections.deque)
        )

        # operation_id -> OperationJob
        self._jobs: dict[str, OperationJob] = {}

        # 审计事件列表
        self._audit_log: list[AuditEvent] = []
        self._persona_sessions: dict[str, PersonaSession] = {}
        self._persona_cooldowns: dict[str, PersonaCooldown] = {}

    # ---- 消息去重 ----

    async def claim_message(self, message_id: str) -> bool:
        """标记 message_id 已处理；返回 True 表示首次。"""
        if message_id in self._dedup:
            return False
        self._dedup[message_id] = True
        return True

    # ---- 上下文 ----

    async def append_context(self, message: NormalizedMessage) -> None:
        """追加消息到短期上下文窗口。"""
        scope_key = f"{message.scope_type.value}:{message.scope_id}"
        ctx = self._contexts[scope_key]
        ctx.append(message)
        # 按数量裁剪
        while len(ctx) > self._context_max:
            ctx.popleft()
        # 按时间裁剪
        self._evict_expired(scope_key)

    async def record_chat_message(self, message: NormalizedMessage) -> None:
        """内存模式不额外保存完整群聊，短期上下文仍由 append_context 管理。"""
        return None

    async def get_context(
        self, scope_id: str, limit: int
    ) -> list[NormalizedMessage]:
        """获取作用域的最近 N 条上下文。"""
        self._evict_expired(scope_id)
        ctx = self._contexts.get(scope_id, collections.deque())
        items = list(ctx)
        return items[-limit:]

    def _evict_expired(self, scope_id: str) -> None:
        """淘汰过期消息。"""
        ctx = self._contexts.get(scope_id)
        if not ctx:
            return
        cutoff = datetime.now(UTC) - timedelta(seconds=self._context_ttl)
        while ctx and ctx[0].created_at < cutoff:
            ctx.popleft()

    # ---- 运维任务 ----

    async def save_job(self, job: OperationJob) -> None:
        """保存或更新任务。"""
        job.updated_at = datetime.now(UTC)
        self._jobs[job.operation_id] = job

    async def get_job(self, operation_id: str) -> OperationJob | None:
        """按 ID 获取任务。"""
        return self._jobs.get(operation_id)

    async def find_pending_approval(
        self, scope_type: ScopeType, scope_id: str, code_hash: str
    ) -> OperationJob | None:
        """按作用域和确认码哈希查找待审批任务。"""
        for job in self._jobs.values():
            if (
                job.request.scope_type == scope_type
                and job.request.scope_id == scope_id
                and job.approval_code_hash == code_hash
                and job.state == OperationState.PENDING_APPROVAL
            ):
                return job
        return None

    async def find_active_job_for_server(
        self, server_id: str
    ) -> OperationJob | None:
        """查找服务器活跃任务（互斥检查用）。"""
        blocking = {
            OperationState.PENDING_APPROVAL,
            OperationState.QUEUED,
            OperationState.RUNNING,
        }
        for job in self._jobs.values():
            if job.request.server_id == server_id and job.state in blocking:
                return job
        return None

    # ---- 审计 ----

    async def append_audit(self, event: AuditEvent) -> None:
        """追加审计事件。"""
        self._audit_log.append(event)

    # ---- 人格短会话与冷却 ----

    async def get_persona_session(self, group_id: str) -> PersonaSession | None:
        return self._persona_sessions.get(group_id)

    async def save_persona_session(self, group_id: str, session: PersonaSession) -> None:
        self._persona_sessions[group_id] = session

    async def delete_persona_session(self, group_id: str) -> None:
        self._persona_sessions.pop(group_id, None)

    async def get_persona_cooldown(self, group_id: str) -> PersonaCooldown:
        return self._persona_cooldowns.get(group_id, PersonaCooldown(None, None))

    async def save_persona_cooldown(self, group_id: str, cooldown: PersonaCooldown) -> None:
        self._persona_cooldowns[group_id] = cooldown

    @property
    def audit_events(self) -> tuple[AuditEvent, ...]:
        """返回审计快照，供测试和未来只读审计接口使用。"""
        return tuple(self._audit_log)

    # ---- 管理 ----

    def clear(self) -> None:
        """清空全部数据（测试用）。"""
        self._dedup.clear()
        self._contexts.clear()
        self._jobs.clear()
        self._audit_log.clear()
        self._persona_sessions.clear()
        self._persona_cooldowns.clear()
