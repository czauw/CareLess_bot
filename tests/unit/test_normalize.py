"""normalize.py 更多规范化边界测试。"""

from __future__ import annotations

from bot.src.plugins.event_ingest.normalize import (
    _display_text,
    _message_type,
    normalize_group_message,
    normalize_private_message,
)


def test_normalize_private_message_basic() -> None:
    event = {
        "message_id": 1,
        "user_id": 10001,
        "sender": {"nickname": "tester"},
        "raw_message": "你好",
        "message_type": "private",
        "message_segments": [{"type": "text", "data": {"text": "你好"}}],
    }
    msg = normalize_private_message(event)
    assert msg.scope_type.value == "private"
    assert msg.scope_id == "10001"
    assert msg.text == "你好"
    assert msg.is_at_bot is True
    assert msg.sender_alias == "tester"


def test_normalize_private_message_reply() -> None:
    event = {
        "message_id": 2,
        "user_id": 10001,
        "sender": {"nickname": "tester"},
        "raw_message": "回复",
        "message_type": "private",
        "message_segments": [
            {"type": "reply", "data": {"id": "99"}},
            {"type": "text", "data": {"text": "知道了"}},
        ],
    }
    msg = normalize_private_message(event)
    assert msg.reply_to == "99"


def test_normalize_private_message_no_nickname() -> None:
    event = {
        "message_id": 3,
        "user_id": 10001,
        "sender": {},
        "raw_message": "test",
        "message_type": "private",
        "message_segments": [],
    }
    msg = normalize_private_message(event)
    assert msg.sender_alias == ""


def test_display_text_all_media_types() -> None:
    segments = [
        {"type": "image", "data": {"file": "pic.jpg"}},
        {"type": "face", "data": {"id": "1"}},
        {"type": "record", "data": {"file": "audio.amr"}},
        {"type": "video", "data": {"file": "vid.mp4"}},
        {"type": "file", "data": {"file": "doc.pdf"}},
        {"type": "json", "data": {"data": "{}"}},
        {"type": "xml", "data": {"data": "<x/>"}},
        {"type": "markdown", "data": {"data": "# hi"}},
    ]
    result = _display_text(segments, "fallback")
    assert "[图片，内容未知]" in result
    assert "[表情]" in result
    assert "[语音，内容未知]" in result
    assert "[视频，内容未知]" in result
    assert "[文件，内容未知]" in result
    assert "[卡片消息]" in result
    assert "[Markdown消息]" in result


def test_display_text_fallback() -> None:
    result = _display_text([], "原始文本")
    assert result == "原始文本"


def test_display_text_unknown_segment_type() -> None:
    segments = [{"type": "custom_type", "data": {}}]
    result = _display_text(segments, "fallback")
    assert "[custom_type消息]" in result


def test_message_type_single() -> None:
    segments = [{"type": "text", "data": {"text": "hello"}}]
    assert _message_type(segments, "text") == "text"


def test_message_type_mixed() -> None:
    segments = [
        {"type": "text", "data": {"text": "hello"}},
        {"type": "image", "data": {"file": "pic.jpg"}},
    ]
    assert _message_type(segments, "text") == "mixed"


def test_message_type_excludes_reply_and_at() -> None:
    segments = [
        {"type": "reply", "data": {"id": "1"}},
        {"type": "at", "data": {"qq": "999"}},
        {"type": "text", "data": {"text": "hi"}},
    ]
    assert _message_type(segments, "text") == "text"


def test_normalize_group_message_without_segments() -> None:
    event = {
        "message_id": 1,
        "user_id": 100,
        "group_id": 20001,
        "sender": {"card": "tester"},
        "raw_message": "纯文本消息",
        "message_type": "group",
        "message_segments": None,
    }
    msg = normalize_group_message(event)
    assert msg.text == "纯文本消息"
    assert msg.message_type == "group"


def test_normalize_group_message_is_at_bot_via_is_to_me() -> None:
    event = {
        "message_id": 1,
        "user_id": 100,
        "group_id": 20001,
        "sender": {"card": "tester"},
        "raw_message": "hi",
        "message_type": "group",
        "message_segments": [{"type": "text", "data": {"text": "hi"}}],
    }
    msg = normalize_group_message(event, bot_qq_id="999", is_to_me=True)
    assert msg.is_at_bot is True
