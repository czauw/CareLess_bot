"""NullLlmProvider 安全降级测试。"""

from __future__ import annotations

import json

import pytest

from bot.src.adapters.null_llm import NullLlmProvider


@pytest.mark.asyncio
async def test_null_llm_returns_fallback() -> None:
    llm = NullLlmProvider(bot_name="测试")
    result = await llm.chat(messages=[{"role": "user", "content": "你好"}])
    parsed = json.loads(result)
    assert "messages" in parsed
    assert isinstance(parsed["messages"], list)
    assert len(parsed["messages"]) == 1


@pytest.mark.asyncio
async def test_null_llm_output_is_valid_json() -> None:
    llm = NullLlmProvider()
    result = await llm.chat(messages=[])
    decoded = json.loads(result)
    assert isinstance(decoded, dict)
    assert "messages" in decoded


@pytest.mark.asyncio
async def test_null_llm_accepts_standard_params() -> None:
    llm = NullLlmProvider()
    result = await llm.chat(
        messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
        max_tokens=100,
        temperature=0.5,
        thinking_enabled=False,
    )
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_null_llm_fallback_replies_are_expected() -> None:
    llm = NullLlmProvider()
    replies: set[str] = set()
    for _ in range(30):
        result = await llm.chat(messages=[])
        parsed = json.loads(result)
        replies.add(parsed["messages"][0])
    assert len(replies) >= 1
    for reply in replies:
        assert "（" in reply
        assert "）" in reply
