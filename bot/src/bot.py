"""CareLess Bot —— NoneBot2 启动入口。

通过 OneBot 11 反向 WebSocket 接收 NapCat 推送的 QQ 事件，
加载各插件并启动机器人进程。
"""

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

from bot.src.config import load_config
from bot.src.bootstrap import build_runtime

# 加载并校验配置
config = load_config()

# 初始化 NoneBot，并将 OneBot 鉴权令牌传给适配器配置。
nonebot.init(onebot_access_token=config.onebot_access_token)
build_runtime(config)

# 注册 OneBot v11 适配器
driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)

# 导入统一 Matcher 完成注册。业务插件不直接耦合 OneBot 事件。
import bot.src.plugins.event_ingest.matcher  # noqa: E402, F401


def run() -> None:
    """启动机器人。"""
    nonebot.run()
