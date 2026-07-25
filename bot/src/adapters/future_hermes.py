"""Hermes Agent 预留适配器（当前禁用）。

任何调用都返回"功能未启用"，绝不执行 fallback Shell。
未来接入时替换为真实 HermesClient 实现。
"""

from __future__ import annotations


class DisabledHermesClient:
    """Hermes 未部署时的安全禁用实现。"""

    DISABLED_MSG = "Hermes Agent 尚未部署，功能不可用。"

    async def create_session(self, actor_qq_id: str, scope_id: str) -> str:
        raise RuntimeError(self.DISABLED_MSG)

    async def send_message(self, session_id: str, text: str) -> dict:
        raise RuntimeError(self.DISABLED_MSG)

    async def approve(self, session_id: str, approval_id: str) -> dict:
        raise RuntimeError(self.DISABLED_MSG)

    async def cancel(self, session_id: str, approval_id: str) -> None:
        raise RuntimeError(self.DISABLED_MSG)
