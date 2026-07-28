"""core/models.py 数据类与枚举测试。"""

from __future__ import annotations

from datetime import UTC, datetime

from bot.src.core.models import (
    ActionType,
    AuditEvent,
    LogsResult,
    NormalizedMessage,
    OperationJob,
    OperationRequest,
    OperationResult,
    OperationState,
    PlayersResult,
    RiskLevel,
    ScopeType,
    ServerStatus,
    ServerTarget,
    TriggerType,
)


def test_normalized_message_defaults() -> None:
    msg = NormalizedMessage(
        message_id="m1",
        sender_id="10001",
        sender_alias="测试",
        scope_type=ScopeType.GROUP,
        scope_id="20001",
        text="你好",
        message_type="text",
        reply_to=None,
        is_at_bot=False,
        created_at=datetime.now(UTC),
    )
    assert msg.at_user_ids == frozenset()
    assert msg.message_id == "m1"


def test_server_target_from_config_full() -> None:
    target = ServerTarget.from_config("survival", {
        "display_name": "生存服",
        "driver": "mock",
        "capabilities": ["status", "start", "stop"],
        "enabled": True,
    })
    assert target.server_id == "survival"
    assert target.display_name == "生存服"
    assert target.driver == "mock"
    assert target.capabilities == frozenset({"status", "start", "stop"})
    assert target.enabled is True


def test_server_target_from_config_minimal() -> None:
    target = ServerTarget.from_config("default", {})
    assert target.display_name == "default"
    assert target.driver == "mock"
    assert target.capabilities == frozenset()
    assert target.enabled is True


def test_operation_request_immutable() -> None:
    req = OperationRequest(
        operation_id="op-1",
        actor_qq_id="10001",
        scope_type=ScopeType.GROUP,
        scope_id="20001",
        action=ActionType.STATUS,
        server_id="survival",
    )
    assert req.risk_level == RiskLevel.R0
    assert req.normalized_params == {}


def test_operation_job_defaults() -> None:
    req = OperationRequest(
        operation_id="op-1",
        actor_qq_id="10001",
        scope_type=ScopeType.GROUP,
        scope_id="20001",
        action=ActionType.START,
        server_id="survival",
        risk_level=RiskLevel.R1,
    )
    job = OperationJob(operation_id="op-1", request=req)
    assert job.state == OperationState.PENDING_APPROVAL
    assert job.approval_code_hash is None
    assert job.approval_expires_at is None
    assert job.result_summary is None
    assert job.created_at is not None
    assert job.updated_at is not None


def test_audit_event_creation() -> None:
    event = AuditEvent(
        event_type="operation",
        actor="***0001",
        scope="group:20001",
        decision="started",
        reason=None,
        correlation_id="corr-1",
        operation_id="op-1",
        action="status",
        target="survival",
        risk_level="R0",
    )
    assert event.event_type == "operation"
    assert event.actor == "***0001"


def test_server_status_defaults() -> None:
    status = ServerStatus(server_id="survival", online=False)
    assert status.server_id == "survival"
    assert status.online is False
    assert status.version is None
    assert status.player_count == 0
    assert status.max_players == 0


def test_players_result_defaults() -> None:
    result = PlayersResult(server_id="survival", online_count=3, max_players=20)
    assert result.players == []
    assert result.online_count == 3


def test_logs_result_creation() -> None:
    result = LogsResult(server_id="survival", lines=["line1", "line2"], total_lines=100)
    assert result.lines == ["line1", "line2"]
    assert result.total_lines == 100


def test_operation_result_creation() -> None:
    result = OperationResult(
        operation_id="op-1",
        success=True,
        state=OperationState.SUCCEEDED,
        summary="启动成功",
    )
    assert result.success is True
    assert result.detail is None


def test_scope_type_values() -> None:
    assert ScopeType.GROUP.value == "group"
    assert ScopeType.PRIVATE.value == "private"


def test_risk_level_values() -> None:
    assert RiskLevel.R0.value == "R0"
    assert RiskLevel.R1.value == "R1"
    assert RiskLevel.R2.value == "R2"
    assert RiskLevel.R3.value == "R3"


def test_operation_state_values() -> None:
    assert OperationState.PENDING_APPROVAL.value == "pending_approval"
    assert OperationState.SUCCEEDED.value == "succeeded"
    assert OperationState.FAILED.value == "failed"


def test_action_type_values() -> None:
    assert ActionType.STATUS.value == "status"
    assert ActionType.START.value == "start"
    assert ActionType.STOP.value == "stop"


def test_trigger_type_values() -> None:
    assert TriggerType.HARD.value == "hard"
    assert TriggerType.SOFT.value == "soft"
    assert TriggerType.COMMAND.value == "command"
    assert TriggerType.NONE.value == "none"
