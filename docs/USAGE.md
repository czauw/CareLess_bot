# CareLess Bot 使用文档

## 可用范围

项目的消息接收、白名单权限、人格会话、OpenAI 兼容 LLM、内存存储、日志和 mock 运维命令已经实现并有单元测试覆盖。满足本地 Python、NapCat/OneBot 11 与 QQ 登录条件后，可以作为 QQ 机器人运行。

以下能力尚不能作为真实生产功能使用：

- 服务器运维仅实现 `mock` Gateway；`OPS_BACKEND=real` 会被拒绝启动。
- SQLAlchemy 代码支持启动前连接检测、revision 校验和可选自动迁移；生产数据库仍应先评审后续 migration 内容。
- 每日群成员风格/人格总结的数据表已规划，调度与生成尚未实现。

本项目不会替你启动 NapCat、登录 QQ、开放防火墙端口、部署数据库或连接真实服务器。

## 环境要求

- Python 3.11 或 3.12
- 可运行的 NapCat（或其他支持 OneBot 11 反向 WebSocket 的实现）和已登录 QQ
- 可选：OpenAI 兼容 API，用于真实人格回复

`requirements.txt` 已包含 Windows 使用 `Asia/Shanghai` 所需的 `tzdata`。

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

## 首次配置

在仓库根目录运行：

```powershell
python -m bot.src.bot
```

第一次运行若没有 `.env`，程序会自动从 `bot/.env.example` 创建根目录 `.env` 并停止。填写至少以下配置后重新运行：

```dotenv
ONEBOT_ACCESS_TOKEN=至少8位的随机令牌
BOT_QQ_ID=机器人QQ号
WHITELIST_QQ_IDS=管理员QQ号
HOST=127.0.0.1
PORT=8080
```

`WHITELIST_QQ_IDS` 支持逗号分隔多个 QQ 号。`ALLOWED_GROUP_IDS` 留空表示所有群允许普通成员使用人格；填写后只允许指定群。

## 配置 NapCat

机器人作为反向 WebSocket 服务端运行。按照 `.env` 中的 `HOST` 与 `PORT` 在 NapCat 里创建 OneBot 11 反向 WebSocket 客户端：

```text
ws://127.0.0.1:8080/onebot/v11/ws
```

将 NapCat 的访问令牌设置为与 `ONEBOT_ACCESS_TOKEN` 完全相同的值。若 NapCat 与机器人不在同一台机器，`HOST` 必须监听可访问的网卡地址，并由部署环境自行处理防火墙和网络安全。

## 启动与检查

```powershell
python -m bot.src.bot
```

启动成功后检查 `log/careless-bot.log`。日志等级、备份数量和控制台输出在 `config/logging.yml` 调整；每个日志文件最大 10MB，`log/` 不会提交到 Git。

连接成功后，在白名单账号的私聊或群内 `@` 机器人发送普通文本，确认能收到回复。人格回复默认在 15–30 秒后异步发送；同一私聊或群在等待期内有新消息时，会以新消息替换尚未发送的旧回复。未配置 `LLM_API_BASE` 和 `LLM_API_KEY` 时使用本地降级回复；配置后才会调用远程 OpenAI 兼容接口。

## 可选数据库初始化

默认 `STORAGE_BACKEND=memory`，不会连接数据库。使用 MySQL 持久化时设置：

```dotenv
STORAGE_BACKEND=sqlalchemy
SQLALCHEMY_DATABASE_URL=mysql+aiomysql://用户名:密码@数据库地址:3306/careless_bot?charset=utf8mb4
DATABASE_SCHEMA_MODE=migrate
```

项目依赖已包含 MySQL 8 的 SHA2 密码认证所需的 `cryptography`；安装 requirements 后无需单独处理。

首次启动使用 `migrate`：机器人会先执行连接检测，再取得 MySQL advisory lock，并自动执行 Alembic `upgrade head` 创建或升级表结构。迁移失败时机器人不会继续启动。

成功初始化后，把 `DATABASE_SCHEMA_MODE` 改回 `validate`。该默认模式只检测连接并确认数据库 revision 与代码的最新 revision 一致；空库、落后版本或未来版本都会拒绝启动，不会隐式改表。当前最新 revision `20260726_03` 会把 `chat_message` 升级为群聊/私聊通用 scope，并把精确回复缓存升级为不限制字符数的 `TEXT`；旧群聊记录自动回填为 `group`。若 MySQL 在 DDL 间中断，下一次 `migrate` 会识别已完成的列变更并继续。多实例部署时只应让一个实例使用 `migrate`。

## 人格配置

编辑 `config/persona.yml` 的 `persona.profile`。默认：

```yaml
profile:
  enabled: false
```

将 `enabled` 改为 `true` 后，可以填写 `name`、`identity`、`background`、`traits`、`speaking_style` 与 `boundaries`。这些字段会被加入稳定系统提示词；不要在 YAML 中填写 API 密钥或真实个人敏感信息。

普通成员必须在允许群中 `@` 机器人才能开始会话。每次会话最多两轮逻辑回复，群级回复与再次艾特均受 `.env` 中的 `GUEST_GROUP_*_COOLDOWN_SECONDS` 控制。单轮回复由模型输出 JSON `messages` 列表，通常发送一条、必要时最多三条实际 QQ 消息；后续消息间会有 1–4 秒自然停顿。管理员可以按配置绕过群白名单和冷却。SQLAlchemy 模式会持久化所有群聊、私聊文本和机器人成功回复；模型分别按群号或私聊对象从数据库读取最近上下文，不会跨作用域混用。

`.env` 中可通过 `PERSONA_REPLY_DELAY_ENABLED` 开关延迟；`PERSONA_REPLY_DELAY_MIN_SECONDS` 与 `PERSONA_REPLY_DELAY_MAX_SECONDS` 默认是 15 和 30。`PERSONA_FOLLOWUP_DELAY_*` 控制同一轮后续消息的短停顿，`PERSONA_REPLY_MAX_MESSAGES` 固定上限为 3。项目不伪造 QQ “正在输入”状态。

若希望机器人偶尔主动插话，将 `.env` 的 `PERSONA_SOFT_TRIGGER_ENABLED` 设为 `true`，并在 `config/persona.yml` 设置 `active_probability`。每条未艾特且不在短会话中的允许群消息都会在静默、群/用户冷却和每小时额度检查后参与概率抽样；例如 `0.02` 表示满足前置条件的消息有 2% 概率触发。主动回复成功后会记录冷却与额度。

## 管理命令

仅 `WHITELIST_QQ_IDS` 中的账号可使用：

- `/帮助`
- `/服 状态 生存服`
- `/服 日志 生存服`
- `/服 停止 生存服`
- `/任务`
- `/确认 <确认码>`
- `/取消 <确认码>`

当前服务器操作只作用于 `config/servers.yml` 中登记的 mock 服务器。停止和重启等高风险操作需要一次性确认码；不要把 mock 行为理解为真实服务器控制。

## 验证与排障

代码验证：

```powershell
python -m pytest -q
python -m compileall -q bot tests
```

常见问题：

- 首次运行后退出：按提示填写根目录 `.env` 后重新运行。
- 收不到 NapCat 消息：确认 WebSocket URL、监听地址、端口和访问令牌一致。
- 管理命令无响应：确认发送者 QQ 在 `WHITELIST_QQ_IDS`，并检查 `ADMIN_COMMANDS_ENABLED=true`。
- 人格没有真实模型回复：同时设置 `LLM_ENABLED=true`、`LLM_API_BASE` 与 `LLM_API_KEY`。
- 数据库启动失败：保持 `STORAGE_BACKEND=memory`，或检查 DSN、数据库服务与 revision。空库首次使用时设置 `DATABASE_SCHEMA_MODE=migrate` 后重启。
