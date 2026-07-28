# ADR-0004: 记忆概念界定 + 领域语言统一 (Conversation)

- **状态**: Accepted
- **日期**: 2026-07-28
- **关联术语**: Memory, Short-term Memory, Long-term Memory, Conversation
- **上游**: 收口 [ADR-0001](0001-memory-vs-knowledge-two-tables-shared-recall.md) / [ADR-0003](0003-message-store-pg-source-of-truth.md) 的命名与定义

## 背景

两件事:

1. **"统一记忆叙事"过宽**:Q8 提出"短期+长期共同决定 LLM 答案故统一称 memory",但该理由同样适用于 RAG 知识库(也注入 prompt 影响答案),会推翻 ADR-0001 的 Memory ≠ Knowledge。需更紧的定义。
2. **命名分裂**:同一概念三套名字--字段 `session_id`、实体 `ChatConversation`、API `/conversations`。

## 决策

1. **Memory 紧定义**:Memory = **从对话中自动积累的信息**(短期=消息窗口+摘要、长期=捕获事实),是系统的**"经验"**;Knowledge = **外部上传的参考文档**,是系统的**"资料"**。两者都影响答案,但 Memory **对话内生**,Knowledge **外部策展**。
2. **统一记忆叙事保留**:短期/长期是刻意的认知心理学类比--短期=工作记忆(近因、精确文本),长期=情景/语义记忆(相似召回)。不同机制对应不同时间尺度,统一于"从对话经验中塑造答案"。该定义把 Knowledge 挡在 memory 之外,保住 ADR-0001。
3. **领域语言统一**:多轮对话概念统一称 **Conversation**,标识符 `conversation_id`。领域词汇清除 "session"(仅保留 Web 层 session 概念,若有)。`ChatConversation` 实体 -> `Conversation`。

## 结果

- Short-term Memory / Long-term Memory / Session-Conversation 术语均转 🟢。
- **API 契约破坏性变更**:`session_id` 字段 -> `conversation_id`(请求/响应体)。路径 `/api/chat/conversations` 本就用复数,保持。因为是整体重写,接受此破坏,前端同步改。
- ADR-0003 的"短期记忆持久化"与此定义一致:Memory 现真正持久化,配得上"经验"。
- 面试可答:"两种记忆策略统一于目的(从对话经验塑造答案),与知识库的区别在**起源**(内生 vs 外部),非机制。"

## 遗留

- ADR-0003 子决策仍未定:LLM 摘要 Redis-only,miss 时持久化到 PG 还是重算?留待收口。
