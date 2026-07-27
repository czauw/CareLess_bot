"""从按群时间线构造低成本、短时间范围的 AI 场景。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from bot.src.core.models import NormalizedMessage


@dataclass(frozen=True)
class GroupScene:
    messages: list[NormalizedMessage]
    eligible_target_ids: frozenset[str]

    def find(self, message_id: str) -> NormalizedMessage | None:
        return next((message for message in self.messages if message.message_id == message_id), None)


class GroupSceneBuilder:
    def __init__(
        self,
        *,
        context_max_messages: int,
        target_max_messages: int,
        target_max_age_seconds: int,
        target_gap_seconds: int,
    ) -> None:
        self._context_max_messages = context_max_messages
        self._target_max_messages = target_max_messages
        self._target_max_age = target_max_age_seconds
        self._target_gap = target_gap_seconds

    def build(self, messages: list[NormalizedMessage]) -> GroupScene:
        # 理解上下文和可回复目标分开：较早消息帮助理解，但不能被模型选中回复。
        selected = messages[-self._context_max_messages :]
        cutoff = datetime.now(UTC).timestamp() - self._target_max_age
        target_window: list[NormalizedMessage] = []
        newer: NormalizedMessage | None = None
        for message in reversed(selected):
            if message.created_at.timestamp() < cutoff:
                break
            if (
                newer is not None
                and (newer.created_at - message.created_at).total_seconds() > self._target_gap
            ):
                break
            target_window.append(message)
            newer = message
            if len(target_window) >= self._target_max_messages:
                break
        eligible = frozenset(
            message.message_id
            for message in target_window
            if message.sender_id != "bot"
            and message.message_id
            and not message.text.lstrip().startswith("/")
            and message.message_type not in {"image", "record", "video", "file"}
        )
        return GroupScene(selected, eligible)
