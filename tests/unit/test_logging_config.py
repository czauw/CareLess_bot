from __future__ import annotations

import pytest

from bot.src.log_config import MAX_LOG_FILE_BYTES, load_logging_options


def test_logging_yaml_loads_human_readable_settings(tmp_path) -> None:
    config_file = tmp_path / "logging.yml"
    config_file.write_text(
        "logging:\n  level: debug\n  max_file_size_mb: 10\n  backup_count: 3\n"
        "  console_enabled: false\n",
        encoding="utf-8",
    )

    options = load_logging_options(config_file)

    assert options.level == "DEBUG"
    assert options.max_bytes == MAX_LOG_FILE_BYTES
    assert options.backup_count == 3
    assert not options.console_enabled


def test_logging_yaml_rejects_files_larger_than_ten_mb(tmp_path) -> None:
    config_file = tmp_path / "logging.yml"
    config_file.write_text("logging:\n  max_file_size_mb: 11\n", encoding="utf-8")

    with pytest.raises(ValueError, match="1 到 10 MB"):
        load_logging_options(config_file)
