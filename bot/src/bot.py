"""CareLess Bot —— NoneBot2 启动入口。

通过 OneBot 11 反向 WebSocket 接收 NapCat 推送的 QQ 事件，
加载各插件并启动机器人进程。
"""

import logging

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

from bot.src.bootstrap import build_runtime
from bot.src.config import DEFAULT_ENV_FILE, ensure_env_file, load_config
from bot.src.core.runtime import get_runtime
from bot.src.log_config import load_logging_options, setup_logging

# 首次启动时只生成示例配置，不以示例值继续运行。
if ensure_env_file():
    raise RuntimeError(
        f"已创建示例配置 {DEFAULT_ENV_FILE}。请填写 ONEBOT_ACCESS_TOKEN、"
        "BOT_QQ_ID 和 WHITELIST_QQ_IDS 后重新启动。"
    )

# 加载并校验配置
config = load_config()

# YAML 是默认日志配置来源；.env 的 LOG_LEVEL 仅用于部署时临时覆盖。
logging_options = load_logging_options()
log_override = config.log_level if "log_level" in config.model_fields_set else None
log_file = setup_logging(logging_options, level_override=log_override)
logger = logging.getLogger(__name__)
logger.info("日志已初始化: %s", log_file)

# 初始化 NoneBot，并将 OneBot 鉴权令牌传给适配器配置。
nonebot.init(onebot_access_token=config.onebot_access_token)
build_runtime(config)
logger.info("运行时已初始化")

# 注册 OneBot v11 适配器
driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)


@driver.on_shutdown
async def close_runtime_resources() -> None:
    """仅在真实启动后释放可选数据库和 LLM HTTP 连接池。"""
    runtime = get_runtime()
    if runtime.database_engine is not None:
        await runtime.database_engine.dispose()
    close = getattr(runtime.llm_provider, "close", None)
    if close is not None:
        await close()
    logger.info("运行时资源已释放")

# 导入统一 Matcher 完成注册。业务插件不直接耦合 OneBot 事件。
import bot.src.plugins.event_ingest.matcher  # noqa: E402, F401


def run() -> None:
    """启动机器人。"""
    logger.info("启动 CareLess Bot")
    nonebot.run()


if __name__ == "__main__":
    run()
