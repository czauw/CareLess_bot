"""Null LLM Provider —— LLM 未配置时的安全空实现。

当 LLM 不可用时：
- 硬触发返回固定的降级文本
- 软触发全部关闭
- 不记录模拟的 Prompt/Response
"""

from __future__ import annotations

import json
import random


class NullLlmProvider:
    """LLM 不可用时的安全降级。"""

    FALLBACK_REPLIES = [
        "（脑子暂时短路了…）",
        "（现在不太方便接话）",
        "（正在发呆中）",
    ]

    def __init__(self, *, bot_name: str = "机器人") -> None:
        self._bot_name = bot_name

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 200,
        temperature: float = 0.8,
        thinking_enabled: bool | None = None,
    ) -> str:
        """返回安全降级文本，不调用任何外部 API。"""
        return json.dumps({"messages": [random.choice(self.FALLBACK_REPLIES)]}, ensure_ascii=False)
