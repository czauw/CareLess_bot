from __future__ import annotations

import pytest
from pydantic import ValidationError

from bot.src.config import Settings


def test_sqlalchemy_backend_requires_a_database_url() -> None:
    with pytest.raises(ValidationError, match="SQLALCHEMY_DATABASE_URL"):
        Settings(
            onebot_access_token="abcdefgh",
            whitelist_qq_ids="10001",
            storage_backend="sqlalchemy",
        )


def test_memory_backend_does_not_require_database_url() -> None:
    settings = Settings(
        onebot_access_token="abcdefgh",
        whitelist_qq_ids="10001",
        storage_backend="memory",
    )

    assert settings.sqlalchemy_database_url is None
