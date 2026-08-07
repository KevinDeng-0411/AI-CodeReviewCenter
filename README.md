**English** | [简体中文](README.zh-CN.md)

---

# CodeAware

An AI-driven developer productivity platform designed for **software engineering lab teams** (code review, onboarding new members, team knowledge retrieval).
The current core deliverable is a **Chat/RAG knowledge-base Q&A app**: upload team documents → automatic parsing & chunking → intelligent Q&A with cited sources and chain-of-thought.

![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688)
![React 19](https://img.shields.io/badge/React-19-61DAFB)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6)
![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-4169E1)
![Redis 7](https://img.shields.io/badge/Redis-7-DC382D)
![Celery](https://img.shields.io/badge/Celery-async-37814A)
![Kafka](https://img.shields.io/badge/Kafka-event--driven-231F20)
![LangGraph](https://img.shields.io/badge/LangGraph-orchestration-FF6F00)
![embedding](https://img.shields.io/badge/embedding-bge--m3-FFA500)

> The project was fully refactored from Java (Spring Boot + LangChain4j) to Python (FastAPI); the legacy Java implementation is kept in [java-legacy/](java-legacy/) for reference only.

---

## Core Features

| Feature | Description |
|---|---|
| 📄 **Knowledge-base Q&A** | Upload MD/DOCX/HTML/PDF → element-aware parsing → chunking & embedding → hybrid retrieval (BM25 + vector RRF) → answers **with cited sources** |
| 🧠 **Streamed chain-of-thought** | DeepSeek `reasoning_content` streamed separately from the answer (8-event typed SSE) — the model's reasoning is visible |
| 🇨🇳 **Chinese retrieval optimization** | jieba segmentation makes Chinese BM25 usable (exact Chinese R@5: 0.25 → **1.000**) |
| 🔀 **Smart routing + self-correction** | LangGraph orchestration: common-sense questions skip retrieval (saves latency); weak retrieval triggers query rewriting & retry (ADR-0015) |
| 👥 **Team-ready** | JWT auth, per-user conversation isolation, shared knowledge base & memory (lab scenario) |
| 📚 **Document management** | List / detail (chunk visualization) / soft delete / replace-update (ADR-0013) |
| 🧩 **Long-term memory** | Facts auto-extracted from conversations + pgvector recall — team context persists across sessions |

---

## Screenshots

![Chat Q&A](./docs/screenshots/chat.png)

*Chat: streaming answer + cited sources + chain-of-thought*

![Knowledge base management](./docs/screenshots/knowledge.png)

*Knowledge base: document list + chunk visualization + upload / replace / soft delete*

![Login page](./docs/screenshots/login.png)

*Login: JWT team authentication*

---

## Quick Start

### Prerequisites

| Dependency | Version | Purpose |
|---|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | any | PostgreSQL / Redis / Ollama containers |
| [uv](https://docs.astral.sh/uv/) | ≥0.4 | Python package manager |
| Node.js | ≥18 | Frontend |
| DeepSeek API key | — | LLM (`api.deepseek.com`) |

> Local dev defaults to the `deepseek-v4-flash` model (configurable); embeddings run on local Ollama bge-m3 — **zero API cost**.

### Step 1: Configure environment variables

```bash
cd codeaware-py
cp .env.example .env        # copy the template
# edit .env — at minimum:
#   LLM_API_KEY=sk-...      ← required, DeepSeek key
#   JWT_SECRET_KEY=...      ← for production, use a random string (openssl rand -hex 32)
```

### Step 2: Start base services and pull the embedding model

```bash
cd ..                       # back to repo root
docker compose up -d        # PG(:5433) + Redis(:6380) + Kafka(:9093) + Celery Worker + Flower(:5555)
# Ollama runs natively (macOS Metal GPU): brew install ollama && ollama pull bge-m3
```

### Step 3: One-command startup (migrations + admin bootstrap + backend + frontend)

```bash
bash codeaware-py/scripts/start.sh
```

The first run guides you through creating an admin account. Then visit:

```text
Frontend:  http://localhost:5173
OpenAPI:   http://localhost:8000/docs
Health:    http://localhost:8000/api/ai/health
```

### Manual startup (step by step)

```bash
docker compose up -d
(cd codeaware-py && uv sync && uv run alembic upgrade head)
(cd codeaware-py && uv run python -m scripts.create_admin)   # first time
(cd codeaware-py && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000)
(cd codeaware-py/frontend && npm ci && npm run dev)
```

### Stop

```bash
bash codeaware-py/scripts/stop.sh      # stop backend + frontend, keep docker
docker compose down                    # stop everything (data persists in volumes)
```

---

## Architecture Diagrams

### 1. System Layered Architecture

```mermaid
graph TB
    subgraph Presentation["Presentation Layer"]
        React["React 19 + Vite<br/>8-module SPA"]
        SSE["Typed SSE Parser<br/>8 events, protocol v1"]
    end

    subgraph Application["Application Layer (FastAPI)"]
        Router["API Router<br/>32 endpoints"]
        Auth["JWT Auth<br/>bcrypt"]
        TC["TurnCoordinator<br/>⚡ state machine"]

        subgraph Context["Context Building"]
            STM["ShortTermMemory<br/>PG messages + Redis window"]
            LTM["LongTermMemory<br/>atomic facts + pgvector"]
            RAG["RagService<br/>rewrite → hybrid → rerank"]
            RR["CrossEncoderReranker<br/>ONNX bge-reranker-v2-m3"]
            PT["PromptTemplate<br/>versioned"]
        end
    end

    subgraph Orchestration["Orchestration Layer"]
        LG["LangGraph<br/>router + self-correction"]
        Celery["Celery Worker<br/>parse + extract"]
        Flower["Flower<br/>:5555"]
    end

    subgraph Infrastructure["Infrastructure Layer"]
        PG["PostgreSQL 16<br/>pgvector + pg_search BM25"]
        Redis["Redis 7<br/>cache + Celery broker"]
        Kafka["Kafka<br/>audit + metrics"]
        Ollama["Ollama<br/>bge-m3 1024-d Metal GPU"]
        DS["DeepSeek v4-flash"]
    end

    React -->|"typed SSE (8 events)"| Router
    Router --> Auth
    Auth --> TC
    TC --> Context
    RAG --> LG
    RAG --> RR
    TC -->|"submit async task"| Celery
    Flower --> Celery
    STM --> PG
    STM --> Redis
    LTM --> PG
    RR --> Ollama
    RAG --> Ollama
    TC -->|"ChatDeepSeek astream"| DS
    TC -->|"emit events"| Kafka
```

### 2. Core Interaction Sequence

```mermaid
sequenceDiagram
    participant U as User
    participant F as Frontend
    participant B as Backend
    participant TC as TurnCoordinator
    participant CB as ContextBuilder
    participant RR as Reranker
    participant LLM as DeepSeek
    participant DB as PG/Redis

    U->>F: 输入问题
    F->>B: POST /chat/send/stream
    B->>TC: prepare_turn(message)
    TC->>DB: 存 USER 消息（commit）
    TC-->>F: chat.started
    TC->>CB: build_context(message)
    CB->>RR: 混合检索 top_20<br/>RRF + cross-encoder 精排
    RR->>DB: BM25 + pgvector
    RR-->>CB: 精排后 top_5
    CB-->>TC: prompt + refs
    TC-->>F: context.references
    TC->>LLM: astream(prompt)
    LLM-->>F: reasoning.delta / token.delta
    TC->>DB: 存 ASSISTANT（commit）
    TC-->>F: chat.completed
```

### 3. Smart Routing & Evaluation Decision Flow

```mermaid
flowchart TD
    A[用户消息] --> B{智能路由<br/>LLM 判断}
    B -->|direct 常识/闲聊| C[跳过检索<br/>直接回答<br/>标注「未检索知识库」]
    B -->|retrieve 技术/资料| D[混合检索<br/>BM25 + pgvector RRF<br/>粗排 top_20]
    D --> E[Reranker 精排<br/>cross-encoder 打分]
    E --> F{评估<br/>match_type 检测}
    F -->|满意| G[注入 top_5 → prompt<br/>→ LLM 生成]
    F -->|不满意 且 retries<2| H[改写查询<br/>防打转 + seen_queries 兜底]
    H --> D
    F -->|达上限 或 query 重复| I[返回"未找到"<br/>+ context.warning]
```

### 4. System Context / Boundary

```mermaid
flowchart LR
    subgraph Team["Software Engineering Lab"]
        Dev["开发者<br/>上传文档 / 提问"]
        Newbie["新人<br/>知识问答"]
    end

    subgraph System["CodeAware"]
        App["Chat/RAG 平台<br/>知识库 + 记忆 + 异步"]
    end

    subgraph External["External"]
        DS["DeepSeek API<br/>LLM 生成"]
        Ollama["Ollama (local)<br/>bge-m3 embedding"]
        Docker["Docker<br/>PG / Redis / Kafka"]
    end

    Dev -->|"上传/提问"| App
    Newbie -->|"检索/问答"| App
    App -->|"LLM 调用"| DS
    App -->|"embedding"| Ollama
    App -->|"数据/事件"| Docker
```

**Core principles**:

- **PostgreSQL is the source of truth; Redis is a disposable cache** — on Redis failure the system falls back to PG automatically, no feature degradation
- **No DB transaction is held while waiting on the model** — the connection pool is never blocked for long
- **Typed SSE with explicit semantics** — 8 event types with protocol version and strictly increasing sequence; the sync endpoint drains the same event stream — a single state machine
- **Dual runtime with rollback** — LangGraph retrieval enhancement (`RAG_RUNTIME=graph`) can be reverted to the original path (`service`) with one env change
- **Rerank is a reversible enhancement** — `reranker_enabled=False` reverts to pure RRF

Detailed design (Chat full-chain sequence, 9-table ER, RAG pipeline): see [docs/roadmap/current-release/README.md](docs/roadmap/current-release/README.md).
## Typed SSE Example (8-event protocol)

For a new conversation, `conversation_id` is created by the server and returned in `chat.started`:

```bash
curl -N http://localhost:8000/api/chat/send/stream \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <token>' \
  -d '{"conversation_id":null,"message":"解释 RAG 完整链路"}'
```

The response is a stream of versioned events, not raw tokens or `[DONE]`:

```text
id: 1
event: chat.started
data: {"protocol_version":1,"conversation_id":"...","turn_id":"...","sequence":1}

id: 2
event: context.references
data: {"protocol_version":1,...,"knowledge_refs":[...],"memory_refs":[...],"sequence":2}

id: 3
event: reasoning.delta
data: {"protocol_version":1,...,"sequence":3,"delta":"首先分析..."}

id: 4
event: token.delta
data: {"protocol_version":1,...,"sequence":4,"delta":"RAG 完整链路包括..."}

event: chat.completed
data: {"protocol_version":1,...,"sequence":N}
```

---

## Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Framework | FastAPI + Pydantic v2 | async HTTP + typed SSE |
| LLM | DeepSeek v4-flash (langchain-deepseek) | ChatDeepSeek extracts reasoning_content |
| Embeddings | Ollama bge-m3 1024-d | local Metal GPU embedding, ~128ms/query, zero API cost |
| Relational DB | PostgreSQL 16 + asyncpg | PG-first source of truth |
| Vector index | pgvector HNSW cosine | inline vectors, same-transaction commit |
| Lexical search | ParadeDB pg_search BM25 | default tokenizer; pg_trgm fallback |
| Retrieval enhancement | LangGraph StateGraph (ADR-0015) | smart routing + self-correction (match_type detection) |
| Reranker | ONNX bge-reranker-v2-m3 | post-RRF cross-encoder re-rank (MRR +0.058) |
| Task queue | Celery + Redis | async document parsing, memory extraction, Flower monitoring |
| Event streaming | Kafka (Confluent) | audit trail, retrieval metrics, error events |
| Cache | Redis 7 | disposable, PG fallback |
| Frontend | React 19 + Vite + TypeScript | 8-module SPA (no router) |
| Tooling | uv + Alembic | locked dependencies + reversible migrations |

---

## Current Status

| Metric | Value |
|---|---|
| Backend tests | **315 passed**, 0 failed (async tasks + Kafka + LangGraph) |
| Frontend tests | **43 passed** |
| API endpoints | 32 |
| Tables | 9 |
| ADRs | 15 (0001-0015) |
| Alembic head | 0011 |
| Delivered | C1-C6 + team A/B/C + document management + async task queue + Kafka event streaming |

**Retrieval evaluation summary** (real bge-m3, 60 golden cases):

- Full evolution tracking (C3→C4→jieba→LangGraph→RAGAS): [retrieval-evolution.md](docs/optimization/retrieval-evolution.md)
- Hybrid retrieval R@5 = 0.975, MRR = 0.941 (with reranker) ([top_k sensitivity](docs/optimization/topk-sensitivity.md))
- jieba Chinese BM25: exact Chinese R@5 0.25 → **1.000** ([ADR-0011](docs/decisions/adr/0011-jieba-chinese-bm25-segmentation.md))
- LangGraph routing accuracy **60/60 = 1.000**, retry rate 0.019 ([eval report](docs/optimization/rag-graph-eval.md))
- Generation quality RAGAS: Faithfulness 0.931 / Answer Relevancy 0.793 ([eval report](docs/optimization/ragas-eval.md))

Full evaluation data (C3/C4 lexical upgrade, per-category, sensitivity analysis): [docs/optimization/](docs/optimization/README.md).

---

## Testing

Running bare `pytest` is forbidden for the backend — a safe runner creates disposable PG/Redis instances and refuses dev databases and remote targets:

```bash
# full test suite (safe)
(cd codeaware-py && uv run python scripts/run_tests_safe.py -q)

# coverage
(cd codeaware-py && uv run python scripts/run_tests_safe.py --cov=app --cov-report=term-missing -q)

# frontend
(cd codeaware-py/frontend && npm run test && npm run lint && npm run build)
```

---

## Technology Decisions

| Decision | Chosen | Rejected after evaluation |
|---|---|---|
| LLM adapter | ChatDeepSeek (extracts reasoning) | ChatOpenAI (drops 3rd-party fields) |
| Lexical search | ParadeDB BM25 (default tokenizer) + jieba | pg_trgm (C3 noise hurt RRF) |
| PDF parsing | pdfminer.six (font-size heading detection) | unstructured.partition.pdf (pulls in torch) |
| Reranker | ONNX bge-reranker-v2-m3 (ADR-0009 re-evaluated) | torch CrossEncoder (heavy dependency) |
| Intent classification | not built (90% knowledge questions) | classifier risks missed retrieval |
| LangGraph | retrieval-layer routing + self-correction (ADR-0015) | full Agent tool loop (no demand) |
| Refresh token | none (7-day access) | lab doesn't need rotation |
| Concurrency guard | in-process set[str] | PG advisory lock (when multi-worker) |
| Task queue | Celery + Redis | Kafka (event stream, not task queue) |
| Ollama deployment | native macOS (Metal GPU) | Docker container (CPU-only) |

---

## Current Boundaries

| Has | Does not have |
|---|---|
| JWT auth + per-user conversation isolation | project management (X-Project-ID) |
| shared knowledge base & memory | per-user KB permissions |
| 8-event typed SSE | WebSocket |
| BM25 + pgvector RRF **粗排** + ONNX cross-encoder **精排** | LLM-as-reranker / torch CrossEncoder |
| element-aware chunking + scanned-PDF rejection | OCR |
| fail-closed disposable test stack | bare pytest |
| single-worker local-first | multi-worker / K8s |
| Celery async task queue | Agent tool loop |
| Kafka event streaming (audit/metrics) | Grafana / Loki dashboard |
| Flower task monitoring | — |
| deterministic Chat state machine | Agent tool loop |
| answer cache (sync endpoint only) | answer cache on streaming endpoint |

## Design vs Implementation Notes

设计阶段与最终实现存在差异的点，记录取舍原因：

| 设计点 | 设计意图 | 实际实现 | 原因 |
|---|---|---|---|
| **答案缓存** | 同步+流式都缓存 | **仅同步端点** | 流式需保留引用/思考展示，缓存回放会丢失；同步全阻塞收益最大（31s→0.02s）。详见 [sync-vs-stream-endpoints.md](docs/optimization/sync-vs-stream-endpoints.md) |
| **Reranker** | 暂缓（torch 依赖） | **ONNX Runtime 落地** | 60 条 golden 暴露 cross_doc MRR=0.750 短板；ONNX 无 torch 依赖，MRR +0.058 |
| **负例降级** | 无关查询返回"未找到" | **保持硬答 + 前端提示** | 前端已有"未检索知识库"标注，降级收益小、改动大，未做 |
| **Ollama 部署** | Docker 容器 | **macOS 原生（Metal GPU）** | Docker 无法直通 GPU 到容器；原生 Metal 加速 45x |
| **Flower 部署** | 独立容器 | **与 Celery Worker 合并容器** | 同一镜像一个 entrypoint 起两进程，简化编排 |
| **Kafka 镜像** | bitnami/kafka | **confluentinc/cp-kafka** | bitnami 镜像拉取限流，本地已有 confluent 镜像 |

> 原则：**有实测收益或解决依赖约束的设计变更才落地**；其余保持原设计，边界明确记录。

---

## Documentation

| Doc | Purpose |
|---|---|
| [AGENTS.md](AGENTS.md) | development rules |
| [docs/roadmap/current-release/README.md](docs/roadmap/current-release/README.md) | current roadmap (C1-C6) |
| [docs/roadmap/团队化升级计划.md](docs/roadmap/团队化升级计划.md) | team upgrade design |
| [docs/roadmap/团队化升级-实施计划.md](docs/roadmap/团队化升级-实施计划.md) | team upgrade implementation |
| [docs/roadmap/部署上线指南.md](docs/roadmap/部署上线指南.md) | deployment (LAN + cloud) |
| [docs/roadmap/chat-to-agent/personal/README.md](docs/roadmap/chat-to-agent/personal/README.md) | Agent roadmap (locked) |
| [docs/optimization/](docs/optimization/README.md) | retrieval optimization evals (jieba/top_k/LangGraph/RAGAS) |
| [docs/decisions/adr/](docs/decisions/adr/) | 15 architecture decision records |
| [docs/interview/面试准备指南.md](docs/interview/面试准备指南.md) | interview deep-dive |
| [docs/interview/面试速通版.md](docs/interview/面试速通版.md) | interview speedrun |
| [docs/interview/项目简历介绍.md](docs/interview/项目简历介绍.md) | resume blurb |
| [docs/migration/Python重构迁移文档.md](docs/migration/Python重构迁移文档.md) | migration history |
