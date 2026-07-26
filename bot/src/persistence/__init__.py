"""SQLAlchemy 持久化层。

本包仅定义元数据、会话工厂和未来 Store 的落点；不会在导入时连接数据库。
"""

from bot.src.persistence.models import Base

__all__ = ["Base"]
