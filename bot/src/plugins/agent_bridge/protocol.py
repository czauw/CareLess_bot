"""Hermes Agent 桥接协议与数据模型（P2 预留）。

定义 Agent 会话、消息和审批映射的数据结构，
以及 HermesClient Protocol 接口的详细约定。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class AgentSessionState(str, Enum):
    """Agent 会话状态。"""

    IDLE = "idle"
    THINKING = "thinking"
    WAITING_APPROVAL = "waiting_approval"
    EXECUTING = "executing"
    DONE = "done"


@dataclass
class AgentMessage:
    """Agent 对话消息。"""

    role: str  # "user" | "agent" | "system" | "tool"
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ApprovalRequest:
    """Hermes 工具调用审批请求——映射回 QQ 展示。"""

    approval_id: str
    session_id: str
    tool_name: str
    tool_args: dict[str, Any]
    risk_level: str
    description: str
    created_at: datetime
    expires_at: datetime


@dataclass
class HermesSession:
    """Hermes Agent 会话。"""

    session_id: str
    actor_qq_id: str
    scope_id: str  # 群聊或私聊 ID
    state: AgentSessionState = AgentSessionState.IDLE
    messages: list[AgentMessage] = field(default_factory=list)
    pending_approvals: list[ApprovalRequest] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
