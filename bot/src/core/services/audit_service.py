"""审计服务 —— 运维操作审计事件记录。

每个运维操作至少记录 actor、动作、目标、风险、审批结果和状态迁移。
普通消息事件只记录处理结果和触发原因，不记录完整原文。
"""

from __future__ import annotations

import uuid
from typing import Protocol

from bot.src.core.models import AuditEvent


class AuditStore(Protocol):
    """审计事件持久化接口。"""

    async def append_audit(self, event: AuditEvent) -> None: ...


class AuditService:
    """审计服务。"""

    def __init__(self, store: AuditStore, *, enabled: bool = True) -> None:
        self._store = store
        self._enabled = enabled

    @staticmethod
    def new_correlation_id() -> str:
        """生成新的 correlation_id（trace）。"""
        return uuid.uuid4().hex[:16]

    @staticmethod
    def mask_actor(actor: str) -> str:
        """保留末四位 QQ 号用于关联，避免在审计存储中写入完整账号。"""
        return f"***{actor[-4:]}" if len(actor) > 4 else "***"

    async def record(
        self,
        event_type: str,
        actor: str,
        scope: str,
        decision: str,
        *,
        reason: str | None = None,
        correlation_id: str | None = None,
        operation_id: str | None = None,
        action: str | None = None,
        target: str | None = None,
        risk_level: str | None = None,
    ) -> AuditEvent:
        """记录审计事件。"""
        event = AuditEvent(
            event_type=event_type,
            actor=self.mask_actor(actor),
            scope=scope,
            decision=decision,
            reason=reason,
            correlation_id=correlation_id or self.new_correlation_id(),
            operation_id=operation_id,
            action=action,
            target=target,
            risk_level=risk_level,
        )
        if self._enabled:
            await self._store.append_audit(event)
        return event
