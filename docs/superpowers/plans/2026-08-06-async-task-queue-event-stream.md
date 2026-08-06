# 异步任务队列 + 事件流实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 引入 Celery + Redis 异步任务队列和 Kafka 事件流，将文档解析/embedding/记忆抽取从同步阻塞改为异步执行，并建立事件驱动的审计和指标流水线。

**Architecture:**
- **Celery + Redis**：任务队列，Broker 复用现有 Redis，结果后端也用 Redis。Worker 独立容器运行，Flower 提供监控面板。
- **Kafka**：事件流平台，记录审计日志（文档 CRUD、对话操作）和指标事件（检索耗时、错误率），消费者独立容器运行。

**Tech Stack:** Celery>=5.4, kafka-python>=2.0, Flower>=2.0, Redis（已有）, Kafka（新增 Docker 容器）

## Global Constraints

- 复用现有 Redis（端口 6380），不新增 Broker 依赖
- Celery 任务函数必须是纯函数，不持有 FastAPI 的 request 上下文
- Kafka 事件必须是非阻塞 fire-and-forget，不阻塞主请求链路
- 所有任务定义在 `app/ai/tasks/` 目录下，按领域分模块
- 所有 Kafka 事件定义在 `app/ai/events/` 目录下，按领域分模块
- 配置项统一加在 `app/core/config.py` 的 Settings 类中

---

## 文件结构

```
codeaware-py/
├── pyproject.toml                          # +celery, +kafka-python, +flower
├── docker-compose.yml                      # +celery_worker, +flower, +kafka, +kafka_consumer
├── app/
│   ├── core/
│   │   └── config.py                       # +celery/kafka 配置项
│   ├── ai/
│   │   ├── celery_app.py                   # [新建] Celery 应用定义
│   │   ├── tasks/
│   │   │   ├── __init__.py                 # [新建]
│   │   │   ├── base.py                     # [新建] 任务基类（重试策略、日志）
│   │   │   ├── document_parse.py           # [新建] 文档解析+分块+embedding
│   │   │   └── memory_extract.py           # [新建] post-turn 记忆抽取
│   │   └── events/
│   │       ├── __init__.py                 # [新建]
│   │       ├── schemas.py                  # [新建] 事件类型定义（Pydantic）
│   │       ├── producer.py                 # [新建] Kafka Producer 单例
│   │       └── consumer.py                 # [新建] Kafka Consumer（日志归档）
│   ├── api/v1/
│   │   ├── knowledge.py                    # 修改：上传文档→提交 Celery 任务
│   │   └── tasks.py                        # [新建] 任务状态查询接口
│   └── ai/services/
│       ├── rag.py                          # 修改：upload_document 拆出可任务化版本
│       └── turn_coordinator.py             # 修改：post-turn 记忆抽取→提交 Celery 任务
├── docker/
│   └── kafka/
│       └── consumer_entry.py               # [新建] Kafka 消费者容器入口
```

---

## 实施任务

### 任务 1: 基础设施 — 依赖 + 配置 + Docker

**Files:**
- Modify: `pyproject.toml`
- Modify: `app/core/config.py`
- Modify: `docker-compose.yml`
- Create: `docker/kafka/consumer_entry.py`

**Interfaces:**
- Produces: Config fields `celery_broker_url`, `celery_result_backend`, `kafka_bootstrap_servers`, `kafka_topic_prefix` in Settings

- [ ] **Step 1: 添加依赖**

```toml
# pyproject.toml dependencies 添加
"celery>=5.4",
"kafka-python>=2.0",
```

- [ ] **Step 2: 添加配置项**

```python
# app/core/config.py Settings 类末尾，jwt_expire_hours 之后

# Celery 任务队列（复用现有 Redis）
celery_broker_url: str = ""  # 默认由 redis_url 属性拼接
celery_result_backend: str = ""  # 默认由 redis_url 属性拼接

# Kafka 事件流
kafka_bootstrap_servers: str = "localhost:9093"
kafka_topic_prefix: str = "codeaware."

@property
def celery_broker(self) -> str:
    return self.celery_broker_url or f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

@property
def celery_backend(self) -> str:
    return self.celery_result_backend or f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
```

- [ ] **Step 3: 更新 docker-compose.yml**

```yaml
# docker-compose.yml 在 services 下追加

  # ============================================================
  # Celery Worker — 异步任务执行
  # ============================================================
  celery_worker:
    build:
      context: ./docker
      dockerfile: Dockerfile.worker
    container_name: ${CODEAWARE_CELERY_WORKER_CONTAINER_NAME:-ai-center-celery-worker}
    depends_on:
      redis:
        condition: service_healthy
    environment:
      REDIS_HOST: redis
      REDIS_PORT: 6380
      LLM_API_KEY: ${LLM_API_KEY}
      OLLAMA_BASE_URL: http://ollama:11434
    volumes:
      - ./codeaware-py:/app
    working_dir: /app
    command: >
      celery -A app.ai.celery_app worker
      --loglevel=info
      --concurrency=2
      --max-tasks-per-child=50
    # concurrency=2 的理由：
    #   - 瓶颈在 Ollama CPU embedding（单线程），2 个 worker 可错开瓶颈：
    #     Worker 1 跑 embedding（CPU 满）时，Worker 2 跑 LLM API（网络 I/O，不抢 CPU）
    #   - Ollama 上 GPU 后可调到 concurrency=4~8
    restart: unless-stopped

  # ============================================================
  # Flower — Celery 任务监控面板
  # ============================================================
  flower:
    image: mher/flower:2.0
    container_name: ${CODEAWARE_FLOWER_CONTAINER_NAME:-ai-center-flower}
    depends_on:
      - celery_worker
    environment:
      CELERY_BROKER_URL: redis://redis:6380/0
      CELERY_RESULT_BACKEND: redis://redis:6380/0
    ports:
      - "${CODEAWARE_FLOWER_HOST_PORT:-5555}:5555"
    restart: unless-stopped

  # ============================================================
  # Kafka — 事件流
  # ============================================================
  kafka:
    image: bitnami/kafka:3.9
    container_name: ${CODEAWARE_KAFKA_CONTAINER_NAME:-ai-center-kafka}
    ports:
      - "${CODEAWARE_KAFKA_HOST_PORT:-9093}:9093"
    environment:
      KAFKA_CFG_NODE_ID: "1"
      KAFKA_CFG_PROCESS_ROLES: "broker,controller"
      KAFKA_CFG_CONTROLLER_QUORUM_VOTERS: "1@localhost:9091"
      KAFKA_CFG_LISTENERS: >
        PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9091,EXTERNAL://0.0.0.0:9093
      KAFKA_CFG_ADVERTISED_LISTENERS: >
        PLAINTEXT://kafka:9092,EXTERNAL://localhost:9093
      KAFKA_CFG_LISTENER_SECURITY_PROTOCOL_MAP: >
        PLAINTEXT:PLAINTEXT,CONTROLLER:PLAINTEXT,EXTERNAL:PLAINTEXT
      KAFKA_CFG_INTER_BROKER_LISTENER_NAME: PLAINTEXT
      KAFKA_CFG_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_CFG_AUTO_CREATE_TOPICS_ENABLE: "true"
      KAFKA_CFG_OFFSETS_TOPIC_REPLICATION_FACTOR: "1"
      KAFKA_CFG_LOG_RETENTION_HOURS: "168"
    volumes:
      - kafkadata:/bitnami/kafka
    healthcheck:
      test: ["CMD-SHELL", "kafka-topics.sh --bootstrap-server localhost:9092 --list"]
      interval: 10s
      timeout: 10s
      retries: 5

  # ============================================================
  # Kafka Consumer — 事件消费（日志归档）
  # ============================================================
  kafka_consumer:
    build:
      context: ./docker
      dockerfile: Dockerfile.worker
    container_name: ${CODEAWARE_KAFKA_CONSUMER_CONTAINER_NAME:-ai-center-kafka-consumer}
    depends_on:
      kafka:
        condition: service_healthy
    environment:
      KAFKA_BOOTSTRAP_SERVERS: kafka:9092
    volumes:
      - ./codeaware-py:/app
    working_dir: /app
    command: python -m app.ai.events.consumer
    restart: unless-stopped

volumes:
  # 已有 volumes 后追加
  kafkadata:
```

- [ ] **Step 4: 创建 Worker Dockerfile**

```dockerfile
# docker/Dockerfile.worker
FROM python:3.12-slim
WORKDIR /app
COPY codeaware-py/pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"
```

- [ ] **Step 5: 创建消费者入口**

```python
# docker/kafka/consumer_entry.py
"""Kafka 消费者容器入口。"""
import os
from app.ai.events.consumer import run_consumer

if __name__ == "__main__":
    run_consumer(
        bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9093"),
        group_id="codeaware-consumer",
    )
```

- [ ] **Step 6: 验证**

```bash
cd /Users/xiujiang/Documents/CC_CODE 2/ai-center
docker compose config  # 验证 YAML 无语法错误
```

- [ ] **Step 7: 提交**

```bash
git add -A && git commit -m "feat: 添加 Celery/Kafka 依赖、配置和 Docker 编排"
```

---

### 任务 2: Celery 应用定义 + 任务基类

**Files:**
- Create: `app/ai/celery_app.py`
- Create: `app/ai/tasks/__init__.py`
- Create: `app/ai/tasks/base.py`

**Interfaces:**
- Produces: `celery_app` 全局单例，`TaskBase` 基类（带重试策略和日志），可用 `from app.ai.celery_app import celery_app` 导入

- [ ] **Step 1: 创建 Celery 应用**

```python
# app/ai/celery_app.py
"""Celery 应用定义 — 任务队列入口。

使用 Redis 作为 Broker 和 Result Backend（复用现有 Redis）。
所有任务定义在 app.ai.tasks 模块下，自动注册。
"""
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "codeaware",
    broker=settings.celery_broker,
    backend=settings.celery_backend,
)

celery_app.conf.update(
    broker_url=settings.celery_broker,
    result_backend=settings.celery_backend,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_retry_delay=60,
    task_max_retries=3,
    result_expires=3600,
)

# 自动发现任务模块
celery_app.autodiscover_tasks(["app.ai.tasks"])
```

- [ ] **Step 2: 创建 tasks 包**

```python
# app/ai/tasks/__init__.py
"""异步任务模块 — 按领域分文件。"""
```

- [ ] **Step 3: 创建任务基类**

```python
# app/ai/tasks/base.py
"""任务基类 — 统一重试策略、日志、监控。"""

import logging
from typing import Any

from celery import Task

logger = logging.getLogger(__name__)


class CodeAwareTask(Task):
    """所有业务任务的基类。

    自动处理：
    - 指数退避重试（60s → 120s → 240s）
    - 结构化日志（task_id, task_name, args）
    - 异常时自动 emit Kafka 事件（如果 producer 可用）
    """

    autoretry_for = (Exception,)
    max_retries = 3
    default_retry_delay = 60
    retry_backoff = True
    retry_backoff_max = 300
    retry_jitter = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(
            "task failed task_id=%s name=%s args=%s error=%s",
            task_id, self.name, args, exc,
        )
        # 尝试发 Kafka 事件（非阻塞，失败不重试）
        self._emit_failure_event(task_id, exc)

    @staticmethod
    def _emit_failure_event(task_id: str, exc: Exception) -> None:
        try:
            from app.ai.events.producer import get_producer
            producer = get_producer()
            if producer:
                producer.send_failure_event("ops.task", {
                    "task_id": task_id,
                    "error": str(exc),
                })
        except Exception:
            pass  # Kafka 不可用时不阻塞任务失败
```

- [ ] **Step 4: 验证导入**

```bash
cd /Users/xiujiang/Documents/CC_CODE 2/ai-center/codeaware-py
uv run python -c "from app.ai.celery_app import celery_app; print(celery_app.conf)")
```

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat: Celery 应用定义 + 任务基类"
```

---

### 任务 3: 文档解析任务

**Files:**
- Create: `app/ai/tasks/document_parse.py`
- Modify: `app/ai/services/rag.py`
- Modify: `app/api/v1/knowledge.py`
- Create: `app/api/v1/tasks.py`

**Interfaces:**
- Consumes: `celery_app` from task 2, `RagService.upload_document` 的同步版本
- Produces: `parse_document_task(doc_id, title, content, source_type, project_name)` 异步任务

- [ ] **Step 1: 创建文档解析任务**

```python
# app/ai/tasks/document_parse.py
"""文档解析+分块+embedding 异步任务。

同步路径（当前）：
  上传请求 → 解析 → 分块 → embedding → 存储（全部在请求内，阻塞 ~10s+）

异步路径（改造后）：
  上传请求 → 解析 → 存父文档 → 提交任务（返回 task_id，<100ms）
  → Worker 异步：分块 → embedding → 存子文档
"""

import logging

from app.ai.celery_app import celery_app
from app.ai.infra.vector_recall import VectorRecallService
from app.ai.rag.chinese_segmenter import segment_chinese
from app.ai.rag.semantic_chunker import SemanticChunker
from app.ai.tasks.base import CodeAwareTask
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models import Document, KnowledgeChunk

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, base=CodeAwareTask, name="document.parse")
def parse_document_task(self, doc_id: int, title: str, content: str,
                        source_type: str = "MANUAL", project_name: str | None = None) -> dict:
    """异步执行文档分块+embedding+入库。

    调用时机：upload_document 已创建父文档(Document)记录后，异步完成子文档(KnowledgeChunk)。
    """
    import asyncio

    async def _run():
        chunker = SemanticChunker()
        chunks = chunker.chunk(content, content_type="md")
        # Celery Worker 是独立进程，需重新创建 VectorRecallService（不能复用 FastAPI 的 lru_cache）
        from app.ai.config import get_embedding_model
        vector_recall = VectorRecallService(get_embedding_model())

        prepared = []
        for chunk_text in chunks:
            embedding = await vector_recall.embed(chunk_text)
            prepared.append((chunk_text, embedding))

        async with AsyncSessionLocal() as session:
            doc = await session.get(Document, doc_id)
            if doc is None:
                raise ValueError(f"Document {doc_id} not found")
            for i, (chunk_text, embedding) in enumerate(prepared):
                kc = KnowledgeChunk(
                    document_id=doc_id,
                    chunk_index=i,
                    chunk_content=chunk_text,
                    chunk_content_segmented=segment_chinese(chunk_text),
                )
                await vector_recall.store_preembedded(session, kc, embedding)
            await session.commit()

        return {"doc_id": doc_id, "chunk_count": len(prepared)}

    return asyncio.get_event_loop().run_until_complete(_run())
```

- [ ] **Step 2: 修改 upload_document 支持异步模式**

```python
# app/ai/services/rag.py — 在 upload_document 方法末尾加可选参数

async def upload_document(
    self,
    title: str,
    content: str,
    source_type: str = "MANUAL",
    project_name: str | None = None,
    content_type: str = "md",
    async_mode: bool = False,  # 新增：True=只存父文档，提交异步任务
) -> Document:
    if async_mode:
        # 异步模式：只存父文档，分块和 embedding 交给 Celery
        doc = Document(title=title, source_type=source_type, project_name=project_name, content=content)
        self.session.add(doc)
        await self.session.flush()
        # 提交 Celery 任务
        from app.ai.tasks.document_parse import parse_document_task
        parse_document_task.delay(doc.id, title, content, source_type, project_name)
        return doc
    # 同步模式：保持原有逻辑不变
    chunks = self.chunker.chunk(content, content_type=content_type)
    prepared_chunks = [
        (chunk_text, await self.vector_recall.embed(chunk_text))
        for chunk_text in chunks
    ]
    doc = Document(title=title, source_type=source_type, project_name=project_name, content=content)
    self.session.add(doc)
    await self.session.flush()
    for i, (chunk_text, embedding) in enumerate(prepared_chunks):
        kc = KnowledgeChunk(
            document_id=doc.id,
            chunk_index=i,
            chunk_content=chunk_text,
            chunk_content_segmented=segment_chinese(chunk_text),
        )
        await self.vector_recall.store_preembedded(self.session, kc, embedding)
    return doc
```

- [ ] **Step 3: 修改上传接口返回 task_id**

```python
# app/api/v1/knowledge.py — 修改 upload 和 upload_file 接口

# 在 upload 方法中
rag = _rag_service(db, llm, vr, lr)
doc = await rag.upload_document(
    req.title, req.content, req.source_type, req.project_name,
    async_mode=True,  # 启用异步模式
)
# 返回 task_id（如果有）
from app.ai.tasks.document_parse import parse_document_task
async_result = parse_document_task.AsyncResult(
    parse_document_task.request.id
) if hasattr(parse_document_task, 'request') else None
return Result.ok(KnowledgeDocumentVO(
    id=doc.id,
    title=doc.title,
    task_id=parse_document_task.request.id if hasattr(parse_document_task, 'request') else None,
))
```

- [ ] **Step 4: 创建任务状态查询接口**

```python
# app/api/v1/tasks.py
"""任务状态查询 API — 供前端轮询异步任务进度。"""

import logging

from celery.result import AsyncResult
from fastapi import APIRouter

from app.ai.celery_app import celery_app
from app.core.response import Result
from app.schemas.task import TaskStatusVO

router = APIRouter(prefix="/api/tasks", tags=["Tasks"])
logger = logging.getLogger(__name__)


@router.get("/{task_id}", response_model=Result[TaskStatusVO])
async def get_task_status(task_id: str):
    """查询异步任务状态。

    返回 PENDING/STARTED/SUCCESS/FAILURE/RETRY，以及结果或错误信息。
    """
    result = AsyncResult(task_id, app=celery_app)
    return Result.ok(TaskStatusVO(
        task_id=task_id,
        status=result.status,
        ready=result.ready(),
        successful=result.successful() if result.ready() else None,
        result=result.result if result.ready() and result.successful() else None,
        error=str(result.result) if result.ready() and not result.successful() else None,
    ))
```

- [ ] **Step 5: 创建任务状态 VO**

```python
# app/schemas/task.py（新建）
from pydantic import BaseModel


class TaskStatusVO(BaseModel):
    task_id: str
    status: str  # PENDING / STARTED / SUCCESS / FAILURE / RETRY
    ready: bool
    successful: bool | None = None
    result: dict | list | str | None = None
    error: str | None = None
```

- [ ] **Step 6: 在 main.py 注册 tasks router**

```python
# app/main.py
from app.api.v1.tasks import router as tasks_router
app.include_router(tasks_router)
```

- [ ] **Step 7: 验证**

```bash
cd /Users/xiujiang/Documents/CC_CODE 2/ai-center/codeaware-py
uv run python -c "from app.ai.tasks.document_parse import parse_document_task; print(parse_document_task.name)"
```

- [ ] **Step 8: 提交**

```bash
git add -A && git commit -m "feat: 文档解析异步任务 + 任务状态查询 API"
```

---

### 任务 4: 记忆抽取异步任务

**Files:**
- Create: `app/ai/tasks/memory_extract.py`
- Modify: `app/ai/services/turn_coordinator.py`

**Interfaces:**
- Consumes: `LongTermMemoryManager.extract_facts_text`, `prepare_facts`, `save_prepared_facts`
- Produces: `extract_memory_task(conversation_id)` 异步任务

- [ ] **Step 1: 创建记忆抽取任务**

```python
# app/ai/tasks/memory_extract.py
"""Post-turn 记忆抽取异步任务。

当前：SSE 流完成后同步执行，阻塞 chat.completed 事件。
改造后：SSE 立即返回 chat.completed，Worker 异步完成抽取。
"""

import logging

from app.ai.celery_app import celery_app
from app.ai.infra.vector_recall import VectorRecallService
from app.ai.tasks.base import CodeAwareTask
from app.db.session import AsyncSessionLocal
from app.models import Message

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, base=CodeAwareTask, name="memory.extract", max_retries=2)
def extract_memory_task(self, conversation_id: str, message_count: int) -> dict:
    """异步抽取对话记忆。

    从 PG 读取最近消息 → LLM 抽取事实 → embedding → 落库。
    """
    import asyncio

    from app.ai.memory.long_term import LongTermMemoryManager
    from app.ai.config import get_chat_model

    async def _run():
        # Celery Worker 独立进程，需重新创建（不能复用 FastAPI 的 lru_cache）
        from app.ai.config import get_embedding_model, get_chat_model
        vector_recall = VectorRecallService(get_embedding_model())
        chat_model = get_chat_model()

        async with AsyncSessionLocal() as session:
            lt = LongTermMemoryManager(session, vector_recall)
            has_mem = await lt.has_memories(conversation_id)
            if has_mem:
                return {"conversation_id": conversation_id, "facts_count": 0,
                        "reason": "already_has_memories"}

            # 读最近消息
            messages = await lt.read_recent_messages(conversation_id)
            if len(messages) < message_count:
                return {"conversation_id": conversation_id, "facts_count": 0,
                        "reason": f"insufficient_messages ({len(messages)} < {message_count})"}

            # 抽取事实（纯 LLM，不持 DB 事务）
            tuples = [(m[0], m[1]) for m in messages]
            facts = await lt.extract_facts_text(tuples, chat_model)
            if not facts:
                return {"conversation_id": conversation_id, "facts_count": 0,
                        "reason": "no_facts_extracted"}

            # 准备 embedding（不持 DB 事务）
            prepared = await lt.prepare_facts(facts)

            # 写库
            async with AsyncSessionLocal() as s2:
                lt2 = LongTermMemoryManager(s2, vector_recall)
                await lt2.save_prepared_facts(conversation_id, prepared)
                await s2.commit()

            return {"conversation_id": conversation_id, "facts_count": len(prepared)}

    return asyncio.get_event_loop().run_until_complete(_run())
```

- [ ] **Step 2: 修改 turn_coordinator 提交异步任务**

```python
# app/ai/services/turn_coordinator.py — 修改 _post_turn_extraction 方法

# 在文件顶部导入
from app.core.config import settings

# 修改 _post_turn_extraction 方法（约 794 行）
async def _post_turn_extraction(self, cid, warnings: list[dict]) -> None:
    try:
        msgs, message_cache_failed = await self._load_messages(cid)
        if message_cache_failed:
            warnings.append(
                self._post_warning(cid, "message_cache", "REDIS_UNAVAILABLE",
                                   "消息缓存回填失败，已使用 PostgreSQL 真相")
            )
        if len(msgs) < MEMORY_EXTRACT_THRESHOLD:
            return
        # 异步模式：提交 Celery 任务，不阻塞
        from app.ai.tasks.memory_extract import extract_memory_task
        extract_memory_task.delay(cid, MEMORY_EXTRACT_THRESHOLD)
        logger.info("memory extraction submitted task_id=%s conversation_id=%s",
                    extract_memory_task.request.id, cid)
    except Exception as exc:
        logger.warning("memory extraction submit failed conversation_id=%s error=%s", cid, exc)
        warnings.append(
            self._post_warning(cid, "memory_extraction", "EXTRACTION_FAILED", "记忆抽取任务提交失败")
        )
```

- [ ] **Step 3: 验证**

```bash
cd /Users/xiujiang/Documents/CC_CODE 2/ai-center/codeaware-py
uv run python -c "from app.ai.tasks.memory_extract import extract_memory_task; print(extract_memory_task.name)"
```

- [ ] **Step 4: 提交**

```bash
git add -A && git commit -m "feat: 记忆抽取异步任务（Celery）"
```

---

### 任务 5: Kafka 事件定义 + Producer

**Files:**
- Create: `app/ai/events/__init__.py`
- Create: `app/ai/events/schemas.py`
- Create: `app/ai/events/producer.py`

**Interfaces:**
- Produces: `get_producer()` 返回 Kafka Producer 单例；事件类型定义在 `schemas.py`；`emit_event(topic, key, data)` 发送事件

- [ ] **Step 1: 创建事件包**

```python
# app/ai/events/__init__.py
"""Kafka 事件流 — 审计日志 + 指标事件。"""
```

- [ ] **Step 2: 创建事件类型定义**

```python
# app/ai/events/schemas.py
"""事件类型定义（Pydantic），对齐 Kafka topic 路由。

Topic 命名规则：{prefix}{domain}.{action}
- 审计类：audit.document, audit.conversation
- 指标类：metrics.retrieval, metrics.task
- 运维类：ops.error
"""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class BaseEvent(BaseModel):
    """所有 Kafka 事件的基类。

    投递语义：
    - 审计/异常/任务类（audit.*, ops.*）→ **至少一次**（Producer 幂等 + Consumer 去重）
    - 指标类（metrics.*）→ **至多一次**（可丢，不重复）
    - 去重方式：Consumer 按 event_id 幂等消费
    """
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_id: str = ""  # UUID，由 producer 填充，Consumer 用于去重


# ── 审计事件 ──

class DocumentAuditEvent(BaseEvent):
    """文档操作审计（上传/删除/替换）。"""
    action: str  # CREATED / DELETED / REPLACED
    document_id: int
    title: str
    user_id: str | None = None
    source_type: str = ""
    project_name: str | None = None


class ConversationAuditEvent(BaseEvent):
    """对话操作审计。"""
    action: str  # CREATED / COMPLETED
    conversation_id: str
    turn_id: str
    user_id: str | None = None
    message_count: int = 0
    elapsed_ms: int = 0


# ── 指标事件 ──

class RetrievalMetricsEvent(BaseEvent):
    """检索指标（每次查询）。"""
    query: str = ""  # 仅记录前 80 字符
    route: str  # retrieve / direct
    lexical_backend: str  # bm25 / pg_trgm
    elapsed_ms: int
    doc_count: int
    retries: int = 0
    match_types: list[str] = []
    rag_runtime: str = "graph"


class TaskMetricsEvent(BaseEvent):
    """任务生命期事件。"""
    task_id: str
    task_name: str
    status: str  # STARTED / SUCCESS / FAILURE / RETRY
    elapsed_ms: int = 0
    result: dict[str, Any] | None = None
    error: str | None = None


# ── 运维事件 ──

class ErrorEvent(BaseEvent):
    """系统异常事件。"""
    component: str  # rag_retrieval / memory_recall / embedding / api
    code: str
    message: str
    details: dict[str, Any] | None = None
```

- [ ] **Step 3: 创建 Kafka Producer**

```python
# app/ai/events/producer.py
"""Kafka Producer 单例 — 非阻塞 fire-and-forget。

Producer 在应用启动时惰性初始化，初始化失败不阻塞应用启动。
所有 send 调用都是异步 fire-and-forget，失败只记日志不抛异常。
"""

import json
import logging
from typing import Any

from kafka import KafkaProducer

from app.core.config import settings

logger = logging.getLogger(__name__)

_producer: KafkaProducer | None = None


def get_producer() -> KafkaProducer | None:
    """获取 Kafka Producer 单例（惰性初始化）。"""
    global _producer
    if _producer is None:
        _producer = _init_producer()
    return _producer


def _init_producer() -> KafkaProducer | None:
    try:
        # 至少一次语义（acks=all, retries=3, enable_idempotence=True）：
        # 消息不会丢，但可能重复。消费者端通过 event_id 去重。
        producer = KafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks="all",                # 所有副本确认，保证不丢
            retries=3,                 # 重试 3 次
            enable_idempotence=True,   # 幂等 Producer，防止重试导致重复写入
            max_in_flight_requests_per_connection=5,
            request_timeout_ms=3000,
        )
        logger.info("Kafka producer initialized servers=%s", settings.kafka_bootstrap_servers)
        return producer
    except Exception as exc:
        logger.warning("Kafka producer init failed (non-blocking): %s", exc)
        return None


def emit_event(topic: str, key: str | None, data: dict[str, Any]) -> None:
    """发送事件到 Kafka（非阻塞，失败不抛异常）。"""
    producer = get_producer()
    if producer is None:
        return
    try:
        future = producer.send(
            f"{settings.kafka_topic_prefix}{topic}",
            key=key,
            value=data,
        )
        # 不阻塞等待结果
        future.add_errback(lambda e: logger.warning("Kafka send failed topic=%s error=%s", topic, e))
    except Exception as exc:
        logger.warning("Kafka emit failed topic=%s error=%s", topic, exc)


def emit_document_event(action: str, document_id: int, title: str,
                        user_id: str | None = None, **kwargs) -> None:
    """便捷方法：发送文档审计事件。"""
    from app.ai.events.schemas import DocumentAuditEvent
    event = DocumentAuditEvent(
        action=action, document_id=document_id, title=title,
        user_id=user_id, **kwargs,
    )
    emit_event("audit.document", key=str(document_id), data=event.model_dump())


def emit_retrieval_metrics(**kwargs) -> None:
    """便捷方法：发送检索指标事件。"""
    from app.ai.events.schemas import RetrievalMetricsEvent
    event = RetrievalMetricsEvent(**kwargs)
    emit_event("metrics.retrieval", key=None, data=event.model_dump())


def emit_error_event(component: str, code: str, message: str, **kwargs) -> None:
    """便捷方法：发送异常事件。"""
    from app.ai.events.schemas import ErrorEvent
    event = ErrorEvent(component=component, code=code, message=message, details=kwargs or None)
    emit_event("ops.error", key=code, data=event.model_dump())
```

- [ ] **Step 4: 验证导入**

```bash
cd /Users/xiujiang/Documents/CC_CODE 2/ai-center/codeaware-py
uv run python -c "from app.ai.events.producer import get_producer; print('producer module ok')"
```

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat: Kafka 事件定义 + Producer（审计/指标/异常事件）"
```

---

### 任务 6: Kafka Consumer（日志归档）

**Files:**
- Create: `app/ai/events/consumer.py`
- Modify: `docker-compose.yml`（kafka_consumer 已加，验证配置）

**Interfaces:**
- Consumes: Kafka topics `codeaware.audit.*`, `codeaware.metrics.*`, `codeaware.ops.*`
- Produces: 日志文件归档（结构化 JSON 日志）

- [ ] **Step 1: 创建 Kafka Consumer**

```python
# app/ai/events/consumer.py
"""Kafka Consumer — 事件消费端。

独立进程运行（kafka_consumer 容器），负责：
1. 审计事件 → 归档到日志文件（按日期分片）
2. 指标事件 → 汇总到结构化日志（可接 Prometheus 等监控）
3. 异常事件 → 实时告警日志

当前实现：结构化日志输出（awaiting 后续接入正式监控系统时替换）。
"""

import json
import logging
import os
from datetime import date

from kafka import KafkaConsumer

logger = logging.getLogger(__name__)

# 审计日志目录
AUDIT_LOG_DIR = os.getenv("AUDIT_LOG_DIR", "/var/log/codeaware/audit")


def _get_audit_logger(topic: str) -> logging.Logger:
    """按 topic 获取对应的审计日志 logger。"""
    log_name = topic.replace(".", "_")
    audit_logger = logging.getLogger(f"audit.{log_name}")
    if not audit_logger.handlers:
        os.makedirs(AUDIT_LOG_DIR, exist_ok=True)
        handler = logging.FileHandler(
            f"{AUDIT_LOG_DIR}/{log_name}_{date.today().isoformat()}.log"
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"
        ))
        audit_logger.addHandler(handler)
        audit_logger.setLevel(logging.INFO)
        audit_logger.propagate = False
    return audit_logger


def run_consumer(bootstrap_servers: str = "localhost:9093",
                 group_id: str = "codeaware-consumer") -> None:
    """启动 Kafka 消费者（阻塞运行）。

    投递语义：
    - audit.* / ops.* → 至少一次（手动提交 offset，失败不提交 → 重启后重消费）
    - metrics.* → 至多一次（先提交 offset 再处理，丢几条指标可接受）
    - 审计事件按 event_id 去重（幂等消费者）
    """
    consumer = KafkaConsumer(
        bootstrap_servers=bootstrap_servers,
        group_id=group_id,
        enable_auto_commit=False,  # 手动控制 offset 提交
        auto_offset_reset="earliest",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        key_deserializer=lambda k: k.decode("utf-8") if k else None,
    )
    # 订阅所有 codeaware 事件
    consumer.subscribe(pattern="codeaware\\..*")

    # 去重缓存（只保最近 1000 条 event_id，防止内存泄漏）
    _seen_ids: set[str] = set()

    logger.info("Kafka consumer started servers=%s group=%s", bootstrap_servers, group_id)
    try:
        for msg in consumer:
            topic = msg.topic.replace("codeaware.", "", 1)
            value = msg.value or {}
            is_metrics = topic.startswith("metrics.")

            # 至少一次：先处理，再提交
            if not is_metrics:
                event_id = value.get("event_id", "")
                if event_id:
                    if event_id in _seen_ids:
                        consumer.commit()  # 跳过重复，但提交 offset
                        continue
                    _seen_ids.add(event_id)
                    if len(_seen_ids) > 1000:
                        _seen_ids.clear()

                audit_logger = _get_audit_logger(topic)
                audit_logger.info(
                    "topic=%s key=%s value=%s",
                    topic, msg.key, json.dumps(value, ensure_ascii=False),
                )
                # 处理完成后手动提交 offset（至少一次语义）
                consumer.commit()
            else:
                # 至多一次：先提交 offset，再处理（丢数据不丢 offset）
                consumer.commit()
                audit_logger = _get_audit_logger(topic)
                audit_logger.info(
                    "topic=%s key=%s value=%s",
                    topic, msg.key, json.dumps(value, ensure_ascii=False),
                )
    except KeyboardInterrupt:
        logger.info("Kafka consumer shutting down")
    finally:
        consumer.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_consumer()
```

- [ ] **Step 2: 验证**

```bash
cd /Users/xiujiang/Documents/CC_CODE 2/ai-center/codeaware-py
uv run python -c "from app.ai.events.consumer import run_consumer; print('consumer module ok')"
```

- [ ] **Step 3: 提交**

```bash
git add -A && git commit -m "feat: Kafka Consumer 日志归档"
```

---

### 任务 7: 集成埋点 — 在关键路径上发 Kafka 事件

**Files:**
- Modify: `app/ai/services/turn_coordinator.py`（检索/对话完成后发事件）
- Modify: `app/api/v1/knowledge.py`（文档操作发审计事件）
- Modify: `app/ai/rag/rag_graph.py`（检索结果发指标事件）

**Interfaces:**
- Consumes: `emit_document_event`, `emit_retrieval_metrics`, `emit_error_event` from task 5

- [ ] **Step 1: 文档操作审计埋点**

```python
# app/api/v1/knowledge.py — 在 upload 和 delete 成功后加事件

# 在 upload 方法末尾，return Result.ok(...) 之前
from app.ai.events.producer import emit_document_event
emit_document_event("CREATED", doc.id, doc.title, source_type=req.source_type)

# 在 delete 方法末尾，return Result.ok() 之前
emit_document_event("DELETED", doc_id, title="", user_id=None)
```

- [ ] **Step 2: 检索指标埋点**

```python
# app/ai/rag/rag_graph.py — 在 run 方法末尾，return result 之前

from app.ai.events.producer import emit_retrieval_metrics
emit_retrieval_metrics(
    query=message[:80],
    route=result.route,
    lexical_backend="bm25",  # 或从配置读取
    elapsed_ms=int((time.perf_counter() - _start) * 1000) if '_start' in dir() else 0,
    doc_count=len(result.docs),
    retries=result.retries,
    rag_runtime="graph",
)
```

- [ ] **Step 3: 异常事件埋点**

```python
# app/ai/services/turn_coordinator.py — 在降级/异常处加事件

from app.ai.events.producer import emit_error_event

# 在 _log_degradation 或 _log_failure 方法中
emit_error_event(
    component=component,
    code=code,
    message=message,
)
```

- [ ] **Step 4: 验证**

```bash
cd /Users/xiujiang/Documents/CC_CODE 2/ai-center/codeaware-py
uv run python -c "from app.ai.events.producer import emit_document_event, emit_retrieval_metrics; print('event emitters ok')"
```

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat: 关键路径埋点 — 文档审计/检索指标/异常事件"
```

---

## 验证方案

### 单元测试

```bash
# 验证 Celery 应用配置
cd /Users/xiujiang/Documents/CC_CODE 2/ai-center/codeaware-py
uv run python -c "
from app.ai.celery_app import celery_app
assert celery_app.conf.task_serializer == 'json'
assert celery_app.conf.broker_url.startswith('redis://')
print('Celery config OK')
"
```

### 集成测试

```bash
# 启动所有服务
cd /Users/xiujiang/Documents/CC_CODE 2/ai-center
docker compose up -d

# 验证 Celery Worker 可用
docker exec ai-center-celery-worker celery -A app.ai.celery_app status

# 验证 Flower 面板
curl -s http://localhost:5555 | head -5

# 验证 Kafka 可用
docker exec ai-center-kafka kafka-topics.sh --bootstrap-server localhost:9092 --list

# 上传文档测试异步任务
curl -X POST http://localhost:8000/api/knowledge/upload \
  -H "Content-Type: application/json" \
  -d '{"title":"test","content":"## Test\nHello","source_type":"MANUAL"}'
# 检查返回的 task_id，然后查询状态
curl http://localhost:8000/api/tasks/{task_id}
```

### 完整回归

```bash
cd /Users/xiujiang/Documents/CC_CODE 2/ai-center/codeaware-py
uv run python scripts/run_tests_safe.py -q
cd frontend && npm run test && npm run lint && npm run build
```

---

## 后续优化项：Ollama GPU 加速

**当前瓶颈**：Ollama bge-m3 embedding 跑在 CPU 上，单次 ~5.8s，占单次检索总延迟的 96%。

**目标**：通过 GPU 加速将 embedding 延迟降到 ~0.1-0.5s，释放 Celery Worker 并发能力。

### 前提

- macOS：Docker Desktop 不能直通 GPU，需用宿主机原生 Ollama（Metal GPU 加速）
- Linux：Docker 加 `nvidia-container-toolkit` + GPU 配置

### 改动

```yaml
# docker-compose.yml — Linux 方案
ollama:
  image: ollama/ollama:latest
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

macOS 直接用宿主机原生 Ollama，改 `OLLAMA_BASE_URL=http://host.docker.internal:11434`。

### 预期收益

| 指标 | 当前（CPU） | 加 GPU 后 |
|---|---|---|
| embedding 单次 | ~5.8s | ~0.1-0.3s |
| 单次检索总延迟 | ~6.0s | ~0.5s |
| 可用 Worker 并发 | 2（抢 CPU） | 4-8（I/O 为主） |

---

## 风险

| 风险 | 缓解 |
|---|---|
| Celery Worker 无法访问 Ollama 容器 | Worker 容器通过 `depends_on` 确保 Ollama 先启动，环境变量 `OLLAMA_BASE_URL=http://ollama:11434` |
| Kafka Consumer 挂了导致事件丢失 | Kafka 消息保留 7 天，Consumer 重启后从上次 offset 继续消费 |
| 异步任务执行失败导致文档无 chunk | 任务失败时 emit 异常事件，可人工介入重跑；API 返回 task_id 供前端轮询 |
| Flower 暴露内部信息 | Flower 仅监听 5555，不对外开放端口；生产部署可加 nginx 认证 |
| 同步/异步模式切换影响现有测试 | 测试环境保持同步模式（`async_mode=False`），不依赖 Celery |