# CareLess Bot

基于 NoneBot2 和 OneBot 11 的 QQ 机器人，包含群聊人格与受控服务器管理命令。当前项目只提供代码与本地开发配置，不会自动部署、连接真实服务器或连接数据库。

完整运行步骤、NapCat 对接和能力边界见 [使用文档](docs/USAGE.md)。

## 已实现功能

- 统一接收群聊和私聊消息，并按 `message_id` 去重。
- 白名单管理员可在任意群 `@` 机器人或私聊时立即得到人格回复；可分别配置是否绕过群白名单和冷却。
- 普通成员仅能在允许群中 `@` 机器人开启短会话。一次会话最多两条机器人回复，回复与再次 `@` 冷却均按群独立。
- 人格模型返回 JSON 消息列表：通常一条，必要时自然拆为至多三条 QQ 消息；保留自然标点，不设字符长度硬上限。
- 每个群和私聊独立采用 15–30 秒异步拟人延迟；等待期出现新消息会替换旧回复，不伪造“正在输入”状态。
- 持久化所有群聊和私聊记录，并按群或私聊对象隔离线性上下文，格式为 `QQ号: 消息`。默认保留 6 小时，最多 20K 近似 token、1000 条消息；机器人成功回复也会写回上下文。
- 使用稳定 system prompt 加追加式上下文，帮助 OpenAI 兼容远程模型命中前缀缓存；另有同群、同上下文、同配置的短 TTL 精确回复缓存。
- 支持可选 OpenAI 兼容 LLM。只有 `LLM_ENABLED=true` 且同时配置 API 地址和密钥时才会发起远程调用。
- 提供白名单运维命令、一次性审批码、审计记录和 mock Ops Gateway。当前不支持真实 Ops Gateway。
- 提供 SQLAlchemy ORM、异步 Store 和 Alembic 入口。默认仍为内存存储，不会连接数据库。

## 快速配置

首次执行 `python -m bot.src.bot` 时，如果仓库根目录没有 `.env`，程序会自动从 `bot/.env.example` 创建一份并停止启动，同时提示填写必填项。已有 `.env` 绝不会被覆盖。填写以下项目后重新启动：

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

安装运行依赖可使用 `python -m pip install -r requirements.txt`；依赖清单位于 [requirements.txt](requirements.txt)。完整环境变量示例和中文注释见 [bot/.env.example](bot/.env.example)。布尔开关均使用 `true` 或 `false`。

| 分类         | 必要配置                                                                          | 说明                                                                                  |
| ------------ | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| OneBot       | `ONEBOT_ACCESS_TOKEN`、`BOT_QQ_ID`                                            | 连接反向 WebSocket 的令牌和机器人 QQ 号。                                             |
| 权限         | `WHITELIST_QQ_IDS`、`ALLOWED_GROUP_IDS`                                       | 白名单可执行管理命令；群白名单限制普通成员人格入口。                                  |
| 总开关       | `BOT_ENABLED`、`ADMIN_COMMANDS_ENABLED`、`PERSONA_ENABLED`、`LLM_ENABLED` | 可整体关闭机器人、命令、人格或远程模型调用。                                          |
| 人格会话     | `GUEST_CONVERSATION_*`、`GUEST_GROUP_*_COOLDOWN_SECONDS`                      | 配置普通成员会话上限、有效期，以及按群独立的回复和艾特冷却。上限由代码限制为 1 到 2。 |
| 拟人回复     | `PERSONA_REPLY_DELAY_*`、`PERSONA_FOLLOWUP_DELAY_*`、`PERSONA_REPLY_MAX_MESSAGES` | 独立异步延迟、分段消息间隔与单轮最多三条实际 QQ 消息。                              |
| 上下文与缓存 | `CONTEXT_*`、`RESPONSE_CACHE_*`                                               | 配置线性记忆预算、保留时间和精确回复缓存 TTL。                                        |
| 运维         | `OPS_*`、`APPROVAL_TTL_SECONDS`                                               | 独立控制只读、写操作和 R1 操作是否也需要确认。当前仅`mock` 后端可用。               |
| 持久化       | `STORAGE_BACKEND`、`SQLALCHEMY_DATABASE_URL`、`DATABASE_SCHEMA_MODE`          | SQLAlchemy 启动时检测连接并校验 revision；可显式自动迁移。                            |
| 日志         | `config/logging.yml`、可选 `LOG_LEVEL`                                        | YAML 设置等级、单文件上限和控制台输出；环境变量可临时覆盖等级。                       |

`PERSONA_ACTIVE_PROBABILITY`、`PERSONA_GROUP_COOLDOWN_SECONDS`、`PERSONA_USER_COOLDOWN_SECONDS` 和 `PERSONA_MAX_ACTIVE_REPLIES_PER_HOUR` 用于主动插话的通用门控。普通成员的 `@` 短会话实际使用 `GUEST_GROUP_REPLY_COOLDOWN_SECONDS` 与 `GUEST_GROUP_MENTION_COOLDOWN_SECONDS`。

`config/persona.yml` 仅可覆盖人格门控、主动概率、通用冷却和静默时段。环境变量中显式设置的同名 `PERSONA_*` 值优先。会话、数据库、全模块开关等仍在 `.env` 中配置。

机器人可选人设也在 `config/persona.yml` 的 `persona.profile` 中管理，使用 YAML 的字符串与列表字段表达昵称、身份、背景、性格、说话风格和边界。`enabled: false` 为默认值，此时不会把任何自定义人设加入提示词；设为 `true` 后才会生效。连接令牌、API 密钥与数据库 DSN 仍应放在 `.env`，不要写入 YAML 配置。

`config/servers.yml` 的服务器需要 `enabled`、`display_name`、`driver` 和 `capabilities`。支持的能力为 `status`、`players`、`logs`、`start`、`stop`、`restart`、`backup`。`enabled: false` 不会注册该服务器，也不能被命令操作；`real` 驱动仅为预留，目前启用会被拒绝。

`config/logging.yml` 控制日志等级，支持 `DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`。每条日志采用“时间 | 等级 | 模块名 | 正文”格式。日志文件写入根目录 `log/`，按启动时间命名为 `月-日-时-分-count.log`，例如 `07-26-21-05-1.log`；单文件上限强制为 10MB，超过后保持同一开始时间并将 count 加一。`log/` 已被 `.gitignore` 忽略。需要部署时临时提高或降低等级，可在 `.env` 设置 `LOG_LEVEL` 覆盖 YAML。

## 人格触发与记忆

- 管理员：任意群 `@` 或私聊命中硬触发后进入按作用域独立的延迟回复队列，可选绕过限制与冷却。
- 普通成员：仅允许群的 `@` 可新建会话；会话内仅同一发起人的自然消息可以续聊，最多两轮逻辑回复；每轮通常发一条、最多三条实际 QQ 消息。
- 输出：LLM 只返回 `{"messages":[...]}`；每项是一条自然 QQ 消息，默认允许标点。延迟期内同一作用域的新消息会取消并替换尚未发送的旧任务，延迟结束后再从数据库读取最新上下文。
- 随机插话：由 `PERSONA_SOFT_TRIGGER_ENABLED` 控制，默认关闭。开启后，未处于普通成员短会话的群消息会在静默、冷却和每小时额度检查后按 `PERSONA_ACTIVE_PROBABILITY` 抽样；未配置可用 LLM 时也不会主动插话。
- 上下文：每个群和每个私聊对象独立，按时间线追加，超出条数、token 预算或 TTL 时淘汰最早内容。SQLAlchemy 模式从持久化聊天记录读取，并将 MySQL 无时区 `DATETIME` 按 UTC 还原，避免 TTL 错误淘汰刚收到的消息；内存模式下重启会丢失。
- 缓存：精确缓存键包含群、线性上下文和人格配置，避免跨群复用。稳定的前缀内容放在前面，便于上游 OpenAI 兼容服务的前缀缓存命中；当前时间会按 `TIMEZONE` 作为最后一条“信息补充”追加到 user prompt，避免动态时间破坏此前的稳定前缀。

## 数据库状态

已声明并接入可选的 SQLAlchemy Store，涵盖群、群聊和私聊消息、去重记录、成员活跃度、人格会话和冷却、记忆摘要、LLM 缓存和指标、管理员、服务器、任务、审批与审计事件。

启用持久化需要自行完成以下准备：

1. 安装 `aiomysql` 等目标数据库的异步驱动；MySQL 8 的 SHA2 认证还需要 `cryptography`（已列入 requirements）。
2. 在 `.env` 设定 `STORAGE_BACKEND=sqlalchemy` 与真实的 `SQLALCHEMY_DATABASE_URL`。
3. 首次初始化将 `DATABASE_SCHEMA_MODE=migrate` 后启动机器人；启动会检测连接、取得 MySQL 迁移锁并执行 `alembic upgrade head`。

默认 `DATABASE_SCHEMA_MODE=validate`，只检测连接并校验数据库 revision；空库或版本落后会拒绝启动，防止隐式改库。`migrate` 才会自动升级，失败也会终止启动。当前最新 revision 为 `20260726_03`：`chat_message` 以 `scope_type + scope_id` 区分群聊和私聊，旧群聊记录会自动回填为 `group` scope；精确回复缓存也使用 `TEXT`，不会限制回复长度。MySQL 的 DDL 不可事务回滚，因此此迁移会检测并续作上次中断后已执行的列变更。后续字段变更必须新增 revision。摘要表与 `summary_run` 已规划，但每日或手动群活跃成员总结的调度和执行功能尚未实现。

## 命令与风险控制

管理命令仅允许白名单 QQ 使用：`/服`、`/任务`、`/确认`、`/取消`、`/帮助`。`停止`、`重启` 等 R2 操作必须使用一次性确认码；确认绑定操作人、会话类型和会话 ID。`启动`、`备份` 等 R1 操作是否需要确认由 `OPS_R1_REQUIRES_APPROVAL` 控制。所有命令当前只调用 mock Gateway，绝不接收 Shell、路径或任意参数。

## 本地开发

安装 `requirements.txt` 或 `bot/pyproject.toml` 中的依赖后，在仓库根目录运行。运行依赖包含 `tzdata`，以保证 Windows 等环境可使用默认的 `Asia/Shanghai` 时区：

```powershell
python -m pytest -q
python -m compileall -q bot tests
python -m bot.src.bot
```

最后一条只启动本地机器人进程，并按 `.env` 的 `HOST`、`PORT` 监听反向 WebSocket。缺少 `.env` 时会创建示例文件并提示填写；已有但无效的 `.env` 会报告具体校验错误。需要可用 OneBot 反向 WebSocket；它不等于部署。

## 验证状态

- `python -m pytest -q`：14 passed
- `python -m compileall -q bot tests`：通过

## 实现记录

- 2026-07-25：完成 NoneBot 运行时装配、统一消息路由、mock Ops Gateway 命令和审批流程。
- 2026-07-25：增加人格上下文隔离、时区静默、LLM 降级和任务超时未知状态处理。
- 2026-07-25：完成管理员即时人格回复、普通成员两回合短会话、群级双冷却、20K 线性上下文与精确回复缓存。
- 2026-07-26：规划 SQLAlchemy 群消息、记忆、缓存、运维和审计表，并接入可选 `SqlAlchemyStore`。
- 2026-07-26：补充 README 与示例配置，明确本地运行、人格行为、可选持久化及尚未实现的边界。
- 2026-07-26：新增 `requirements.txt` 与 YAML 可选人设配置；默认不注入自定义人设。
- 2026-07-26：首次启动缺少 `.env` 时自动从示例创建，并提示填写必填连接与管理员信息。
- 2026-07-26：新增 YAML 日志配置和根目录日志轮转，单文件最大 10MB，日志目录不纳入 Git。
- 2026-07-26：新增使用文档，补齐 NoneBot FastAPI 驱动依赖与反向 WebSocket 监听配置。
- 2026-07-26：修复普通群消息的随机回复入口、短会话续聊和主动回复限流记录。
- 2026-07-26：SQLAlchemy 模式启动时增加连接与 revision 校验，`migrate` 模式可在 MySQL 锁保护下自动执行初始及后续 Alembic 迁移。
- 2026-07-26：修复 NoneBot 2.5 消息事件的原始文本读取兼容性，私聊和群消息可继续进入规范化与人格回复链路。
- 2026-07-26：SQLAlchemy 模式下私聊无持久化上下文时回退使用触发消息，保证管理员私聊硬触发可回复。
- 2026-07-26：人格 LLM 增加 `LLM_THINKING_ENABLED` 开关；默认关闭 DeepSeek 思考模式，避免 reasoning_content 占用短回复输出预算。
- 2026-07-26：聊天消息表升级为作用域记录，私聊和群聊均持久化，SQLAlchemy 上下文直接从数据库读取。
- 2026-07-26：修复 MySQL `DATETIME` 读取缺失时区导致 TTL 错误淘汰私聊上下文的问题。
- 2026-07-26：人格回复改为 JSON 消息列表，支持一轮最多三条 QQ 消息与按作用域 15–30 秒异步拟人延迟。
- 2026-07-26：日志文件改为按启动时间与序号命名，超过 10MB 时递增序号轮转，并统一记录时间、等级和模块名。
- 2026-07-26：人格提示词在聊天上下文末尾追加按 `TIMEZONE` 格式化的当前时间信息，保留稳定提示词和线性上下文前缀的缓存命中条件。
