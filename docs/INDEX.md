# 文档索引（INDEX）

> **编码前先查此索引**：按功能/编码场景定位相关文档与章节，再按指引阅读。
> 文档按关注点分目录：`roadmap/`（渐进升级执行卡）、`migration/`（迁移蓝图）、`decisions/`（ADR + 术语表）、`integration/`（外部集成）、`interview/`（面试）。

## 如何用

1. 要编码某功能 -> 在下表查「功能」行 -> 读对应 ADR 与当前执行卡。
2. ADR 负责长期语义；`current-release/` 负责当前 C1–C3 实施；`migration/` 只作迁移历史与背景。
3. 当前先按[升级总入口](roadmap/README.md)完成 C1–C3；只有[机器可校验证据](roadmap/证据清单与解锁规则.md)可以改变阶段状态。
4. Chat → Agent 是锁定的未来方向；C3 后仍需用户逐阶段另行授权，才按[未来路线](roadmap/chat-to-agent/README.md)实施。
5. 编码铁律、技术栈、目录结构见根目录 `CLAUDE.md`。

## 功能 -> 文档映射

| 功能 / 编码场景 | ADR | 迁移文档章节 | 其他 |
|---|---|---|---|
| 总览 / 核心域=Chat | [ADR-0007](decisions/adr/0007-core-domain-and-bounded-contexts.md) | §1 §9 | [术语表](decisions/glossary.md) |
| 迁移路线图 / 阶段验收 | - | [§6 路线图](migration/Python重构迁移文档.md) · §11 清单 | - |
| 后续升级 / 缺口与预留 | - | [后续升级计划](migration/后续升级计划.md) | - |
| 当前版本必须完成 | [ADR-0001~0007](decisions/adr/) | - | [当前版本 C1–C3](roadmap/current-release/README.md) · [证据模板](roadmap/current-release/验收证据模板.md) |
| 阶段解锁 / 机器可校验证据 | - | - | [证据清单与解锁规则](roadmap/证据清单与解锁规则.md) |
| Chat → Agent 渐进升级（未来、锁定） | [ADR-0007](decisions/adr/0007-core-domain-and-bounded-contexts.md) | - | [未来路线与阶段实施卡](roadmap/chat-to-agent/README.md) · [公共契约](roadmap/chat-to-agent/00-执行约定与公共契约.md) |
| 技术选型 / AI 搜索 / Agent 能力地图 | [ADR-0007](decisions/adr/0007-core-domain-and-bounded-contexts.md) | - | [技术选型与能力地图](roadmap/技术选型与能力地图.md) |
| Agent Run / Tool / Artifact / Approval / SSE 事件 | - | - | [公共契约](roadmap/chat-to-agent/00-执行约定与公共契约.md) |
| 阶段闭环 / 演示 / 验收证据 | - | - | [统一规则](roadmap/证据清单与解锁规则.md) · [当前模板](roadmap/current-release/验收证据模板.md) · [Agent 模板](roadmap/chat-to-agent/验收证据模板.md) |
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
| [roadmap/README.md](roadmap/README.md) | 升级总入口：先当前版本，后未来 Agent；含硬门禁和文档权威边界 |
| [roadmap/技术选型与能力地图.md](roadmap/技术选型与能力地图.md) | 当前保留/新增技术、搜索/RAG 与 Agent 能力差距、未来选型触发条件 |
| [roadmap/模型实施任务模板.md](roadmap/模型实施任务模板.md) | 可直接交给其他编码模型的单阶段实施/只读评审任务模板 |
| [roadmap/证据清单与解锁规则.md](roadmap/证据清单与解锁规则.md) | manifest、产物哈希、安全测试、回退边界与逐阶段授权规则 |
| [roadmap/current-release/README.md](roadmap/current-release/README.md) | 当前必须实施的 C1 缺口修复、C2 七域闭环、C3 版本冻结 |
| [roadmap/current-release/01-当前缺口修复.md](roadmap/current-release/01-当前缺口修复.md) | 修复 typed SSE、摘要、multipart、空环境和真实 AIReadMe |
| [roadmap/current-release/02-现有功能闭环验收.md](roadmap/current-release/02-现有功能闭环验收.md) | 现有 7 个功能域的契约、测试、持久化和 UI 演示闭环 |
| [roadmap/current-release/03-版本冻结与交接.md](roadmap/current-release/03-版本冻结与交接.md) | 文档/OpenAPI/配置校准、空环境复现、指标与 Agent 解锁条件 |
| [roadmap/current-release/验收证据模板.md](roadmap/current-release/验收证据模板.md) | 当前版本每阶段必须提交的验收证据 |
| [roadmap/chat-to-agent/README.md](roadmap/chat-to-agent/README.md) | 锁定的未来 Chat → Agent 顺序、阶段依赖、门禁与完成标准 |
| [roadmap/chat-to-agent/00-执行约定与公共契约.md](roadmap/chat-to-agent/00-执行约定与公共契约.md) | Conversation / Run / Tool / Event / Artifact / Approval 的跨阶段稳定契约 |
| [roadmap/chat-to-agent/01-稳定Chat基线.md](roadmap/chat-to-agent/01-稳定Chat基线.md) | 当前 Chat 基线技术附录；实施以 current-release/C1 为唯一来源 |
| [roadmap/chat-to-agent/02-项目作用域隔离.md](roadmap/chat-to-agent/02-项目作用域隔离.md) | S1：项目模型、数据回填、API 上下文与跨项目隔离 |
| [roadmap/chat-to-agent/03-Graph前分层重构.md](roadmap/chat-to-agent/03-Graph前分层重构.md) | S2：行为等价地拆分 repository、context、model gateway 与 post-turn |
| [roadmap/chat-to-agent/04-确定性LangGraph.md](roadmap/chat-to-agent/04-确定性LangGraph.md) | S3：双运行时对照的确定性 Workflow，不宣称 Agent |
| [roadmap/chat-to-agent/05-只读工具Agent.md](roadmap/chat-to-agent/05-只读工具Agent.md) | S4：受预算约束的只读工具选择、事件与引用 |
| [roadmap/chat-to-agent/06-仓库感知Agent.md](roadmap/chat-to-agent/06-仓库感知Agent.md) | S5：安全源码索引、代码检索工具和可定位引用 |
| [roadmap/chat-to-agent/07-可恢复AgentRun.md](roadmap/chat-to-agent/07-可恢复AgentRun.md) | S6：持久 Run、队列 Worker、检查点、回放和故障恢复 |
| [roadmap/chat-to-agent/08-沙箱补丁Agent.md](roadmap/chat-to-agent/08-沙箱补丁Agent.md) | S7：安全物化源码快照、补丁产物和独立受限验证 |
| [roadmap/chat-to-agent/09-审批式行动Agent.md](roadmap/chat-to-agent/09-审批式行动Agent.md) | S8：精确审批、受控本地分支与提交 |
| [roadmap/chat-to-agent/10-生态集成与多Agent.md](roadmap/chat-to-agent/10-生态集成与多Agent.md) | S9：按指标触发的 Git、MCP、远程身份与多 Agent 扩展 |
| [roadmap/chat-to-agent/验收证据模板.md](roadmap/chat-to-agent/验收证据模板.md) | 每阶段必须提交的测试、演示、指标、回滚和交接证据模板 |
| [migration/Python重构迁移文档.md](migration/Python重构迁移文档.md) | Java → Python 历史迁移记录（含 ADR 索引；不再直接下发任务） |
| [migration/testing-notes.md](migration/testing-notes.md) | 测试与集成踩坑留痕（langchain 导入 hang / test_migration 性能 / 异步客户端 loop） |
| [migration/后续升级计划.md](migration/后续升级计划.md) | 计划内缺口（摘要接入·首要）+ 可升级预留项（后端分层重构·U1前置 / LangGraph / 语义切分 / tsvector / Pinecone / 数据归并） |
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
