"""应用日志配置。

日志文件固定写入仓库根目录 log/。每次启动以开始时间创建
``月-日-时-分-count.log`` 文件；单文件超过 10 MB 时只递增 count，不覆盖旧日志。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
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
    console_enabled: bool = True

    @property
    def max_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


class TimestampedSizeRotatingFileHandler(logging.FileHandler):
    """按启动时间命名、按大小递增序号的文件处理器。

    命名示例：`07-26-21-05-1.log`。同一次进程启动发生轮转时保持前四段
    时间不变，仅把最后的 count 加一；若同一分钟已有旧文件，也会避开已有序号。
    """

    def __init__(
        self,
        directory: Path,
        *,
        max_bytes: int,
        started_at: datetime | None = None,
        encoding: str = "utf-8",
    ) -> None:
        self._directory = directory
        self._directory.mkdir(parents=True, exist_ok=True)
        self._max_bytes = max_bytes
        self._started_at = started_at or datetime.now()
        self._timestamp = self._started_at.strftime("%m-%d-%H-%M")
        self._count = self._next_available_count()
        super().__init__(self._path_for(self._count), encoding=encoding)

    def shouldRollover(self, record: logging.LogRecord) -> bool:  # noqa: N802
        """在写入前按 UTF-8 字节数判断，尽量不越过配置上限。"""
        if self.stream is None:
            self.stream = self._open()
        rendered = f"{self.format(record)}{self.terminator}"
        encoded_size = len(rendered.encode(self.encoding or "utf-8", errors="replace"))
        self.stream.seek(0, 2)
        return self.stream.tell() + encoded_size > self._max_bytes

    def doRollover(self) -> None:  # noqa: N802
        """关闭满文件并创建同一启动时间、count 加一的新文件。"""
        if self.stream is not None:
            self.stream.close()
            self.stream = None
        self._count = self._next_available_count(start=self._count + 1)
        self.baseFilename = str(self._path_for(self._count))
        self.stream = self._open()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self.shouldRollover(record):
                self.doRollover()
            super().emit(record)
        except Exception:
            self.handleError(record)

    def _path_for(self, count: int) -> Path:
        return self._directory / f"{self._timestamp}-{count}.log"

    def _next_available_count(self, *, start: int = 1) -> int:
        count = start
        while self._path_for(count).exists():
            count += 1
        return count


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
    console_enabled = raw.get("console_enabled", True)
    if level not in VALID_LOG_LEVELS:
        raise ValueError(f"日志等级必须是 {sorted(VALID_LOG_LEVELS)} 之一")
    if not isinstance(max_file_size_mb, int) or not 1 <= max_file_size_mb <= 10:
        raise ValueError("单个日志文件大小必须是 1 到 10 MB")
    if not isinstance(console_enabled, bool):
        raise ValueError("console_enabled 必须是 true 或 false")
    return LoggingOptions(level, max_file_size_mb, console_enabled)


def setup_logging(options: LoggingOptions, *, level_override: str | None = None) -> Path:
    """安装根日志处理器并返回当前日志文件路径。"""
    level = (level_override or options.level).upper()
    if level not in VALID_LOG_LEVELS:
        raise ValueError(f"日志等级必须是 {sorted(VALID_LOG_LEVELS)} 之一")

    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 仅替换本项目创建的处理器，不干扰测试框架或宿主程序的处理器。
    for handler in list(root_logger.handlers):
        if getattr(handler, "_careless_bot_handler", False):
            root_logger.removeHandler(handler)
            handler.close()

    file_handler = TimestampedSizeRotatingFileHandler(LOG_DIRECTORY, max_bytes=options.max_bytes)
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
    return Path(file_handler.baseFilename)
