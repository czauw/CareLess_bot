"""Responder 写作风格规则验证与更多边界测试。"""

from __future__ import annotations

from datetime import UTC, datetime

from bot.src.core.models import NormalizedMessage, ScopeType
from bot.src.plugins.persona.responder import Responder, build_profile_prompt


def test_group_prompt_includes_writing_style() -> None:
    prompt = Responder.GROUP_SYSTEM_PROMPT
    assert "写作风格" in prompt
    assert "书面短句" in prompt
    assert "一句说完" in prompt
    assert "少用标点" in prompt


def test_private_prompt_includes_writing_style() -> None:
    prompt = Responder.PRIVATE_SYSTEM_PROMPT
    assert "写作风格" in prompt
    assert "书面短句" in prompt
    assert "一句说完" in prompt


def test_writing_style_forbids_colloquial_words() -> None:
    for prompt in (Responder.GROUP_SYSTEM_PROMPT, Responder.PRIVATE_SYSTEM_PROMPT):
        assert "语气词" in prompt
        assert "缩略词" in prompt


def test_writing_style_forbids_ai_mimicking_phrases() -> None:
    prompt = Responder.GROUP_SYSTEM_PROMPT
    assert "说白了" in prompt
    assert "就行" in prompt
    assert "就好" in prompt
    assert "超简单" in prompt
    assert "咱们" in prompt
    assert "谁懂啊" in prompt
    assert "再也不会" in prompt


def test_writing_style_forbids_emotional_expressions() -> None:
    prompt = Responder.GROUP_SYSTEM_PROMPT
    assert "千万不要" in prompt
    assert "绝了" in prompt


def test_writing_style_replaces_subjective_words() -> None:
    prompt = Responder.GROUP_SYSTEM_PROMPT
    assert "老实说" in prompt
    assert "我觉得" in prompt


def test_sanitize_removes_control_chars() -> None:
    result = Responder._sanitize_message("hello\x00world\x01")
    assert "\x00" not in result
    assert "\x01" not in result
    assert "hello" in result
    assert "world" in result


def test_sanitize_collapses_newlines() -> None:
    result = Responder._sanitize_message("第一行\n第二行\n第三行")
    assert "\n" not in result
    assert result == "第一行 第二行 第三行"


def test_sanitize_trims_whitespace() -> None:
    result = Responder._sanitize_message("  hello  ")
    assert result == "hello"


def test_group_system_prompt_includes_de_ai_rules() -> None:
    """确保群聊系统提示词包含完整的去 AI 味规则。"""
    prompt = Responder.GROUP_SYSTEM_PROMPT
    required_phrases = [
        "书面短句",
        "一句说完",
        "少用标点",
        "语气词",
        "缩略词",
        "说白了",
        "AI套话",
        "强烈表达",
        "整体感受",
        "主观开头",
    ]
    for phrase in required_phrases:
        assert phrase in prompt, f"缺少关键词: {phrase}"


def test_build_profile_prompt_disabled() -> None:
    assert build_profile_prompt({"enabled": False}) == ""
    assert build_profile_prompt({}) == ""
    assert build_profile_prompt("not a dict") == ""


def test_build_profile_prompt_with_all_fields() -> None:
    profile = {
        "enabled": True,
        "name": "阿洛",
        "identity": "老成员",
        "background": "喜欢折腾服务器",
        "traits": ["嘴硬", "热心", "不端着"],
        "speaking_style": "短句 口语化",
        "boundaries": ["不编造经历", "不评价隐私"],
    }
    result = build_profile_prompt(profile)
    assert "昵称：阿洛" in result
    assert "身份：老成员" in result
    assert "背景：喜欢折腾服务器" in result
    assert "性格：嘴硬、热心、不端着" in result
    assert "说话风格：短句 口语化" in result
    assert "额外边界：不编造经历、不评价隐私" in result


def test_build_profile_prompt_skips_empty_fields() -> None:
    profile = {
        "enabled": True,
        "name": "",
        "traits": [],
        "speaking_style": "   ",
    }
    result = build_profile_prompt(profile)
    assert "昵称" not in result
    assert "性格" not in result
    assert "说话风格" not in result


def test_no_reply_decision() -> None:
    from bot.src.plugins.persona.responder import NO_REPLY_DECISION
    assert NO_REPLY_DECISION.action == "no_reply"
    assert NO_REPLY_DECISION.messages == []
    assert NO_REPLY_DECISION.keep_session is False
