"""配置加载、校验与默认值。

所有配置通过 pydantic-settings 从环境变量 / .env 文件加载，
启动时执行校验，阻止使用示例默认值。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_ENV_EXAMPLE_FILE = PROJECT_ROOT / "bot" / ".env.example"


def ensure_env_file(
    env_file: Path = DEFAULT_ENV_FILE,
    example_file: Path = DEFAULT_ENV_EXAMPLE_FILE,
) -> bool:
    """缺少 .env 时从示例创建，并返回是否刚刚创建。

    不覆盖已有文件，避免启动时意外替换用户的令牌和数据库配置。
    """
    if env_file.exists():
        if not env_file.is_file():
            raise RuntimeError(f"配置路径不是文件: {env_file}")
        return False
    if not example_file.is_file():
        raise RuntimeError(f"找不到环境变量示例文件: {example_file}")
    shutil.copyfile(example_file, env_file)
    return True


class Settings(BaseSettings):
    """机器人全局配置。"""

    model_config = SettingsConfigDict(
        env_file=DEFAULT_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        enable_decoding=False,
    )

    # --- QQ / OneBot 连接 ---
    onebot_access_token: str = Field(default="", min_length=8)
    # NoneBot 反向 WebSocket 服务监听地址；NapCat 应连接到 /onebot/v11/ws。
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8080, ge=1, le=65535)
    bot_qq_id: str = Field(default="")

    # --- 全局与模块开关 ---
    # BOT_ENABLED=false 时丢弃所有入站消息，适合维护窗口。
    bot_enabled: bool = Field(default=True)
    # ADMIN_COMMANDS_ENABLED=false 时不处理任何 / 命令。
    admin_commands_enabled: bool = Field(default=True)
    # PERSONA_ENABLED=false 时不记录人格上下文，也不生成闲聊回复。
    persona_enabled: bool = Field(default=True)
    # CONTEXT_ENABLED=false 时人格只参考触发消息，不保留短期聊天记录。
    persona_context_enabled: bool = Field(default=True)
    # 两种人格触发可分别关闭；私聊也受硬触发开关控制。
    persona_hard_trigger_enabled: bool = Field(default=True)
    # 默认关闭随机插话；普通成员通过 @ 开启至多两回合的短会话。
    persona_soft_trigger_enabled: bool = Field(default=False)
    # LLM_ENABLED=false 时强制使用安全的 Null LLM 降级实现。
    llm_enabled: bool = Field(default=True)
    # AUDIT_ENABLED=false 时不写审计事件，仅建议用于本地无状态调试。
    audit_enabled: bool = Field(default=True)

    # --- 白名单 ---
    whitelist_qq_ids: set[str] = Field(default_factory=set)

    # --- 允许的群 ---
    allowed_group_ids: set[str] = Field(default_factory=set)

    # --- 数据库 ---
    # memory 不连接数据库；sqlalchemy 启动时会检测连接并校验数据库结构。
    storage_backend: Literal["memory", "sqlalchemy"] = Field(default="memory")
    sqlalchemy_database_url: str | None = Field(default=None)
    # validate 仅校验 revision；migrate 会在启动时执行 Alembic upgrade head。
    database_schema_mode: Literal["validate", "migrate"] = Field(default="validate")
    database_migration_lock_timeout_seconds: int = Field(default=60, ge=1, le=600)

    # --- 群聊人格 ---
    persona_active_probability: float = Field(default=0.02, ge=0.0, le=1.0)
    persona_group_cooldown_seconds: int = Field(default=600, ge=0)
    persona_user_cooldown_seconds: int = Field(default=1200, ge=0)
    # 管理员白名单可绕过群白名单和普通成员的冷却。
    admin_bypass_group_allowlist: bool = Field(default=True)
    admin_bypass_cooldowns: bool = Field(default=True)
    # 普通成员仅在群白名单内可用，私聊默认不响应。
    guest_private_reply_enabled: bool = Field(default=False)
    guest_conversation_max_replies: int = Field(default=2, ge=1, le=2)
    guest_conversation_ttl_seconds: int = Field(default=300, ge=10, le=3600)
    guest_group_reply_cooldown_seconds: int = Field(default=120, ge=0)
    guest_group_mention_cooldown_seconds: int = Field(default=300, ge=0)
    persona_max_active_replies_per_hour: int = Field(default=3, ge=0)
    # 拟人回复延迟使用独立后台任务，不阻塞其他消息处理。
    persona_reply_delay_enabled: bool = Field(default=True)
    persona_reply_delay_min_seconds: float = Field(default=15.0, ge=0.0, le=600.0)
    persona_reply_delay_max_seconds: float = Field(default=30.0, ge=0.0, le=600.0)
    # 分成多条 QQ 消息时，后续消息只使用较短的自然停顿。
    persona_followup_delay_min_seconds: float = Field(default=1.0, ge=0.0, le=60.0)
    persona_followup_delay_max_seconds: float = Field(default=4.0, ge=0.0, le=60.0)
    # 模型最多返回三条实际 QQ 消息；多数情况由提示词引导为一条。
    persona_reply_max_messages: int = Field(default=3, ge=1, le=3)
    persona_quiet_start: str = Field(default="00:30")
    persona_quiet_end: str = Field(default="07:30")

    # --- 上下文 ---
    # 20K 是提示词输入上限的近似 token 预算，不会强行填满。
    context_max_tokens: int = Field(default=20_000, ge=256, le=100_000)
    context_max_messages: int = Field(default=1_000, ge=1)
    context_ttl_seconds: int = Field(default=21_600, ge=0)
    # 精确回复缓存只命中相同群、相同上下文和相同配置，避免串群。
    response_cache_enabled: bool = Field(default=True)
    response_cache_ttl_seconds: int = Field(default=60, ge=0, le=3600)

    # --- 运维 ---
    ops_backend: Literal["mock", "real"] = Field(default="mock")
    # OPS_ENABLED 是运维总开关；读写开关可以独立控制。
    ops_enabled: bool = Field(default=True)
    ops_read_enabled: bool = Field(default=True)
    ops_write_enabled: bool = Field(default=True)
    # R1（启动、备份）默认直接执行；开启后同样需要一次性确认码。
    ops_r1_requires_approval: bool = Field(default=False)
    ops_command_timeout_seconds: int = Field(default=30, ge=1)
    ops_max_log_lines: int = Field(default=100, ge=1, le=1000)
    approval_ttl_seconds: int = Field(default=120, ge=1)

    # --- LLM ---
    llm_api_base: str | None = Field(default=None)
    llm_api_key: str | None = Field(default=None)
    llm_model: str = Field(default="gpt-4o-mini")
    # 机器人短回复默认关闭思考模式，48 token 足够生成最终正文。
    llm_max_tokens: int = Field(default=48, ge=16, le=512)
    # DeepSeek 等兼容服务支持 thinking 参数；短回复默认关闭以避免 token 被推理占尽。
    llm_thinking_enabled: bool = Field(default=False)

    # --- Hermes (P2) ---
    hermes_api_base: str | None = Field(default=None)
    hermes_api_key: str | None = Field(default=None)

    # --- 日志 ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO")

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
        if self.admin_commands_enabled and not self.whitelist_qq_ids:
            raise ValueError("WHITELIST_QQ_IDS 为空。至少需要一个白名单 QQ 号。")
        if self.storage_backend == "sqlalchemy" and not self.sqlalchemy_database_url:
            raise ValueError("STORAGE_BACKEND=sqlalchemy 时必须配置 SQLALCHEMY_DATABASE_URL。")
        if self.ops_backend == "real" and not self.sqlalchemy_database_url:
            raise ValueError("使用真实 Ops Gateway 时必须配置数据库。")
        if self.persona_reply_delay_min_seconds > self.persona_reply_delay_max_seconds:
            raise ValueError("PERSONA_REPLY_DELAY_MIN_SECONDS 不能大于最大延迟。")
        if self.persona_followup_delay_min_seconds > self.persona_followup_delay_max_seconds:
            raise ValueError("PERSONA_FOLLOWUP_DELAY_MIN_SECONDS 不能大于最大延迟。")
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
