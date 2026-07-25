"""速率限制服务 —— 防止刷屏与滥用。

提供简单的滑动窗口限流，用于：
- 群聊主动回复频率控制
- 用户级冷却
- 命令调用限流
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class _Bucket:
    """滑动窗口计数器。"""

    window_seconds: float
    max_count: int
    _timestamps: list[float] = field(default_factory=list)

    def allow(self) -> bool:
        """检查是否允许，并在允许时记录。"""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        self._timestamps = [t for t in self._timestamps if t > cutoff]
        if len(self._timestamps) >= self.max_count:
            return False
        self._timestamps.append(now)
        return True

    @property
    def count(self) -> int:
        """当前窗口内计数。"""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        return sum(1 for t in self._timestamps if t > cutoff)


class RateLimitService:
    """速率限制。"""

    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}

    def _bucket_key(self, scope: str, key: str) -> str:
        return f"{scope}:{key}"

    def check_and_consume(
        self,
        scope: str,
        key: str,
        *,
        window_seconds: float,
        max_count: int,
    ) -> bool:
        """检查并消耗一次额度；返回 True 表示允许。"""
        bk = self._bucket_key(scope, key)
        if bk not in self._buckets:
            self._buckets[bk] = _Bucket(
                window_seconds=window_seconds, max_count=max_count
            )
        return self._buckets[bk].allow()

    def remaining(
        self, scope: str, key: str, *, window_seconds: float, max_count: int
    ) -> int:
        """查询剩余额度。"""
        bk = self._bucket_key(scope, key)
        if bk not in self._buckets:
            return max_count
        return max_count - self._buckets[bk].count

    def reset(self, scope: str, key: str) -> None:
        """重置指定键的限流状态。"""
        bk = self._bucket_key(scope, key)
        self._buckets.pop(bk, None)
