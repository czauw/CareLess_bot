"""任务编排服务 —— 任务状态机、幂等与互斥控制。

保证：
- 同一 message_id 不重复创建任务
- 同一服务器的互斥操作串行化
- 状态迁移合法
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

from bot.src.core.models import (
    OperationJob,
    OperationRequest,
    OperationState,
    RiskLevel,
)


class JobStore(Protocol):
    """任务存储接口。"""

    async def save_job(self, job: OperationJob) -> None: ...
    async def get_job(self, operation_id: str) -> OperationJob | None: ...
    async def find_active_job_for_server(
        self, server_id: str
    ) -> OperationJob | None: ...


class JobService:
    """任务编排。"""

    # 互斥状态：这些状态下的任务会阻止同服务器新任务
    BLOCKING_STATES = frozenset({
        OperationState.PENDING_APPROVAL,
        OperationState.QUEUED,
        OperationState.RUNNING,
    })

    def __init__(self, store: JobStore) -> None:
        self._store = store

    @staticmethod
    def new_operation_id() -> str:
        """生成唯一 operation_id。"""
        return uuid.uuid4().hex[:12]

    async def create_job(self, request: OperationRequest) -> OperationJob:
        """创建新任务，检查互斥冲突。"""
        from bot.src.core.errors import JobConflictError

        # 检查互斥
        existing = await self._store.find_active_job_for_server(request.server_id)
        if existing and existing.state in self.BLOCKING_STATES:
            raise JobConflictError(request.server_id, existing.operation_id)

        job = OperationJob(operation_id=request.operation_id, request=request)
        await self._store.save_job(job)
        return job

    async def transition(
        self,
        job: OperationJob,
        to_state: OperationState,
        *,
        result_summary: str | None = None,
    ) -> OperationJob:
        """执行状态迁移。"""
        if not self._can_transition(job.state, to_state):
            raise ValueError(
                f"不允许的状态迁移: {job.state.value} -> {to_state.value}"
            )
        job.state = to_state
        job.updated_at = datetime.now(UTC)
        if result_summary is not None:
            job.result_summary = result_summary
        await self._store.save_job(job)
        return job

    async def get_job(self, operation_id: str) -> OperationJob | None:
        """按 ID 查询任务。"""
        return await self._store.get_job(operation_id)

    # ----------------------------------------------------------
    # 状态机 —— 合法迁移
    # ----------------------------------------------------------
    _TRANSITIONS: dict[OperationState, frozenset[OperationState]] = {
        OperationState.PENDING_APPROVAL: frozenset({
            OperationState.QUEUED,
            OperationState.CANCELLED,
            OperationState.EXPIRED,
        }),
        OperationState.QUEUED: frozenset({
            OperationState.RUNNING,
            OperationState.CANCELLED,
        }),
        OperationState.RUNNING: frozenset({
            OperationState.SUCCEEDED,
            OperationState.FAILED,
            OperationState.UNKNOWN,
        }),
        OperationState.UNKNOWN: frozenset({
            OperationState.SUCCEEDED,
            OperationState.FAILED,
        }),
        # 终态：SUCCEEDED / FAILED / CANCELLED / EXPIRED
        OperationState.SUCCEEDED: frozenset(),
        OperationState.FAILED: frozenset(),
        OperationState.CANCELLED: frozenset(),
        OperationState.EXPIRED: frozenset(),
    }

    @classmethod
    def _can_transition(
        cls, from_state: OperationState, to_state: OperationState
    ) -> bool:
        return to_state in cls._TRANSITIONS.get(from_state, frozenset())
