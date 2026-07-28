# AI Center - 领域术语表 (Glossary)

> 本表由 `/grill-with-docs` grilling 会话维护。每条术语标注状态：
> - 🔴 **contested** - 定义有歧义/冲突，待 grilling 敲定
> - 🟡 **drafting** - 已有初步定义，待验证
> - 🟢 **settled** - 已敲定，关联 ADR

| 术语 | 当前理解 | 状态 | 关联 ADR |
|------|----------|------|----------|
| 核心领域 | **Chat(智能问答)** 为核心域;AI 编排基建(Prompt/Memory/VectorRecall)为支撑子域;CR/UT/AIReadMe 为次要工具上下文。 | 🟢 settled | [ADR-0007](adr/0007-core-domain-and-bounded-contexts.md) |
| Conversation | 多轮对话领域概念，统一称 Conversation，标识 `conversation_id`。清除领域词汇 "session"。 | 🟢 settled | [ADR-0004](adr/0004-memory-concept-and-conversation-naming.md) |
| Memory(统一概念) | 对话内生、塑造答案的信息。统一 short/long，排除 Knowledge(外部)。 | 🟢 settled | [ADR-0004](adr/0004-memory-concept-and-conversation-naming.md) |
| Short-term Memory | 工作记忆:消息窗口+摘要。机制=PG 真相源+Redis 缓存+fallback;起源=对话内生。 | 🟢 settled | [ADR-0003](adr/0003-message-store-pg-source-of-truth.md) [ADR-0004](adr/0004-memory-concept-and-conversation-naming.md) |
| Long-term Memory | 情景/语义记忆:原子事实+向量召回。起源=对话内生，区别于 Knowledge(外部策展)。 | 🟢 settled | [ADR-0001](adr/0001-memory-vs-knowledge-two-tables-shared-recall.md) [ADR-0004](adr/0004-memory-concept-and-conversation-naming.md) |
| Knowledge Document | 父实体 `documents`(全文存一次) + 子 `knowledge_chunks`(分块+embedding)。外部策展资料，per-project，混合召回。 | 🟢 settled | [ADR-0001](adr/0001-memory-vs-knowledge-two-tables-shared-recall.md) [ADR-0002](adr/0002-knowledge-document-parent-child.md) |
| Chunk | `knowledge_chunks` 子实体(document_id FK + chunk_index + chunk_content + embedding)。不再是扁平行。 | 🟢 settled | [ADR-0002](adr/0002-knowledge-document-parent-child.md) |
| VectorRecallService | 共享的 embed+内联 pgvector(`Vector(1024)`,消除 UUID 反查)+cosine 检索服务,Memory/Knowledge 共用。Hybrid Retrieval(pg_trgm+pgvector)为其一种检索策略。Embedding/Hybrid 均为基础设施实现细节,不单独立 ADR。 | 🟢 settled | [ADR-0001](adr/0001-memory-vs-knowledge-two-tables-shared-recall.md) |
| Prompt Template | 领域实体。逻辑身份=type,每行=版本,编辑=新增版本,每 type 恰一激活,可回滚。CHAT 纳入模板。 | 🟢 settled | [ADR-0005](adr/0005-prompttemplate-versioning-activation-chat.md) |
| AI Operation Record | 审计日志(append-only 事件流水),非实体。CR/UT 合并为 `ai_operation_records`(type 鉴别+result+metadata JSON)。 | 🟢 settled | [ADR-0006](adr/0006-records-audit-log-merge.md) |

> 全部术语已 🟢。ADR-0003 摘要子决策已定:PG `conversations.summary` 真相 + Redis 缓存,miss 读 PG 不重算,写入异步双写。无未决遗留。
