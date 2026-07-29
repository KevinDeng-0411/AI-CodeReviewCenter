# CodeAware - Java -> Python 重构迁移文档

> **文档先行**：本文件是后续按优先级逐步实现迁移的**唯一蓝图**。每个阶段自洽，可逐阶段交付、逐阶段验证。
>
> 中间件保持不变：PostgreSQL 16 + pgvector / Redis 7 / Ollama bge-m3 / DeepSeek API / `docker-compose.yml` 原样复用，**只重写应用层**。
>
> 本文档已与 `docs/decisions/adr/` 的 7 份架构决策记录对齐（见 §0.1 索引）。ADR 是权威，本文档为可执行蓝图；二者冲突以 ADR 为准。

---

## 0. 已确认选型

| 维度 | 决策 |
|------|------|
| ORM | **SQLAlchemy 2.0 async**（asyncpg 驱动） |
| AI 框架 | **统一 LangChain (Python)**；LangGraph 编排为预留演进，本次迁移不实现 |
| Web | FastAPI |
| 向量存储 | pgvector SQLAlchemy 类型，**内联同表** |
| 包管理 | uv + `pyproject.toml` |

### 0.1 ADR 索引（grilling 产出，权威决策）

| ADR | 决策 | 影响章节 |
|-----|------|---------|
| [0001](../decisions/adr/0001-memory-vs-knowledge-two-tables-shared-recall.md) | Memory/Knowledge 分表（结构差异）+ **共享 VectorRecallService** | §3 §7.3 §7.5 §7.7 |
| [0002](../decisions/adr/0002-knowledge-document-parent-child.md) | Knowledge 拆 `documents`+`knowledge_chunks` 父子表 | §3.5 §7.2.2 |
| [0003](../decisions/adr/0003-message-store-pg-source-of-truth.md) | 消息 **PG 真相源 + Redis 缓存 + fallback 读** | §3.5 §7.6 |
| [0004](../decisions/adr/0004-memory-concept-and-conversation-naming.md) | Memory 紧定义 + 统一 **`conversation_id`**（清除 session） | §7.4 §7.6 §7.7 §7.8 |
| [0005](../decisions/adr/0005-prompttemplate-versioning-activation-chat.md) | PromptTemplate **版本化 + 每 type 恰一激活 + CHAT 纳入模板** | §3.5 §7.4 §7.11(新) |
| [0006](../decisions/adr/0006-records-audit-log-merge.md) | Record=审计日志 + CR/UT **合并 `ai_operation_records`** | §3.5 §7.2.2 |
| [0007](../decisions/adr/0007-core-domain-and-bounded-contexts.md) | **核心域=Chat**，基建为支撑子域，工具为次要上下文 | §9 |

---

## 1. 现状分析（迁移起点）

### 1.1 Java 技术栈
Spring Boot 3.2.5 · LangChain4j 0.36.2 · MyBatis-Plus 3.5.5 · PostgreSQL/pgvector · Redis 7 · Ollama bge-m3 · DeepSeek V4 · Tika · Knife4j · Hutool/Lombok/Jackson。

### 1.2 模块结构（Maven 四模块）
- `ai-center-common`：`Result`/`PageResult`、枚举、`BusinessException`
- `ai-center-model`：Entity / DTO / VO / Mapper（MyBatis-Plus）
- `ai-center-ai`：`AIConfig` + service + memory + prompt + rag
- `ai-center-server`：Controller + 配置 + 启动类

### 1.3 功能与 API 规模
22 个 API，4 大模块：AI Code Review（七层结构化 Prompt）、AI 单测生成、AIReadMe 生成、智能问答（多轮 + 两级记忆 + RAG）。

### 1.4 关键实现定位（迁移时对照源码）
| 组件 | 源文件 | 职责 |
|------|--------|------|
| AI Bean 工厂 | `ai/.../config/AIConfig.java` | LLM/Embedding/VectorStore Bean |
| 代码评审 | `ai/.../service/CodeReviewService.java` | 模板渲染->LLM->JSON 解析->持久化 |
| 短期记忆 | `ai/.../memory/ShortTermMemoryManager.java` | Redis 滑窗 + LLM 摘要 + PG 持久化 |
| 长期记忆 | `ai/.../memory/LongTermMemoryManager.java` | pgvector + UUID 反向索引 |
| 混合检索 | `ai/.../rag/HybridRetriever.java` | 内存伪 BM25 + 向量 |
| 查询重写/分块 | `ai/.../rag/QueryRewriter.java` `SemanticChunker.java` | 改写变体 / Markdown 感知分块 |
| RAG 服务 | `ai/.../service/RagService.java` | 重写->分块->检索->注入 |
| 对话服务 | `ai/.../service/ChatService.java` | 三级整合 + SSE 流式 |
| 全局异常 | `server/.../config/GlobalExceptionHandler.java` | `@RestControllerAdvice` |
| 表结构 | `server/.../resources/db/init.sql` | 8 张表 + 预置 Prompt |

---

## 2. 目标技术栈选型

| 层级 | Java 现状 | Python 目标 | 说明 |
|------|-----------|-------------|------|
| 语言 | Java 17 | **Python 3.12** | |
| Web | Spring Boot 3 | **FastAPI** | AI 应用事实标准，原生 async + 内置 OpenAPI |
| AI 框架 | LangChain4j 0.36 | **LangChain** | 与 LangChain4j 1:1 对称，面试认知度最高 |
| LLM | OpenAiChatModel(DeepSeek) | `ChatOpenAI`(base_url=DeepSeek) | OpenAI 兼容，零成本 |
| Embedding | OllamaEmbeddingModel | `OllamaEmbeddings`(bge-m3, 1024-d) | 不变 |
| 向量存储 | PgVectorEmbeddingStore(独立表+UUID反查) | **pgvector `Vector` 类型，内联同表** | 改进点① |
| 关键词检索 | 内存伪 BM25（全量扫描） | **PG `pg_trgm` / `tsvector`** | 改进点② |
| ORM | MyBatis-Plus | **SQLAlchemy 2.0 async** | asyncpg |
| 缓存 | StringRedisTemplate | **redis-py (async)** | |
| 文档解析 | Apache Tika | **unstructured**(+ pypdf/python-docx 兜底) | |
| 校验/DTO | Java DTO + Hutool JSON | **Pydantic v2** | DTO/VO/校验一体 |
| 配置 | application.yml + @ConfigurationProperties | **pydantic-settings (.env)** | 类型安全 |
| API 文档 | Knife4j | **FastAPI 内置 /docs** | 零依赖 |
| 迁移 | 无 | **Alembic** | |
| 包管理 | Maven | **uv + pyproject.toml** | |
| 测试 | JUnit | **pytest + httpx** | |

---

## 3. 架构改进点（迁移最大价值 / 面试核心卖点）

### ① 内联 pgvector，消除 UUID 反向索引
Java 版因 LangChain4j 的 `PgVectorEmbeddingStore` 自管 `ai_embeddings` 表，关系表只能在 `embedding` 列存 UUID 反查（`LongTermMemoryManager.java:50-55`、`init.sql:91/106`）。
Python 用 `pgvector` 的 `Vector` 类型把向量**直接存进 `knowledge_chunks` / `long_term_memories` 同表**：增删查、来源追溯一步到位，少一张表、少一层 UUID 间接。（ADR-0001）

### ② 原生关键词检索下沉到 PG
Java 版 `HybridRetriever.java:66` `selectList(null)` 全量加载到内存算 TF-IDF 变体，**不可扩展**。
Python 把关键词腿下沉到 PG：
- 默认 `pg_trgm` `similarity()`：无需分词扩展，对中文友好，开箱即用；
- 生产可升级 `tsvector` + `zhparser`：真 BM25 排序。
向量腿用 pgvector `<=>`（cosine distance）。融合用 **RRF（Reciprocal Rank Fusion）** 或加权求和（保留 0.3/0.7）。

### ③ 结构化输出替代手写 JSON 提取
Java 版 `CodeReviewService.java:172` 用正则 `extractJson` 兜底 markdown 代码块。
Python 用 LangChain `with_structured_output(Pydantic schema)`，LLM 直接返回强类型对象，解析鲁棒性大幅提升。`QueryRewriter` 同理（替换 `QueryRewriter.java:52` 手写 JSON 数组切分）。

### ④ 全异步 + 原生 SSE 流式
FastAPI + asyncpg + async redis，LLM I/O 密集场景并发优势明显；`ChatOpenAI.astream()` + `StreamingResponse` 替代 `StreamingChatResponseHandler` 回调。另：Java 版 `generateSummaryAsync` 名为异步实为同步（`ShortTermMemoryManager.java:127` 在调用栈内执行），Python 用 `BackgroundTasks` 真异步。

### 3.5 grilling 审出的设计修正（ADR 驱动，迁移时一并修正）

> 以下不是"原 Java 没做好"，而是迁移时**借机修正**的建模/实现问题，每条对应一份 ADR，面试时是"我真审过、真改过"的弹药：

| 问题（Java 现状） | 修正（Python） | ADR |
|------|------|-----|
| Knowledge 全文按 chunk 重复存 + 删文档只删一个 chunk + 无文档身份（`RagService.java:49/99`） | 拆 `documents` 父表 + `knowledge_chunks` 子表，全文存一次，文档级增删/去重 | 0002 |
| 消息"PG 持久化"只写不读，Redis TTL 到期历史即空（`ShortTermMemoryManager.java:160` 写、读路径只读 Redis） | **PG 真相源 + Redis 缓存 + miss 回查 PG 重建窗口** | 0003 |
| Memory/Knowledge 的 embed+store+recall 各抄一遍 | 抽 **共享 `VectorRecallService`**，两者薄表调用 | 0001 |
| Prompt 激活非确定性（`refreshCache` last-wins 无 ORDER BY）+ 死分支（`getActiveTemplateByName(type,null)`）+ 幽灵 `version` 列 + CHAT prompt 硬编码空壳 | PromptTemplate **版本化（每行=版本）+ 每 type 恰一激活（部分唯一索引+事务）+ CHAT 纳入模板** | 0005 |
| CR/UT 两张记录表无结构差异却分表（违反自己的分表原则） | 合并 `ai_operation_records`（type 鉴别 + result + metadata JSON） | 0006 |
| `session_id` / `ChatConversation` / `/conversations` 同一概念三套名 | 领域统一 **`conversation_id`**，清除 session | 0004 |
| "研发效能中台"营销词掩盖领域结构 | 明确**核心域=Chat**，基建为支撑子域，工具为次要上下文 | 0007 |

---

## 4. 目录结构设计

```
codeaware-py/
├── pyproject.toml              # uv 依赖
├── docker-compose.yml          # 复用（PG/Redis/Ollama 不变）
├── .env.example
├── alembic/                    # 由 init.sql 转换的迁移
├── app/
│   ├── main.py                 # FastAPI 入口 + 异常注册 + 路由挂载
│   ├── core/
│   │   ├── config.py           # pydantic-settings（替代 application.yml）
│   │   ├── response.py         # Result / PageResult
│   │   └── exceptions.py       # BusinessException + handler
│   ├── api/v1/                 # 7 个 router（对应 7 controller）
│   │   ├── code_review.py  unit_test.py  ai_readme.py  chat.py
│   │   ├── knowledge.py    memory.py     prompt.py
│   │   └── deps.py             # Depends 依赖注入（db/redis/llm/...）
│   ├── schemas/                # Pydantic DTO/VO（替代 model 模块）
│   ├── models/                 # SQLAlchemy ORM（8 表，含内联 Vector）
│   ├── ai/
│   │   ├── config.py           # LLM/Embedding 工厂
│   │   ├── infra/
│   │   │   └── vector_recall.py # 共享 VectorRecallService（ADR-0001）
│   │   ├── services/           # code_review/unit_test/ai_readme/chat/rag/document_parser/prompt
│   │   ├── memory/             # short_term / long_term
│   │   ├── rag/                # query_rewriter / semantic_chunker / hybrid_retriever
│   │   └── prompt/             # template_manager（版本化+激活，ADR-0005）
│   ├── db/session.py           # async engine/session
│   └── repositories/           # 可选数据访问层（替代 Mapper）
└── tests/
```

**模块映射**：`common -> core` · `model -> schemas + models`（Mapper 消融，SQLAlchemy 即 mapper）· `ai -> ai` · `server -> api + main`。

---

## 5. 模块映射总表

| Java 组件 | Python 对应 | 说明 |
|-----------|-------------|------|
| `Result`/`PageResult` | `core/response.py` | 统一响应 `{code,data,msg}` |
| 枚举（PromptType/SeverityLevel/...） | `core/enums.py`(Enum) | |
| `BusinessException` + `@RestControllerAdvice` | `core/exceptions.py` + `@app.exception_handler` | |
| Entity（8 个） | `models/*.py`(SQLAlchemy) | 表集合见 §7.2.2（与 Java 不同：合并 CR/UT、拆分 Knowledge） |
| DTO/VO | `schemas/*.py`(Pydantic v2) | |
| Mapper（11 接口） | SQLAlchemy `select()` / `repositories/` | |
| `MyMetaObjectHandler`(自动 created_at) | `server_default=func.now()` | |
| `MybatisPlusConfig`(分页插件) | 手动 `limit/offset` 或 fastapi-pagination | |
| `AIConfig` Bean | `ai/config.py` 工厂(`lru_cache`) | |
| **(新) embed+store+recall 复制逻辑** | `ai/infra/vector_recall.py` | 共享 `VectorRecallService`（ADR-0001） |
| `CodeReviewService` | `ai/services/code_review.py` | + `with_structured_output` + 版本化 prompt |
| `ShortTermMemoryManager` | `ai/memory/short_term.py` | redis async + `BackgroundTasks` + **PG fallback 读**(ADR-0003) |
| `LongTermMemoryManager` | `ai/memory/long_term.py` | 内联 pgvector，调 VectorRecallService |
| `HybridRetriever` | `ai/rag/hybrid_retriever.py` | pg_trgm + pgvector + RRF，作用在 `knowledge_chunks` |
| `QueryRewriter` | `ai/rag/query_rewriter.py` | + 结构化输出 |
| `SemanticChunker` | `ai/rag/semantic_chunker.py` | unstructured `chunk_by_title`(默认) + 语义切分(预留升级) |
| `RagService` | `ai/services/rag.py` | 写 `documents`+`knowledge_chunks`(ADR-0002) |
| `ChatService` | `ai/services/chat.py` | `astream` + `StreamingResponse`；CHAT prompt 走模板(ADR-0005)；`conversation_id`(ADR-0004) |
| `DocumentParserService`(Tika) | `ai/services/document_parser.py` | `unstructured` |
| `PromptTemplateManager`/`PromptService` | `ai/prompt/template_manager.py` + `api/v1/prompt.py` | 版本化+激活(ADR-0005) |
| `code_review_records`+`unit_test_records` | `models/ai_operation_record.py` | 合并(ADR-0006) |
| `knowledge_documents` | `models/document.py`+`models/knowledge_chunk.py` | 父子拆分(ADR-0002) |
| `chat_conversations`/`chat_messages` | `models/conversation.py`/`models/message.py` | `conversation_id`(ADR-0004) |
| Controller（7 个） | `api/v1/*.py`(APIRouter) | |
| `RedisConfig` | `db/` 下 redis async client | |
| `Knife4jConfig` | 无需（FastAPI 内置） | |
| application.yml | `core/config.py`(.env) | |
| `AiCenterApplication` | `main.py`(uvicorn) | |

---

## 6. 分阶段迁移路线图（按优先级）

> 每阶段独立可验证。建议每完成一阶段对照本节"验收标准"做 curl 冒烟。

| 阶段 | 内容 | 本阶段测试 | 验收标准 | 工期 |
|------|------|-----------|----------|------|
| **P0 骨架** | uv 工程、FastAPI 骨架、core(config/response/exceptions)、db/session、复用 compose | `test_health` `test_response` `test_exception_handler` | `GET /health` 200；统一响应；异常兜底 | 1–2d |
| **P1 数据层** | 8 表 SQLAlchemy 模型（内联 pgvector、父子拆分、记录合并）、Alembic、Pydantic schemas、基础 CRUD | `test_models` `test_migration` `test_crud` `test_pgvector_column` | 表结构与 ADR 一致；迁移可 up/down | 2–3d |
| **P2 AI 基建** | `ai/config.py` + **`VectorRecallService`**(ADR-0001)：ChatOpenAI+OllamaEmbeddings+共享召回；连通性自测 | `test_llm_connect`(mock) `test_embedding_dim`(1024) `test_vector_recall` | 三大模型可调通；VectorRecallService 可存取 | 1–2d |
| **P3 核心 AI 服务** | 见 6.1 子优先级 | 见 6.3 各子项 | 7 类 AI 能力单测可跑 | 4–6d |
| **P4 API 层** | 7 router + Depends + SSE 端点 | `test_api_*`（22 端点契约，对照 README curl） | 22 个 API 全通，curl 对齐 Java 版 | 2–3d |
| **P5 端到端** | 双端对比、覆盖率、README+话术更新 | e2e 冒烟脚本；覆盖率报告 | 双端行为一致；话术升级 | 2–3d |

> **原则：每阶段代码与测试同步交付，测试不过不进入下一阶段。** 测试分层与 fixtures 见 6.2，各阶段测试用例见 6.3。

### 6.1 P3 子优先级（先做面试最能讲的）
1. `PromptTemplateManager`（版本化+激活，ADR-0005）+ `CodeReviewService`（七层 Prompt 主打 + 改进③）
2. `ShortTermMemoryManager`（PG fallback，ADR-0003）-> `LongTermMemoryManager`（内联 pgvector，ADR-0001）
3. `SemanticChunker`（unstructured `chunk_by_title` 500/50；语义切分预留）+ `QueryRewriter` + `HybridRetriever`（改进②）
4. `RagService`（父子表，ADR-0002）-> `ChatService`（三级整合 + SSE + CHAT 模板，改进④）
5. `UnitTestService` / `AiReadmeService` / `DocumentParserService`(unstructured) / `PromptService`（薄壳，复制 CR 模式，低优先）

> 总计约 2–3 周（业余时间）。
>
> **本次迁移范围**:P0–P5 交付功能基线(Chat 功能基线 + 薄工具);LangGraph/Agent 编排等 Chat 工程深度加深为**预留,不在本次迁移**(见 [ADR-0007](../decisions/adr/0007-core-domain-and-bounded-contexts.md) 决策点 4)。
>
> **分块策略(P3-3,已定)**:`unstructured` 解析 -> `chunk_by_title(elements, max_characters=500, overlap=50)`。按 title 元素切(结构感知)+ 控大小 + overlap,**格式无关**(PDF/Word/HTML/Markdown 通吃),parse+chunk 一库完成。仅作用于 Knowledge 文档(ADR-0002);Long-term Memory 原子不分块(ADR-0001)。
>
> **预留升级**:若**无结构流水文本**检索质量差,改用 LangChain `SemanticChunker`(按相邻句向量相似度断点切)。结构化团队文档默认 `chunk_by_title` 边际收益最高;语义切分成本/复杂度高(每句算向量、变长块、调阈值),条件触发,不在本次迁移实现。

### 6.2 测试策略与分层

- **三层测试**：unit（mock LLM/DB）-> integration（真实 PG/Redis）-> e2e（双端 curl 对比）。
- **LLM 必须 mock**：CI 不调真实 DeepSeek/Ollama。用 monkeypatch / fake response 固定 LLM 输出，验证**解析与流程逻辑**（这才是迁移要保证的）；真实连通性测试标 `@pytest.mark.integration`，本地按需跑。
- **测试库隔离**：独立 PG database（如 `ai_center_test`）+ 专属 Redis db（如 db=15）；每个测试函数事务回滚或 fixture 清表，互不污染。
- **核心 fixtures**：`db_session`（带回滚）、`redis_client`、`mock_llm`（固定文本/JSON 返回）、`mock_embedder`（返回固定 1024 维向量，确定性可断言）。
- **依赖**：pytest、pytest-asyncio、httpx（`AsyncClient` 测 FastAPI + SSE）、testcontainers-python（可选，真实 PG）、respx（mock 外部 HTTP，可选）。
- **覆盖率方针**：`pytest --cov=app`。核心模块（`rag` / `memory` / `code_review`）≥80% 为**下限**，重逻辑模块（检索融合/记忆窗口+fallback/结构化解析）深测到 90%+，**不追求全局 90%**——测对的地方，不测所有地方；薄层/LLM 调用（已 mock）不强求。P5 统一验收。

### 6.3 各阶段测试交付清单

| 阶段 | 测试文件 | 关键用例 |
|------|---------|---------|
| P0 | `test_health` / `test_response` / `test_exception_handler` | `/health` 200；`Result{code,data}` 结构；`BusinessException` 返回 400+结构 |
| P1 | `test_models` / `test_migration` / `test_crud` / `test_pgvector_column` | 8 表对齐 ADR（父子表/合并表/内联向量）；alembic up/down 往返；`Vector` 列读写 + `<=>` 距离查询 |
| P2 | `test_llm_connect` / `test_embedding_dim` / `test_vector_recall` | LLM 调通（mock）；embedding 1024 维；VectorRecallService 存取+cosine 检索 |
| P3-1 | `test_code_review` / `test_prompt_manager` | 结构化输出解析；critical/warning/info 计数；持久化；`{{source_code}}` 渲染；**版本化激活/回滚**(ADR-0005) |
| P3-2 | `test_short_term` / `test_long_term` | 滑窗裁剪；摘要触发+异步双写(Redis+PG)；消息 miss 回查 PG 重建；摘要 miss 读 PG 不重算(ADR-0003)；内联向量召回 + threshold |
| P3-3 | `test_chunker` / `test_query_rewriter` / `test_hybrid` | Markdown 分块 + overlap；重写变体（mock）；pg_trgm+pgvector 融合、`matchType`、去重 |
| P3-4 | `test_chat` | 三级上下文拼接；SSE token + `[DONE]`；会话增删查；**CHAT prompt 走模板**(ADR-0005) |
| P3-5 | `test_unit_test` / `test_ai_readme` / `test_document_parser` / `test_prompt_api` | 各服务核心流程；unstructured 多格式解析 |
| P4 | `test_api_*`（7 路由） | 22 端点契约对照 `README.md` curl 示例（路径/请求/响应结构；`conversation_id`） |
| P5 | `tests/e2e_smoke` | 双端 22 接口响应结构比对；全链路冒烟（上传知识库->RAG->多轮对话->CR） |

---

## 7. 各组件迁移详细指南

### 7.1 配置层（P0）
`application.yml` -> `core/config.py`（pydantic-settings）。字段一一对应 `application.yml:64-101`。

```python
# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__")
    # Web
    app_name: str = "codeaware"
    # DB (对应 application.yml:17-21)
    pg_host: str = "localhost"; pg_port: int = 5433
    pg_user: str = "aicenter"; pg_password: str = "aicenter123"
    pg_db: str = "ai_center"
    # Redis (对应 application.yml:24-33)
    redis_host: str = "localhost"; redis_port: int = 6380
    # AI (对应 application.yml:64-101)
    llm_api_key: str; llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-v4-flash"; llm_temperature: float = 0.1; llm_max_tokens: int = 4096
    ollama_base_url: str = "http://localhost:11434"; ollama_embedding_model: str = "bge-m3"
    # memory / rag 参数同 yml
    mem_window_size: int = 20; mem_summary_threshold: int = 10
    rag_chunk_size: int = 500; rag_chunk_overlap: int = 50
    rag_bm25_weight: float = 0.3; rag_vector_weight: float = 0.7

    @property
    def pg_url_async(self) -> str:
        return f"postgresql+asyncpg://{self.pg_user}:{self.pg_password}@{self.pg_host}:{self.pg_port}/{self.pg_db}"
    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"

settings = Settings()
```

> **安全**：迁移时务必把 `application-dev.yml` 里硬编码的 DeepSeek key 改为只走 `.env`，并补 `.gitignore`。原 `application-dev.yml:3` 含明文 key，迁移是修正时机。

### 7.2 数据层（P1）

#### 7.2.1 async engine/session
```python
# app/db/session.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings
engine = create_async_engine(settings.pg_url_async, echo=False, pool_size=8)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
async def get_db():  # FastAPI Depends
    async with AsyncSessionLocal() as s:
        yield s
```

#### 7.2.2 SQLAlchemy 模型（ADR-0001/0002/0004/0005/0006）

**Python 共 8 表**（与 Java 同数，但组成不同：合并 CR/UT 记录、拆分 Knowledge 父子、内联向量、`conversation_id` 命名）：

1. `prompt_templates`（版本化，ADR-0005）：`(id, type, version, name[标签], role_setting, template_body, review_dimensions, severity_levels, is_active, created_at)`；部分唯一索引 `(type) WHERE is_active=true`。
2. `ai_operation_records`（合并 CR/UT，ADR-0006）：`(id, type[CODE_REVIEW/UNIT_TEST], project_name, file_path, source_code, result[TEXT/JSON], prompt_template_id, ai_model, metadata[JSON], created_at)`。
3. `conversations`（ADR-0004）：`(id, conversation_id[unique], title, summary[TEXT, ADR-0003 摘要持久化], created_at)`。
4. `messages`（ADR-0004）：`(id, conversation_id, role, content, token_count, created_at)`。
5. `long_term_memories`（ADR-0001）：`(id, conversation_id, content, memory_type, embedding[Vector(1024)], metadata, created_at)`。
6. `documents`（父，ADR-0002）：`(id, title, source_type, project_name, content[全文一次], created_at)`。
7. `knowledge_chunks`（子，ADR-0002）：`(id, document_id[FK], chunk_index, chunk_content, embedding[Vector(1024)], created_at)`。
8. `ai_readme_documents`（不变）：`(id, project_name, section, content, version, created_at)`。

> 相比 Java：删 `ai_embeddings`（UUID 反查表）+ `code_review_records`/`unit_test_records` 合一 + `knowledge_documents` 拆父子 + 向量内联。

父子表示例（ADR-0002 核心）：

```python
# app/models/document.py
class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    source_type: Mapped[str] = mapped_column(String(30))
    project_name: Mapped[str | None] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)        # 全文只存一次（修 Java 的按 chunk 重复存）
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")

# app/models/knowledge_chunk.py
class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)  # 内联（ADR-0001）
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    document: Mapped["Document"] = relationship(back_populates="chunks")
```

`long_term_memories.embedding` 同样用 `Vector(1024)` 内联。所有 `created_at` 用 `server_default=func.now()` 替代 MyBatis-Plus 自动填充。

#### 7.2.3 Alembic 迁移
从 `init.sql` 转首个迁移：`CREATE EXTENSION vector;` + `CREATE EXTENSION pg_trgm;` + 8 建表（按 §7.2.2 新结构）+ 预置 Prompt 模板（`init.sql:129-137` 的七层 CR Prompt 成为 CODE_REVIEW 的 active v1，另 seed CHAT/UNIT_TEST/AI_README v1）。**数据迁移需做归并**：旧 `knowledge_documents` 按 title 聚合 chunk 行 -> 提取父 `documents`；旧 `code_review_records`/`unit_test_records` -> 带 type 灌入 `ai_operation_records`；旧 `embedding` UUID 列 -> 重新 embed 或按映射回填 `Vector`。

#### 7.2.4 Pydantic schemas
DTO/VO 一一对应 `model/dto` `model/vo`。例如 `CodeReviewVO` + `ReviewIssueVO`：

```python
# app/schemas/code_review.py
from pydantic import BaseModel, Field

class ReviewIssue(BaseModel):
    dimension: str; severity: str; line_range: str
    title: str; description: str; suggestion: str
    fix_code: str | None = Field(default=None, alias="fix_code")  # 对齐 Prompt 的 snake_case

class CodeReviewVO(BaseModel):
    id: int | None = None
    project_name: str | None = None; file_path: str | None = None
    summary: str = ""; score: int = 0
    issues: list[ReviewIssue] = []
    highlights: list[str] = []
    issues_count: int = 0; critical_count: int = 0; warning_count: int = 0; info_count: int = 0
    ai_model: str = "deepseek-v4-flash"
```

### 7.3 AI 基建（P2）
`AIConfig.java` -> `ai/config.py` 工厂（`lru_cache` 单例）+ **共享 `VectorRecallService`**（ADR-0001，消除 Java 版两处复制的 embed+store+recall）：

```python
# app/ai/config.py
from functools import lru_cache
from langchain_openai import ChatOpenAI
from langchain_ollama import OllamaEmbeddings
from app.core.config import settings

@lru_cache
def get_chat_model() -> ChatOpenAI:
    return ChatOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url,
                      model=settings.llm_model, temperature=settings.llm_temperature,
                      max_tokens=settings.llm_max_tokens, timeout=120)

@lru_cache
def get_embedding_model() -> OllamaEmbeddings:
    return OllamaEmbeddings(base_url=settings.ollama_base_url, model=settings.ollama_embedding_model)
```

```python
# app/ai/infra/vector_recall.py  -- ADR-0001 共享服务
# embed 文本 + 内联 Vector 存储 + cosine 检索；Memory 与 Knowledge 共用。
# 检索策略（纯向量 / 混合 BM25+向量）作为参数，而非各自复制一套。
class VectorRecallService:
    def __init__(self, embedder, db): self.embedder = embedder; self.db = db
    async def store(self, entity, text): ...          # embed + 写 Vector 列
    async def recall(self, model, text, top_k, threshold, hybrid=False): ...
```
> Pinecone 双模式作为可选 `ai/config.py` 分支保留（与 Java 版一致）。

### 7.4 CodeReviewService（P3-1，改进③ + ADR-0005）
对照 `CodeReviewService.java:52` 流程不变，替换解析方式 + 走版本化激活模板：

```python
# app/ai/services/code_review.py
from app.schemas.code_review import CodeReviewVO, ReviewIssue, CodeReviewResult
from app.ai.config import get_chat_model

class CodeReviewResult(BaseModel):  # 结构化输出契约（替代 extractJson 正则）
    summary: str; score: int
    issues: list[ReviewIssue]; highlights: list[str] = []

async def review(project_name, file_path, source_code, conversation_id=None):
    template = await prompt_manager.get_active(PromptType.CODE_REVIEW)  # ADR-0005 版本化激活
    system_prompt = prompt_manager.render(template, {"source_code": source_code})
    structured = get_chat_model().with_structured_output(CodeReviewResult)  # 改进③
    result: CodeReviewResult = await structured.ainvoke(system_prompt)
    vo = _to_vo(result, project_name, file_path)
    await repo.save_record(type="CODE_REVIEW", ...)   # 写 ai_operation_records（ADR-0006）
    return vo
```
> `QueryRewriter` 同样用 `with_structured_output(list[str])` 替换 `QueryRewriter.java:52` 手写 JSON 数组切分。

### 7.5 HybridRetriever（P3-3，改进②核心）
对照 `HybridRetriever.java:45`，关键词腿下沉 PG，向量腿内联 pgvector，**作用在 `knowledge_chunks`**（ADR-0002）：

```python
# app/ai/rag/hybrid_retriever.py
from sqlalchemy import select, func
from app.models.knowledge_chunk import KnowledgeChunk

async def search(db, query_vec: list[float], query_text: str, top_k: int):
    # 向量腿：内联 pgvector cosine 距离（替代 embeddingStore.search + UUID 反查）
    vec_stmt = select(
        KnowledgeChunk,
        (1 - KnowledgeChunk.embedding.cosine_distance(query_vec)).label("vec_score")
    ).order_by(KnowledgeChunk.embedding.cosine_distance(query_vec)).limit(top_k * 3)

    # 关键词腿：pg_trgm similarity（中文友好，无需分词扩展）替代内存伪 BM25
    kw_stmt = select(
        KnowledgeChunk,
        func.similarity(KnowledgeChunk.chunk_content, query_text).label("kw_score")
    ).where(func.similarity(KnowledgeChunk.chunk_content, query_text) > 0.1
    ).order_by(func.similarity(KnowledgeChunk.chunk_content, query_text).desc()).limit(top_k * 3)

    # 融合：RRF（或保留加权 0.3/0.7）
    return _rrf_fuse(await _fetch(db, vec_stmt), await _fetch(db, kw_stmt), top_k)
```
> **中文检索决策**：默认 `pg_trgm`（需 `CREATE EXTENSION pg_trgm;`，零分词依赖）。生产升级路径：`tsvector` + `zhparser` 扩展做真 BM25。
> **保留来源追溯**：`matchType`(vector/keyword/both) + `sourceStats` 沿用 Java 版 RAG 返回结构（`c518ff5` 提交）。

### 7.6 ShortTermMemoryManager（P3-2，ADR-0003）
对照 `ShortTermMemoryManager.java:43`，redis async + 真异步摘要 + **PG fallback 读**（修只写不读死代码）：

```python
# app/ai/memory/short_term.py
import redis.asyncio as redis
from fastapi import BackgroundTasks
SEP = ":::"
async def save_message(r: redis.Redis, cid, role, content, bg: BackgroundTasks):
    await r.rpush(f"msgs:{cid}", f"{role}{SEP}{content}")      # 对应 opsForList().rightPush
    await r.ltrim(f"msgs:{cid}", -WINDOW_SIZE, -1)             # 裁剪窗口
    await r.expire(f"msgs:{cid}", 168 * 3600)
    size = await r.llen(f"msgs:{cid}")
    if size >= SUMMARY_THRESHOLD and size % 5 == 0:
        bg.add_task(generate_summary, r, cid)                  # 真异步（Java 版实为同步）
    await repo.insert_message(cid, role, content)              # 持久化 PG（真相源）

async def get_messages(r, db, cid):
    entries = await r.lrange(f"msgs:{cid}", 0, -1)
    if not entries:                                             # ADR-0003 fallback
        entries = await repo.recent_messages_from_pg(cid, WINDOW_SIZE)  # Redis miss 回查 PG 重建
        if entries:
            await _refill_redis(r, cid, entries)
    return _parse(entries)
```
> **LLM 摘要持久化（ADR-0003 已定）**：摘要存 PG `conversations.summary`(真相)+ Redis `summary:{cid}`(缓存)。读:Redis 优先,miss 读 PG,**不从消息重算**;写:命中阈值由 `BackgroundTasks` 异步生成/更新并双写。

### 7.7 LongTermMemoryManager（P3-2，改进①）
对照 `LongTermMemoryManager.java:39`，去掉 UUID 间接层，调 `VectorRecallService`：

```python
# app/ai/memory/long_term.py
async def save_memory(db, content, memory_type, conversation_id, metadata):
    mem = LongTermMemory(content=content, memory_type=memory_type,
                         conversation_id=conversation_id, metadata=metadata or "{}")  # ADR-0004
    db.add(mem); await db.flush()
    await vector_recall.store(mem, content)          # ADR-0001 共享服务内联向量
    await db.commit(); return mem

async def recall(db, query, threshold, top_k):
    return await vector_recall.recall(LongTermMemory, query, top_k, threshold)  # 纯向量策略
```

### 7.8 ChatService（P3-4，改进④ + ADR-0004/0005）
对照 `ChatService.java:51/83`，三级整合 + SSE + `conversation_id` + **CHAT prompt 走模板**：

```python
# app/ai/services/chat.py
from fastapi.responses import StreamingResponse
from app.ai.config import get_chat_model

async def chat(cid, message):                                   # 对应 chat()
    cid = await ensure_conversation(cid, message)
    await short_term.save_message(cid, "USER", message)
    prompt = await build_context_prompt(cid, message)           # 长期记忆+RAG+短期记忆
    reply = await get_chat_model().ainvoke(prompt)
    await short_term.save_message(cid, "ASSISTANT", reply.content)
    return ChatResponseVO(conversation_id=cid, reply=reply.content)  # ADR-0004

async def chat_stream(cid, message):                            # SSE，对应 chatStream()
    cid = await ensure_conversation(cid, message)
    await short_term.save_message(cid, "USER", message)
    prompt = await build_context_prompt(cid, message)
    async def gen():
        full = []
        async for chunk in get_chat_model().astream(prompt):   # 改进④
            full.append(chunk.content); yield f"data: {chunk.content}\n\n"
        await short_term.save_message(cid, "ASSISTANT", "".join(full))
        yield f"data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")
```
`buildContextPrompt` 对应 `ChatService.java:136`，**改走 CHAT 模板**（ADR-0005）：加载激活的 CHAT 模板，渲染占位符 `{{long_term_memory}}`/`{{rag_context}}`/`{{conversation_history}}`/`{{user_message}}`；模板存静态外壳 + 占位符，拼装逻辑（拉记忆/RAG/历史）留代码。

### 7.9 API 层（P4）
7 个 `APIRouter` 对应 7 controller，路径与 `README.md` API 汇总表完全一致（保持前端/CI 调用不变）。SSE 端点用 `StreamingResponse`。FastAPI 自动生成 `/docs` 替代 Knife4j。**请求/响应体 `session_id` -> `conversation_id`**（ADR-0004，破坏性变更，前端同步改）。

```python
# app/api/v1/code_review.py
from fastapi import APIRouter, Depends
router = APIRouter(prefix="/api/code-review", tags=["CodeReview"])

@router.post("/review")
async def review(req: CodeReviewRequest, db = Depends(get_db)):
    vo = await code_review_service.review(req.project_name, req.file_path, req.source_code)
    return Result.ok(vo)
```

### 7.10 全局异常（P0）
`GlobalExceptionHandler.java` -> FastAPI handler：
```python
@app.exception_handler(BusinessException)
async def biz_handler(req, exc: BusinessException):
    return JSONResponse(status_code=400, content=Result.error(exc.message).model_dump())
```

### 7.11 PromptTemplate 版本化与激活（P3-1，ADR-0005 新增）
Java 版 `PromptTemplateManager` 的激活非确定性 + 幽灵 `version` + CHAT 空壳，Python 版落实：

```python
# app/ai/prompt/template_manager.py
async def get_active(type_: PromptType) -> PromptTemplate:   # 每 type 恰一激活
    return await db.scalar(select(PromptTemplate)
        .where(PromptTemplate.type == type_, PromptTemplate.is_active == True))

async def save_and_activate(type_, body, role_setting, name_label, **meta) -> PromptTemplate:
    # 事务：新建 version = max+1；deactivate 同 type 其他；activate 新行（回滚 = 激活旧 version）
    async with db.begin():
        max_v = await _max_version(type_)
        t = PromptTemplate(type=type_, version=max_v+1, name=name_label,
                           template_body=body, role_setting=role_setting, is_active=True, **meta)
        db.add(t)
        await db.execute(update(PromptTemplate)
            .where(PromptTemplate.type == type_, PromptTemplate.is_active == True)
            .values(is_active=False))
```
- 渲染：`{{source_code}}` 等占位符替换；CHAT 模板含 `{{long_term_memory}}`/`{{rag_context}}`/`{{conversation_history}}`/`{{user_message}}`。
- DB 部分唯一索引 `(type) WHERE is_active = true` 兜底唯一性。

---

## 8. 端到端验证（P5）

> 单元/集成测试已下沉到各阶段（见 6.2 / 6.3），本节聚焦跨阶段端到端验证。

1. **双端契约对齐**：用 `README.md` 的 22 个 curl 示例对 Java/Python 双端逐接口比对，响应结构（`code/data`）一致（注意 `conversation_id` 重命名）。
2. **e2e 冒烟脚本**：`tests/e2e_smoke.py` 串起全链路：上传知识库 -> RAG 检索 -> 多轮对话 -> Code Review。
3. **覆盖率验收**：`pytest --cov=app`。核心模块（`rag`/`memory`/`code_review`）≥80%（下限），重逻辑模块 90%+，不追求全局 90%。
4. **数据迁移**：复用同一 PG 实例，迁移期两套代码可共存验证；正式切换前 dump/restore + §7.2.3 归并。

### 8.1 P5 验收结果（实测）

- **e2e 全链路**：`tests/e2e_smoke.py`（dependency_overrides 注入 mock LLM/embedder，ASGI 客户端）串通 上传知识库 -> RAG 检索 -> 存长期记忆 -> 多轮对话(同步+SSE) -> 会话管理 -> Code Review -> 记录查询，1 用例覆盖核心域 Chat 全链路。
- **契约对齐**：e2e 顺带暴露并修复了 Python 端 2 类序列化契约 bug（此前零测试覆盖的端点）：
  - `GET /api/chat/conversations` / `GET /api/chat/conversations/{id}` 原返回裸 ORM（`Conversation` / `MessageEntry`），经 `Result`(Pydantic) 序列化抛 `PydanticSerializationError` -> 改为 router 层 dict 投影（与 knowledge/memory/prompt 端点一致）。
  - `GET /api/code-review/records` / `GET /api/code-review/records/{id}` / `/api/unit-test/records*` 原返回裸 `AiOperationRecord` ORM -> 抽 `record_to_dict`（ORM `meta` -> 对外 `metadata`，规避 `DeclarativeBase.metadata` 冲突）共享投影。
  - Java 端作为回退源码保留；Python 端契约已对齐 README 文档化端点。迁移期同库共存，正式切换前 dump/restore + 归并时再做双端 curl 逐接口比对。
- **覆盖率**（`uv run pytest --cov=app`，73 passed / 1 integration deselected）：

  | 模块 | 覆盖率 | 备注 |
  |------|--------|------|
  | `ai/infra/vector_recall.py` | 100% | 检索融合（重逻辑） |
  | `ai/memory/short_term.py` | 94% | 滑窗+fallback+摘要（重逻辑） |
  | `ai/memory/long_term.py` | 100% | |
  | `ai/rag/hybrid_retriever.py` | 100% | RRF 融合（重逻辑） |
  | `ai/rag/query_rewriter.py` | 90% | |
  | `ai/rag/semantic_chunker.py` | 100% | |
  | `ai/services/code_review.py` | 100% | 结构化解析（重逻辑） |
  | `ai/services/rag.py` | 100% | |
  | `ai/services/chat.py` | 88% | 核心域 Chat（>80% 下限）；余量为 defensive `except` + 无模板 fallback |
  | `ai/prompt/template_manager.py` | 98% | 版本化+激活（重逻辑） |
  | **全局** | **92%** | 薄层（API router/DI）不强求 |

  核心模块全部 ≥80% 下限达标，重逻辑模块 90%+；未追求全局 90%（薄层/LLM 调用已 mock 不强求，见 §6.2）。

---

## 9. 面试叙事升级

> 核心域定位（ADR-0007）：**核心域 = Chat（智能问答）**，两级记忆+RAG+prompt 编排在此收敛；共享 AI 基建（Prompt/Memory/VectorRecall）为支撑子域；CR/单测/AIReadMe 是复用基建的次要工具上下文。**价值类型**：Chat=架构纵深，CR=提示词工程展示（七层 Prompt），UT/AIReadMe=薄壳复用。不再说含糊的"研发效能中台"。

> 30 秒电梯演讲（技术栈表述更新 + 重构升级层）：

> 「我先用 Spring Boot 3 + LangChain4j 独立开发了 AI 研发效能中台 CodeAware，22 个 API 覆盖 AI Code Review、单测生成、AIReadMe、智能问答（多轮+两级记忆+RAG），**核心域是智能问答 Chat**。随后用 Python 主流栈（FastAPI + LangChain + SQLAlchemy + pgvector）重构，先做了一轮领域建模 grilling 产出 7 份 ADR，并在迁移中修正了多个设计问题：① 向量内联 pgvector 消除 UUID 反查；② 关键词检索下沉 PG 的 pg_trgm 替代内存伪 BM25；③ LLM 结构化输出 + 全异步 SSE 替代手写 JSON 解析与同步回调；④ Knowledge 拆父子表修全文冗余、消息改 PG 真相源修只写不读、Prompt 模板版本化修激活非确定性。」

**追问弹药**：
- 为什么不用 SonarQube？（保留原话术：规则引擎 vs 语义理解）
- BM25 vs pg_trgm vs tsvector 取舍？（中文分词、扩展性、零依赖）
- 为什么内联向量而非独立向量表？（同表增删查 + 来源追溯；Java 版受 LangChain4j EmbeddingStore 限制）
- 为什么全异步？（LLM I/O 密集，async 提升并发）
- LangChain vs LlamaIndex？（对称迁移叙事；LangGraph 编排为预留，本次迁移不实现）
- 核心域是什么？为什么是 Chat 而非 CR？（业务价值收敛处；CR 是薄工具，IP 在 prompt/记忆/召回基建）
- Memory 和 Knowledge 都用向量，为何分表？（聚合结构差异：原子 vs 文档-分块父子；起源差异：对话内生 vs 外部策展）

**预留演进（本次迁移不实现）**：`ChatService` 的"召回->检索->生成->持久化"升级为 **LangGraph** 状态图编排，展示 Agent/Graph 能力。本次迁移只交付 Chat 功能基线，工程深度加深留作后续（见 ADR-0007 决策点 4）。

---

## 10. 风险与回退

| 风险 | 缓解 |
|------|------|
| DeepSeek API 行为差异（结构化输出兼容性） | `with_structured_output` 失败时回退到 `ainvoke` + Pydantic `model_validate` 兜底解析 |
| pg_trgm 中文召回精度 | 可切换 `tsvector+zhparser`；保留加权融合参数可调 |
| bge-m3 向量维度变化 | `Vector(1024)` 维度常量化，Alembic 可重建 |
| 双端切换数据一致性 | 同一 PG 实例共存验证；正式切换前 dump/restore + 归并 |
| `conversation_id` 破坏性重命名 | 整体重写，前端同步改；迁移期双端共存验证 |
| 迁移周期 | 按 P0–P5 逐阶段交付，每阶段可独立验收，Java 版全程可用作回退 |

---

## 11. 实施清单（后续逐阶段勾选）

> 每阶段含「实现」+「测试」两组勾选，测试通过方可进入下一阶段。

- [x] **P0** 工程骨架 / FastAPI / config / response / exceptions / db session / `/health`
  - [x] 测试：`test_health` / `test_response` / `test_exception_handler`
- [x] **P1** 8 表 SQLAlchemy 模型（父子拆分/记录合并/内联 pgvector）/ Alembic / schemas / CRUD
  - [x] 测试：`test_models`(对齐 ADR) / `test_migration`(up-down) / `test_crud` / `test_pgvector_column`
- [x] **P2** `ai/config.py` + `VectorRecallService`(ADR-0001) / LLM+Embedding 连通性自测
  - [x] 测试：`test_llm_connect`(mock) / `test_embedding_dim`(1024) / `test_vector_recall`
- [x] **P3-1** PromptTemplateManager(版本化+激活,ADR-0005) + CodeReviewService（结构化输出）
  - [x] 测试：`test_code_review`(解析/计数/持久化) / `test_prompt_manager`(渲染/激活/回滚)
- [x] **P3-2** ShortTermMemory(PG fallback,ADR-0003) + LongTermMemory（内联 pgvector,ADR-0001）
  - [x] 测试：`test_short_term`(滑窗/摘要触发+双写/miss 回查) / `test_long_term`(召回+threshold)
- [x] **P3-3** SemanticChunker + QueryRewriter + HybridRetriever（pg_trgm，作用 knowledge_chunks）
  - [x] 测试：`test_chunker`(分块+overlap) / `test_query_rewriter`(变体) / `test_hybrid`(融合+matchType+去重)
- [x] **P3-4** RagService(父子表,ADR-0002) + ChatService（SSE + CHAT 模板,ADR-0005 + conversation_id）
  - [x] 测试：`test_chat`(三级上下文 / SSE token+[DONE] / 会话增删查 / CHAT 走模板)
- [x] **P3-5** UnitTest / AiReadme / DocumentParser(unstructured) / Prompt
  - [x] 测试：`test_unit_test` / `test_ai_readme` / `test_document_parser` / `test_prompt_api`
- [x] **P4** 7 router + Depends + SSE，22 API 对齐（conversation_id）
  - [x] 测试：`test_api_*`（端点契约对照 README curl）
- [x] **P5** e2e 全链路 / 覆盖率 / README+话术更新
  - [x] 测试：`e2e_smoke` 全链路（上传知识库->RAG->多轮对话同步+SSE->会话管理->CR） / 核心模块覆盖率 ≥80%（实测：核心域 chat 88%，全局 92%；下限达标，不追求全局 90%）
