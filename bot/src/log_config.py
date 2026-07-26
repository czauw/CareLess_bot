"""应用日志配置。

日志文件固定写入仓库根目录 log/，使用大小轮转避免单个文件无限增长。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOGGING_CONFIG = PROJECT_ROOT / "config" / "logging.yml"
LOG_DIRECTORY = PROJECT_ROOT / "log"
VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
MAX_LOG_FILE_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class LoggingOptions:
    """经过校验的日志设置。"""

    level: str = "INFO"
    max_file_size_mb: int = 10
    backup_count: int = 5
    console_enabled: bool = True

    @property
    def max_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


def load_logging_options(path: Path = DEFAULT_LOGGING_CONFIG) -> LoggingOptions:
    """读取人类可维护的 YAML 日志配置。"""
    if not path.is_file():
        raise RuntimeError(f"找不到日志配置文件: {path}")
    with path.open(encoding="utf-8") as file:
        data: dict[str, Any] = yaml.safe_load(file) or {}
    raw = data.get("logging", {})
    if not isinstance(raw, dict):
        raise ValueError(f"日志配置格式无效: {path}")

    level = str(raw.get("level", "INFO")).upper()
    max_file_size_mb = raw.get("max_file_size_mb", 10)
    backup_count = raw.get("backup_count", 5)
    console_enabled = raw.get("console_enabled", True)
    if level not in VALID_LOG_LEVELS:
        raise ValueError(f"日志等级必须是 {sorted(VALID_LOG_LEVELS)} 之一")
    if not isinstance(max_file_size_mb, int) or not 1 <= max_file_size_mb <= 10:
        raise ValueError("单个日志文件大小必须是 1 到 10 MB")
    if not isinstance(backup_count, int) or not 1 <= backup_count <= 30:
        raise ValueError("日志备份数量必须是 1 到 30")
    if not isinstance(console_enabled, bool):
        raise ValueError("console_enabled 必须是 true 或 false")
    return LoggingOptions(level, max_file_size_mb, backup_count, console_enabled)


def setup_logging(options: LoggingOptions, *, level_override: str | None = None) -> Path:
    """安装根日志处理器并返回当前日志文件路径。"""
    level = (level_override or options.level).upper()
    if level not in VALID_LOG_LEVELS:
        raise ValueError(f"日志等级必须是 {sorted(VALID_LOG_LEVELS)} 之一")

    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIRECTORY / "careless-bot.log"
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 仅替换本项目创建的处理器，不干扰测试框架或宿主程序的处理器。
    for handler in list(root_logger.handlers):
        if getattr(handler, "_careless_bot_handler", False):
            root_logger.removeHandler(handler)
            handler.close()

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=options.max_bytes,
        backupCount=options.backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    file_handler._careless_bot_handler = True  # type: ignore[attr-defined]
    root_logger.addHandler(file_handler)

    if options.console_enabled:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        console_handler._careless_bot_handler = True  # type: ignore[attr-defined]
        root_logger.addHandler(console_handler)
    return log_file
