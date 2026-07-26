"""SQLAlchemy 持久化适配器。

所有方法均在调用时创建短生命周期异步会话。本模块不负责迁移建表；
启动前会按 DATABASE_SCHEMA_MODE 校验或执行 Alembic migration。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.src.core.models import (
    ActionType,
    AuditEvent,
    NormalizedMessage,
    OperationJob,
    OperationRequest,
    OperationState,
    RiskLevel,
    ScopeType,
)
from bot.src.persistence.models import (
    AuditEventRecord,
    BotAdmin,
    ChatGroup,
    ChatMessage,
    GroupMemberActivityDaily,
    GroupPersonaCooldown,
    GroupPersonaSession,
    LlmResponseCache,
    OperationApprovalRecord,
    OperationJobRecord,
    ProcessedMessage,
)
from bot.src.plugins.persona.session import PersonaCooldown, PersonaSession


class SqlAlchemyStore:
    """实现当前 Store 端口，并将群聊数据写入已规划的 SQL 表。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    # ---- 消息去重与完整群聊记录 ----

    async def claim_message(self, message_id: str) -> bool:
        """原子声明 OneBot 消息 ID；冲突表示消息已处理。"""
        now = datetime.now(UTC)
        try:
            async with self._sessions() as session:
                async with session.begin():
                    existing = await session.get(ProcessedMessage, message_id)
                    if existing is not None and existing.expires_at > now:
                        return False
                    if existing is not None:
                        existing.claimed_at = now
                        existing.expires_at = now + timedelta(days=7)
                    else:
                        session.add(
                            ProcessedMessage(
                                platform_message_id=message_id,
                                expires_at=now + timedelta(days=7),
                            )
                        )
            return True
        except IntegrityError:
            return False

    async def record_chat_message(self, message: NormalizedMessage) -> None:
        """保存所有群聊消息并更新当天成员活跃计数。"""
        if message.scope_type != ScopeType.GROUP:
            return
        async with self._sessions() as session:
            async with session.begin():
                await self._ensure_group(session, message.scope_id)
                session.add(
                    ChatMessage(
                        platform_message_id=message.message_id,
                        group_id=message.scope_id,
                        sender_id=message.sender_id,
                        sender_alias=message.sender_alias[:128],
                        normalized_text=message.text,
                        message_type=message.message_type[:24],
                        reply_to_message_id=message.reply_to,
                        is_at_bot=message.is_at_bot,
                        sent_at=message.created_at,
                    )
                )
                await self._increment_daily_activity(session, message)

    async def append_context(self, message: NormalizedMessage) -> None:
        """入站消息已由路由全量保存；这里只补存机器人成功回复。"""
        if message.scope_type == ScopeType.GROUP and message.sender_id == "bot":
            await self.record_chat_message(message)

    async def get_context(self, scope_id: str, limit: int) -> list[NormalizedMessage]:
        """按时间读取群线性上下文；私聊数据库记录不属于本次需求范围。"""
        if not scope_id.startswith("group:"):
            return []
        group_id = scope_id.removeprefix("group:")
        async with self._sessions() as session:
            statement = (
                select(ChatMessage)
                .where(ChatMessage.group_id == group_id)
                .order_by(ChatMessage.sent_at.desc(), ChatMessage.id.desc())
                .limit(limit)
            )
            rows = list((await session.scalars(statement)).all())
        return [self._to_message(row) for row in reversed(rows)]

    # ---- 运维任务与审批 ----

    async def save_job(self, job: OperationJob) -> None:
        async with self._sessions() as session:
            async with session.begin():
                record = await session.get(OperationJobRecord, job.operation_id)
                if record is None:
                    record = OperationJobRecord(operation_id=job.operation_id)
                    session.add(record)
                self._apply_job(record, job)

                if job.approval_code_hash:
                    approval = await session.get(OperationApprovalRecord, job.operation_id)
                    if approval is None:
                        approval = OperationApprovalRecord(
                            operation_id=job.operation_id,
                            code_hash=job.approval_code_hash,
                            expires_at=job.approval_expires_at or datetime.now(UTC),
                        )
                        session.add(approval)
                    else:
                        approval.code_hash = job.approval_code_hash
                        approval.expires_at = job.approval_expires_at or approval.expires_at
                    if job.state == OperationState.CANCELLED:
                        approval.cancelled_at = datetime.now(UTC)
                    elif job.state in {
                        OperationState.QUEUED,
                        OperationState.RUNNING,
                        OperationState.SUCCEEDED,
                        OperationState.FAILED,
                        OperationState.UNKNOWN,
                    } and approval.used_at is None:
                        approval.used_at = datetime.now(UTC)

    async def get_job(self, operation_id: str) -> OperationJob | None:
        async with self._sessions() as session:
            record = await session.get(OperationJobRecord, operation_id)
            if record is None:
                return None
            approval = await session.get(OperationApprovalRecord, operation_id)
            return self._to_job(record, approval)

    async def find_pending_approval(
        self, scope_type: ScopeType, scope_id: str, code_hash: str
    ) -> OperationJob | None:
        async with self._sessions() as session:
            statement = (
                select(OperationJobRecord)
                .join(OperationApprovalRecord)
                .where(
                    OperationJobRecord.scope_type == scope_type.value,
                    OperationJobRecord.scope_id == scope_id,
                    OperationJobRecord.state == OperationState.PENDING_APPROVAL.value,
                    OperationApprovalRecord.code_hash == code_hash,
                )
            )
            record = (await session.scalars(statement)).first()
            if record is None:
                return None
            approval = await session.get(OperationApprovalRecord, record.operation_id)
            return self._to_job(record, approval)

    async def find_active_job_for_server(self, server_id: str) -> OperationJob | None:
        active_states = [
            OperationState.PENDING_APPROVAL.value,
            OperationState.QUEUED.value,
            OperationState.RUNNING.value,
        ]
        async with self._sessions() as session:
            statement = (
                select(OperationJobRecord)
                .where(OperationJobRecord.server_id == server_id, OperationJobRecord.state.in_(active_states))
                .order_by(OperationJobRecord.created_at.asc())
                .limit(1)
            )
            record = (await session.scalars(statement)).first()
            if record is None:
                return None
            approval = await session.get(OperationApprovalRecord, record.operation_id)
            return self._to_job(record, approval)

    # ---- 审计 ----

    async def append_audit(self, event: AuditEvent) -> None:
        async with self._sessions() as session:
            async with session.begin():
                session.add(
                    AuditEventRecord(
                        correlation_id=event.correlation_id,
                        operation_id=event.operation_id,
                        actor_masked=event.actor,
                        scope=event.scope,
                        event_type=event.event_type,
                        action=event.action,
                        target=event.target,
                        risk_level=event.risk_level,
                        decision=event.decision,
                        reason=event.reason,
                        created_at=event.created_at,
                    )
                )

    # ---- LLM 精确回复缓存 ----

    async def get_llm_cached_response(self, cache_key: str, group_id: str) -> str | None:
        async with self._sessions() as session:
            record = await session.get(LlmResponseCache, cache_key)
            if record is None or record.group_id != group_id:
                return None
            if record.expires_at <= datetime.now(UTC):
                await session.delete(record)
                await session.commit()
                return None
            return record.response_text

    async def save_llm_cached_response(
        self, cache_key: str, group_id: str, response: str, expires_at: datetime
    ) -> None:
        async with self._sessions() as session:
            async with session.begin():
                await self._ensure_group(session, group_id)
                record = await session.get(LlmResponseCache, cache_key)
                if record is None:
                    record = LlmResponseCache(cache_key=cache_key, group_id=group_id)
                    session.add(record)
                record.group_id = group_id
                record.response_text = response
                record.expires_at = expires_at

    # ---- 人格短会话与冷却 ----

    async def get_persona_session(self, group_id: str) -> PersonaSession | None:
        async with self._sessions() as session:
            record = await session.get(GroupPersonaSession, group_id)
            if record is None:
                return None
            return PersonaSession(record.actor_id, record.remaining_replies, record.expires_at)

    async def save_persona_session(self, group_id: str, state: PersonaSession) -> None:
        async with self._sessions() as session:
            async with session.begin():
                await self._ensure_group(session, group_id)
                record = await session.get(GroupPersonaSession, group_id)
                if record is None:
                    record = GroupPersonaSession(group_id=group_id)
                    session.add(record)
                record.actor_id = state.actor_id
                record.remaining_replies = state.remaining_replies
                record.expires_at = state.expires_at

    async def delete_persona_session(self, group_id: str) -> None:
        async with self._sessions() as session:
            async with session.begin():
                record = await session.get(GroupPersonaSession, group_id)
                if record is not None:
                    await session.delete(record)

    async def get_persona_cooldown(self, group_id: str) -> PersonaCooldown:
        async with self._sessions() as session:
            record = await session.get(GroupPersonaCooldown, group_id)
            if record is None:
                return PersonaCooldown(None, None)
            return PersonaCooldown(record.reply_blocked_until, record.mention_blocked_until)

    async def save_persona_cooldown(self, group_id: str, cooldown: PersonaCooldown) -> None:
        async with self._sessions() as session:
            async with session.begin():
                await self._ensure_group(session, group_id)
                record = await session.get(GroupPersonaCooldown, group_id)
                if record is None:
                    record = GroupPersonaCooldown(group_id=group_id)
                    session.add(record)
                record.reply_blocked_until = cooldown.reply_blocked_until
                record.mention_blocked_until = cooldown.mention_blocked_until

    # ---- 映射与内部查询 ----

    async def _ensure_group(self, session: AsyncSession, group_id: str) -> None:
        if await session.get(ChatGroup, group_id) is None:
            session.add(ChatGroup(group_id=group_id))

    async def _increment_daily_activity(self, session: AsyncSession, message: NormalizedMessage) -> None:
        activity_date = message.created_at.astimezone(UTC).date()
        key = (message.scope_id, message.sender_id, activity_date)
        activity = await session.get(GroupMemberActivityDaily, key)
        if activity is None:
            activity = GroupMemberActivityDaily(
                group_id=message.scope_id,
                sender_id=message.sender_id,
                activity_date=activity_date,
            )
            session.add(activity)
        activity.message_count += 1
        activity.character_count += len(message.text)
        activity.last_message_at = message.created_at

    @staticmethod
    def _to_message(record: ChatMessage) -> NormalizedMessage:
        return NormalizedMessage(
            message_id=record.platform_message_id,
            sender_id=record.sender_id,
            sender_alias=record.sender_alias,
            scope_type=ScopeType.GROUP,
            scope_id=record.group_id,
            text=record.normalized_text,
            message_type=record.message_type,
            reply_to=record.reply_to_message_id,
            is_at_bot=record.is_at_bot,
            created_at=record.sent_at,
        )

    @staticmethod
    def _apply_job(record: OperationJobRecord, job: OperationJob) -> None:
        request = job.request
        record.actor_qq_id = request.actor_qq_id
        record.scope_type = request.scope_type.value
        record.scope_id = request.scope_id
        record.action = request.action.value
        record.server_id = request.server_id
        record.risk_level = request.risk_level.value
        record.normalized_params = request.normalized_params
        record.state = job.state.value
        record.result_summary = job.result_summary
        record.created_at = job.created_at
        record.updated_at = job.updated_at

    @staticmethod
    def _to_job(
        record: OperationJobRecord, approval: OperationApprovalRecord | None = None
    ) -> OperationJob:
        request = OperationRequest(
            operation_id=record.operation_id,
            actor_qq_id=record.actor_qq_id,
            scope_type=ScopeType(record.scope_type),
            scope_id=record.scope_id,
            action=ActionType(record.action),
            server_id=record.server_id,
            normalized_params=record.normalized_params,
            risk_level=RiskLevel(record.risk_level),
        )
        return OperationJob(
            operation_id=record.operation_id,
            request=request,
            state=OperationState(record.state),
            approval_code_hash=approval.code_hash if approval else None,
            approval_expires_at=approval.expires_at if approval else None,
            result_summary=record.result_summary,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
