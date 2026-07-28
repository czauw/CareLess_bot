"""core/errors.py 业务异常测试。"""

from __future__ import annotations

from bot.src.core.errors import (
    AmbiguousServerError,
    ApprovalAlreadyUsedError,
    ApprovalError,
    ApprovalExpiredError,
    ApprovalMismatchError,
    CareLessError,
    CommandParseError,
    HermesDisabledError,
    JobConflictError,
    JobNotFoundError,
    NotWhitelistedError,
    OpsGatewayError,
    RiskLevelBlockedError,
    ServiceUnavailableError,
    UnknownServerError,
)


def test_careless_error_base() -> None:
    error = CareLessError("基础错误")
    assert str(error) == "基础错误"
    assert isinstance(error, Exception)


def test_not_whitelisted_error() -> None:
    error = NotWhitelistedError("12345")
    assert error.sender_id == "12345"
    assert "12345" in str(error)


def test_command_parse_error() -> None:
    error = CommandParseError("语法错误")
    assert "语法错误" in str(error)
    assert isinstance(error, CareLessError)


def test_unknown_server_error() -> None:
    error = UnknownServerError("myserver")
    assert error.server_id == "myserver"
    assert "myserver" in str(error)


def test_ambiguous_server_error() -> None:
    error = AmbiguousServerError("mc", ["mc1", "mc2"])
    assert error.name == "mc"
    assert error.matches == ["mc1", "mc2"]


def test_risk_level_blocked_error() -> None:
    error = RiskLevelBlockedError("R3")
    assert error.risk_level == "R3"
    assert "R3" in str(error)


def test_approval_error_base() -> None:
    error = ApprovalError("审批失败")
    assert isinstance(error, CareLessError)


def test_approval_expired_error() -> None:
    error = ApprovalExpiredError("已过期")
    assert isinstance(error, ApprovalError)


def test_approval_already_used_error() -> None:
    error = ApprovalAlreadyUsedError("已使用")
    assert isinstance(error, ApprovalError)


def test_approval_mismatch_error() -> None:
    error = ApprovalMismatchError("不匹配")
    assert isinstance(error, ApprovalError)


def test_job_conflict_error() -> None:
    error = JobConflictError("survival", "job-1")
    assert error.server_id == "survival"
    assert error.existing_job_id == "job-1"
    assert "survival" in str(error)


def test_job_not_found_error() -> None:
    error = JobNotFoundError()
    assert isinstance(error, CareLessError)


def test_ops_gateway_error() -> None:
    error = OpsGatewayError("连接超时")
    assert "连接超时" in str(error)


def test_hermes_disabled_error() -> None:
    error = HermesDisabledError()
    assert "Hermes Agent" in str(error)


def test_service_unavailable_error() -> None:
    error = ServiceUnavailableError("LLM", "超时")
    assert error.service == "LLM"
    assert "LLM" in str(error)
    assert "超时" in str(error)


def test_all_errors_catchable_by_base() -> None:
    errors: list[CareLessError] = [
        NotWhitelistedError("1"),
        CommandParseError("x"),
        UnknownServerError("x"),
        AmbiguousServerError("x", []),
        RiskLevelBlockedError("R3"),
        ApprovalError("x"),
        ApprovalExpiredError("x"),
        ApprovalAlreadyUsedError("x"),
        ApprovalMismatchError("x"),
        JobConflictError("x", "y"),
        JobNotFoundError("任务不存在"),
        OpsGatewayError("x"),
        HermesDisabledError(),
        ServiceUnavailableError("x"),
    ]
    for error in errors:
        assert isinstance(error, CareLessError)
        assert str(error) != ""
