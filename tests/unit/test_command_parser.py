"""CommandParser 边界情况测试。"""

from __future__ import annotations

import pytest

from bot.src.core.errors import AmbiguousServerError, CommandParseError, UnknownServerError
from bot.src.plugins.admin_command.parser import CommandParser


def make_parser() -> CommandParser:
    return CommandParser({"生存服": "survival", "创造服": "creative", "测试服": "test"})


def test_parse_help() -> None:
    parser = make_parser()
    cmd = parser.parse("/帮助")
    assert cmd.kind == "help"


def test_parse_status_with_server() -> None:
    parser = make_parser()
    cmd = parser.parse("/服 状态 生存服")
    assert cmd.kind == "server_op"
    assert cmd.action.value == "status"
    assert cmd.server_id == "survival"


def test_parse_players_without_server() -> None:
    parser = make_parser()
    cmd = parser.parse("/服 玩家")
    assert cmd.action.value == "players"
    assert cmd.server_id is None


def test_parse_logs_with_count() -> None:
    parser = make_parser()
    cmd = parser.parse("/服 日志 生存服 50")
    assert cmd.action.value == "logs"
    assert cmd.server_id == "survival"
    assert cmd.params.get("limit") == "50"


def test_parse_logs_count_only() -> None:
    parser = make_parser()
    cmd = parser.parse("/服 日志 30")
    assert cmd.action.value == "logs"
    assert cmd.server_id is None
    assert cmd.params.get("limit") == "30"


def test_parse_logs_default_limit() -> None:
    parser = make_parser()
    cmd = parser.parse("/服 日志 生存服")
    assert cmd.params.get("limit") == "20"


def test_parse_logs_rejects_extra_arg() -> None:
    parser = make_parser()
    with pytest.raises(CommandParseError, match="日志行数后不能再提供额外参数"):
        parser.parse("/服 日志 50 生存服")


def test_parse_logs_rejects_non_numeric() -> None:
    parser = make_parser()
    with pytest.raises(CommandParseError, match="日志行数必须是数字"):
        parser.parse("/服 日志 生存服 十行")


def test_parse_start() -> None:
    parser = make_parser()
    cmd = parser.parse("/服 启动 生存服")
    assert cmd.action.value == "start"
    assert cmd.server_id == "survival"


def test_parse_stop() -> None:
    parser = make_parser()
    cmd = parser.parse("/服 停止 生存服")
    assert cmd.action.value == "stop"


def test_parse_restart() -> None:
    parser = make_parser()
    cmd = parser.parse("/服 重启 生存服")
    assert cmd.action.value == "restart"


def test_parse_backup() -> None:
    parser = make_parser()
    cmd = parser.parse("/服 备份 生存服")
    assert cmd.action.value == "backup"


def test_parse_job_query() -> None:
    parser = make_parser()
    cmd = parser.parse("/任务 abc123")
    assert cmd.kind == "job_query"
    assert cmd.params["job_id"] == "abc123"


def test_parse_approve() -> None:
    parser = make_parser()
    cmd = parser.parse("/确认 CODE123")
    assert cmd.kind == "approve"
    assert cmd.raw_code == "CODE123"


def test_parse_cancel() -> None:
    parser = make_parser()
    cmd = parser.parse("/取消 CODE456")
    assert cmd.kind == "cancel"
    assert cmd.raw_code == "CODE456"


def test_parse_invalid_command() -> None:
    parser = make_parser()
    with pytest.raises(CommandParseError):
        parser.parse("普通聊天消息")


def test_parse_extra_arg_rejected() -> None:
    parser = make_parser()
    with pytest.raises(CommandParseError, match="只接受一个服务器名称参数"):
        parser.parse("/服 状态 生存服 多余")


def test_server_resolution_exact_id() -> None:
    parser = make_parser()
    cmd = parser.parse("/服 状态 survival")
    assert cmd.server_id == "survival"


def test_server_resolution_fuzzy() -> None:
    parser = make_parser()
    cmd = parser.parse("/服 状态 生存")
    assert cmd.server_id == "survival"


def test_server_resolution_ambiguous() -> None:
    parser = CommandParser({"生存服A": "srv_a", "生存服B": "srv_b"})
    with pytest.raises(AmbiguousServerError):
        parser.parse("/服 状态 生存")


def test_server_resolution_unknown() -> None:
    parser = make_parser()
    with pytest.raises(UnknownServerError):
        parser.parse("/服 状态 不存在的服")


def test_parse_with_extra_whitespace() -> None:
    parser = make_parser()
    cmd = parser.parse("  /服 状态 生存服  ")
    assert cmd.action.value == "status"


def test_parse_job_without_id_raises() -> None:
    parser = make_parser()
    with pytest.raises(CommandParseError):
        parser.parse("/任务")
