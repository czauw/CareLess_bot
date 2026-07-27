"""按聊天作用域串行安排人格回复，模拟自然的阅读与输入等待。"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable


logger = logging.getLogger(__name__)
ReplyCallback = Callable[[], Awaitable[None]]


class PersonaReplyScheduler:
    """每个群或私聊对象至多保留一个等待中的回复任务。

    新消息到来时会替换同一作用域尚未开始发送的旧任务。真正开始生成或发送后
    不再取消，避免已经发出第一条分段消息却丢失后续内容。所有等待均是异步的，
    不会阻塞其他群聊、私聊或 NoneBot 的事件循环。
    """

    def __init__(
        self,
        *,
        enabled: bool,
        min_delay_seconds: float,
        max_delay_seconds: float,
        followup_min_delay_seconds: float,
        followup_max_delay_seconds: float,
    ) -> None:
        self._enabled = enabled
        self._min_delay = min_delay_seconds
        self._max_delay = max_delay_seconds
        self._followup_min_delay = followup_min_delay_seconds
        self._followup_max_delay = followup_max_delay_seconds
        self._pending: dict[str, asyncio.Task[None]] = {}
        self._queued: dict[str, ReplyCallback] = {}
        self._active_scopes: set[str] = set()
        self._tasks: set[asyncio.Task[None]] = set()

    def schedule(self, scope_key: str, callback: ReplyCallback) -> bool:
        """延迟执行回调；同一作用域的等待任务会被较新的消息替换。"""
        if scope_key in self._active_scopes:
            # 模型请求期间的新消息保留为下一次判断；同一群只保留最新回调，
            # 避免并发回复乱序，也避免明确 @ 在随机判断期间被直接丢掉。
            self._queued[scope_key] = callback
            logger.debug("人格回复正在生成，已保留最新后续任务 scope=%s", scope_key)
            return True

        if previous := self._pending.get(scope_key):
            previous.cancel()
        task = asyncio.create_task(self._run(scope_key, callback), name=f"persona-reply:{scope_key}")
        self._pending[scope_key] = task
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return True

    async def wait_before_followup(self) -> None:
        """两个或三个实际 QQ 消息之间的短停顿。"""
        if self._enabled:
            await asyncio.sleep(random.uniform(self._followup_min_delay, self._followup_max_delay))

    async def close(self) -> None:
        """关闭时取消尚未发送的回复，避免释放数据库连接后继续写入。"""
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._pending.clear()
        self._queued.clear()
        self._active_scopes.clear()

    async def _run(self, scope_key: str, callback: ReplyCallback) -> None:
        current_task = asyncio.current_task()
        try:
            if self._enabled:
                # 三角分布比完全均匀的固定区间更自然，峰值位于中间偏前的位置。
                await asyncio.sleep(random.triangular(self._min_delay, self._max_delay, 21.0))

            if self._pending.get(scope_key) is not current_task:
                return
            self._pending.pop(scope_key, None)
            self._active_scopes.add(scope_key)
            await callback()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("延迟人格回复执行失败 scope=%s", scope_key)
        finally:
            if self._pending.get(scope_key) is current_task:
                self._pending.pop(scope_key, None)
            self._active_scopes.discard(scope_key)
            if callback := self._queued.pop(scope_key, None):
                self.schedule(scope_key, callback)
