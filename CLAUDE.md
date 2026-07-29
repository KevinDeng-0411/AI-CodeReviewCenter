# CLAUDE.md - CodeAware 编码参考

> 本文件供 AI 编码助手参考。本项目正在从 Java 迁移到 Python，**本文档针对 Python 目标实现**；Java 源码（`ai-center-*` 模块）仅作遗留参考。
> 长期领域语义以 `docs/decisions/adr/0001~0007` 和 `docs/decisions/glossary.md` 为权威；`docs/migration/Python重构迁移文档.md` 仅是历史迁移记录。当前实现以 `docs/roadmap/current-release/` 为执行权威。**编码前先查 [docs/INDEX.md](docs/INDEX.md) 定位相关文档。**
>
> 当前优先级以[升级总入口](docs/roadmap/README.md)为准：先完成[当前版本 C1–C3 收尾](docs/roadmap/current-release/README.md)。Chat → Agent 是锁定的未来方向；没有 C1–C3 evidence 和用户在其后的另行授权，不得开始 Agent 代码改造。
>
> 获得未来 Agent 实施授权后，工作另受 [Chat → Agent 渐进升级总路线](docs/roadmap/chat-to-agent/README.md)约束。实施前必须再读[公共契约](docs/roadmap/chat-to-agent/00-执行约定与公共契约.md)和当前阶段卡；一次只实施一个阶段，未形成测试、演示、回滚和证据闭环，不得进入下一阶段。
>
> 阶段完成与解锁只认[证据清单与解锁规则](docs/roadmap/证据清单与解锁规则.md)定义的 `manifest.json`。ADR 管长期语义，`current-release/` 管当前实现，`migration/` 只作历史背景；C3 之后首次 Agent 实施授权只能解锁 S1。

## Chat → Agent 阶段实施铁律

- 当前版本 C1–C3 未全部完成前，本节仅供未来参考；不得据此提前安装框架、建表或开放工具。
- 当前阶段以[总路线阶段表](docs/roadmap/chat-to-agent/README.md#4-未来唯一实施顺序)为唯一顺序，不从旧“预留项”中自行挑选功能。
- 开工前验证上一个阶段的 `evidence/Sx/manifest.json`；验证器未通过时，不实施下一阶段。
- `Conversation / Memory / AgentRun / AgentState / ToolCall / RunEvent / Artifact / Approval` 必须按公共契约分开，不混用生命周期。
- S3 只是确定性 LangGraph Workflow；S4 模型能够选择只读工具后才可称为 Agent。
- S1–S8 只证明本机单用户模式：固定 sentinel actor，`project_id` 只做数据隔离；远程身份、成员关系和 R2/R3 写能力必须等 S9-C。
- S1 前不开放工具，S6 前不做可暂停审批，S7 前不执行模型生成内容，S8 前不修改源仓库。
- 新能力必须带 feature flag 或兼容路径、明确删除阶段，并按[验收证据模板](docs/roadmap/chat-to-agent/验收证据模板.md)留档。

## 项目是什么

**CodeAware** - AI 驱动的研发效能平台。**核心域 = Chat（智能问答）**：多轮对话 + 两级记忆 + RAG 在此收敛。支撑子域 = AI 编排基建（Prompt / Memory / VectorRecall）。次要上下文 = Code Review / Unit Test / AIReadMe（复用基建的薄工具）。详见 [ADR-0007](docs/decisions/adr/0007-core-domain-and-bounded-contexts.md)。

22 个 API，4 大功能：AI Code Review（七层结构化 Prompt）、单测生成、AIReadMe 生成、智能问答。

## 技术栈（Python 目标，已确认）

- **语言**：Python 3.12
- **Web**：FastAPI（原生 async + 内置 OpenAPI `/docs`）
- **AI**：LangChain（`ChatOpenAI` 指 DeepSeek；`OllamaEmbeddings` bge-m3 1024 维）
- **ORM**：SQLAlchemy 2.0 async（asyncpg）
- **向量**：pgvector `Vector(1024)` 内联同表
- **缓存**：redis-py (async)
- **文档解析**：unstructured
- **校验/DTO**：Pydantic v2
- **配置**：pydantic-settings (.env)
- **迁移**：Alembic
- **包管理**：uv + `pyproject.toml`
- **测试**：pytest + httpx

**中间件不变**（复用 `docker-compose.yml`）：PostgreSQL 16 + pgvector / Redis 7 / Ollama bge-m3 / DeepSeek API。

## 目录结构

```
app/
├── main.py                 # FastAPI 入口
├── core/                   # config / response / exceptions
├── api/v1/                 # 7 router + deps.py
├── schemas/                # Pydantic DTO/VO
├── models/                 # SQLAlchemy ORM（8 表）
├── ai/
│   ├── config.py           # LLM/Embedding 工厂
│   ├── infra/vector_recall.py   # 共享 VectorRecallService
│   ├── services/           # code_review/unit_test/ai_readme/chat/rag/document_parser/prompt
│   ├── memory/             # short_term / long_term
│   ├── rag/                # query_rewriter / semantic_chunker / hybrid_retriever
│   └── prompt/             # template_manager
├── db/session.py
└── repositories/
```

## 领域模型（8 表，必须遵循 ADR）

| 实体 | 表 | 关键约束 | ADR |
|------|----|---------|-----|
| PromptTemplate | `prompt_templates` | 逻辑身份=type；每行=版本；**每 type 恰一 is_active**（部分唯一索引+事务）；编辑=新增版本；CHAT 纳入模板 | 0005 |
| AiOperationRecord | `ai_operation_records` | 合并 CR/UT；type 鉴别 + result + metadata JSON；**append-only 审计日志** | 0006 |
| Conversation | `conversations` | 标识 `conversation_id`（**不用 session_id**） | 0004 |
| Message | `messages` | conversation_id FK | 0004 |
| LongTermMemory | `long_term_memories` | 原子事实；`embedding Vector(1024)` 内联 | 0001 |
| Document | `documents` | 父；全文 content **只存一次** | 0002 |
| KnowledgeChunk | `knowledge_chunks` | 子；document_id FK + CASCADE；`embedding Vector(1024)` 内联 | 0002 |
| AiReadmeDocument | `ai_readme_documents` | 不变 | - |

## 编码铁律（do / don't）

- ✅ 用 `conversation_id`，**绝不**用 `session_id`（ADR-0004）
- ✅ 向量的 embed + 存储 + cosine 检索**只走 `VectorRecallService`**（ADR-0001）；Memory 和 Knowledge 都调它，不复制逻辑
- ✅ 向量**内联 `Vector(1024)`**，绝不建 UUID 反查列 / 独立 `ai_embeddings` 表（ADR-0001）
- ✅ Knowledge 写入：父 `documents` 存全文一次 + N 个 `knowledge_chunks` 各存 chunk + embedding；删除走文档级 CASCADE（ADR-0002）
- ✅ 消息：**PG 是 source of truth**，Redis 是缓存；Redis miss 必须回查 PG 重建窗口（ADR-0003）
- ✅ Prompt 激活：事务内 deactivate 同 type 其他 + activate 新版本；靠 `(type) WHERE is_active` 部分唯一索引兜底（ADR-0005）
- ✅ CHAT 系统 prompt 从 `prompt_templates` 加载并渲染占位符（`{{long_term_memory}}`/`{{rag_context}}`/`{{conversation_history}}`/`{{user_message}}`），不硬编码（ADR-0005）
- ✅ 混合检索作用在 `knowledge_chunks`：pg_trgm similarity（关键词腿）+ pgvector cosine（向量腿）+ RRF/加权融合（ADR-0001/0002）
- ✅ LLM 结构化输出用 `with_structured_output(Pydantic schema)`，不手写 JSON 正则提取（改进③）
- ✅ 全异步：async 路由 + async SQLAlchemy + async redis；SSE 用 `ChatOpenAI.astream()` + `StreamingResponse`（改进④）
- ✅ `created_at` 用 `server_default=func.now()`，不用应用层自动填充
- ✅ **端点绝不返回裸 ORM**：`Result.ok(orm_obj)` 经 Pydantic v2 序列化会抛 `PydanticSerializationError`；router 层投影成 dict（或 `Schema.model_validate(orm)`）。`AiOperationRecord` 用共享 `record_to_dict`（ORM `meta` -> 对外 `metadata`，规避 `DeclarativeBase.metadata` 冲突）。见 [testing-notes §5](docs/migration/testing-notes.md)

## 概念区分（ubiquitous language，见 glossary）

- **Memory ≠ Knowledge**：Memory = 对话内生（短期=消息窗口+摘要；长期=捕获事实）；Knowledge = 外部上传资料。两者都喂 LLM，但起源不同（ADR-0001/0004）
- **Short-term Memory ≠ Long-term Memory**：工作记忆（近因、精确文本）vs 情景/语义记忆（相似召回）；不同机制，统一于"对话经验塑造答案"
- **Prompt 是迭代资产（版本化）vs Document 是一次性资料（upsert 替换）**（ADR-0002 vs 0005）
- **Record 是审计日志（append-only）非领域实体**（ADR-0006）

## 测试规则

- **当前安全警告**：C1 完成前禁止直接运行 pytest。现有 `tests/conftest.py` 使用环境变量 `setdefault` 后会执行 `drop_all` 和 Redis `flushdb`，若调用者已导出开发库配置会破坏数据。C1 必须先交付 fail-closed 的 `scripts/run_tests_safe.py`。
- **LLM 必须 mock**（monkeypatch/fake response），CI 不调真实 DeepSeek/Ollama；真实连通性测试标 `@pytest.mark.integration` 本地跑
- 测试库隔离：每次运行使用带唯一后缀的一次性 PG db（含独立迁移测试库）+ 非 0 的测试专用 Redis DB；安全执行器必须拒绝开发库 `ai_center` / `ai_center_py`
- 核心 fixtures：`db_session`（回滚）、`redis_client`、`mock_llm`、`mock_embedder`（固定 1024 维）
- 每阶段代码与测试同步交付，测试不过不进下一阶段
- **覆盖率方针**：核心模块（rag/memory/code_review）≥80% 是**下限，不是目标**；重逻辑模块（检索融合/记忆窗口+fallback/结构化解析）深测、自然到 90%+；**不追求全局 90%**——测对的地方，不测所有地方。薄 API 层/getter/LLM 调用本身（已 mock）不强求覆盖
- 断言验证**行为**而非"不崩"；关键路径配集成测试；LLM mock 覆盖边界用例（空返回/格式错/超时）
- 测试/集成踩坑见 [docs/migration/testing-notes.md](docs/migration/testing-notes.md)（langchain 导入 hang、test_migration 性能、异步客户端 loop）

## 常用命令

> 下列是 C1 完成后的目标命令。当前 fresh volume 存在 `ai_center` / `ai_center_py` 库名失配，C1 前不得把这段当作已验证启动流程；不要删除用户 volume。后端测试同样必须等待 C1 的 safe runner。

```bash
docker compose up -d                          # 从仓库根起 PG/Redis/Ollama
docker exec ai-center-ollama ollama pull bge-m3
(cd codeaware-py && uv sync)                  # 装后端依赖
(cd codeaware-py && uv run alembic upgrade head)
(cd codeaware-py && uv run uvicorn app.main:app --reload)
# C1 交付安全执行器后才可运行：
(cd codeaware-py && uv run python scripts/run_tests_safe.py -q)
(cd codeaware-py && uv run python scripts/run_tests_safe.py --cov=app)
(cd codeaware-py/frontend && npm run lint && npm run build)
```

## 摘要持久化（ADR-0003 已定）

- LLM 摘要存 PG `conversations.summary`（真相）+ Redis `summary:{cid}`（缓存）
- 读：Redis 优先，miss 读 PG `conversations.summary`，**不从消息重算**（下策，避免）
- 写：按 current-release C1 在 assistant 消息持久化后执行可观测的 inline post-turn；摘要/记忆完成后才发 `chat.completed`。不得把请求级 `AsyncSession` 传入 `BackgroundTasks`。

## DeepSeek 集成约定

- thinking 模型（deepseek-v4-flash）：结构化输出用 `with_structured_output(Schema, method="json_mode")` + `ainvoke` 回退；**勿用** `function_calling`（thinking 拒强制 tool_choice）与 `json_schema`（DeepSeek 通用限制，两模式均不可用）。
- agentic 多轮工具调用（thinking）：每轮须完整回传 `reasoning_content`、不强制 `tool_choice`、带 `extra_body={"thinking":{"type":"enabled"}}`，否则 400。
- 非思考模式（`thinking: disabled`）：解除强制 tool_choice -> `function_calling` 可用（已实测，比 json_mode schema 更严）；无 reasoning_content 回传。S4 首个只读工具 Agent 固定采用该模式，thinking 工具循环推迟到 durable state 建成后再评估。
- 详见 [docs/integration/deepseek-notes.md](docs/integration/deepseek-notes.md)。

## 参考

- 文档索引（编码先查）：[docs/INDEX.md](docs/INDEX.md)
- 迁移蓝图：[docs/migration/Python重构迁移文档.md](docs/migration/Python重构迁移文档.md)
- 决策记录：[docs/decisions/adr/](docs/decisions/adr/)（0001~0007）
- 术语表：[docs/decisions/glossary.md](docs/decisions/glossary.md)
- DeepSeek 集成：[docs/integration/deepseek-notes.md](docs/integration/deepseek-notes.md)
- 面试话术：[docs/interview/面试准备指南.md](docs/interview/面试准备指南.md)
- Java 遗留源码：`ai-center-common` / `ai-center-model` / `ai-center-ai` / `ai-center-server`
