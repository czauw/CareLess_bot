from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from bot.src.adapters.sqlalchemy_store import SqlAlchemyStore
from bot.src.persistence.models import Base, ChatMessage, GroupMemorySummary, OperationJobRecord


def test_schema_declares_all_required_persistence_tables() -> None:
    expected_tables = {
        "audit_event",
        "bot_admin",
        "chat_group",
        "chat_message",
        "group_member_activity_daily",
        "group_memory_summary",
        "group_persona_cooldown",
        "group_persona_session",
        "llm_request_metric",
        "llm_response_cache",
        "operation_approval",
        "operation_job",
        "processed_message",
        "server_target",
        "summary_run",
    }

    assert expected_tables <= set(Base.metadata.tables)
    assert "normalized_text" in ChatMessage.__table__.c
    assert "scope_type" in ChatMessage.__table__.c
    assert "scope_id" in ChatMessage.__table__.c
    assert ChatMessage.__table__.c.group_id.nullable
    assert "memory_version" in GroupMemorySummary.__table__.c
    assert "normalized_params" in OperationJobRecord.__table__.c


def test_initial_alembic_revision_is_available() -> None:
    revision_file = Path("bot/alembic/versions/20260726_01_initial_schema.py")
    assert revision_file.is_file()
    assert 'revision = "20260726_01"' in revision_file.read_text(encoding="utf-8")


def test_private_context_alembic_revision_is_available() -> None:
    revision_file = Path("bot/alembic/versions/20260726_02_private_chat_context.py")
    assert revision_file.is_file()
    assert 'revision = "20260726_02"' in revision_file.read_text(encoding="utf-8")


def test_unbounded_cached_response_alembic_revision_is_available() -> None:
    revision_file = Path("bot/alembic/versions/20260726_03_unbounded_cached_response.py")
    assert revision_file.is_file()
    assert 'revision = "20260726_03"' in revision_file.read_text(encoding="utf-8")


def test_sqlalchemy_message_timestamps_are_restored_as_utc() -> None:
    """MySQL DATETIME 读取为 naive datetime，不能按本机时区解释。"""
    record = SimpleNamespace(
        platform_message_id="private-message",
        sender_id="10001",
        sender_alias="tester",
        scope_type="private",
        scope_id="10001",
        normalized_text="remember this",
        message_type="text",
        reply_to_message_id=None,
        is_at_bot=False,
        sent_at=datetime(2026, 7, 26, 13, 0, 0),
    )

    message = SqlAlchemyStore._to_message(record)

    assert message.created_at == datetime(2026, 7, 26, 13, 0, 0, tzinfo=UTC)
