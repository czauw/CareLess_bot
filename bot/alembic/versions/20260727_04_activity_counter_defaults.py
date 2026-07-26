"""initialize daily activity counters reliably

Revision ID: 20260727_04
Revises: 20260726_03
Create Date: 2026-07-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260727_04"
down_revision = "20260726_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Backfill malformed counters and add database-side zero defaults."""
    op.execute(
        "UPDATE group_member_activity_daily "
        "SET message_count = COALESCE(message_count, 0), "
        "character_count = COALESCE(character_count, 0)"
    )
    for column in ("message_count", "character_count"):
        op.alter_column(
            "group_member_activity_daily",
            column,
            existing_type=sa.Integer(),
            existing_nullable=False,
            server_default=sa.text("0"),
        )


def downgrade() -> None:
    """Remove only the server defaults; existing activity data is retained."""
    for column in ("message_count", "character_count"):
        op.alter_column(
            "group_member_activity_daily",
            column,
            existing_type=sa.Integer(),
            existing_nullable=False,
            server_default=None,
        )
