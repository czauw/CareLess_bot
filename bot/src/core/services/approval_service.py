"""审批服务 —— 确认码的生成、校验与生命周期管理。

确认码：
- 高熵随机字符串，只保存 SHA-256 哈希
- 绑定 sender_id、scope、operation_id 和参数哈希
- 默认有效期 120 秒，单次使用后立即失效
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Protocol

from bot.src.core.models import OperationJob, OperationState


class ApprovalCodeStore(Protocol):
    """确认码存储接口——用于查询和更新待审批任务。"""

    async def find_pending_approval(
        self, scope_id: str, code_hash: str
    ) -> OperationJob | None: ...

    async def save_job(self, job: OperationJob) -> None: ...


class ApprovalService:
    """审批确认码管理。"""

    CODE_BYTES = 16  # 确认码原始熵（字节）
    DEFAULT_TTL_SECONDS = 120

    def __init__(
        self,
        store: ApprovalCodeStore,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._store = store
        self._ttl = ttl_seconds

    def generate_code(self) -> str:
        """生成高熵一次性确认码（明文，仅用于展示给用户）。"""
        return secrets.token_hex(self.CODE_BYTES)

    @staticmethod
    def hash_code(code: str) -> str:
        """对确认码取 SHA-256 哈希——存储和查询用哈希，不存明文。"""
        return hashlib.sha256(code.encode()).hexdigest()

    def expires_at(self) -> datetime:
        """计算新确认码的过期时间。"""
        return datetime.utcnow() + timedelta(seconds=self._ttl)

    async def create_approval(self, job: OperationJob) -> str:
        """为待审批任务创建确认码，返回明文码。"""
        code = self.generate_code()
        job.approval_code_hash = self.hash_code(code)
        job.approval_expires_at = self.expires_at()
        job.state = OperationState.PENDING_APPROVAL
        await self._store.save_job(job)
        return code

    async def validate(
        self,
        scope_id: str,
        code: str,
        *,
        expected_scope_id: str,
        expected_actor: str,
    ) -> OperationJob:
        """校验确认码。

        Raises:
            ApprovalError: 确认码无效、过期、已使用或会话/操作不匹配。
        """
        from bot.src.core.errors import (
            ApprovalAlreadyUsedError,
            ApprovalExpiredError,
            ApprovalMismatchError,
        )

        code_hash = self.hash_code(code)
        job = await self._store.find_pending_approval(scope_id, code_hash)

        if job is None:
            raise ApprovalMismatchError(
                f"确认码无效或不属于当前会话"
            )

        if scope_id != expected_scope_id:
            raise ApprovalMismatchError(
                "确认必须来自创建操作的同一会话"
            )

        if job.request.actor_qq_id != expected_actor:
            raise ApprovalMismatchError(
                "确认人必须与创建人一致"
            )

        if job.state == OperationState.EXPIRED:
            raise ApprovalExpiredError()

        if job.state != OperationState.PENDING_APPROVAL:
            raise ApprovalAlreadyUsedError()

        if (
            job.approval_expires_at is not None
            and datetime.utcnow() > job.approval_expires_at
        ):
            job.state = OperationState.EXPIRED
            await self._store.save_job(job)
            raise ApprovalExpiredError()

        return job

    async def cancel(self, job: OperationJob) -> None:
        """取消待审批任务。"""
        job.state = OperationState.CANCELLED
        await self._store.save_job(job)

    async def expire_stale(self) -> int:
        """清理过期的待审批任务，返回清理数量。"""
        # MVP 阶段由调用方在 store 实现中处理
        return 0
