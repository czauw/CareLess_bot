from __future__ import annotations

import pytest
from pydantic import ValidationError

from bot.src.config import Settings, ensure_env_file


def test_missing_env_file_is_created_from_example(tmp_path) -> None:
    example = tmp_path / ".env.example"
    example.write_text("ONEBOT_ACCESS_TOKEN=example\n", encoding="utf-8")
    target = tmp_path / ".env"

    assert ensure_env_file(target, example) is True
    assert target.read_text(encoding="utf-8") == "ONEBOT_ACCESS_TOKEN=example\n"
    assert ensure_env_file(target, example) is False


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


def test_database_schema_mode_defaults_to_validate() -> None:
    settings = Settings(onebot_access_token="abcdefgh", whitelist_qq_ids="10001")

    assert settings.database_schema_mode == "validate"
