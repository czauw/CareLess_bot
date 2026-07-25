# CareLess Bot

基于 NoneBot2 和 OneBot 11 的 QQ 群聊人格与个人服务器管家机器人。当前实现严格处于 MVP 阶段：仅使用内存存储和模拟 Ops Gateway，不包含真实服务器控制、Hermes 或部署配置执行。

## 当前功能

- 统一规范化 OneBot 群聊与私聊消息，并按 `message_id` 去重。
- 管理命令：`/服`、`/任务`、`/确认`、`/取消`、`/帮助`。
- 白名单仅基于 OneBot `sender_id` 判断；非白名单用户不能创建任务、审批或调用网关。
- 服务器动作只生成受限的结构化请求，绝不接收 Shell、路径或任意参数。
- `停止`、`重启` 等 R2 操作使用一次性确认码；确认码绑定操作者、群/私聊类型和会话 ID，不能跨会话确认。
- 任务支持互斥、状态迁移、超时转 `unknown` 和状态核验。
- 管理员在任意群 `@` 机器人或私聊时即时回复；默认绕过群白名单和普通成员冷却。
- 普通成员仅能在允许群内通过 `@` 开启短会话：每条消息最多一条机器人回复，同一发起人最多两回合；回复和艾特冷却按群独立。
- 群聊人格使用可配置保留时间的线性 QQ 上下文，默认最多 20K 近似 tokens、1000 条、6 小时。成功发送的机器人回复也会回写上下文。
- 人格回复强制为单行、20 字以内、无标点；没有可用 LLM 时，只保留硬触发降级回复。
- 使用稳定 system prompt 加追加式线性上下文，帮助兼容 OpenAI 格式的远程模型命中前缀缓存；另有同群同上下文的短 TTL 精确回复缓存。
- 支持可选 OpenAI 兼容 LLM 客户端；仅在同时配置 `LLM_API_BASE` 与 `LLM_API_KEY` 时启用。
- 所有 QQ 输出经过脱敏；所有服务器操作记录审计事件，高风险操作额外记录创建、确认、取消和超时。审计中的 QQ 号仅保留后四位。
- 支持全局、命令、人格、上下文、LLM、审计、运维读写、R1 审批和单服务器启用开关。

## 目录

- `bot/src/core/`：领域模型、端口、权限、审批、任务和审计服务。
- `bot/src/plugins/`：事件接入、群聊人格、确定性管理命令和 Hermes 预留协议。
- `bot/src/adapters/`：内存存储、模拟 Ops Gateway、OneBot 输出脱敏和可选 LLM 客户端。
- `config/servers.yml`：模拟服务器登记与能力清单。
- `tests/`：命令、审批、作用域隔离和人格安全测试。

## 本地开发

从仓库根目录安装 `bot/pyproject.toml` 中的依赖后，可运行：

```powershell
python -m pytest -q
python -m bot.src.bot
```

第二条命令仅用于启动本地机器人进程；需要先按 `bot/.env.example` 创建有效 `.env`。本仓库当前不会自动部署或连接真实服务器。

## 配置

`bot/.env.example` 包含每个环境变量的中文注释。开关均使用 `true` 或 `false`：

- `BOT_ENABLED`：维护总开关，关闭后丢弃全部入站消息。
- `ADMIN_COMMANDS_ENABLED`、`PERSONA_ENABLED`、`PERSONA_CONTEXT_ENABLED`：分别控制命令、人格和人格短期记忆。
- `PERSONA_HARD_TRIGGER_ENABLED`、`PERSONA_SOFT_TRIGGER_ENABLED`、`LLM_ENABLED`：控制人格触发与 LLM 使用。
- `ADMIN_BYPASS_GROUP_ALLOWLIST`、`ADMIN_BYPASS_COOLDOWNS`：管理员是否绕过普通成员的群限制和冷却。
- `GUEST_CONVERSATION_MAX_REPLIES`、`GUEST_CONVERSATION_TTL_SECONDS`：普通成员短会话上限和有效期；上限强制不超过两回合。
- `GUEST_GROUP_REPLY_COOLDOWN_SECONDS`、`GUEST_GROUP_MENTION_COOLDOWN_SECONDS`：普通成员按群独立的回复与艾特冷却。
- `CONTEXT_MAX_TOKENS`、`CONTEXT_MAX_MESSAGES`、`CONTEXT_TTL_SECONDS`：线性上下文预算、条数与记忆保留时间。
- `RESPONSE_CACHE_ENABLED`、`RESPONSE_CACHE_TTL_SECONDS`：同群精确回复缓存；不会跨群复用。
- `OPS_ENABLED`、`OPS_READ_ENABLED`、`OPS_WRITE_ENABLED`、`OPS_R1_REQUIRES_APPROVAL`：控制服务器操作范围和 R1 审批策略。
- `AUDIT_ENABLED`：仅限本地调试关闭；正常运行应保持开启。

`config/persona.yml` 管理人格参数，环境变量中的同名 `PERSONA_*` 配置优先。`config/servers.yml` 的每台服务器均有 `enabled`、`driver` 和 `capabilities`；能力列表只能使用 `status`、`players`、`logs`、`start`、`stop`、`restart`、`backup`。

## 验证状态

- `python -m pytest -q`：11 passed
- `python -m compileall -q bot tests`：通过

## 实现记录

- 2026-07-25：完成 NoneBot 运行时装配、统一消息路由、模拟 Ops Gateway 命令与审批流程。
- 2026-07-25：增加人格上下文隔离、时区静默、LLM 降级与超时未知状态处理。
- 2026-07-25：增加审批作用域类型绑定及结构化高风险操作审计。
- 2026-07-25：补齐所有服务器操作的开始、成功和失败审计，避免向 QQ 回显网关异常详情。
- 2026-07-25：完成配置开关策略、人格 YAML 生效、单服启用状态和运维读写策略。
- 2026-07-25：实现管理员即时人格回复、普通成员两回合短会话、群级双冷却、20K 线性上下文与回复缓存。
