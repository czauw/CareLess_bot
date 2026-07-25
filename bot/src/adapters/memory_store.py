"""MVP 内存存储实现。

提供消息去重、短期上下文、任务和审计的内存存储。
所有数据进程内保存，重启即丢失——仅用于 MVP 验证流程。
"""

from __future__ import annotations

import collections
from datetime import datetime, timedelta

from bot.src.core.models import (
    AuditEvent,
    NormalizedMessage,
    OperationJob,
    OperationState,
)


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
        scope_id = message.scope_id
        ctx = self._contexts[scope_id]
        ctx.append(message)
        # 按数量裁剪
        while len(ctx) > self._context_max:
            ctx.popleft()
        # 按时间裁剪
        self._evict_expired(scope_id)

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
        cutoff = datetime.utcnow() - timedelta(seconds=self._context_ttl)
        while ctx and ctx[0].created_at < cutoff:
            ctx.popleft()

    # ---- 运维任务 ----

    async def save_job(self, job: OperationJob) -> None:
        """保存或更新任务。"""
        job.updated_at = datetime.utcnow()
        self._jobs[job.operation_id] = job

    async def get_job(self, operation_id: str) -> OperationJob | None:
        """按 ID 获取任务。"""
        return self._jobs.get(operation_id)

    async def find_pending_approval(
        self, scope_id: str, code_hash: str
    ) -> OperationJob | None:
        """按作用域和确认码哈希查找待审批任务。"""
        for job in self._jobs.values():
            if (
                job.request.scope_id == scope_id
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

    # ---- 管理 ----

    def clear(self) -> None:
        """清空全部数据（测试用）。"""
        self._dedup.clear()
        self._contexts.clear()
        self._jobs.clear()
        self._audit_log.clear()
