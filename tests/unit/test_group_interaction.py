from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from bot.src.core.models import NormalizedMessage, ScopeType
from bot.src.plugins.event_ingest.normalize import normalize_group_message
from bot.src.plugins.persona.interaction import GroupInteractionCoordinator, GroupRoute
from bot.src.plugins.persona.responder import Responder
from bot.src.plugins.persona.scene import GroupSceneBuilder


def message(
    message_id: str,
    sender_id: str,
    text: str,
    *,
    seconds_ago: int = 0,
    is_at_bot: bool = False,
    reply_to: str | None = None,
) -> NormalizedMessage:
    return NormalizedMessage(
        message_id=message_id,
        sender_id=sender_id,
        sender_alias="",
        scope_type=ScopeType.GROUP,
        scope_id="20001",
        text=text,
        message_type="text",
        reply_to=reply_to,
        is_at_bot=is_at_bot,
        created_at=datetime.now(UTC) - timedelta(seconds=seconds_ago),
    )


def coordinator(clock: list[float]) -> GroupInteractionCoordinator:
    return GroupInteractionCoordinator(
        soft_trigger_enabled=True,
        trigger_probability=1.0,
        ai_check_cooldown_seconds=30,
        ambient_reply_cooldown_seconds=120,
        bucket_capacity=2,
        bucket_refill_seconds=1200,
        same_user_cooldown_seconds=300,
        session_ttl_seconds=120,
        session_question_ttl_seconds=180,
        session_max_bot_turns=4,
        session_max_ai_checks=8,
        max_new_messages_during_generation=5,
        quiet_start="00:00",
        quiet_end="00:00",
        timezone="UTC",
        random_provider=lambda: 0.0,
        now_provider=lambda: clock[0],
    )


def scene_builder() -> GroupSceneBuilder:
    return GroupSceneBuilder(
        context_max_messages=60,
        target_max_messages=15,
        target_max_age_seconds=180,
        target_gap_seconds=90,
    )


def test_normalizer_extracts_structured_at_and_reply_segments() -> None:
    normalized = normalize_group_message(
        {
            "message_id": 123,
            "user_id": 100,
            "group_id": 20001,
            "sender": {"card": "tester"},
            "message_type": "group",
            "raw_message": "ignored",
            "message_segments": [
                {"type": "reply", "data": {"id": "88"}},
                {"type": "at", "data": {"qq": "999"}},
                {"type": "text", "data": {"text": " 在吗"}},
                {"type": "image", "data": {"file": "secret.jpg"}},
            ],
        },
        bot_qq_id="999",
    )

    assert normalized.reply_to == "88"
    assert normalized.is_at_bot
    assert normalized.at_user_ids == frozenset({"999"})
    assert normalized.text == "@999 在吗[图片，内容未知]"
    assert normalized.message_type == "mixed"


def test_normalizer_keeps_nonebot_to_me_after_adapter_removes_at_segment() -> None:
    normalized = normalize_group_message(
        {
            "message_id": 124,
            "user_id": 100,
            "group_id": 20001,
            "sender": {"card": "tester"},
            "message_type": "group",
            "raw_message": "[CQ:at,qq=999] 说句话",
            # NoneBot 的 _check_at_me 已经从 event.message 中移除了 at 段。
            "message_segments": [{"type": "text", "data": {"text": "说句话"}}],
        },
        bot_qq_id="999",
        is_to_me=True,
    )

    assert normalized.is_at_bot
    assert normalized.text == "说句话"


def test_scene_builder_applies_age_gap_and_target_rules() -> None:
    builder = scene_builder()
    scene = builder.build(
        [
            message("old", "1", "旧话题", seconds_ago=170),
            message("m1", "1", "今晚玩吗", seconds_ago=30),
            message("bot1", "bot", "可以", seconds_ago=20),
            message("m2", "2", "/服 状态", seconds_ago=10),
            message("m3", "3", "我都行"),
        ]
    )

    assert [item.message_id for item in scene.messages] == ["old", "m1", "bot1", "m2", "m3"]
    assert scene.eligible_target_ids == frozenset({"m1", "m3"})


def test_scene_carries_sixty_messages_but_only_targets_recent_fifteen() -> None:
    messages = [
        message(f"m{index}", str(index), f"message {index}")
        for index in range(70)
    ]

    scene = scene_builder().build(messages)

    assert len(scene.messages) == 60
    assert [item.message_id for item in scene.messages[:2]] == ["m10", "m11"]
    assert len(scene.eligible_target_ids) == 15
    assert scene.eligible_target_ids == frozenset(f"m{index}" for index in range(55, 70))


def test_ambient_reply_opens_group_wide_session_window() -> None:
    clock = [1000.0]
    service = coordinator(clock)
    first = service.route(message("m1", "1", "今晚玩吗"), reply_to_bot=False)
    assert first.route == GroupRoute.AMBIENT
    lease = service.begin_request(first, "20001")
    assert lease is not None
    service.record_reply(
        lease,
        target_user_id="1",
        bot_message_id="bot-1",
        keep_session=False,
        expecting_answer=False,
    )
    service.finish_request(lease)

    # 会话不绑定第一个目标用户，其他群友也会交给 AI 自行判断。
    followup = service.route(message("m2", "2", "我也来"), reply_to_bot=False)
    assert followup.route == GroupRoute.SESSION
    assert not service.user_available_for_ambient("20001", "1")


def test_no_reply_consumes_only_ai_check_cooldown() -> None:
    clock = [1000.0]
    service = coordinator(clock)
    first = service.route(message("m1", "1", "第一条"), reply_to_bot=False)
    lease = service.begin_request(first, "20001")
    assert lease is not None
    service.record_no_reply(lease, keep_session=False)
    service.finish_request(lease)

    clock[0] += 10
    blocked = service.route(message("m2", "2", "第二条"), reply_to_bot=False)
    assert blocked.reason == "AI 检查冷却中"
    clock[0] += 21
    assert service.route(message("m3", "3", "第三条"), reply_to_bot=False).route == GroupRoute.AMBIENT


def test_explicit_message_is_not_replaced_by_ordinary_session_message() -> None:
    clock = [1000.0]
    service = coordinator(clock)
    direct = service.route(message("m1", "1", "在吗", is_at_bot=True), reply_to_bot=False)
    assert direct.route == GroupRoute.DIRECT

    ordinary = service.route(message("m2", "2", "你们继续聊"), reply_to_bot=False)
    assert ordinary.route == GroupRoute.NONE
    assert ordinary.reason == "等待处理明确搭话"
    assert service.begin_request(direct, "20001") is not None


def test_explicit_no_reply_still_keeps_forced_session_window() -> None:
    clock = [1000.0]
    service = GroupInteractionCoordinator(
        soft_trigger_enabled=False,
        trigger_probability=0.0,
        ai_check_cooldown_seconds=30,
        ambient_reply_cooldown_seconds=120,
        bucket_capacity=0,
        bucket_refill_seconds=1200,
        same_user_cooldown_seconds=300,
        session_ttl_seconds=120,
        session_question_ttl_seconds=180,
        session_max_bot_turns=4,
        session_max_ai_checks=8,
        max_new_messages_during_generation=5,
        quiet_start="00:00",
        quiet_end="00:00",
        timezone="UTC",
        random_provider=lambda: 1.0,
        now_provider=lambda: clock[0],
    )

    direct = service.route(message("m1", "1", "说句话", is_at_bot=True), reply_to_bot=False)
    assert direct.route == GroupRoute.DIRECT
    lease = service.begin_request(direct, "20001")
    assert lease is not None
    service.record_no_reply(lease, keep_session=False)
    service.finish_request(lease)

    followup = service.route(message("m2", "2", "怎么不说话"), reply_to_bot=False)
    assert followup.route == GroupRoute.SESSION


def test_explicit_message_bypasses_cooldown_and_does_not_consume_bucket() -> None:
    clock = [1000.0]
    service = coordinator(clock)
    ambient = service.route(message("m1", "1", "第一条"), reply_to_bot=False)
    ambient_lease = service.begin_request(ambient, "20001")
    assert ambient_lease is not None
    service.record_reply(
        ambient_lease,
        target_user_id="1",
        bot_message_id="bot-1",
        keep_session=False,
        expecting_answer=False,
    )
    service.finish_request(ambient_lease)

    clock[0] += 1
    direct = service.route(message("m2", "2", "@你", is_at_bot=True), reply_to_bot=False)
    assert direct.route == GroupRoute.DIRECT
    direct_lease = service.begin_request(direct, "20001")
    assert direct_lease is not None
    service.record_reply(
        direct_lease,
        target_user_id="2",
        bot_message_id="bot-2",
        keep_session=False,
        expecting_answer=False,
    )
    service.finish_request(direct_lease)

    # direct 窗口过期后仍剩一个随机令牌，证明明确互动没有消耗额度。
    clock[0] += 121
    assert service.route(message("m3", "3", "第三条"), reply_to_bot=False).route == GroupRoute.AMBIENT


def test_group_decision_uses_stable_prefix_and_validates_target() -> None:
    class CapturingLlm:
        def __init__(self) -> None:
            self.messages: list[dict[str, str]] = []

        async def chat(self, **kwargs: object) -> str:
            self.messages = kwargs["messages"]  # type: ignore[assignment,index]
            return (
                '{"action":"reply","target_message_id":"m1",'
                '"messages":["缺人的话算我一个"],"keep_session":true,'
                '"expecting_answer":false}'
            )

    llm = CapturingLlm()
    responder = Responder(llm)
    scene = scene_builder().build(
        [message("m1", "1", "今晚有人打游戏吗"), message("m2", "2", "我都行")]
    )
    result = asyncio.run(responder.generate_group_decision("ambient", scene))

    assert result.target_message_id == "m1"
    assert result.messages == ["缺人的话算我一个"]
    assert result.keep_session
    assert llm.messages[0]["content"] == responder.GROUP_SYSTEM_PROMPT
    assert llm.messages[0]["content"] != responder.PRIVATE_SYSTEM_PROMPT
    assert "<group_scene>" in llm.messages[-1]["content"]
    assert "<private_conversation>" not in llm.messages[-1]["content"]
    assert "可选目标" not in llm.messages[-1]["content"]
    assert "<eligible_target_ids>\nm1\nm2\n</eligible_target_ids>" in llm.messages[-1]["content"]
    assert llm.messages[-1]["content"].endswith("。")


def test_direct_decision_requires_reply_and_session_window() -> None:
    class CapturingLlm:
        def __init__(self) -> None:
            self.messages: list[dict[str, str]] = []

        async def chat(self, **kwargs: object) -> str:
            self.messages = kwargs["messages"]  # type: ignore[assignment,index]
            return (
                '{"action":"reply","target_message_id":"m1",'
                '"messages":["我在"],"keep_session":true,'
                '"expecting_answer":false}'
            )

    llm = CapturingLlm()
    scene = scene_builder().build([message("m1", "1", "说句话", is_at_bot=True)])
    result = asyncio.run(Responder(llm).generate_group_decision("direct", scene))

    assert result.action == "reply"
    assert result.keep_session
    assert "必须自然回应" in llm.messages[1]["content"]
    assert "keep_session 必须为 true" in llm.messages[1]["content"]


def test_group_decision_rejects_model_invented_message_id() -> None:
    class InvalidTargetLlm:
        async def chat(self, **_: object) -> str:
            return (
                '{"action":"reply","target_message_id":"invented",'
                '"messages":["不该发送"],"keep_session":true,'
                '"expecting_answer":false}'
            )

    scene = scene_builder().build(
        [message("m1", "1", "今晚有人打游戏吗"), message("m2", "2", "我都行")]
    )
    result = asyncio.run(Responder(InvalidTargetLlm()).generate_group_decision("ambient", scene))

    assert result.action == "no_reply"
    assert result.messages == []


def test_session_llm_failure_keeps_window_without_retrying() -> None:
    class FailingLlm:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, **_: object) -> str:
            self.calls += 1
            raise TimeoutError("upstream timeout")

    llm = FailingLlm()
    scene = scene_builder().build([message("m1", "1", "继续聊")])

    session = asyncio.run(Responder(llm).generate_group_decision("session", scene))
    ambient = asyncio.run(Responder(llm).generate_group_decision("ambient", scene))

    assert session.action == "no_reply"
    assert session.keep_session
    assert not ambient.keep_session
    assert llm.calls == 2


def test_group_alias_stays_stable_when_context_window_slides() -> None:
    responder = Responder(type("UnusedLlm", (), {})())
    first_scene = scene_builder().build(
        [message("old", "1", "old"), message("same", "2", "same")]
    )
    second_scene = scene_builder().build(
        [message("same", "2", "same"), message("new", "3", "new")]
    )

    first_prompt = responder._build_group_scene_prompt(first_scene)
    second_prompt = responder._build_group_scene_prompt(second_scene)
    first_same_line = next(line for line in first_prompt.splitlines() if line.startswith("[same |"))
    second_same_line = next(
        line for line in second_prompt.splitlines() if line.startswith("[same |")
    )

    assert first_same_line == second_same_line
