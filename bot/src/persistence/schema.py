"""SQLAlchemy 启动前的连接检测、版本校验与可选 Alembic 迁移。"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine


logger = logging.getLogger(__name__)
BOT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BOT_ROOT / "alembic.ini"
MIGRATION_LOCK_NAME = "careless_bot_schema_migration"


class DatabaseSchemaError(RuntimeError):
    """数据库无法连接或其 revision 不符合启动要求。"""


def _alembic_config(database_url: str) -> Any:
    """仅在 SQLAlchemy 模式校验或迁移时导入 Alembic。"""
    try:
        from alembic.config import Config
    except ImportError as error:
        raise DatabaseSchemaError("未安装 alembic，无法校验或迁移 SQLAlchemy 数据库") from error

    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(BOT_ROOT / "alembic"))
    config.attributes["database_url"] = database_url
    return config


def migration_head_revision() -> str:
    """返回代码中唯一的最新 Alembic revision。"""
    try:
        from alembic.script import ScriptDirectory
    except ImportError as error:
        raise DatabaseSchemaError("未安装 alembic，无法校验或迁移 SQLAlchemy 数据库") from error

    script = ScriptDirectory.from_config(_alembic_config(""))
    heads = script.get_heads()
    if len(heads) != 1:
        raise DatabaseSchemaError(f"迁移分支异常，期望一个 head，实际为 {heads}")
    return heads[0]


async def _read_database_revision(database_url: str) -> str | None:
    """执行 SELECT 1，并读取 alembic_version；不存在版本表时返回 None。"""
    engine = create_async_engine(database_url, pool_pre_ping=True, future=True)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            has_version_table = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).has_table("alembic_version")
            )
            if not has_version_table:
                return None
            return (await connection.execute(text("SELECT version_num FROM alembic_version"))).scalar_one_or_none()
    except Exception as error:
        raise DatabaseSchemaError("数据库连接检测失败，请检查 SQLALCHEMY_DATABASE_URL 和数据库服务") from error
    finally:
        await engine.dispose()


def _run_alembic_upgrade(database_url: str) -> None:
    """在线程中运行同步 Alembic API，避免嵌套应用主事件循环。"""
    try:
        from alembic import command
    except ImportError as error:
        raise DatabaseSchemaError("未安装 alembic，无法执行数据库迁移") from error

    command.upgrade(_alembic_config(database_url), "head")


async def _migrate_with_lock(database_url: str, lock_timeout_seconds: int) -> None:
    """MySQL 使用 advisory lock 串行化迁移，其他方言保留单进程迁移能力。"""
    engine = create_async_engine(database_url, pool_pre_ping=True, future=True)
    try:
        async with engine.connect() as connection:
            is_mysql = connection.dialect.name.startswith("mysql")
            locked = False
            if is_mysql:
                acquired = await connection.scalar(
                    text("SELECT GET_LOCK(:lock_name, :timeout_seconds)"),
                    {"lock_name": MIGRATION_LOCK_NAME, "timeout_seconds": lock_timeout_seconds},
                )
                if acquired != 1:
                    raise DatabaseSchemaError("等待数据库迁移锁超时，已有实例正在初始化数据库")
                locked = True
            try:
                await asyncio.to_thread(_run_alembic_upgrade, database_url)
            finally:
                if locked:
                    await connection.execute(text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": MIGRATION_LOCK_NAME})
    except DatabaseSchemaError:
        raise
    except Exception as error:
        raise DatabaseSchemaError("数据库迁移失败，机器人不会继续启动") from error
    finally:
        await engine.dispose()


def ensure_database_schema(
    database_url: str,
    *,
    mode: Literal["validate", "migrate"],
    migration_lock_timeout_seconds: int,
) -> None:
    """检测数据库并确保 revision 与代码一致；失败时拒绝启动。"""
    expected_revision = migration_head_revision()
    current_revision = asyncio.run(_read_database_revision(database_url))
    if current_revision == expected_revision:
        logger.info("数据库结构校验通过，revision=%s", current_revision)
        return

    if mode == "validate":
        current = current_revision or "<未初始化>"
        raise DatabaseSchemaError(
            f"数据库结构版本不匹配，当前 {current}，期望 {expected_revision}。"
            "将 DATABASE_SCHEMA_MODE=migrate 后重启可执行迁移。"
        )

    logger.warning("开始数据库迁移，当前 revision=%s，目标 revision=%s", current_revision, expected_revision)
    asyncio.run(_migrate_with_lock(database_url, migration_lock_timeout_seconds))
    migrated_revision = asyncio.run(_read_database_revision(database_url))
    if migrated_revision != expected_revision:
        raise DatabaseSchemaError(
            f"数据库迁移后版本异常，当前 {migrated_revision}，期望 {expected_revision}"
        )
    logger.info("数据库迁移完成，revision=%s", migrated_revision)
