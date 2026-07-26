"""MySQL 8 / SQLAlchemy 2.x 表结构。

正文表只保存群聊文本和必要元数据，不保存媒体二进制。时间均使用 UTC。
实际建表由 Alembic migration 执行，本文件只声明当前 schema。
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    """ORM Python 端 UTC 默认值。"""
    return datetime.now(UTC)


def new_id() -> str:
    """生成不暴露数据库自增序号的 32 位标识。"""
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    """所有 ORM 模型的 declarative base。"""


class ChatGroup(Base):
    """机器人加入的群及群级人格、摘要开关。"""

    __tablename__ = "chat_group"

    group_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    persona_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    summary_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class ChatMessage(Base):
    """所有机器人所在群的规范化文本消息。"""

    __tablename__ = "chat_message"
    __table_args__ = (
        UniqueConstraint("platform", "platform_message_id", name="uq_chat_message_platform_id"),
        Index("ix_chat_message_group_sent", "group_id", "sent_at", "id"),
        Index("ix_chat_message_group_sender_sent", "group_id", "sender_id", "sent_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(24), default="onebot_v11", nullable=False)
    platform_message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    group_id: Mapped[str] = mapped_column(ForeignKey("chat_group.group_id"), nullable=False)
    sender_id: Mapped[str] = mapped_column(String(32), nullable=False)
    sender_alias: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(24), default="text", nullable=False)
    reply_to_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_at_bot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ProcessedMessage(Base):
    """入站事件幂等声明，过期后可由后台清理。"""

    __tablename__ = "processed_message"

    platform_message_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class GroupMemberActivityDaily(Base):
    """用于每日活跃成员排序的轻量统计，不需要扫描全文消息。"""

    __tablename__ = "group_member_activity_daily"
    __table_args__ = (Index("ix_activity_group_date_count", "group_id", "activity_date", "message_count"),)

    group_id: Mapped[str] = mapped_column(ForeignKey("chat_group.group_id"), primary_key=True)
    sender_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    activity_date: Mapped[date] = mapped_column(Date, primary_key=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GroupMemorySummary(Base):
    """可过期的群风格与活跃成员摘要，更新后递增 memory_version。"""

    __tablename__ = "group_memory_summary"
    __table_args__ = (Index("ix_summary_group_version", "group_id", "summary_type", "memory_version"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    group_id: Mapped[str] = mapped_column(ForeignKey("chat_group.group_id"), nullable=False)
    summary_type: Mapped[str] = mapped_column(String(32), default="daily", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_from_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_to_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    memory_version: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class GroupPersonaSession(Base):
    """普通成员至多两回合的短会话，可跨机器人进程重启恢复。"""

    __tablename__ = "group_persona_session"

    group_id: Mapped[str] = mapped_column(ForeignKey("chat_group.group_id"), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(32), nullable=False)
    remaining_replies: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class GroupPersonaCooldown(Base):
    """群级回复与艾特冷却。"""

    __tablename__ = "group_persona_cooldown"

    group_id: Mapped[str] = mapped_column(ForeignKey("chat_group.group_id"), primary_key=True)
    reply_blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mention_blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class LlmResponseCache(Base):
    """同群、同上下文、同提示词版本的精确回复缓存。"""

    __tablename__ = "llm_response_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("chat_group.group_id"), nullable=False, index=True)
    memory_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    response_text: Mapped[str] = mapped_column(String(80), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class LlmRequestMetric(Base):
    """不保存提示词正文的模型调用指标，用于观察 Provider 缓存命中。"""

    __tablename__ = "llm_request_metric"
    __table_args__ = (Index("ix_llm_metric_group_created", "group_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class BotAdmin(Base):
    """数据库白名单；部署时可与环境变量白名单合并。"""

    __tablename__ = "bot_admin"

    qq_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ServerTargetRecord(Base):
    """未来替代 servers.yml 的服务器登记表，不存储服务器凭据。"""

    __tablename__ = "server_target"

    server_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    driver: Mapped[str] = mapped_column(String(24), nullable=False)
    capabilities_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class OperationJobRecord(Base):
    """结构化运维任务，不保存原始 QQ 命令或 Shell。"""

    __tablename__ = "operation_job"
    __table_args__ = (
        Index("ix_operation_job_server_state", "server_id", "state"),
        Index("ix_operation_job_scope_created", "scope_type", "scope_id", "created_at"),
    )

    operation_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    actor_qq_id: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    server_id: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(8), nullable=False)
    normalized_params: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class OperationApprovalRecord(Base):
    """高风险任务的一次性确认码哈希与使用状态。"""

    __tablename__ = "operation_approval"

    operation_id: Mapped[str] = mapped_column(
        ForeignKey("operation_job.operation_id"), primary_key=True
    )
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEventRecord(Base):
    """只追加的审计事件；actor 保持脱敏格式。"""

    __tablename__ = "audit_event"
    __table_args__ = (Index("ix_audit_correlation_created", "correlation_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    operation_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    actor_masked: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[str] = mapped_column(String(80), nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target: Mapped[str | None] = mapped_column(String(128), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(8), nullable=True)
    decision: Mapped[str] = mapped_column(String(48), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class SummaryRun(Base):
    """每日或管理员手动触发的群摘要任务记录。"""

    __tablename__ = "summary_run"
    __table_args__ = (Index("ix_summary_run_group_started", "group_id", "started_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    group_id: Mapped[str] = mapped_column(ForeignKey("chat_group.group_id"), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    top_n: Mapped[int] = mapped_column(Integer, nullable=False)
    source_from_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_to_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    result_summary_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
