"""message_id 幂等去重。

同一 message_id 在处理后立即标记，防止：
- NapCat 重连后重发
- 多插件重复消费
- 重复回复
"""

from __future__ import annotations

from bot.src.core.ports import Store


async def is_duplicate(store: Store, message_id: str) -> bool:
    """检查 message_id 是否已处理；首次调用返回 False 并自动标记。"""
    return not await store.claim_message(message_id)
