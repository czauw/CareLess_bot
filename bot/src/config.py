"""配置加载、校验与默认值。

所有配置通过 pydantic-settings 从环境变量 / .env 文件加载，
启动时执行校验，阻止使用示例默认值。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """机器人全局配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        enable_decoding=False,
    )

    # --- QQ / OneBot 连接 ---
    onebot_access_token: str = Field(default="", min_length=8)
    onebot_reverse_ws: str = Field(default="ws://127.0.0.1:8080/onebot/v11/ws")
    bot_qq_id: str = Field(default="")

    # --- 白名单 ---
    whitelist_qq_ids: set[str] = Field(default_factory=set)

    # --- 允许的群 ---
    allowed_group_ids: set[str] = Field(default_factory=set)

    # --- 数据库 ---
    sqlalchemy_database_url: str | None = Field(default=None)

    # --- 群聊人格 ---
    persona_active_probability: float = Field(default=0.02, ge=0.0, le=1.0)
    persona_group_cooldown_seconds: int = Field(default=600, ge=0)
    persona_user_cooldown_seconds: int = Field(default=1200, ge=0)
    persona_max_active_replies_per_hour: int = Field(default=3, ge=0)
    persona_max_reply_length: int = Field(default=80, ge=1)
    persona_quiet_start: str = Field(default="00:30")
    persona_quiet_end: str = Field(default="07:30")

    # --- 上下文 ---
    context_max_messages: int = Field(default=30, ge=1)
    context_ttl_seconds: int = Field(default=1200, ge=0)

    # --- 运维 ---
    ops_backend: Literal["mock", "real"] = Field(default="mock")
    ops_command_timeout_seconds: int = Field(default=30, ge=1)
    approval_ttl_seconds: int = Field(default=120, ge=1)

    # --- LLM ---
    llm_api_base: str | None = Field(default=None)
    llm_api_key: str | None = Field(default=None)
    llm_model: str = Field(default="gpt-4o-mini")

    # --- Hermes (P2) ---
    hermes_api_base: str | None = Field(default=None)
    hermes_api_key: str | None = Field(default=None)

    # --- 日志 ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")

    # --- 时区 ---
    timezone: str = Field(default="Asia/Shanghai")

    @field_validator("whitelist_qq_ids", "allowed_group_ids", mode="before")
    @classmethod
    def _split_id_sets(cls, value: object) -> object:
        """支持 .env 中常用的逗号分隔 QQ 号配置。"""
        if isinstance(value, str):
            return {item.strip() for item in value.split(",") if item.strip()}
        return value

    @model_validator(mode="after")
    def _validate_critical(self) -> "Settings":
        """校验关键配置——阻止使用示例值启动。"""
        if not self.onebot_access_token:
            raise ValueError("ONEBOT_ACCESS_TOKEN 未设置。请生成高强度随机令牌。")
        if self.onebot_access_token == "请替换为高强度随机令牌":
            raise ValueError("ONEBOT_ACCESS_TOKEN 使用了示例值，请替换为自己的令牌。")
        if not self.whitelist_qq_ids:
            raise ValueError("WHITELIST_QQ_IDS 为空。至少需要一个白名单 QQ 号。")
        if self.ops_backend == "real" and not self.sqlalchemy_database_url:
            raise ValueError("使用真实 Ops Gateway 时必须配置数据库。")
        return self

    @property
    def is_quiet_hours(self, hour: int) -> bool:
        """检查给定小时是否在静默时段内。"""
        start_h, _ = map(int, self.persona_quiet_start.split(":"))
        end_h, _ = map(int, self.persona_quiet_end.split(":"))
        if start_h < end_h:
            return start_h <= hour < end_h
        # 跨午夜（如 23:00 — 07:00）
        return hour >= start_h or hour < end_h


# --- 全局单例 ---
_settings: Settings | None = None


def load_config() -> Settings:
    """加载并缓存配置（启动时调用一次）。"""
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings


def get_config() -> Settings:
    """获取已加载的配置；未加载时抛出异常。"""
    if _settings is None:
        raise RuntimeError("配置尚未加载，请先调用 load_config()。")
    return _settings
