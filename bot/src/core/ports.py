"""核心端口（抽象接口）。

所有外部能力通过 Protocol 定义，插件只依赖接口而非具体实现。
MVP 使用内存/模拟适配器；生产环境替换为真实实现。
"""

from __future__ import annotations

from typing import Protocol

from bot.src.core.models import (
    AuditEvent,
    LogsResult,
    NormalizedMessage,
    OperationJob,
    OperationResult,
    PlayersResult,
    ServerStatus,
    ScopeType,
)


# ============================================================
# 存储端口
# ============================================================

class Store(Protocol):
    """消息、任务与审计的持久化接口。"""

    # -- 消息去重 --
    async def claim_message(self, message_id: str) -> bool:
        """标记 message_id 已处理；返回 True 表示首次处理。"""
        ...

    # -- 上下文 --
    async def append_context(self, message: NormalizedMessage) -> None:
        """将消息追加到对应作用域的短期上下文窗口。"""
        ...

    async def record_chat_message(self, message: NormalizedMessage) -> None:
        """持久化所有群聊、私聊消息；内存实现可为无操作。"""
        ...

    async def get_context(
        self, scope_id: str, limit: int
    ) -> list[NormalizedMessage]:
        """获取作用域的最近 N 条上下文消息。"""
        ...

    # -- 运维任务 --
    async def save_job(self, job: OperationJob) -> None:
        """保存或更新任务。"""
        ...

    async def get_job(self, operation_id: str) -> OperationJob | None:
        """按 ID 获取任务。"""
        ...

    async def find_pending_approval(
        self, scope_type: ScopeType, scope_id: str, code_hash: str
    ) -> OperationJob | None:
        """按作用域和确认码哈希查找待审批任务。"""
        ...

    # -- 审计 --
    async def append_audit(self, event: AuditEvent) -> None:
        """追加审计事件。"""
        ...


# ============================================================
# Ops Gateway 端口
# ============================================================

class OpsGateway(Protocol):
    """服务器运维能力接口——只暴露结构化动作，不暴露 Shell。"""

    async def get_status(self, server_id: str) -> ServerStatus:
        """查询服务器状态。"""
        ...

    async def get_players(self, server_id: str) -> PlayersResult:
        """查询在线玩家。"""
        ...

    async def get_logs(self, server_id: str, limit: int) -> LogsResult:
        """获取最近日志。"""
        ...

    async def start_server(self, server_id: str) -> OperationResult:
        """启动服务器。"""
        ...

    async def stop_server(self, server_id: str) -> OperationResult:
        """停止服务器。"""
        ...

    async def restart_server(self, server_id: str) -> OperationResult:
        """重启服务器。"""
        ...

    async def backup_server(self, server_id: str) -> OperationResult:
        """触发备份。"""
        ...

    async def check_operation(self, operation_id: str) -> OperationResult:
        """查询异步任务状态。"""
        ...


# ============================================================
# LLM Provider 端口
# ============================================================

class LlmProvider(Protocol):
    """LLM 调用接口——仅用于群聊人格回复，不参与权限/命令判断。"""

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 200,
        temperature: float = 0.8,
        thinking_enabled: bool | None = None,
    ) -> str:
        """发送对话并返回生成的文本。"""
        ...


# ============================================================
# Hermes Agent 端口（P2 预留）
# ============================================================

class HermesClient(Protocol):
    """Hermes Agent 桥接接口。"""

    async def create_session(self, actor_qq_id: str, scope_id: str) -> str:
        """创建 Agent 会话。"""
        ...

    async def send_message(self, session_id: str, text: str) -> dict:
        """向 Agent 发送消息。"""
        ...

    async def approve(self, session_id: str, approval_id: str) -> dict:
        """审批 Agent 提出的危险操作。"""
        ...

    async def cancel(self, session_id: str, approval_id: str) -> None:
        """取消 Agent 待审批操作。"""
        ...
