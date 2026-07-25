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
from bot.src.config import Settings
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
from bot.src.plugins.persona.responder import Responder


def default_servers_path() -> Path:
    """返回仓库和容器布局都可用的服务器配置路径。"""
    return Path(__file__).resolve().parents[2] / "config" / "servers.yml"


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
        if target.display_name in display_names:
            raise ValueError(f"服务器展示名称重复: {target.display_name}")
        display_names.add(target.display_name)
        targets[target.server_id] = target
    return targets


def build_runtime(settings: Settings, *, servers_path: Path | None = None) -> Runtime:
    """创建 MVP 运行时并注入全局容器。"""
    if settings.ops_backend != "mock":
        raise ValueError("当前代码仅实现 mock Ops Gateway")

    targets = load_server_targets(servers_path)
    store = MemoryStore(settings.context_max_messages, settings.context_ttl_seconds)
    gateway = MockOpsGateway(default_timeout=settings.ops_command_timeout_seconds)
    for target in targets.values():
        gateway.register_server(target.server_id, target.display_name)

    runtime = Runtime.create()
    runtime.config = settings
    runtime.store = store
    runtime.ops_gateway = gateway
    has_llm = bool(settings.llm_api_base and settings.llm_api_key)
    runtime.llm_provider = (
        OpenAICompatibleLlmProvider(settings.llm_api_base, settings.llm_api_key, settings.llm_model)
        if has_llm
        else NullLlmProvider()
    )
    runtime.auth_service = AuthService(settings.whitelist_qq_ids)
    runtime.approval_service = ApprovalService(store, settings.approval_ttl_seconds)
    runtime.job_service = JobService(store)
    runtime.audit_service = AuditService(store)
    runtime.rate_limit_service = RateLimitService()
    runtime.context_service = ContextService(
        store,
        max_messages=settings.context_max_messages,
        ttl_seconds=settings.context_ttl_seconds,
    )
    runtime.persona_gate = PersonaGate(
        # Null LLM 仅服务硬触发降级，不能参与主动回复。
        active_probability=settings.persona_active_probability if has_llm else 0.0,
        group_cooldown_seconds=settings.persona_group_cooldown_seconds,
        user_cooldown_seconds=settings.persona_user_cooldown_seconds,
        max_active_replies_per_hour=settings.persona_max_active_replies_per_hour,
        quiet_start=settings.persona_quiet_start,
        quiet_end=settings.persona_quiet_end,
        bot_qq_id=settings.bot_qq_id,
        timezone=settings.timezone,
    )
    runtime.responder = Responder(runtime.llm_provider, max_reply_length=settings.persona_max_reply_length)
    names = {target.display_name: target.server_id for target in targets.values()}
    runtime.command_handler = CommandHandler(CommandParser(names), gateway, store)
    runtime.server_targets = targets
    init_runtime(runtime)
    return runtime
