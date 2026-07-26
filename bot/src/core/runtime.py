"""运行时依赖注入与生命周期管理。

通过单例容器管理所有服务实例，在 NoneBot 启动/关闭时初始化和清理。
插件通过 get_runtime() 获取所需服务。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 前向引用——在 runtime 初始化时注入具体实现
from bot.src.core.ports import LlmProvider, OpsGateway, Store
from bot.src.core.services.approval_service import ApprovalService
from bot.src.core.services.audit_service import AuditService
from bot.src.core.services.auth_service import AuthService
from bot.src.core.services.job_service import JobService
from bot.src.core.services.rate_limit_service import RateLimitService


@dataclass
class Runtime:
    """应用运行时容器——持有所有服务单例。

    在 NoneBot 启动时由 bot.py 初始化，插件通过 get_runtime() 获取。
    """

    config: Any = None  # Settings
    database_engine: Any = None
    store: Store | None = None
    ops_gateway: OpsGateway | None = None
    llm_provider: LlmProvider | None = None
    auth_service: AuthService | None = None
    approval_service: ApprovalService | None = None
    job_service: JobService | None = None
    audit_service: AuditService | None = None
    rate_limit_service: RateLimitService | None = None
    context_service: Any = None
    persona_gate: Any = None
    responder: Any = None
    group_conversation_service: Any = None
    command_handler: Any = None
    server_targets: dict[str, Any] = field(default_factory=dict)

    _initialized: bool = False

    @classmethod
    def create(cls) -> "Runtime":
        """创建空的运行时容器。"""
        return cls()

    def is_ready(self) -> bool:
        """所有核心服务是否已注入。"""
        return self._initialized


# --- 全局单例 ---
_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    """获取当前运行时容器。未初始化时抛出异常。"""
    if _runtime is None:
        raise RuntimeError("Runtime 尚未初始化，请先调用 init_runtime()。")
    return _runtime


def init_runtime(runtime: Runtime) -> None:
    """注入全局运行时实例（启动时调用一次）。"""
    global _runtime
    _runtime = runtime
    _runtime._initialized = True
