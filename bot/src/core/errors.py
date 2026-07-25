"""业务异常。

所有异常继承自 CareLessError，便于统一捕获和日志记录。
"""

from __future__ import annotations


class CareLessError(Exception):
    """所有业务异常的基类。"""


# --- 权限 ---

class NotWhitelistedError(CareLessError):
    """发送者不在白名单中。"""

    def __init__(self, sender_id: str) -> None:
        self.sender_id = sender_id
        super().__init__(f"sender_id={sender_id} 不在白名单中")


# --- 命令解析 ---

class CommandParseError(CareLessError):
    """命令解析失败——语法错误、未知命令或参数不合法。"""


class UnknownServerError(CareLessError):
    """目标服务器未在配置中登记。"""

    def __init__(self, server_id: str) -> None:
        self.server_id = server_id
        super().__init__(f"未知服务器: {server_id}")


class AmbiguousServerError(CareLessError):
    """服务器名称有歧义。"""

    def __init__(self, name: str, matches: list[str]) -> None:
        self.name = name
        self.matches = matches
        super().__init__(f"服务器名称 {name} 匹配多个目标: {matches}")


class RiskLevelBlockedError(CareLessError):
    """操作风险等级被禁止（R3 或当前配置不允许）。"""

    def __init__(self, risk_level: str) -> None:
        self.risk_level = risk_level
        super().__init__(f"风险等级 {risk_level} 的操作在当前阶段不允许")


# --- 审批 ---

class ApprovalError(CareLessError):
    """审批流程异常——确认码无效、过期或已使用。"""


class ApprovalExpiredError(ApprovalError):
    """确认码已过期。"""


class ApprovalAlreadyUsedError(ApprovalError):
    """确认码已被使用。"""


class ApprovalMismatchError(ApprovalError):
    """确认码与会话/操作不匹配。"""


# --- 任务 ---

class JobConflictError(CareLessError):
    """同一服务器已有互斥任务在执行。"""

    def __init__(self, server_id: str, existing_job_id: str) -> None:
        self.server_id = server_id
        self.existing_job_id = existing_job_id
        super().__init__(f"服务器 {server_id} 已有任务 {existing_job_id}")


class JobNotFoundError(CareLessError):
    """任务 ID 不存在。"""


# --- 运维 ---

class OpsGatewayError(CareLessError):
    """Ops Gateway 调用失败。"""


class HermesDisabledError(CareLessError):
    """Hermes Agent 功能未启用。"""

    def __init__(self) -> None:
        super().__init__("Hermes Agent 尚未部署，功能不可用。")


# --- 降级 ---

class ServiceUnavailableError(CareLessError):
    """服务不可用时的降级错误。"""

    def __init__(self, service: str, detail: str = "") -> None:
        self.service = service
        super().__init__(f"{service} 不可用: {detail}")
