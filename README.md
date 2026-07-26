# CareLess Bot

基于 NoneBot2 和 OneBot 11 的 QQ 机器人，包含群聊人格与受控服务器管理命令。当前项目只提供代码与本地开发配置，不会自动部署、连接真实服务器或连接数据库。

## 已实现功能

- 统一接收群聊和私聊消息，并按 `message_id` 去重。
- 白名单管理员可在任意群 `@` 机器人或私聊时立即得到人格回复；可分别配置是否绕过群白名单和冷却。
- 普通成员仅能在允许群中 `@` 机器人开启短会话。一次会话最多两条机器人回复，回复与再次 `@` 冷却均按群独立。
- 人格回复限制为一行、最多 20 字、移除标点。LLM 不可用时保留硬触发降级回复。
- 维护按群隔离的线性上下文，格式为 `QQ号: 消息`。默认保留 6 小时，最多 20K 近似 token、1000 条消息；机器人成功回复也会写回上下文。
- 使用稳定 system prompt 加追加式上下文，帮助 OpenAI 兼容远程模型命中前缀缓存；另有同群、同上下文、同配置的短 TTL 精确回复缓存。
- 支持可选 OpenAI 兼容 LLM。只有 `LLM_ENABLED=true` 且同时配置 API 地址和密钥时才会发起远程调用。
- 提供白名单运维命令、一次性审批码、审计记录和 mock Ops Gateway。当前不支持真实 Ops Gateway。
- 提供 SQLAlchemy ORM、异步 Store 和 Alembic 入口。默认仍为内存存储，不会连接数据库。

## 快速配置

复制 `bot/.env.example` 为本地 `.env`，至少填写以下项目后才可启动：

```dotenv
ONEBOT_ACCESS_TOKEN=替换为至少8位的随机令牌
BOT_QQ_ID=机器人QQ号
WHITELIST_QQ_IDS=管理员QQ号
```

默认 `STORAGE_BACKEND=memory`，不需要数据库。人格使用远程模型时，再设置：

```dotenv
LLM_ENABLED=true
LLM_API_BASE=https://你的OpenAI兼容接口/v1
LLM_API_KEY=你的密钥
LLM_MODEL=gpt-4o-mini
```

`ALLOWED_GROUP_IDS` 用逗号分隔群号；留空表示所有群都允许普通成员使用人格。管理员是否绕过此限制由 `ADMIN_BYPASS_GROUP_ALLOWLIST` 决定。

## 配置说明

完整示例和中文注释见 [bot/.env.example](bot/.env.example)。布尔开关均使用 `true` 或 `false`。

| 分类 | 必要配置 | 说明 |
| --- | --- | --- |
| OneBot | `ONEBOT_ACCESS_TOKEN`、`BOT_QQ_ID` | 连接反向 WebSocket 的令牌和机器人 QQ 号。|
| 权限 | `WHITELIST_QQ_IDS`、`ALLOWED_GROUP_IDS` | 白名单可执行管理命令；群白名单限制普通成员人格入口。|
| 总开关 | `BOT_ENABLED`、`ADMIN_COMMANDS_ENABLED`、`PERSONA_ENABLED`、`LLM_ENABLED` | 可整体关闭机器人、命令、人格或远程模型调用。|
| 人格会话 | `GUEST_CONVERSATION_*`、`GUEST_GROUP_*_COOLDOWN_SECONDS` | 配置普通成员会话上限、有效期，以及按群独立的回复和艾特冷却。上限由代码限制为 1 到 2。|
| 上下文与缓存 | `CONTEXT_*`、`RESPONSE_CACHE_*` | 配置线性记忆预算、保留时间和精确回复缓存 TTL。|
| 运维 | `OPS_*`、`APPROVAL_TTL_SECONDS` | 独立控制只读、写操作和 R1 操作是否也需要确认。当前仅 `mock` 后端可用。|
| 持久化 | `STORAGE_BACKEND`、`SQLALCHEMY_DATABASE_URL` | 选择内存或 SQLAlchemy 存储。SQLAlchemy 必须显式设置 DSN。|

`PERSONA_ACTIVE_PROBABILITY`、`PERSONA_GROUP_COOLDOWN_SECONDS`、`PERSONA_USER_COOLDOWN_SECONDS` 和 `PERSONA_MAX_ACTIVE_REPLIES_PER_HOUR` 用于主动插话的通用门控。普通成员的 `@` 短会话实际使用 `GUEST_GROUP_REPLY_COOLDOWN_SECONDS` 与 `GUEST_GROUP_MENTION_COOLDOWN_SECONDS`。

`config/persona.yml` 仅可覆盖人格门控、主动概率、通用冷却、回复长度和静默时段。环境变量中显式设置的同名 `PERSONA_*` 值优先。会话、数据库、全模块开关等仍在 `.env` 中配置。

`config/servers.yml` 的服务器需要 `enabled`、`display_name`、`driver` 和 `capabilities`。支持的能力为 `status`、`players`、`logs`、`start`、`stop`、`restart`、`backup`。`enabled: false` 不会注册该服务器，也不能被命令操作；`real` 驱动仅为预留，目前启用会被拒绝。

## 人格触发与记忆

- 管理员：任意群 `@` 或私聊命中硬触发后立即回复，可选绕过限制与冷却。
- 普通成员：仅允许群的 `@` 可新建会话；会话内仅同一发起人的自然消息可以续聊，最多两次回复。
- 随机插话：由 `PERSONA_SOFT_TRIGGER_ENABLED` 控制，默认关闭；未配置可用 LLM 时也不会主动插话。
- 上下文：每个群独立，按时间线追加，超出条数、token 预算或 TTL 时淘汰最早内容。内存模式下重启会丢失；SQLAlchemy 模式可持久化。
- 缓存：精确缓存键包含群、线性上下文和人格配置，避免跨群复用。稳定的前缀内容放在前面，便于上游 OpenAI 兼容服务的前缀缓存命中。

## 数据库状态

已声明并接入可选的 SQLAlchemy Store，涵盖群、聊天消息、去重记录、成员活跃度、人格会话和冷却、记忆摘要、LLM 缓存和指标、管理员、服务器、任务、审批与审计事件。

启用持久化需要自行完成以下准备，项目不会自动执行：

1. 安装 `aiomysql` 等目标数据库的异步驱动。
2. 在 `.env` 设定 `STORAGE_BACKEND=sqlalchemy` 与真实的 `SQLALCHEMY_DATABASE_URL`。
3. 从 `bot/` 目录显式执行 Alembic 迁移。

仓库当前只有 Alembic 环境入口，尚未提交初始 revision；因此不能把“设定 DSN”当作已可用数据库。摘要表与 `summary_run` 已规划，但每日或手动群活跃成员总结的调度和执行功能尚未实现。

## 命令与风险控制

管理命令仅允许白名单 QQ 使用：`/服`、`/任务`、`/确认`、`/取消`、`/帮助`。`停止`、`重启` 等 R2 操作必须使用一次性确认码；确认绑定操作人、会话类型和会话 ID。`启动`、`备份` 等 R1 操作是否需要确认由 `OPS_R1_REQUIRES_APPROVAL` 控制。所有命令当前只调用 mock Gateway，绝不接收 Shell、路径或任意参数。

## 本地开发

安装 `bot/pyproject.toml` 中的依赖后，在仓库根目录运行：

```powershell
python -m pytest -q
python -m compileall -q bot tests
python -m bot.src.bot
```

最后一条只启动本地机器人进程，需要先创建有效 `.env` 和可用 OneBot 反向 WebSocket；它不等于部署。

## 验证状态

- `python -m pytest -q`：14 passed
- `python -m compileall -q bot tests`：通过

## 实现记录

- 2026-07-25：完成 NoneBot 运行时装配、统一消息路由、mock Ops Gateway 命令和审批流程。
- 2026-07-25：增加人格上下文隔离、时区静默、LLM 降级和任务超时未知状态处理。
- 2026-07-25：完成管理员即时人格回复、普通成员两回合短会话、群级双冷却、20K 线性上下文与精确回复缓存。
- 2026-07-26：规划 SQLAlchemy 群消息、记忆、缓存、运维和审计表，并接入可选 `SqlAlchemyStore`。
- 2026-07-26：补充 README 与示例配置，明确本地运行、人格行为、可选持久化及尚未实现的边界。
