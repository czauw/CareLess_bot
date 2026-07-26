from __future__ import annotations

from pathlib import Path

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
    assert "memory_version" in GroupMemorySummary.__table__.c
    assert "normalized_params" in OperationJobRecord.__table__.c


def test_initial_alembic_revision_is_available() -> None:
    revision_file = Path("bot/alembic/versions/20260726_01_initial_schema.py")
    assert revision_file.is_file()
    assert 'revision = "20260726_01"' in revision_file.read_text(encoding="utf-8")
