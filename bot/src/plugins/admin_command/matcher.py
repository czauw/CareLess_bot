"""管理命令 NoneBot2 Matcher 注册。

将命令文本匹配规则注册为 NoneBot Matcher，
在群聊和私聊中同时生效。
"""

from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event, GroupMessageEvent, PrivateMessageEvent
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.rule import Rule

from bot.src.core.runtime import get_runtime

# 命令前缀匹配
HELP = on_command("帮助", aliases={"help"}, priority=1, block=True)

SERVER_OP = on_command("服", priority=1, block=True)

JOB_QUERY = on_command("任务", priority=1, block=True)

APPROVE = on_command("确认", priority=1, block=True)

CANCEL = on_command("取消", priority=1, block=True)


# 通用权限检查
async def _get_sender_id(event: Event) -> str:
    """从事件中提取 sender_id。"""
    return str(event.get_user_id())


async def _check_whitelist(event: Event) -> bool:
    """检查 sender_id 是否在白名单中。"""
    runtime = get_runtime()
    sender_id = str(event.get_user_id())
    return runtime.auth_service.is_whitelisted(sender_id)


def whitelist_only() -> Rule:
    """仅白名单用户可用的规则。"""
    return Rule(_check_whitelist)
