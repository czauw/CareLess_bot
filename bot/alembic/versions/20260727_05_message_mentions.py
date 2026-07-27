"""persist structured mention metadata

Revision ID: 20260727_05
Revises: 20260727_04
Create Date: 2026-07-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260727_05"
down_revision = "20260727_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """保存结构化 @ 目标，供群场景在进程重启后继续使用。"""
    op.add_column("chat_message", sa.Column("at_user_ids_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_message", "at_user_ids_json")
