"""dedup.py 幂等去重测试。"""

from __future__ import annotations

import pytest

from bot.src.adapters.memory_store import MemoryStore
from bot.src.plugins.event_ingest.dedup import is_duplicate


@pytest.mark.asyncio
async def test_first_message_not_duplicate() -> None:
    store = MemoryStore()
    assert await is_duplicate(store, "msg-1") is False


@pytest.mark.asyncio
async def test_second_message_is_duplicate() -> None:
    store = MemoryStore()
    await is_duplicate(store, "msg-1")
    assert await is_duplicate(store, "msg-1") is True


@pytest.mark.asyncio
async def test_different_messages_not_duplicate() -> None:
    store = MemoryStore()
    assert await is_duplicate(store, "msg-1") is False
    assert await is_duplicate(store, "msg-2") is False
