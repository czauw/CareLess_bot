"""OneBot 消息发送与敏感信息脱敏。

所有发送到 QQ 的文本必须经过 Redactor 处理。
"""

from __future__ import annotations

import re
from typing import Protocol


class SendAdapter(Protocol):
    """消息发送适配器——由 NoneBot Bot 实例实现。"""

    async def send_group_msg(
        self, group_id: str, message: str
    ) -> None: ...

    async def send_private_msg(
        self, user_id: str, message: str
    ) -> None: ...


class Redactor:
    """敏感信息脱敏——发送前和写日志前使用。

    替换：
    - Token / API key / 密码
    - 公网 IP 地址
    - 绝对路径
    - 环境变量值
    """

    PATTERNS: list[tuple[str, str]] = [
        # Bearer token / API key
        (r'(?:Bearer\s+)?[A-Za-z0-9_\-]{32,}', '[REDACTED_TOKEN]'),
        # 通用键值对凭据
        (r'(?:api_key|apikey|secret|password|passwd|token)\s*[:=]\s*\S+',
         '[REDACTED_CREDENTIAL]'),
        # IPv4 公网地址（保留 127.0.0.1 和私有地址）
        (r'\b(?!127\.|10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)'
         r'(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b',
         '[REDACTED_IP]'),
        # 绝对路径（Linux/Windows）
        (r'(?:/[^\s,，。；;]*){2,}', '[REDACTED_PATH]'),
        (r'[A-Za-z]:\\[^\s,，。；;]+', '[REDACTED_PATH]'),
        # 数据库 DSN
        (r'(?:mysql|postgres|postgresql|sqlite)://[^\s]+', '[REDACTED_DSN]'),
    ]

    @classmethod
    def redact(cls, text: str) -> str:
        """对文本执行脱敏替换。"""
        for pattern, replacement in cls.PATTERNS:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text


class OneBotSender:
    """消息发送封装——自动脱敏。"""

    def __init__(self, adapter: SendAdapter) -> None:
        self._adapter = adapter

    async def send_group(self, group_id: str, text: str) -> None:
        """向群聊发送脱敏后的消息。"""
        safe = Redactor.redact(text)
        await self._adapter.send_group_msg(group_id, safe)

    async def send_private(self, user_id: str, text: str) -> None:
        """向私聊发送脱敏后的消息。"""
        safe = Redactor.redact(text)
        await self._adapter.send_private_msg(user_id, safe)
