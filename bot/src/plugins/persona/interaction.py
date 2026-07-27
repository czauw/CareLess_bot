"""按群维护随机搭话额度、场景版本和 AI 驱动的短会话窗口。"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable
from zoneinfo import ZoneInfo

from bot.src.core.models import NormalizedMessage


class GroupRoute(str, Enum):
    NONE = "none"
    AMBIENT = "ambient"
    DIRECT = "direct"
    SESSION = "session"


@dataclass(frozen=True)
class RouteDecision:
    route: GroupRoute
    scene_version: int
    reason: str


@dataclass(frozen=True)
class RequestLease:
    route: GroupRoute
    group_id: str
    scene_version: int


@dataclass
class ConversationWindow:
    expires_at: float
    bot_turns: int = 0
    ai_checks: int = 0
    expecting_answer: bool = False
    last_bot_message_id: str | None = None


@dataclass
class GroupInteractionState:
    scene_version: int = 0
    last_direct_version: int = 0
    last_ai_check_at: float = float("-inf")
    last_ambient_reply_at: float = float("-inf")
    ambient_pending: bool = False
    direct_pending: bool = False
    request_in_flight: bool = False
    bucket_tokens: float = 0.0
    bucket_updated_at: float = field(default_factory=time.monotonic)
    per_user_last_ambient_reply: dict[str, float] = field(default_factory=dict)
    window: ConversationWindow | None = None


class GroupInteractionCoordinator:
    """本地处理概率、额度和时间；语义选择交给一次 LLM 调用。"""

    def __init__(
        self,
        *,
        soft_trigger_enabled: bool,
        trigger_probability: float,
        ai_check_cooldown_seconds: float,
        ambient_reply_cooldown_seconds: float,
        bucket_capacity: int,
        bucket_refill_seconds: float,
        same_user_cooldown_seconds: float,
        session_ttl_seconds: float,
        session_question_ttl_seconds: float,
        session_max_bot_turns: int,
        session_max_ai_checks: int,
        max_new_messages_during_generation: int,
        quiet_start: str,
        quiet_end: str,
        timezone: str,
        random_provider: Callable[[], float] | None = None,
        now_provider: Callable[[], float] | None = None,
    ) -> None:
        self._soft_enabled = soft_trigger_enabled
        self._probability = trigger_probability
        self._ai_check_cooldown = ai_check_cooldown_seconds
        self._reply_cooldown = ambient_reply_cooldown_seconds
        self._bucket_capacity = bucket_capacity
        self._bucket_refill = bucket_refill_seconds
        self._same_user_cooldown = same_user_cooldown_seconds
        self._session_ttl = session_ttl_seconds
        self._question_ttl = session_question_ttl_seconds
        self._session_max_turns = session_max_bot_turns
        self._session_max_checks = session_max_ai_checks
        self._max_new_messages = max_new_messages_during_generation
        self._quiet_start = quiet_start
        self._quiet_end = quiet_end
        self._timezone = ZoneInfo(timezone)
        self._random = random_provider or random.random
        self._now = now_provider or time.monotonic
        self._states: dict[str, GroupInteractionState] = {}

    def route(self, message: NormalizedMessage, *, reply_to_bot: bool) -> RouteDecision:
        state = self._state(message.scope_id)
        state.scene_version += 1
        version = state.scene_version
        now = self._now()
        direct = message.is_at_bot or reply_to_bot

        if direct:
            state.last_direct_version = version
            state.ambient_pending = False
            state.direct_pending = True
            self._open_or_refresh_window(state, now)
            return RouteDecision(GroupRoute.DIRECT, version, "明确艾特或引用机器人")

        window = self._active_window(state, now)
        if window is not None:
            if state.direct_pending:
                return RouteDecision(GroupRoute.NONE, version, "等待处理明确搭话")
            if window.bot_turns >= self._session_max_turns:
                state.window = None
            elif window.ai_checks >= self._session_max_checks:
                state.window = None
            else:
                return RouteDecision(GroupRoute.SESSION, version, "群级短会话窗口")

        if not self._soft_enabled:
            return RouteDecision(GroupRoute.NONE, version, "随机搭话已关闭")
        if self._is_quiet_hours():
            return RouteDecision(GroupRoute.NONE, version, "夜间静默")
        self._refill_bucket(state, now)
        if state.ambient_pending or state.request_in_flight:
            return RouteDecision(GroupRoute.NONE, version, "已有群聊判断任务")
        if now - state.last_ai_check_at < self._ai_check_cooldown:
            return RouteDecision(GroupRoute.NONE, version, "AI 检查冷却中")
        if now - state.last_ambient_reply_at < self._reply_cooldown:
            return RouteDecision(GroupRoute.NONE, version, "随机发言冷却中")
        if state.bucket_tokens < 1:
            return RouteDecision(GroupRoute.NONE, version, "随机发言额度不足")
        if self._random() >= self._probability:
            return RouteDecision(GroupRoute.NONE, version, "概率未命中")
        state.ambient_pending = True
        return RouteDecision(GroupRoute.AMBIENT, version, "随机检查命中")

    def begin_request(self, decision: RouteDecision, group_id: str) -> RequestLease | None:
        state = self._state(group_id)
        if state.request_in_flight:
            return None
        if decision.route == GroupRoute.AMBIENT:
            if not state.ambient_pending:
                return None
            state.ambient_pending = False
            state.last_ai_check_at = self._now()
        elif decision.route in {GroupRoute.DIRECT, GroupRoute.SESSION}:
            window = self._active_window(state, self._now())
            if window is None:
                return None
            if decision.route == GroupRoute.DIRECT:
                if not state.direct_pending:
                    return None
                state.direct_pending = False
            window.ai_checks += 1
        else:
            return None
        state.request_in_flight = True
        return RequestLease(decision.route, group_id, state.scene_version)

    def finish_request(self, lease: RequestLease) -> None:
        self._state(lease.group_id).request_in_flight = False

    def may_send(self, lease: RequestLease) -> bool:
        state = self._state(lease.group_id)
        if lease.route != GroupRoute.AMBIENT:
            return self._active_window(state, self._now()) is not None
        if state.last_direct_version > lease.scene_version:
            return False
        return state.scene_version - lease.scene_version <= self._max_new_messages

    def user_available_for_ambient(self, group_id: str, user_id: str) -> bool:
        last = self._state(group_id).per_user_last_ambient_reply.get(user_id, float("-inf"))
        return self._now() - last >= self._same_user_cooldown

    def record_no_reply(self, lease: RequestLease, *, keep_session: bool) -> None:
        if lease.route == GroupRoute.AMBIENT:
            return
        # 明确 @/引用已经强制开启窗口；本次模型沉默不能立刻关闭它。
        if lease.route == GroupRoute.DIRECT:
            return
        state = self._state(lease.group_id)
        if not keep_session:
            state.window = None

    def record_reply(
        self,
        lease: RequestLease,
        *,
        target_user_id: str,
        bot_message_id: str | None,
        keep_session: bool,
        expecting_answer: bool,
    ) -> None:
        state = self._state(lease.group_id)
        now = self._now()
        if lease.route == GroupRoute.AMBIENT:
            self._refill_bucket(state, now)
            state.bucket_tokens = max(0.0, state.bucket_tokens - 1)
            state.last_ambient_reply_at = now
            state.per_user_last_ambient_reply[target_user_id] = now
            # 主动插话成功后固定开放一个短窗口；是否继续延长仍由后续 AI 决定。
            state.window = ConversationWindow(
                expires_at=now + (self._question_ttl if expecting_answer else self._session_ttl),
                bot_turns=1,
                expecting_answer=expecting_answer,
                last_bot_message_id=bot_message_id,
            )
            return

        window = self._active_window(state, now)
        if window is None:
            return
        window.bot_turns += 1
        window.expecting_answer = expecting_answer
        window.last_bot_message_id = bot_message_id
        if lease.route == GroupRoute.DIRECT:
            window.expires_at = now + (
                self._question_ttl if expecting_answer else self._session_ttl
            )
            return
        if not keep_session or window.bot_turns >= self._session_max_turns:
            state.window = None
        else:
            window.expires_at = now + (
                self._question_ttl if expecting_answer else self._session_ttl
            )

    def _state(self, group_id: str) -> GroupInteractionState:
        state = self._states.get(group_id)
        if state is None:
            now = self._now()
            state = GroupInteractionState(
                bucket_tokens=float(self._bucket_capacity),
                bucket_updated_at=now,
            )
            self._states[group_id] = state
        return state

    def _open_or_refresh_window(self, state: GroupInteractionState, now: float) -> None:
        window = self._active_window(state, now)
        if window is None:
            state.window = ConversationWindow(expires_at=now + self._session_ttl)
        else:
            window.expires_at = now + self._session_ttl

    def _active_window(
        self, state: GroupInteractionState, now: float
    ) -> ConversationWindow | None:
        if state.window is not None and now >= state.window.expires_at:
            state.window = None
        return state.window

    def _refill_bucket(self, state: GroupInteractionState, now: float) -> None:
        if self._bucket_capacity <= 0:
            state.bucket_tokens = 0
            return
        if self._bucket_refill <= 0:
            state.bucket_tokens = float(self._bucket_capacity)
        else:
            elapsed = max(0.0, now - state.bucket_updated_at)
            state.bucket_tokens = min(
                float(self._bucket_capacity),
                state.bucket_tokens + elapsed / self._bucket_refill,
            )
        state.bucket_updated_at = now

    def _is_quiet_hours(self) -> bool:
        now = datetime.now(self._timezone).time()
        start = datetime.strptime(self._quiet_start, "%H:%M").time()
        end = datetime.strptime(self._quiet_end, "%H:%M").time()
        if start == end:
            return False
        if start < end:
            return start <= now < end
        return now >= start or now < end
