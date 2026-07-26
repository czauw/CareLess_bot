"""OpenAI 兼容 Chat Completions LLM 适配器。

仅供人格回复使用。连接错误、非成功响应和无效响应均交给调用方降级处理。
"""

from __future__ import annotations

from typing import Any

import httpx


class OpenAICompatibleLlmProvider:
    """最小化 OpenAI 兼容接口客户端，不参与命令或权限决策。"""

    def __init__(self, api_base: str, api_key: str, model: str, *, timeout_seconds: float = 15) -> None:
        self._endpoint = f"{api_base.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self._model = model
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 200,
        temperature: float = 0.8,
        thinking_enabled: bool | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if thinking_enabled is not None:
            payload["thinking"] = {"type": "enabled" if thinking_enabled else "disabled"}
        response = await self._client.post(
            self._endpoint,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=payload,
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        try:
            content = payload["choices"][0]["message"]["content"]
        except (IndexError, KeyError, TypeError) as error:
            raise ValueError("LLM 返回格式无效") from error
        if not isinstance(content, str):
            raise ValueError("LLM 返回内容不是文本")
        return content

    async def close(self) -> None:
        await self._client.aclose()
