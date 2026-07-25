"""核心领域模型与枚举。

定义系统内部使用的所有数据结构，与 OneBot 协议细节解耦。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Literal


# ============================================================
# 枚举
# ============================================================

class RiskLevel(str, Enum):
    """运维操作风险等级。"""

    R0 = "R0"  # 只读
    R1 = "R1"  # 可逆
    R2 = "R2"  # 有中断
    R3 = "R3"  # 破坏性（MVP 禁止）


class OperationState(str, Enum):
    """运维任务状态。"""

    PENDING_APPROVAL = "pending_approval"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ActionType(str, Enum):
    """运维动作类型。"""

    STATUS = "status"
    PLAYERS = "players"
    LOGS = "logs"
    START = "start"
    STOP = "stop"
    RESTART = "restart"
    BACKUP = "backup"


class ScopeType(str, Enum):
    """会话作用域类型。"""

    GROUP = "group"
    PRIVATE = "private"


class TriggerType(str, Enum):
    """回复触发类型。"""

    HARD = "hard"      # 硬触发（@、回复、命令）
    SOFT = "soft"      # 软触发（概率吐槽）
    COMMAND = "command"  # 管理命令
    NONE = "none"      # 不触发


# ============================================================
# 消息模型
# ============================================================

@dataclass(frozen=True)
class NormalizedMessage:
    """从 OneBot 事件规范化的内部消息。"""

    message_id: str
    sender_id: str
    sender_alias: str  # 群名片或昵称快照
    scope_type: ScopeType
    scope_id: str  # 群聊为 group_id，私聊为发送者 QQ 号
    text: str
    message_type: str  # "text", "image", "file" 等
    reply_to: str | None
    is_at_bot: bool
    created_at: datetime


# ============================================================
# 运维模型
# ============================================================

@dataclass(frozen=True)
class ServerTarget:
    """登记的服务器目标。"""

    server_id: str
    display_name: str
    driver: str  # "mock" | "real"
    capabilities: frozenset[str]
    enabled: bool = True

    @classmethod
    def from_config(cls, server_id: str, data: dict) -> "ServerTarget":
        return cls(
            server_id=server_id,
            display_name=data.get("display_name", server_id),
            driver=data.get("driver", "mock"),
            capabilities=frozenset(data.get("capabilities", [])),
            enabled=bool(data.get("enabled", True)),
        )


@dataclass(frozen=True)
class OperationRequest:
    """从 QQ 消息解析的运维请求——只能构造此结构，不能构造 Shell 字符串。"""

    operation_id: str
    actor_qq_id: str
    scope_type: ScopeType
    scope_id: str
    action: ActionType
    server_id: str
    normalized_params: dict[str, str] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.R0


@dataclass
class OperationJob:
    """运维任务完整记录。"""

    operation_id: str
    request: OperationRequest
    state: OperationState = OperationState.PENDING_APPROVAL
    approval_code_hash: str | None = None
    approval_expires_at: datetime | None = None
    result_summary: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ============================================================
# 审计模型
# ============================================================

@dataclass(frozen=True)
class AuditEvent:
    """审计事件。"""

    event_type: str
    actor: str  # 脱敏后的 QQ 号
    scope: str
    decision: str
    reason: str | None
    correlation_id: str
    operation_id: str | None = None
    action: str | None = None
    target: str | None = None
    risk_level: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# ============================================================
# 运维结果模型
# ============================================================

@dataclass(frozen=True)
class ServerStatus:
    """服务器状态。"""

    server_id: str
    online: bool
    version: str | None = None
    player_count: int = 0
    max_players: int = 0
    tps: float | None = None  # Minecraft TPS
    mspt: float | None = None  # Minecraft MSPT
    cpu_percent: float | None = None
    memory_percent: float | None = None
    uptime: str | None = None


@dataclass(frozen=True)
class PlayersResult:
    """在线玩家信息。"""

    server_id: str
    online_count: int
    max_players: int
    players: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LogsResult:
    """服务器日志。"""

    server_id: str
    lines: list[str]
    total_lines: int


@dataclass(frozen=True)
class OperationResult:
    """运维操作执行结果。"""

    operation_id: str
    success: bool
    state: OperationState
    summary: str
    detail: dict | None = None
