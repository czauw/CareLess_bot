from __future__ import annotations

import logging
from datetime import datetime

import pytest

from bot.src.log_config import (
    MAX_LOG_FILE_BYTES,
    TimestampedSizeRotatingFileHandler,
    load_logging_options,
)


def test_logging_yaml_loads_human_readable_settings(tmp_path) -> None:
    config_file = tmp_path / "logging.yml"
    config_file.write_text(
        "logging:\n  level: debug\n  max_file_size_mb: 10\n  console_enabled: false\n",
        encoding="utf-8",
    )

    options = load_logging_options(config_file)

    assert options.level == "DEBUG"
    assert options.max_bytes == MAX_LOG_FILE_BYTES
    assert not options.console_enabled


def test_logging_yaml_rejects_files_larger_than_ten_mb(tmp_path) -> None:
    config_file = tmp_path / "logging.yml"
    config_file.write_text("logging:\n  max_file_size_mb: 11\n", encoding="utf-8")

    with pytest.raises(ValueError, match="1 到 10 MB"):
        load_logging_options(config_file)


def test_timestamped_handler_rotates_by_incrementing_count(tmp_path) -> None:
    handler = TimestampedSizeRotatingFileHandler(
        tmp_path,
        max_bytes=20,
        started_at=datetime(2026, 7, 26, 21, 5),
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("careless-test-log-rotation")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False

    logger.info("first-entry")
    logger.info("second-entry")
    handler.close()

    assert (tmp_path / "07-26-21-05-1.log").read_text(encoding="utf-8") == "first-entry\n"
    assert (tmp_path / "07-26-21-05-2.log").read_text(encoding="utf-8") == "second-entry\n"
