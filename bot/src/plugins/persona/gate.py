"""触发门控 —— 硬/软触发判定 + 总闸门。

决策树：
收到消息
  ├─ 机器人自身消息 → 丢弃
  ├─ 管理命令 → 管理命令流程
  ├─ 群未启用/全局维护 → 仅消费
  ├─ 夜间且非硬触发 → 仅消费
  ├─ 命中禁止触发 → 仅消费并记录原因
  ├─ 硬触发（@、回复） → 检查限流后进入回复
  └─ 软触发 → 候选评分 → 概率抽样 → 检查额度 → 回复或沉默
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from bot.src.core.models import NormalizedMessage, TriggerType


@dataclass
class GateResult:
    """门控判定结果。"""

    trigger_type: TriggerType
    should_reply: bool
    reason: str = ""


class PersonaGate:
    """群聊人格触发门控。"""

    def __init__(
        self,
        *,
        active_probability: float = 0.02,
        group_cooldown_seconds: int = 600,
        user_cooldown_seconds: int = 1200,
        max_active_replies_per_hour: int = 3,
        quiet_start: str = "00:30",
        quiet_end: str = "07:30",
        bot_qq_id: str = "",
        timezone: str = "Asia/Shanghai",
    ) -> None:
        self._active_prob = active_probability
        self._group_cooldown = group_cooldown_seconds
        self._user_cooldown = user_cooldown_seconds
        self._max_per_hour = max_active_replies_per_hour
        self._quiet_start = quiet_start
        self._quiet_end = quiet_end
        self._bot_qq_id = bot_qq_id
        self._timezone = ZoneInfo(timezone)

        # 冷却追踪
        self._group_last_reply: dict[str, float] = {}
        self._user_last_reply: dict[str, float] = {}
        # 每小时计数
        self._hourly_count: dict[str, list[float]] = {}

    def is_hard_trigger(self, msg: NormalizedMessage) -> bool:
        """是否为硬触发：@机器人、回复机器人、以昵称开头。"""
        if msg.is_at_bot:
            return True
        # 私聊始终为硬触发
        if msg.scope_type.value == "private":
            return True
        return False

    def is_quiet_hours(self) -> bool:
        """当前是否在夜间静默时段。"""
        now = datetime.now(self._timezone)
        hour = now.hour  # UTC; 实际使用时需根据时区转换（MVP 先简化）
        start_h, _ = map(int, self._quiet_start.split(":"))
        end_h, _ = map(int, self._quiet_end.split(":"))
        if start_h < end_h:
            return start_h <= hour < end_h
        return hour >= start_h or hour < end_h

    def evaluate(self, msg: NormalizedMessage) -> GateResult:
        """评估消息是否应触发回复。"""
        now = time.monotonic()

        # 硬触发也必须受群和用户冷却限制。
        if self.is_hard_trigger(msg):
            if not self._within_cooldown(msg, now):
                return GateResult(TriggerType.NONE, should_reply=False, reason="回复冷却中")
            return GateResult(TriggerType.HARD, should_reply=True, reason="硬触发")

        # 夜间只响应硬触发
        if self.is_quiet_hours():
            return GateResult(TriggerType.NONE, should_reply=False, reason="夜间静默")

        # 群级冷却
        if not self._within_cooldown(msg, now):
            return GateResult(TriggerType.NONE, should_reply=False, reason="回复冷却中")

        # 每小时额度
        if not self._check_hourly_quota(msg.scope_id):
            return GateResult(TriggerType.NONE, should_reply=False, reason="每小时额度耗尽")

        # 概率抽样
        if random.random() < self._active_prob:
            return GateResult(TriggerType.SOFT, should_reply=True, reason="软触发抽中")
        return GateResult(TriggerType.NONE, should_reply=False, reason="未抽中")

    # ----------------------------------------------------------
    # 内部
    # ----------------------------------------------------------

    def record_reply(self, msg: NormalizedMessage) -> None:
        """仅在成功发送后记录回复，避免 LLM 失败占用冷却。"""
        self._record_reply(msg.scope_id, msg.sender_id)

    def _within_cooldown(self, msg: NormalizedMessage, now: float) -> bool:
        group_last = self._group_last_reply.get(msg.scope_id, float("-inf"))
        user_last = self._user_last_reply.get(msg.sender_id, float("-inf"))
        return (
            now - group_last >= self._group_cooldown
            and now - user_last >= self._user_cooldown
        )

    def _record_reply(self, scope_id: str, sender_id: str) -> None:
        """记录回复事件（冷却、计数）。"""
        now = time.monotonic()
        self._group_last_reply[scope_id] = now
        self._user_last_reply[sender_id] = now
        self._hourly_count.setdefault(scope_id, []).append(now)

    def _check_hourly_quota(self, scope_id: str) -> bool:
        """检查每小时主动回复额度。"""
        now = time.monotonic()
        cutoff = now - 3600
        timestamps = self._hourly_count.get(scope_id, [])
        recent = [t for t in timestamps if t > cutoff]
        self._hourly_count[scope_id] = recent
        return len(recent) < self._max_per_hour
