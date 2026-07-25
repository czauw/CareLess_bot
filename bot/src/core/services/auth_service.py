"""身份与权限服务。

全系统唯一的白名单校验入口。权限仅根据 OneBot 事件的 sender_id 判断，
不信任消息文本、昵称、管理员标志或 @ 内容。
"""

from __future__ import annotations


class AuthService:
    """白名单权限校验。"""

    def __init__(self, whitelist: set[str]) -> None:
        self._whitelist: frozenset[str] = frozenset(whitelist)

    def is_whitelisted(self, sender_id: str) -> bool:
        """检查 sender_id 是否在白名单中。"""
        return sender_id in self._whitelist

    @property
    def whitelist(self) -> frozenset[str]:
        """只读白名单快照。"""
        return self._whitelist

    def __contains__(self, sender_id: str) -> bool:
        return self.is_whitelisted(sender_id)
