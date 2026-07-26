"""异步 SQLAlchemy 引擎与会话工厂。

调用者必须显式创建引擎；本模块本身不建立网络连接。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def create_database_engine(database_url: str) -> AsyncEngine:
    """根据示例 DSN 创建异步引擎，实际连接延后到首次数据库操作。"""
    return create_async_engine(database_url, pool_pre_ping=True, future=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """创建不自动提交、不自动过期的异步会话工厂。"""
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
