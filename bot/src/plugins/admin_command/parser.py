"""确定性命令解析器。

将 QQ 文本解析为结构化命令对象，不依赖 LLM。
支持的命令：
  /服 状态|玩家|日志|启动|停止|重启|备份 [服名] [参数]
  /任务 [任务ID]
  /确认 <一次性码>
  /取消 <一次性码>
  /帮助

设计原则：
- 命令名、子命令和参数数量必须明确匹配
- 服名只能映射到配置中的 server_id
- 解析结果是领域对象，不保留原始命令字符串
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from bot.src.core.errors import CommandParseError
from bot.src.core.models import ActionType, OperationRequest, RiskLevel, ScopeType

# --- 风险映射 ---
ACTION_RISK: dict[ActionType, RiskLevel] = {
    ActionType.STATUS: RiskLevel.R0,
    ActionType.PLAYERS: RiskLevel.R0,
    ActionType.LOGS: RiskLevel.R0,
    ActionType.START: RiskLevel.R1,
    ActionType.BACKUP: RiskLevel.R1,
    ActionType.STOP: RiskLevel.R2,
    ActionType.RESTART: RiskLevel.R2,
}


# --- 命令解析结果 ---

@dataclass
class ParsedCommand:
    """解析后的命令对象。"""

    kind: str  # "server_op" | "job_query" | "approve" | "cancel" | "help"
    action: ActionType | None = None
    server_id: str | None = None
    params: dict[str, str] = field(default_factory=dict)
    raw_code: str = ""  # 确认/取消码


class CommandParser:
    """确定性命令解析器。"""

    # /服 <子命令> [服名] [参数]
    SERVER_CMD = re.compile(
        r"^/服\s+(状态|玩家|日志|启动|停止|重启|备份)"
        r"(?:\s+(\S+))?"
        r"(?:\s+(\S+))?$"
    )

    # /任务 <ID>
    JOB_CMD = re.compile(r"^/任务\s+(\S+)$")

    # /确认 <码>
    APPROVE_CMD = re.compile(r"^/确认\s+(\S+)$")

    # /取消 <码>
    CANCEL_CMD = re.compile(r"^/取消\s+(\S+)$")

    # /帮助
    HELP_CMD = re.compile(r"^/帮助$")

    # 子命令 → ActionType
    ACTION_MAP: dict[str, ActionType] = {
        "状态": ActionType.STATUS,
        "玩家": ActionType.PLAYERS,
        "日志": ActionType.LOGS,
        "启动": ActionType.START,
        "停止": ActionType.STOP,
        "重启": ActionType.RESTART,
        "备份": ActionType.BACKUP,
    }

    def __init__(self, server_names: dict[str, str]) -> None:
        """server_names: {显示名 → server_id} 映射。"""
        self._servers = server_names

    def parse(self, text: str) -> ParsedCommand:
        """解析文本为 ParsedCommand；失败抛出 CommandParseError。"""
        text = text.strip()

        # /帮助
        if m := self.HELP_CMD.match(text):
            return ParsedCommand(kind="help")

        # /任务
        if m := self.JOB_CMD.match(text):
            return ParsedCommand(kind="job_query", params={"job_id": m.group(1)})

        # /确认
        if m := self.APPROVE_CMD.match(text):
            return ParsedCommand(kind="approve", raw_code=m.group(1))

        # /取消
        if m := self.CANCEL_CMD.match(text):
            return ParsedCommand(kind="cancel", raw_code=m.group(1))

        # /服
        if m := self.SERVER_CMD.match(text):
            sub = m.group(1)
            arg1 = m.group(2)
            arg2 = m.group(3)

            action = self.ACTION_MAP[sub]

            # 解析服名 / 行数
            server_id: str | None = None
            params: dict[str, str] = {}

            if action == ActionType.LOGS:
                # /服 日志 [服名] [行数]
                if arg1 and arg1.isdigit():
                    params["limit"] = arg1
                elif arg1:
                    server_id = self._resolve_server(arg1)
                    if arg2 and arg2.isdigit():
                        params["limit"] = arg2
                params.setdefault("limit", "20")
            else:
                if arg1:
                    server_id = self._resolve_server(arg1)

            return ParsedCommand(
                kind="server_op",
                action=action,
                server_id=server_id,
                params=params,
            )

        raise CommandParseError(f"无法解析命令: {text[:50]}")

    def _resolve_server(self, name: str) -> str:
        """按显示名或 server_id 解析服务器；失败抛出异常。"""
        from bot.src.core.errors import AmbiguousServerError, UnknownServerError

        # 精确匹配 server_id
        if name in self._servers.values():
            return name

        # 模糊匹配显示名
        matches = [
            sid for dname, sid in self._servers.items()
            if name.lower() in dname.lower()
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise AmbiguousServerError(name, matches)
        raise UnknownServerError(name)
