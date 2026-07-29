# 测试与集成踩坑留痕

> 迁移过程中遇到的测试/集成坑，记录症状/根因/解法，避免重复踩。
>
> **当前安全覆盖规则**：本文件记录的是历史做法，不是可直接复制的测试命令。C1 完成前禁止裸跑 pytest、固定库 migration roundtrip 或 Redis flush；现有 fixture 的 `setdefault` 可能保留调用者导出的开发库配置。先执行[当前版本 C1 的 fail-closed 安全测试入口](../roadmap/current-release/01-当前缺口修复.md)，最终以[统一证据规则](../roadmap/证据清单与解锁规则.md)为准。

## 1. langchain 1.x / unstructured 导入与调用 hang（库遥测网络请求）

- **症状**：`from langchain_openai import ChatOpenAI` 卡死；`unstructured.partition.md.partition_md` 调用卡死--pytest 无输出、app 启动无响应。
- **根因**：langchain 1.x 导入时发起 LangSmith tracing / 匿名遥测网络请求；unstructured 的 partition 调用发起匿名遥测（`run_halo`）。网络不通则 hang（P3-1 时网络通未暴露，P3-2/P3-3 时触发）。
- **定位**：`LANGCHAIN_TRACING_V2=false ANONYMIZED_TELEMETRY=false`（langchain）/ `UNSTRUCTURED_TELEMETRY_DISABLE=1`（unstructured）后秒过。
- **解法**：`app/__init__.py`（库导入/调用前执行）
  ```python
  os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
  os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
  os.environ.setdefault("UNSTRUCTURED_TELEMETRY_DISABLE", "1")
  ```
  `setdefault` 不覆盖显式启用。
- **注意**：本项不用 LangSmith/unstructured 遥测；若未来启用，移除相应 setdefault 或显式设 env。
- **规律**：AI/解析类库常带匿名遥测，网络受限环境会 hang 导入/调用；引入新库先查遥测开关。

## 2. test_migration 子进程慢（uv run alembic ×5，全量 84s）

- **症状**：全量测试 84s；排除 test_migration 后 0.62s。
- **根因**：test_migration 用 5 次 `uv run alembic` 子进程，uv 启动 + 环境校验开销大（lock 变更后尤甚）。
- **解法**：改 alembic `command` API（同步测试；内部 `asyncio.run`，sync 测试无运行 loop 不与 pytest-asyncio session loop 冲突）。经 `settings.pg_db` 临时切 `ai_center_migtest`，env.py 自动连独立库。
- **结果**：84s -> 0.74s。
- **要点**：sync 测试调 alembic command API 可行；async 测试中调会与运行中的 loop 冲突（那时需子进程或 `run_sync`）。

## 3. asyncpg / redis 异步客户端与测试事件循环

- **现象**：`redis.asyncio` 客户端若在模块导入时创建，可能绑定到非测试 loop，操作时 hang。
- **约定**：测试中异步客户端（redis 等）在 **fixture 内创建**（绑定 session loop），不用模块级单例。app 生产用的模块级客户端不影响（uvicorn 单 loop）。
- **已应用**：`tests/conftest.py` 的 `redis_client` fixture 内 `aioredis.from_url(...)`，每测试 flushdb 隔离。

## 4. e2e_smoke.py 不被默认收集（文件名不匹配 python_files）

- **症状**：`pytest tests/e2e_smoke.py` 单独跑能收集通过；全量 `pytest` 却不收集它（计数不变，覆盖率不增）。
- **根因**：pytest 默认 `python_files = test_*.py *_test.py`，`e2e_smoke.py` 既不以 `test_` 开头也不以 `_test.py` 结尾 -> 不被视为测试文件。显式传路径时才收集。
- **解法**：`pyproject.toml` 的 `[tool.pytest.ini_options]` 加 `python_files = ["test_*.py", "*_test.py", "e2e_*.py"]`，保留 `e2e_smoke.py` 命名（语义为冒烟脚本）同时被全量收集。
- **规律**：非 `test_` 前缀的测试文件（如 `e2e_*` / `*_smoke`）需显式配置 `python_files`，否则只在显式指定路径时才跑。

## 5. 裸 ORM 经 Result(Pydantic) 序列化抛 PydanticSerializationError

- **症状**：`GET /api/chat/conversations` 返回 500，`PydanticSerializationError: Unable to serialize unknown type: <class 'Conversation'>`。
- **根因**：`Result(BaseModel, Generic[T])` 的 `data: T | None`，`Result.ok(orm_obj)` 时 T 未绑定等同 `Any`；Pydantic v2 序列化 `Any` 字段里的 SQLAlchemy ORM 对象（非 Pydantic model / 基础类型）抛错。FastAPI 返回 Pydantic model 时走 Pydantic 序列化，不会 fallback 到 `jsonable_encoder` 的 ORM `__dict__`。
- **波及**：所有"返回裸 ORM"的端点--`/api/chat/conversations`、`/api/chat/conversations/{id}`、`/api/code-review/records`、`/api/code-review/records/{id}`、`/api/unit-test/records*`。此前零测试覆盖，故未暴露。
- **解法**：router 层投影成 dict（与 knowledge/memory/prompt 端点既有模式一致）。`AiOperationRecord` 抽共享 `record_to_dict`（`app/schemas/entities.py`），ORM 属性 `meta` -> 对外字段 `metadata`（规避 `DeclarativeBase.metadata` 冲突）。
- **规律**：FastAPI + Pydantic v2 下，端点不要直接 `Result.ok(orm_obj)`；统一在 router 层投影成 dict 或 `Schema.model_validate(orm)`（注意 ORM 属性名与 schema 字段名映射，如 `meta`/`metadata`）。e2e 全链路是发现此类契约 bug 的有效手段。

## 6. get_db 不 commit -> 所有写端点不落盘（p0 级阻塞）

> **历史修复记录，当前 Chat/SSE 不得复制。** “等待 StreamingResponse teardown 后统一 commit”无法满足 C1 的 `chat.started/completed` 真实时序；当前同步/流式路径必须由 TurnCoordinator 显式拥有短事务，PG commit 后才刷新 Redis。见[当前版本 C1](../roadmap/current-release/01-当前缺口修复.md)。

- **症状**：真实跑应用时，知识库上传返回 doc_id、CR 返回结果、Chat 返回回复，但**重启/另开会话查不到任何数据**；RAG 检索永远命中 0 条（chunks 被回滚）。
- **根因**：`get_db` 只 `yield session` 不 commit；service 层（CR/knowledge/memory/chat）只 `flush` 不 `commit`。请求结束 `async with` 关闭 session -> 事务回滚 -> 数据丢失。测试没抓到：测试用 `dependency_overrides[get_db] = lambda: db_session`，db_session 是共享事务、uncommitted 也可见，回滚仅用于隔离。
- **解法**：`get_db` 成功时 `commit`、异常时 `rollback`：
  ```python
  async def get_db():
      async with AsyncSessionLocal() as session:
          try:
              yield session
              await session.commit()
          except Exception:
              await session.rollback()
              raise
  ```
  这段只解释当时如何修复普通请求的“完全不提交”；它不是当前 SSE 事务方案。
- **当前规律**：普通请求可以使用 dependency commit；流式 Chat 必须显式拥有并提交短事务，不能依赖响应结束后的 teardown。纯单元测试仍容易漏掉持久化层，需隔离 e2e/真实启动验证。

## 7. 0001 仅 seed CODE_REVIEW -> UNIT_TEST/AI_README 抛「未找到模板」

- **症状**：`/api/unit-test/generate`、`/api/ai-readme/generate` 返回 `code=0 未找到 UNIT_TEST/AI_README Prompt 模板`；CHAT 退化为硬编码 fallback。
- **根因**：迁移文档 §7.2.3 本应 seed 4 类（CODE_REVIEW/CHAT/UNIT_TEST/AI_README），但 0001 只 seed 了 CODE_REVIEW 七层 Prompt。
- **解法**：补 0002 迁移 seed CHAT/UNIT_TEST/AI_README active v1（模板 body 含各自占位符 + json_mode 输出契约）。
- **规律**：迁移 seed 完整性需对照设计文档逐 type 核对；`get_active(type)` 返回 None 时服务抛 BusinessException 是兜底，但正常使用前应确保 4 类模板齐全。
