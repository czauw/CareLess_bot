"""remove the response-cache character limit

Revision ID: 20260726_03
Revises: 20260726_02
Create Date: 2026-07-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260726_03"
down_revision = "20260726_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """使精确回复缓存与实际回复一样不受字符列长度限制。"""
    op.alter_column(
        "llm_response_cache",
        "response_text",
        existing_type=sa.String(length=80),
        existing_nullable=False,
        type_=sa.Text(),
    )


def downgrade() -> None:
    """拒绝可能截断已缓存长回复的破坏性降级。"""
    raise RuntimeError("20260726_03 不支持自动降级，以免截断已缓存的长回复")
