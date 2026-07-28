"""GroupScene / GroupSceneBuilder 更多边界测试。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bot.src.core.models import NormalizedMessage, ScopeType
from bot.src.plugins.persona.scene import GroupScene, GroupSceneBuilder


def _message(
    message_id: str,
    sender_id: str,
    text: str,
    *,
    seconds_ago: int = 0,
    scope_type: ScopeType = ScopeType.GROUP,
) -> NormalizedMessage:
    return NormalizedMessage(
        message_id=message_id,
        sender_id=sender_id,
        sender_alias="",
        scope_type=scope_type,
        scope_id="20001",
        text=text,
        message_type="text",
        reply_to=None,
        is_at_bot=False,
        created_at=datetime.now(UTC) - timedelta(seconds=seconds_ago),
    )


def make_builder() -> GroupSceneBuilder:
    return GroupSceneBuilder(
        context_max_messages=60,
        target_max_messages=15,
        target_max_age_seconds=180,
        target_gap_seconds=90,
    )


def test_find_existing_message() -> None:
    scene = make_builder().build([
        _message("m1", "1", "第一条"),
        _message("m2", "2", "第二条"),
    ])
    found = scene.find("m1")
    assert found is not None
    assert found.text == "第一条"


def test_find_missing_message() -> None:
    scene = make_builder().build([_message("m1", "1", "test")])
    assert scene.find("nonexistent") is None


def test_empty_messages_list() -> None:
    scene = make_builder().build([])
    assert len(scene.messages) == 0
    assert len(scene.eligible_target_ids) == 0


def test_excludes_bot_messages_from_targets() -> None:
    scene = make_builder().build([
        _message("bot1", "bot", "bot reply"),
        _message("m1", "1", "human"),
    ])
    assert "bot1" not in scene.eligible_target_ids
    assert "m1" in scene.eligible_target_ids


def test_excludes_command_messages_from_targets() -> None:
    scene = make_builder().build([
        _message("m1", "1", "/服 状态"),
        _message("m2", "2", "正常聊天"),
    ])
    assert "m1" not in scene.eligible_target_ids
    assert "m2" in scene.eligible_target_ids


def test_excludes_media_only_messages() -> None:
    media_msg = NormalizedMessage(
        message_id="img1",
        sender_id="1",
        sender_alias="",
        scope_type=ScopeType.GROUP,
        scope_id="20001",
        text="[图片，内容未知]",
        message_type="image",
        reply_to=None,
        is_at_bot=False,
        created_at=datetime.now(UTC),
    )
    text_msg = _message("m1", "2", "hi")
    scene = make_builder().build([media_msg, text_msg])
    assert "img1" not in scene.eligible_target_ids
    assert "m1" in scene.eligible_target_ids


def test_build_respects_gap_limit() -> None:
    builder = GroupSceneBuilder(
        context_max_messages=30,
        target_max_messages=15,
        target_max_age_seconds=600,
        target_gap_seconds=30,
    )
    messages = [
        _message("m1", "1", "old", seconds_ago=100),
        _message("m2", "2", "new", seconds_ago=10),
    ]
    scene = builder.build(messages)
    assert "m1" not in scene.eligible_target_ids
    assert "m2" in scene.eligible_target_ids
