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

启动成功后检查根目录 `log/`。日志格式为“时间 | 等级 | 模块名 | 正文”；每次启动以开始时间创建 `月-日-时-分-count.log`，例如 `07-26-21-05-1.log`。单文件最大 10MB，超过后以相同开始时间创建 count 加一的新文件。日志等级、单文件上限和控制台输出在 `config/logging.yml` 调整；`log/` 不会提交到 Git。

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

成功初始化后，把 `DATABASE_SCHEMA_MODE` 改回 `validate`。当前最新 revision 是 `20260727_05`，包含群聊/私聊 scope、无长度回复缓存、活跃计数默认值修复和结构化 `@` 元数据。旧数据库必须先以 `migrate` 启动一次；多实例部署时只应让一个实例执行迁移。

## 人格配置

编辑 `config/persona.yml` 的 `persona.profile`。默认：

```yaml
profile:
  enabled: false
```

将 `enabled` 改为 `true` 后，可以填写 `name`、`identity`、`background`、`traits`、`speaking_style` 与 `boundaries`。这些字段会被加入稳定系统提示词；不要在 YAML 中填写 API 密钥或真实个人敏感信息。

普通消息默认以 1% 概率触发一次 AI 场景检查，概率命中不等于必定回复。模型最多携带最近 60 条群消息帮助理解多人对话，但只有最近 15 条、180 秒内且不跨越 90 秒空档的消息可以成为回复目标。一次调用同时选择目标、生成内容并决定会话状态；无自然机会时返回 `no_reply`。

随机回复成功、群内 `@` 或引用机器人都会开启短会话窗口。明确互动会强制进入窗口，不受随机概率、AI 检查冷却、随机发言冷却或令牌额度限制，也不消耗随机发言令牌。窗口按群管理、不绑定发起人，管理员和普通成员的后续消息都会进入窗口判断。窗口默认持续 120 秒；AI 提问时可持续 180 秒，最多 4 次机器人回复和 8 次 AI 检查。窗口内新消息仍由 AI 判断接谁或保持沉默。同一群的模型任务串行执行，等待期间的新消息会合并，避免并发重复回复。机器人输出始终直接发送文本，不使用 QQ 回复/引用消息段。

群聊和私聊提示词完全分开。群聊使用稳定的群内匿名成员 ID、消息 ID、引用和候选目标；私聊只包含当前对象与机器人的一对一记录，最多携带 60 条，并明确禁止混入群聊信息。可分别用 `GROUP_CONTEXT_MAX_MESSAGES` 和 `PRIVATE_CONTEXT_MAX_MESSAGES` 调整。两者仍受 `CONTEXT_MAX_TOKENS` 与 `CONTEXT_TTL_SECONDS` 约束。

为提高上游前缀缓存命中，固定 system/task 提示词放在最前，历史按时间顺序追加；群成员匿名 ID 在同一群内保持稳定。会变化的候选目标列表和当前时间位于末尾。达到 60 条并淘汰最旧消息时，动态历史前缀不可避免会变化，但群/私聊各自的固定提示词前缀不会变化。

`.env` 中可通过 `PERSONA_REPLY_DELAY_ENABLED` 开关延迟；`PERSONA_REPLY_DELAY_MIN_SECONDS` 与 `PERSONA_REPLY_DELAY_MAX_SECONDS` 默认是 15 和 30。`PERSONA_FOLLOWUP_DELAY_*` 控制同一轮后续消息的短停顿，`PERSONA_REPLY_MAX_MESSAGES` 固定上限为 3。项目不伪造 QQ “正在输入”状态。

随机检查由 `PERSONA_SOFT_TRIGGER_ENABLED` 控制，示例配置默认开启；没有可用 LLM 时自动关闭。`AMBIENT_AI_CHECK_COOLDOWN_SECONDS` 限制检查频率，`PERSONA_GROUP_COOLDOWN_SECONDS` 只在实际发言后生效。每群使用容量 2、每 20 分钟恢复 1 个的令牌桶；AI 返回 `no_reply` 不消耗令牌。同一目标用户默认 300 秒内不会被再次主动选择。

`LLM_TIMEOUT_SECONDS` 默认 30 秒。超时不会自动重试，避免一次群聊判断产生额外模型调用；失败会记录完整异常，后续新消息仍可重新触发判断。

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
