# CLAUDE.md - CodeAware 编码参考

> 本文件供 AI 编码助手参考。本项目正在从 Java 迁移到 Python，**本文档针对 Python 目标实现**；Java 源码（`ai-center-*` 模块）仅作遗留参考。
> 权威设计决策见 `docs/adr/0001~0007` + `docs/glossary.md` + `docs/Python重构迁移文档.md`。冲突时以 ADR 为准。

## 项目是什么

**CodeAware** - AI 驱动的研发效能平台。**核心域 = Chat（智能问答）**：多轮对话 + 两级记忆 + RAG 在此收敛。支撑子域 = AI 编排基建（Prompt / Memory / VectorRecall）。次要上下文 = Code Review / Unit Test / AIReadMe（复用基建的薄工具）。详见 [ADR-0007](docs/adr/0007-core-domain-and-bounded-contexts.md)。

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

## 概念区分（ubiquitous language，见 glossary）

- **Memory ≠ Knowledge**：Memory = 对话内生（短期=消息窗口+摘要；长期=捕获事实）；Knowledge = 外部上传资料。两者都喂 LLM，但起源不同（ADR-0001/0004）
- **Short-term Memory ≠ Long-term Memory**：工作记忆（近因、精确文本）vs 情景/语义记忆（相似召回）；不同机制，统一于"对话经验塑造答案"
- **Prompt 是迭代资产（版本化）vs Document 是一次性资料（upsert 替换）**（ADR-0002 vs 0005）
- **Record 是审计日志（append-only）非领域实体**（ADR-0006）

## 测试规则

- **LLM 必须 mock**（monkeypatch/fake response），CI 不调真实 DeepSeek/Ollama；真实连通性测试标 `@pytest.mark.integration` 本地跑
- 测试库隔离：独立 PG db（`ai_center_test`）+ Redis db=15；事务回滚或清表
- 核心 fixtures：`db_session`（回滚）、`redis_client`、`mock_llm`、`mock_embedder`（固定 1024 维）
- 每阶段代码与测试同步交付，测试不过不进下一阶段
- **覆盖率方针**：核心模块（rag/memory/code_review）≥80% 是**下限，不是目标**；重逻辑模块（检索融合/记忆窗口+fallback/结构化解析）深测、自然到 90%+；**不追求全局 90%**——测对的地方，不测所有地方。薄 API 层/getter/LLM 调用本身（已 mock）不强求覆盖
- 断言验证**行为**而非"不崩"；关键路径配集成测试；LLM mock 覆盖边界用例（空返回/格式错/超时）

## 常用命令

```bash
docker compose up -d                          # 起 PG/Redis/Ollama
docker exec ai-center-ollama ollama pull bge-m3
uv sync                                       # 装依赖
uv run alembic upgrade head                   # 迁移
uv run uvicorn app.main:app --reload          # 启动
uv run pytest                                 # 测试
uv run pytest --cov=app                       # 覆盖率
```

## 摘要持久化（ADR-0003 已定）

- LLM 摘要存 PG `conversations.summary`（真相）+ Redis `summary:{cid}`（缓存）
- 读：Redis 优先，miss 读 PG `conversations.summary`，**不从消息重算**（下策，避免）
- 写：命中阈值由 `BackgroundTasks` 异步生成/更新摘要，双写 Redis + PG

## DeepSeek 集成约定

- thinking 模型（deepseek-v4-flash）：结构化输出用 `with_structured_output(Schema, method="json_mode")` + `ainvoke` 回退；**勿用** `json_schema`/`function_calling`（thinking 拒强制 tool_choice / response_format）。
- agentic 多轮工具调用：每轮须完整回传 `reasoning_content`、不强制 `tool_choice`、带 `extra_body={"thinking":{"type":"enabled"}}`，否则 400。
- 非思考模式（`thinking: disabled`）为速度/严格 schema 备选，暂未启用。
- 详见 [docs/deepseek-notes.md](docs/deepseek-notes.md)。

## 参考

- 迁移蓝图：[docs/Python重构迁移文档.md](docs/Python重构迁移文档.md)
- 决策记录：[docs/adr/](docs/adr/)（0001~0007）
- 术语表：[docs/glossary.md](docs/glossary.md)
- 面试话术：[docs/面试准备指南.md](docs/面试准备指南.md)
- Java 遗留源码：`ai-center-common` / `ai-center-model` / `ai-center-ai` / `ai-center-server`
