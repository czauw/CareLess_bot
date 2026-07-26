"""应用装配。

仅在这里选择 MVP 适配器；业务插件只通过 Runtime 使用服务。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from bot.src.adapters.memory_store import MemoryStore
from bot.src.adapters.mock_ops_gateway import MockOpsGateway
from bot.src.adapters.null_llm import NullLlmProvider
from bot.src.adapters.openai_compatible_llm import OpenAICompatibleLlmProvider
from bot.src.adapters.sqlalchemy_store import SqlAlchemyStore
from bot.src.config import Settings
from bot.src.persistence.database import create_database_engine, create_session_factory
from bot.src.persistence.schema import ensure_database_schema
from bot.src.core.models import ServerTarget
from bot.src.core.runtime import Runtime, init_runtime
from bot.src.core.services.approval_service import ApprovalService
from bot.src.core.services.audit_service import AuditService
from bot.src.core.services.auth_service import AuthService
from bot.src.core.services.job_service import JobService
from bot.src.core.services.rate_limit_service import RateLimitService
from bot.src.plugins.admin_command.handler import CommandHandler
from bot.src.plugins.admin_command.parser import CommandParser
from bot.src.plugins.persona.context import ContextService
from bot.src.plugins.persona.gate import PersonaGate
from bot.src.plugins.persona.reply_scheduler import PersonaReplyScheduler
from bot.src.plugins.persona.responder import Responder
from bot.src.plugins.persona.session import GroupConversationService


VALID_CAPABILITIES = frozenset({
    "status", "players", "logs", "start", "stop", "restart", "backup"
})


def default_servers_path() -> Path:
    """返回仓库和容器布局都可用的服务器配置路径。"""
    return Path(__file__).resolve().parents[2] / "config" / "servers.yml"


def default_persona_path() -> Path:
    """返回人格 YAML 配置路径。"""
    return Path(__file__).resolve().parents[2] / "config" / "persona.yml"


def load_persona_options(path: Path | None = None) -> dict[str, Any]:
    """读取人格 YAML；环境变量中的同名配置会在运行时覆盖它。"""
    config_path = path or default_persona_path()
    with config_path.open(encoding="utf-8") as file:
        data: dict[str, Any] = yaml.safe_load(file) or {}
    options = data.get("persona", {})
    if not isinstance(options, dict):
        raise ValueError(f"人格配置格式无效: {config_path}")
    return options


def persona_value(settings: Settings, options: dict[str, Any], name: str) -> Any:
    """环境变量或显式 Settings 参数优先，其余值从 persona.yml 读取。"""
    field_name = f"persona_{name}"
    if field_name in settings.model_fields_set:
        return getattr(settings, field_name)
    return options.get(name, getattr(settings, field_name))


def load_server_targets(path: Path | None = None) -> dict[str, ServerTarget]:
    """读取并校验登记的服务器，拒绝重复展示名称和非法配置。"""
    config_path = path or default_servers_path()
    with config_path.open(encoding="utf-8") as file:
        data: dict[str, Any] = yaml.safe_load(file) or {}

    raw_servers = data.get("servers")
    if not isinstance(raw_servers, dict) or not raw_servers:
        raise ValueError(f"服务器配置为空或格式无效: {config_path}")

    targets: dict[str, ServerTarget] = {}
    display_names: set[str] = set()
    for server_id, raw in raw_servers.items():
        if not isinstance(server_id, str) or not isinstance(raw, dict):
            raise ValueError("服务器配置必须为 server_id 到对象的映射")
        target = ServerTarget.from_config(server_id, raw)
        if target.driver not in {"mock", "real"}:
            raise ValueError(f"服务器 {server_id} 使用了不支持的 driver: {target.driver}")
        unknown_capabilities = target.capabilities - VALID_CAPABILITIES
        if unknown_capabilities:
            raise ValueError(f"服务器 {server_id} 有未知能力: {sorted(unknown_capabilities)}")
        if target.display_name in display_names:
            raise ValueError(f"服务器展示名称重复: {target.display_name}")
        display_names.add(target.display_name)
        targets[target.server_id] = target
    return targets


def build_runtime(
    settings: Settings,
    *,
    servers_path: Path | None = None,
    persona_path: Path | None = None,
) -> Runtime:
    """创建 MVP 运行时并注入全局容器。"""
    if settings.ops_backend != "mock":
        raise ValueError("当前代码仅实现 mock Ops Gateway")

    targets = load_server_targets(servers_path)
    persona_options = load_persona_options(persona_path)
    if settings.storage_backend == "sqlalchemy":
        database_url = settings.sqlalchemy_database_url or ""
        ensure_database_schema(
            database_url,
            mode=settings.database_schema_mode,
            migration_lock_timeout_seconds=settings.database_migration_lock_timeout_seconds,
        )
        engine = create_database_engine(database_url)
        store = SqlAlchemyStore(create_session_factory(engine))
    else:
        engine = None
        store = MemoryStore(settings.context_max_messages, settings.context_ttl_seconds)
    gateway = MockOpsGateway(default_timeout=settings.ops_command_timeout_seconds)
    for target in targets.values():
        if target.enabled:
            if target.driver != "mock":
                raise ValueError("当前 MVP 仅支持已启用服务器使用 mock driver")
            gateway.register_server(target.server_id, target.display_name)

    runtime = Runtime.create()
    runtime.config = settings
    runtime.database_engine = engine
    runtime.store = store
    runtime.ops_gateway = gateway
    has_llm = bool(settings.llm_enabled and settings.llm_api_base and settings.llm_api_key)
    runtime.llm_provider = (
        OpenAICompatibleLlmProvider(settings.llm_api_base, settings.llm_api_key, settings.llm_model)
        if has_llm
        else NullLlmProvider()
    )
    runtime.auth_service = AuthService(settings.whitelist_qq_ids)
    runtime.approval_service = ApprovalService(store, settings.approval_ttl_seconds)
    runtime.job_service = JobService(store)
    runtime.audit_service = AuditService(store, enabled=settings.audit_enabled)
    runtime.rate_limit_service = RateLimitService()
    runtime.context_service = ContextService(
        store,
        max_messages=settings.context_max_messages,
        max_tokens=settings.context_max_tokens,
        ttl_seconds=settings.context_ttl_seconds,
    )
    runtime.group_conversation_service = GroupConversationService(
        store,
        max_replies=settings.guest_conversation_max_replies,
        session_ttl_seconds=settings.guest_conversation_ttl_seconds,
        reply_cooldown_seconds=settings.guest_group_reply_cooldown_seconds,
        mention_cooldown_seconds=settings.guest_group_mention_cooldown_seconds,
    )
    runtime.persona_gate = PersonaGate(
        # Null LLM 仅服务硬触发降级，不能参与主动回复。
        active_probability=persona_value(settings, persona_options, "active_probability") if has_llm else 0.0,
        group_cooldown_seconds=persona_value(settings, persona_options, "group_cooldown_seconds"),
        user_cooldown_seconds=persona_value(settings, persona_options, "user_cooldown_seconds"),
        max_active_replies_per_hour=persona_value(settings, persona_options, "max_active_replies_per_hour"),
        quiet_start=persona_value(settings, persona_options, "quiet_start"),
        quiet_end=persona_value(settings, persona_options, "quiet_end"),
        bot_qq_id=settings.bot_qq_id,
        timezone=settings.timezone,
        hard_trigger_enabled=persona_value(settings, persona_options, "hard_trigger_enabled"),
        soft_trigger_enabled=persona_value(settings, persona_options, "soft_trigger_enabled"),
    )
    runtime.responder = Responder(
        runtime.llm_provider,
        llm_max_tokens=settings.llm_max_tokens,
        llm_thinking_enabled=settings.llm_thinking_enabled,
        profile=persona_options.get("profile"),
        max_messages=settings.persona_reply_max_messages,
        cache_enabled=settings.response_cache_enabled,
        cache_ttl_seconds=settings.response_cache_ttl_seconds,
        cache_store=store if settings.storage_backend == "sqlalchemy" else None,
        timezone=settings.timezone,
    )
    runtime.persona_reply_scheduler = PersonaReplyScheduler(
        enabled=settings.persona_reply_delay_enabled,
        min_delay_seconds=settings.persona_reply_delay_min_seconds,
        max_delay_seconds=settings.persona_reply_delay_max_seconds,
        followup_min_delay_seconds=settings.persona_followup_delay_min_seconds,
        followup_max_delay_seconds=settings.persona_followup_delay_max_seconds,
    )
    names = {target.display_name: target.server_id for target in targets.values()}
    runtime.command_handler = CommandHandler(CommandParser(names), gateway, store)
    runtime.server_targets = targets
    init_runtime(runtime)
    return runtime
