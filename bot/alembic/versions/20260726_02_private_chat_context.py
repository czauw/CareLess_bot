"""persist private messages and scope-based context

Revision ID: 20260726_02
Revises: 20260726_01
Create Date: 2026-07-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260726_02"
down_revision = "20260726_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """迁移至群/私聊通用 scope，并兼容 MySQL 中断后的再次启动。

    MySQL 的 DDL 不能随 Alembic 事务回滚。若进程在多个 DDL 之间中断，
    revision 尚未写入但部分列可能已经存在；因此每一步均根据实际表结构决定
    是否执行，避免下一次启动因重复 ADD COLUMN 而永久卡住。
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"]: column for column in inspector.get_columns("chat_message")}

    # 既有记录均为群消息；先以服务器默认值平滑回填，再移除默认值。
    added_scope_type = "scope_type" not in columns
    if added_scope_type:
        op.add_column(
            "chat_message",
            sa.Column("scope_type", sa.String(length=16), nullable=False, server_default="group"),
        )
    if "scope_id" not in columns:
        op.add_column("chat_message", sa.Column("scope_id", sa.String(length=32), nullable=True))

    op.execute("UPDATE chat_message SET scope_id = group_id WHERE scope_id IS NULL")

    # MySQL CHANGE/MODIFY 必须提供现有列类型。
    if added_scope_type or columns.get("scope_type", {}).get("default") is not None:
        op.alter_column(
            "chat_message",
            "scope_type",
            existing_type=sa.String(length=16),
            existing_nullable=False,
            server_default=None,
        )

    # 使用新的 inspector，确保首次迁移和上次半完成后的恢复都能得到正确 nullable 状态。
    columns = {column["name"]: column for column in sa.inspect(bind).get_columns("chat_message")}
    if columns["scope_id"]["nullable"]:
        op.alter_column(
            "chat_message",
            "scope_id",
            existing_type=sa.String(length=32),
            existing_nullable=True,
            nullable=False,
        )
    if not columns["group_id"]["nullable"]:
        op.alter_column(
            "chat_message",
            "group_id",
            existing_type=sa.String(length=32),
            existing_nullable=False,
            nullable=True,
        )

    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("chat_message")}
    if "ix_chat_message_scope_sent" not in indexes:
        op.create_index(
            "ix_chat_message_scope_sent",
            "chat_message",
            ["scope_type", "scope_id", "sent_at", "id"],
        )


def downgrade() -> None:
    # 私聊记录无法无损映射回旧的 group_id 非空结构，拒绝破坏性降级。
    raise RuntimeError("包含私聊记录的 20260726_02 迁移不支持自动降级")
