"""MVP 模拟 Ops Gateway。

用内存状态模拟服务器运维，支持配置延迟、成功/失败/超时场景，
用于验证整个审批→执行→结果回报流程。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime

from bot.src.core.models import (
    LogsResult,
    OperationResult,
    OperationState,
    PlayersResult,
    ServerStatus,
)


@dataclass
class _MockServer:
    """模拟服务器状态。"""

    server_id: str
    display_name: str
    online: bool = False
    player_count: int = 0
    max_players: int = 20
    version: str = "1.21"
    uptime_start: float | None = None
    log_lines: list[str] = field(default_factory=list)
    backup_count: int = 0


class MockOpsGateway:
    """模拟运维网关——所有状态在内存中。"""

    def __init__(
        self,
        *,
        default_delay: float = 0.3,
        default_timeout: float = 30.0,
    ) -> None:
        self._servers: dict[str, _MockServer] = {}
        self._default_delay = default_delay
        self._default_timeout = default_timeout

    # ---- 服务器注册（测试用） ----

    def register_server(
        self,
        server_id: str,
        display_name: str = "",
        *,
        online: bool = False,
        player_count: int = 0,
        max_players: int = 20,
        version: str = "1.21",
    ) -> _MockServer:
        """注册模拟服务器。"""
        srv = _MockServer(
            server_id=server_id,
            display_name=display_name or server_id,
            online=online,
            player_count=player_count,
            max_players=max_players,
            version=version,
        )
        if online:
            srv.uptime_start = time.monotonic()
        self._servers[server_id] = srv
        return srv

    def _get(self, server_id: str) -> _MockServer:
        from bot.src.core.errors import UnknownServerError
        srv = self._servers.get(server_id)
        if srv is None:
            raise UnknownServerError(server_id)
        return srv

    async def _delay(self) -> None:
        await asyncio.sleep(self._default_delay)

    # ---- OpsGateway 接口实现 ----

    async def get_status(self, server_id: str) -> ServerStatus:
        await self._delay()
        srv = self._get(server_id)
        uptime = ""
        if srv.online and srv.uptime_start is not None:
            secs = int(time.monotonic() - srv.uptime_start)
            h, m, s = secs // 3600, (secs % 3600) // 60, secs % 60
            uptime = f"{h}h {m}m {s}s"
        return ServerStatus(
            server_id=server_id,
            online=srv.online,
            version=srv.version,
            player_count=srv.player_count,
            max_players=srv.max_players,
            tps=20.0 if srv.online else None,
            mspt=15.3 if srv.online else None,
            cpu_percent=35.2 if srv.online else None,
            memory_percent=62.1 if srv.online else None,
            uptime=uptime,
        )

    async def get_players(self, server_id: str) -> PlayersResult:
        await self._delay()
        srv = self._get(server_id)
        # 生成虚拟玩家名
        players = [f"Player_{i+1}" for i in range(srv.player_count)]
        return PlayersResult(
            server_id=server_id,
            online_count=srv.player_count,
            max_players=srv.max_players,
            players=players,
        )

    async def get_logs(self, server_id: str, limit: int) -> LogsResult:
        await self._delay()
        srv = self._get(server_id)
        lines = srv.log_lines[-limit:] if srv.log_lines else [
            "[Server] Everything is running smoothly.",
            f"[Server] Uptime: OK, Players: {srv.player_count}",
        ]
        return LogsResult(
            server_id=server_id,
            lines=lines,
            total_lines=len(srv.log_lines) or len(lines),
        )

    async def start_server(self, server_id: str) -> OperationResult:
        await self._delay()
        srv = self._get(server_id)
        if srv.online:
            return OperationResult(
                operation_id="",
                success=True,
                state=OperationState.SUCCEEDED,
                summary=f"服务器 {srv.display_name} 已在运行中",
            )
        srv.online = True
        srv.uptime_start = time.monotonic()
        return OperationResult(
            operation_id="",
            success=True,
            state=OperationState.SUCCEEDED,
            summary=f"服务器 {srv.display_name} 已启动",
        )

    async def stop_server(self, server_id: str) -> OperationResult:
        await self._delay()
        srv = self._get(server_id)
        if not srv.online:
            return OperationResult(
                operation_id="",
                success=True,
                state=OperationState.SUCCEEDED,
                summary=f"服务器 {srv.display_name} 已处于离线状态",
            )
        srv.online = False
        srv.uptime_start = None
        return OperationResult(
            operation_id="",
            success=True,
            state=OperationState.SUCCEEDED,
            summary=f"服务器 {srv.display_name} 已优雅停止",
        )

    async def restart_server(self, server_id: str) -> OperationResult:
        await self._delay()
        srv = self._get(server_id)
        srv.online = False
        await asyncio.sleep(self._default_delay)
        srv.online = True
        srv.uptime_start = time.monotonic()
        return OperationResult(
            operation_id="",
            success=True,
            state=OperationState.SUCCEEDED,
            summary=f"服务器 {srv.display_name} 已重启完成",
        )

    async def backup_server(self, server_id: str) -> OperationResult:
        await self._delay()
        srv = self._get(server_id)
        srv.backup_count += 1
        snapshot_id = f"snap-{srv.server_id}-{srv.backup_count:03d}"
        return OperationResult(
            operation_id="",
            success=True,
            state=OperationState.SUCCEEDED,
            summary=f"备份完成，快照 ID: {snapshot_id}",
            detail={"snapshot_id": snapshot_id, "backup_number": srv.backup_count},
        )

    async def check_operation(self, operation_id: str) -> OperationResult:
        return OperationResult(
            operation_id=operation_id,
            success=True,
            state=OperationState.SUCCEEDED,
            summary="模拟：任务已完成",
        )
