"""管理命令处理 —— 权限、审批与任务交互。

处理流程：
1. 校验 sender_id 白名单
2. 解析命令 → ParsedCommand
3. 风险判定 → 低风险直接执行 / 高风险创建审批
4. 调用 Ops Gateway 执行结构化动作
5. 返回脱敏后的结果
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

from bot.src.core.errors import (
    ApprovalAlreadyUsedError,
    ApprovalExpiredError,
    ApprovalMismatchError,
    CommandParseError,
    HermesDisabledError,
    JobConflictError,
    JobNotFoundError,
    NotWhitelistedError,
    RiskLevelBlockedError,
)
from bot.src.core.models import (
    ActionType,
    OperationRequest,
    OperationState,
    RiskLevel,
    ScopeType,
)
from bot.src.core.ports import OpsGateway, Store
from bot.src.core.runtime import get_runtime
from bot.src.plugins.admin_command.parser import ACTION_RISK, CommandParser, ParsedCommand


class CommandHandler:
    """管理命令处理器。"""

    HELP_TEXT = (
        "📋 可用命令：\n"
        "/服 状态 [服名]    查询服务器状态\n"
        "/服 玩家 [服名]    查询在线玩家\n"
        "/服 日志 [服名] [行数]  查看最近日志（默认 20 行）\n"
        "/服 启动 [服名]    启动服务器\n"
        "/服 停止 [服名]    停止服务器（需确认）\n"
        "/服 重启 [服名]    重启服务器（需确认）\n"
        "/服 备份 [服名]    触发备份\n"
        "/任务 [ID]         查询异步任务进度\n"
        "/确认 <确认码>     确认高风险操作\n"
        "/取消 <确认码>     取消待审批操作\n"
        "/帮助              显示本帮助"
    )

    def __init__(
        self,
        parser: CommandParser,
        ops: OpsGateway,
        store: Store,
    ) -> None:
        self._parser = parser
        self._ops = ops
        self._store = store

    async def handle(
        self,
        sender_id: str,
        scope_type: ScopeType,
        scope_id: str,
        text: str,
    ) -> str:
        """处理管理命令并返回响应文本。"""
        runtime = get_runtime()

        if not runtime.config.admin_commands_enabled:
            return "管理命令当前未启用。"

        # 1. 权限校验
        if not runtime.auth_service.is_whitelisted(sender_id):
            raise NotWhitelistedError(sender_id)

        # 2. 解析命令
        cmd = self._parser.parse(text)
        await runtime.audit_service.record(
            "admin_command",
            sender_id,
            f"{scope_type.value}:{scope_id}",
            "accepted",
            reason=cmd.kind,
        )

        # 3. 分发
        if cmd.kind == "help":
            return self.HELP_TEXT

        if cmd.kind == "server_op":
            return await self._handle_server_op(cmd, sender_id, scope_type, scope_id)

        if cmd.kind == "job_query":
            return await self._handle_job_query(cmd)

        if cmd.kind == "approve":
            return await self._handle_approve(cmd, sender_id, scope_type, scope_id)

        if cmd.kind == "cancel":
            return await self._handle_cancel(cmd, sender_id, scope_type, scope_id)

        return "未知命令，发送 /帮助 查看可用命令。"

    # ----------------------------------------------------------
    # 服务器操作
    # ----------------------------------------------------------

    async def _handle_server_op(
        self,
        cmd: ParsedCommand,
        sender_id: str,
        scope_type: ScopeType,
        scope_id: str,
    ) -> str:
        assert cmd.action is not None

        if cmd.server_id is None:
            return "请指定服务器名称。例如：/服 状态 生存服"

        action = cmd.action
        risk = ACTION_RISK[action]

        runtime = get_runtime()
        if not runtime.config.ops_enabled:
            return "服务器运维功能当前未启用。"
        if risk == RiskLevel.R0 and not runtime.config.ops_read_enabled:
            return "服务器查询功能当前未启用。"
        if risk != RiskLevel.R0 and not runtime.config.ops_write_enabled:
            return "服务器操作功能当前未启用。"
        target = runtime.server_targets.get(cmd.server_id)
        if target is None or not target.enabled:
            return f"服务器 {cmd.server_id} 当前未启用。"
        if action.value not in target.capabilities:
            return f"服务器 {cmd.server_id} 不支持操作 {action.value}。"

        # R3 拒绝
        if risk == RiskLevel.R3:
            raise RiskLevelBlockedError(risk.value)

        # R0/R1 直接执行（R1 可配置确认，当前默认无需确认）
        if risk == RiskLevel.R0 or (
            risk == RiskLevel.R1 and not runtime.config.ops_r1_requires_approval
        ):
            return await self._execute_direct_action(
                action,
                cmd.server_id,
                cmd.params,
                sender_id,
                scope_type,
                scope_id,
                risk,
            )

        # R2 创建审批
        return await self._create_approval(
            action, cmd.server_id, sender_id, scope_type, scope_id, cmd.params
        )

    async def _execute_action(
        self,
        action: ActionType,
        server_id: str,
        params: dict[str, str],
    ) -> "OperationResult":
        """直接执行运维动作。"""
        if action == ActionType.STATUS:
            status = await self._ops.get_status(server_id)
            online = "🟢 在线" if status.online else "🔴 离线"
            parts = [f"{status.server_id} {online}"]
            if status.version:
                parts.append(f"版本: {status.version}")
            if status.online:
                parts.append(f"玩家: {status.player_count}/{status.max_players}")
                if status.tps:
                    parts.append(f"TPS: {status.tps:.1f}")
                if status.uptime:
                    parts.append(f"运行: {status.uptime}")
            return type(
                "Result", (),
                {"summary": "\n".join(parts)}
            )()

        elif action == ActionType.PLAYERS:
            result = await self._ops.get_players(server_id)
            if not result.players:
                return type("Result", (), {"summary": f"{server_id} 无在线玩家"})()
            return type(
                "Result", (),
                {"summary": f"{server_id} 在线 {result.online_count}/{result.max_players}:\n" + ", ".join(result.players)}
            )()

        elif action == ActionType.LOGS:
            limit = int(params.get("limit", "20"))
            max_log_lines = getattr(get_runtime().config, "ops_max_log_lines", 100)
            limit = max(1, min(max_log_lines, limit))
            result = await self._ops.get_logs(server_id, limit)
            return type("Result", (), {"summary": "\n".join(result.lines)})()
        else:
            method = getattr(self._ops, {
                ActionType.START: "start_server",
                ActionType.STOP: "stop_server",
                ActionType.RESTART: "restart_server",
                ActionType.BACKUP: "backup_server",
            }[action])
            result = await method(server_id)
            return result

    async def _execute_direct_action(
        self,
        action: ActionType,
        server_id: str,
        params: dict[str, str],
        sender_id: str,
        scope_type: ScopeType,
        scope_id: str,
        risk_level: RiskLevel,
    ) -> str:
        """执行低风险操作，并记录不依赖任务表的审计闭环。"""
        runtime = get_runtime()
        correlation_id = runtime.job_service.new_operation_id()
        audit_args = {
            "correlation_id": correlation_id,
            "operation_id": correlation_id,
            "action": action.value,
            "target": server_id,
            "risk_level": risk_level.value,
        }
        await runtime.audit_service.record(
            "operation",
            sender_id,
            f"{scope_type.value}:{scope_id}",
            "started",
            **audit_args,
        )
        try:
            result = await self._execute_action(action, server_id, params)
        except Exception as error:
            await runtime.audit_service.record(
                "operation",
                sender_id,
                f"{scope_type.value}:{scope_id}",
                "failed",
                reason=type(error).__name__,
                **audit_args,
            )
            return f"操作失败，诊断 ID: {correlation_id}。"

        await runtime.audit_service.record(
            "operation",
            sender_id,
            f"{scope_type.value}:{scope_id}",
            "succeeded",
            **audit_args,
        )
        return result.summary

    async def _create_approval(
        self,
        action: ActionType,
        server_id: str,
        sender_id: str,
        scope_type: ScopeType,
        scope_id: str,
        params: dict[str, str],
    ) -> str:
        """创建高风险操作审批。"""
        runtime = get_runtime()

        operation_id = runtime.job_service.new_operation_id()
        request = OperationRequest(
            operation_id=operation_id,
            actor_qq_id=sender_id,
            scope_type=scope_type,
            scope_id=scope_id,
            action=action,
            server_id=server_id,
            normalized_params=params,
            risk_level=ACTION_RISK[action],
        )

        try:
            job = await runtime.job_service.create_job(request)
        except JobConflictError as e:
            return f"服务器 {server_id} 已有任务 {e.existing_job_id} 在进行中，请等待完成后再操作。"

        code = await runtime.approval_service.create_approval(job)
        await self._audit_operation(job, "approval_requested")

        return (
            f"⚠️ 高风险操作确认\n"
            f"操作: {action.value} {server_id}\n"
            f"确认码: {code}\n"
            f"两分钟内有效。请发送 /确认 {code} 以确认执行。\n"
            f"发送 /取消 {code} 可取消。"
        )

    # ----------------------------------------------------------
    # 确认 / 取消
    # ----------------------------------------------------------

    async def _handle_approve(
        self,
        cmd: ParsedCommand,
        sender_id: str,
        scope_type: ScopeType,
        scope_id: str,
    ) -> str:
        runtime = get_runtime()

        try:
            job = await runtime.approval_service.validate(
                scope_type,
                scope_id,
                cmd.raw_code,
                expected_scope_type=scope_type,
                expected_scope_id=scope_id,
                expected_actor=sender_id,
            )
        except ApprovalMismatchError:
            return "确认码无效或不属于当前会话。"
        except ApprovalExpiredError:
            return "确认码已过期，请重新发起操作。"
        except ApprovalAlreadyUsedError:
            return "该确认码已被使用。"

        # 执行
        await runtime.job_service.transition(job, OperationState.QUEUED)
        await runtime.job_service.transition(job, OperationState.RUNNING)
        await self._audit_operation(job, "approval_confirmed")

        try:
            timeout_seconds = getattr(runtime.config, "ops_command_timeout_seconds", 30)
            result = await asyncio.wait_for(
                self._execute_action(
                    job.request.action,
                    job.request.server_id,
                    job.request.normalized_params,
                ),
                timeout=timeout_seconds,
            )
            await runtime.job_service.transition(
                job, OperationState.SUCCEEDED, result_summary=result.summary
            )
            await self._audit_operation(job, "succeeded")
            return f"✅ {result.summary}"
        except TimeoutError:
            await runtime.job_service.transition(
                job,
                OperationState.UNKNOWN,
                result_summary="操作超时，等待状态核验",
            )
            try:
                await self._ops.check_operation(job.operation_id)
            except Exception:
                pass
            await self._audit_operation(job, "unknown", reason="operation_timeout")
            return f"❓ 操作超时，任务 {job.operation_id} 已标记为未知状态，请稍后查询。"
        except Exception as e:
            await runtime.job_service.transition(
                job, OperationState.FAILED, result_summary=str(e)
            )
            await self._audit_operation(job, "failed", reason=type(e).__name__)
            return f"❌ 操作失败，任务 {job.operation_id} 已记录。"

    async def _handle_cancel(
        self,
        cmd: ParsedCommand,
        sender_id: str,
        scope_type: ScopeType,
        scope_id: str,
    ) -> str:
        runtime = get_runtime()

        code_hash = runtime.approval_service.hash_code(cmd.raw_code)
        job = await self._store.find_pending_approval(scope_type, scope_id, code_hash)

        if job is None:
            return "未找到对应的待审批操作。"
        if job.request.actor_qq_id != sender_id:
            return "只有创建该操作的本人才能取消。"

        await runtime.approval_service.cancel(job)
        await self._audit_operation(job, "cancelled")
        return "已取消该操作。"

    async def _audit_operation(
        self,
        job: "OperationJob",
        decision: str,
        *,
        reason: str | None = None,
    ) -> None:
        """记录不包含命令原文的高风险操作审计事件。"""
        runtime = get_runtime()
        await runtime.audit_service.record(
            "operation",
            job.request.actor_qq_id,
            f"{job.request.scope_type.value}:{job.request.scope_id}",
            decision,
            reason=reason,
            correlation_id=job.operation_id,
            operation_id=job.operation_id,
            action=job.request.action.value,
            target=job.request.server_id,
            risk_level=job.request.risk_level.value,
        )

    # ----------------------------------------------------------
    # 任务查询
    # ----------------------------------------------------------

    async def _handle_job_query(self, cmd: ParsedCommand) -> str:
        job_id = cmd.params.get("job_id", "")
        runtime = get_runtime()
        job = await runtime.job_service.get_job(job_id)

        if job is None:
            return f"未找到任务 {job_id}。"

        state_map = {
            OperationState.PENDING_APPROVAL: "⏳ 待确认",
            OperationState.QUEUED: "📋 排队中",
            OperationState.RUNNING: "🔄 执行中",
            OperationState.SUCCEEDED: "✅ 已完成",
            OperationState.FAILED: "❌ 失败",
            OperationState.CANCELLED: "🚫 已取消",
            OperationState.EXPIRED: "⏰ 已过期",
            OperationState.UNKNOWN: "❓ 未知",
        }

        return (
            f"📋 任务 {job.operation_id}\n"
            f"操作: {job.request.action.value} {job.request.server_id}\n"
            f"状态: {state_map.get(job.state, job.state.value)}\n"
            f"{job.result_summary or ''}"
        )
