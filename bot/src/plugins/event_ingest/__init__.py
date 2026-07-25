"""事件接入插件 —— OneBot 事件规范化、去重与路由。

职责：
1. 将 OneBot 事件的 sender_id、message_id、群/私聊等提取为 NormalizedMessage
2. 对 message_id 做幂等去重，防止断线重发或重复回复
3. 过滤机器人自身消息
4. 路由到管理命令或群聊人格
"""
