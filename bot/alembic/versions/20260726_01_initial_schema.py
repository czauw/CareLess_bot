"""initial schema

Revision ID: 20260726_01
Revises:
Create Date: 2026-07-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260726_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_group",
        sa.Column("group_id", sa.String(length=32), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("persona_enabled", sa.Boolean(), nullable=False),
        sa.Column("summary_enabled", sa.Boolean(), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "processed_message",
        sa.Column("platform_message_id", sa.String(length=96), primary_key=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_processed_message_expires_at", "processed_message", ["expires_at"])
    op.create_table(
        "bot_admin",
        sa.Column("qq_id", sa.String(length=32), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "server_target",
        sa.Column("server_id", sa.String(length=64), primary_key=True),
        sa.Column("display_name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("driver", sa.String(length=24), nullable=False),
        sa.Column("capabilities_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "chat_message",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("platform", sa.String(length=24), nullable=False),
        sa.Column("platform_message_id", sa.String(length=64), nullable=False),
        sa.Column("group_id", sa.String(length=32), sa.ForeignKey("chat_group.group_id"), nullable=False),
        sa.Column("sender_id", sa.String(length=32), nullable=False),
        sa.Column("sender_alias", sa.String(length=128), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("message_type", sa.String(length=24), nullable=False),
        sa.Column("reply_to_message_id", sa.String(length=64), nullable=True),
        sa.Column("is_at_bot", sa.Boolean(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("platform", "platform_message_id", name="uq_chat_message_platform_id"),
    )
    op.create_index("ix_chat_message_group_sent", "chat_message", ["group_id", "sent_at", "id"])
    op.create_index(
        "ix_chat_message_group_sender_sent", "chat_message", ["group_id", "sender_id", "sent_at"]
    )
    op.create_table(
        "group_member_activity_daily",
        sa.Column("group_id", sa.String(length=32), sa.ForeignKey("chat_group.group_id"), primary_key=True),
        sa.Column("sender_id", sa.String(length=32), primary_key=True),
        sa.Column("activity_date", sa.Date(), primary_key=True),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_activity_group_date_count", "group_member_activity_daily", ["group_id", "activity_date", "message_count"]
    )
    op.create_table(
        "group_memory_summary",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("group_id", sa.String(length=32), sa.ForeignKey("chat_group.group_id"), nullable=False),
        sa.Column("summary_type", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_from_message_id", sa.BigInteger(), nullable=True),
        sa.Column("source_to_message_id", sa.BigInteger(), nullable=True),
        sa.Column("memory_version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_summary_group_version", "group_memory_summary", ["group_id", "summary_type", "memory_version"])
    op.create_index("ix_group_memory_summary_expires_at", "group_memory_summary", ["expires_at"])
    op.create_table(
        "group_persona_session",
        sa.Column("group_id", sa.String(length=32), sa.ForeignKey("chat_group.group_id"), primary_key=True),
        sa.Column("actor_id", sa.String(length=32), nullable=False),
        sa.Column("remaining_replies", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_group_persona_session_expires_at", "group_persona_session", ["expires_at"])
    op.create_table(
        "group_persona_cooldown",
        sa.Column("group_id", sa.String(length=32), sa.ForeignKey("chat_group.group_id"), primary_key=True),
        sa.Column("reply_blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mention_blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "llm_response_cache",
        sa.Column("cache_key", sa.String(length=64), primary_key=True),
        sa.Column("group_id", sa.String(length=32), sa.ForeignKey("chat_group.group_id"), nullable=False),
        sa.Column("memory_version", sa.Integer(), nullable=False),
        sa.Column("response_text", sa.String(length=80), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_llm_response_cache_group_id", "llm_response_cache", ["group_id"])
    op.create_index("ix_llm_response_cache_expires_at", "llm_response_cache", ["expires_at"])
    op.create_table(
        "llm_request_metric",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.String(length=32), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_llm_metric_group_created", "llm_request_metric", ["group_id", "created_at"])
    op.create_table(
        "operation_job",
        sa.Column("operation_id", sa.String(length=32), primary_key=True),
        sa.Column("actor_qq_id", sa.String(length=32), nullable=False),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("scope_id", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("server_id", sa.String(length=64), nullable=False),
        sa.Column("risk_level", sa.String(length=8), nullable=False),
        sa.Column("normalized_params", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_operation_job_server_state", "operation_job", ["server_id", "state"])
    op.create_index("ix_operation_job_scope_created", "operation_job", ["scope_type", "scope_id", "created_at"])
    op.create_table(
        "operation_approval",
        sa.Column("operation_id", sa.String(length=32), sa.ForeignKey("operation_job.operation_id"), primary_key=True),
        sa.Column("code_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_operation_approval_expires_at", "operation_approval", ["expires_at"])
    op.create_table(
        "audit_event",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("operation_id", sa.String(length=32), nullable=True),
        sa.Column("actor_masked", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=80), nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=True),
        sa.Column("target", sa.String(length=128), nullable=True),
        sa.Column("risk_level", sa.String(length=8), nullable=True),
        sa.Column("decision", sa.String(length=48), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_event_operation_id", "audit_event", ["operation_id"])
    op.create_index("ix_audit_correlation_created", "audit_event", ["correlation_id", "created_at"])
    op.create_table(
        "summary_run",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("group_id", sa.String(length=32), sa.ForeignKey("chat_group.group_id"), nullable=False),
        sa.Column("trigger_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("top_n", sa.Integer(), nullable=False),
        sa.Column("source_from_message_id", sa.BigInteger(), nullable=True),
        sa.Column("source_to_message_id", sa.BigInteger(), nullable=True),
        sa.Column("result_summary_id", sa.String(length=32), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_summary_run_group_started", "summary_run", ["group_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_summary_run_group_started", table_name="summary_run")
    op.drop_table("summary_run")
    op.drop_index("ix_audit_correlation_created", table_name="audit_event")
    op.drop_index("ix_audit_event_operation_id", table_name="audit_event")
    op.drop_table("audit_event")
    op.drop_index("ix_operation_approval_expires_at", table_name="operation_approval")
    op.drop_table("operation_approval")
    op.drop_index("ix_operation_job_scope_created", table_name="operation_job")
    op.drop_index("ix_operation_job_server_state", table_name="operation_job")
    op.drop_table("operation_job")
    op.drop_index("ix_llm_metric_group_created", table_name="llm_request_metric")
    op.drop_table("llm_request_metric")
    op.drop_index("ix_llm_response_cache_expires_at", table_name="llm_response_cache")
    op.drop_index("ix_llm_response_cache_group_id", table_name="llm_response_cache")
    op.drop_table("llm_response_cache")
    op.drop_table("group_persona_cooldown")
    op.drop_index("ix_group_persona_session_expires_at", table_name="group_persona_session")
    op.drop_table("group_persona_session")
    op.drop_index("ix_group_memory_summary_expires_at", table_name="group_memory_summary")
    op.drop_index("ix_summary_group_version", table_name="group_memory_summary")
    op.drop_table("group_memory_summary")
    op.drop_index("ix_activity_group_date_count", table_name="group_member_activity_daily")
    op.drop_table("group_member_activity_daily")
    op.drop_index("ix_chat_message_group_sender_sent", table_name="chat_message")
    op.drop_index("ix_chat_message_group_sent", table_name="chat_message")
    op.drop_table("chat_message")
    op.drop_table("server_target")
    op.drop_table("bot_admin")
    op.drop_index("ix_processed_message_expires_at", table_name="processed_message")
    op.drop_table("processed_message")
    op.drop_table("chat_group")
