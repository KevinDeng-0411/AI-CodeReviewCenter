# ADR-0003: 对话消息存储 - PG 为真相源, Redis 为缓存

- **状态**: Accepted
- **日期**: 2026-07-28
- **关联术语**: Short-term Memory, Session/Conversation

## 背景

Java 版 Short-term Memory 号称"热数据 Redis、冷数据持久化 PG",但读路径只读 Redis:

- `getContextWindow`([ShortTermMemoryManager.java:68](../ai-center-ai/src/main/java/com/aicenter/ai/memory/ShortTermMemoryManager.java#L68))、`getMessages`([:99](../ai-center-ai/src/main/java/com/aicenter/ai/memory/ShortTermMemoryManager.java#L99)):摘要 + 消息均**只读 Redis**。
- `persistMessage`([:160](../ai-center-ai/src/main/java/com/aicenter/ai/memory/ShortTermMemoryManager.java#L160)):写 `chat_messages`(PG)。
- Redis TTL 7 天([:48](../ai-center-ai/src/main/java/com/aicenter/ai/memory/ShortTermMemoryManager.java#L48))。

后果:Redis TTL 一到,`/api/chat/conversations/{sessionId}` 返回空,尽管 PG `chat_messages` 全在。**PG 持久化只写不读,是死代码**。

## 决策

1. **PG(`chat_messages`)是对话消息的 source of truth**;Redis 是热缓存(滑窗 + 摘要),仅用于快速拼上下文。
2. **补 fallback 读**:Redis miss 时,从 `chat_messages` 回查最近 N 条重建窗口,再回填 Redis。对话历史不再随 TTL 蒸发。
3. `persistMessage` 不再是死代码;它是真相写入,Redis 是其加速缓存。

## 结果

- 对话历史跨 Redis 过期存活,API 永远能返回。
- Redis 仍是上下文拼装的热路径(性能不变)。
- **遗留子决策**:LLM 摘要当前 Redis-only(`REDIS_SESSION_SUMMARY`),Redis miss 时摘要也丢。需定:摘要持久化到 PG(如 `chat_conversations.summary` 列)还是 miss 时从消息重算。**待 grilling**。
- 此决定**强化** Q8 的"统一记忆叙事":短期记忆现在真正持久化(不再 7 天蒸发),才配得上"记忆"二字。
