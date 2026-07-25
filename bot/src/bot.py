"""CareLess Bot —— NoneBot2 启动入口。

通过 OneBot 11 反向 WebSocket 接收 NapCat 推送的 QQ 事件，
加载各插件并启动机器人进程。
"""

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

from bot.src.config import load_config

# 初始化 NoneBot
nonebot.init()

# 加载并校验配置
config = load_config()

# 注册 OneBot v11 适配器
driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)

# 插件由 NoneBot2 自动发现加载
# 约定：插件位于 src/plugins/ 下


def run() -> None:
    """启动机器人。"""
    nonebot.run()
