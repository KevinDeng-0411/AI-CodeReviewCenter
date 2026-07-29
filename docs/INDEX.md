# 文档索引（INDEX）

> **编码前先查此索引**：按功能/编码场景定位相关文档与章节，再按指引阅读。
> 文档按关注点分目录：`migration/`（迁移蓝图）、`decisions/`（ADR + 术语表）、`integration/`（外部集成）、`interview/`（面试）。

## 如何用

1. 要编码某功能 -> 在下表查「功能」行 -> 读对应 **ADR**（权威决策）+ **迁移文档章节**（可执行蓝图）。
2. ADR 与迁移文档冲突时，**以 ADR 为准**。
3. 编码铁律、技术栈、目录结构见根目录 `CLAUDE.md`。

## 功能 -> 文档映射

| 功能 / 编码场景 | ADR | 迁移文档章节 | 其他 |
|---|---|---|---|
| 总览 / 核心域=Chat | [ADR-0007](decisions/adr/0007-core-domain-and-bounded-contexts.md) | §1 §9 | [术语表](decisions/glossary.md) |
| 迁移路线图 / 阶段验收 | - | [§6 路线图](migration/Python重构迁移文档.md) · §11 清单 | - |
| 后续升级 / 缺口与预留 | - | [后续升级计划](migration/后续升级计划.md) | - |
| 数据模型（8 表） | 0001 / 0002 / 0004 / 0005 / 0006 | §7.2.2 | - |
| 向量召回基建 VectorRecallService | [0001](decisions/adr/0001-memory-vs-knowledge-two-tables-shared-recall.md) | §7.3 | - |
| 短期记忆（滑窗+摘要+PG fallback） | [0003](decisions/adr/0003-message-store-pg-source-of-truth.md) · [0004](decisions/adr/0004-memory-concept-and-conversation-naming.md) | §7.6 | - |
| 长期记忆（内联向量召回） | [0001](decisions/adr/0001-memory-vs-knowledge-two-tables-shared-recall.md) · [0004](decisions/adr/0004-memory-concept-and-conversation-naming.md) | §7.7 | - |
| Knowledge / RAG（父子表+混合检索） | [0001](decisions/adr/0001-memory-vs-knowledge-two-tables-shared-recall.md) · [0002](decisions/adr/0002-knowledge-document-parent-child.md) | §7.2.2 · §7.5 | - |
| Conversation / Chat（SSE+CHAT 模板） | [0004](decisions/adr/0004-memory-concept-and-conversation-naming.md) | §7.8 | - |
| Code Review（结构化输出） | [0005](decisions/adr/0005-prompttemplate-versioning-activation-chat.md) · [0006](decisions/adr/0006-records-audit-log-merge.md) | §7.4 · §7.11 | - |
| Prompt 模板（版本化+激活） | [0005](decisions/adr/0005-prompttemplate-versioning-activation-chat.md) | §7.11 | - |
| Records（审计日志合并） | [0006](decisions/adr/0006-records-audit-log-merge.md) | §7.2.2 | - |
| 单测生成 / AIReadMe | - | §7.4（流程同 CR） | - |
| DeepSeek / LLM 集成 | - | - | [deepseek-notes](integration/deepseek-notes.md) |
| 测试策略 / 覆盖率方针 | - | §6.2 · §6.3 | `CLAUDE.md` 测试规则 · [testing-notes](migration/testing-notes.md) |
| 面试话术 | - | §9 | [面试准备指南](interview/面试准备指南.md) |

## 文档清单

| 路径 | 内容 |
|------|------|
| [migration/Python重构迁移文档.md](migration/Python重构迁移文档.md) | Java->Python 迁移蓝图（唯一，含 ADR 索引 §0.1） |
| [migration/testing-notes.md](migration/testing-notes.md) | 测试与集成踩坑留痕（langchain 导入 hang / test_migration 性能 / 异步客户端 loop） |
| [migration/后续升级计划.md](migration/后续升级计划.md) | 计划内缺口（摘要接入·首要）+ 可升级预留项（LangGraph/语义切分/tsvector/Pinecone/数据归并） |
| [decisions/adr/](decisions/adr/) | 7 份架构决策记录 0001~0007 |
| [decisions/glossary.md](decisions/glossary.md) | 领域术语表（10 术语全 settled） |
| [integration/deepseek-notes.md](integration/deepseek-notes.md) | DeepSeek thinking/非思考模式集成约定 |
| [interview/面试准备指南.md](interview/面试准备指南.md) | 面试讲解与追问话术 |

## ADR 速查

| ADR | 决策 |
|-----|------|
| [0001](decisions/adr/0001-memory-vs-knowledge-two-tables-shared-recall.md) | Memory/Knowledge 分表 + 共享 VectorRecallService |
| [0002](decisions/adr/0002-knowledge-document-parent-child.md) | Knowledge 拆 documents+knowledge_chunks 父子表 |
| [0003](decisions/adr/0003-message-store-pg-source-of-truth.md) | 消息 PG 真相源 + Redis 缓存 + fallback + 摘要持久化 |
| [0004](decisions/adr/0004-memory-concept-and-conversation-naming.md) | Memory 紧定义 + conversation_id 命名 |
| [0005](decisions/adr/0005-prompttemplate-versioning-activation-chat.md) | PromptTemplate 版本化 + 每 type 恰一激活 + CHAT 纳入模板 |
| [0006](decisions/adr/0006-records-audit-log-merge.md) | Record=审计日志 + CR/UT 合并 ai_operation_records |
| [0007](decisions/adr/0007-core-domain-and-bounded-contexts.md) | 核心域=Chat，基建支撑子域，工具次要上下文 |
