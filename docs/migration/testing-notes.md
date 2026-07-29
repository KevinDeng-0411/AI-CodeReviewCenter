# 测试与集成踩坑留痕

> 迁移过程中遇到的测试/集成坑，记录症状/根因/解法，避免重复踩。

## 1. langchain 1.x 导入 hang（LangSmith / 遥测网络请求）

- **症状**：`from langchain_openai import ChatOpenAI` 卡死——pytest 无输出、app 启动无响应。
- **根因**：langchain 1.x 导入 `langchain_openai` 时发起 LangSmith tracing / 匿名遥测网络请求；网络不通则 hang（P3-1 时网络通未暴露，P3-2 时触发）。
- **定位**：`LANGCHAIN_TRACING_V2=false ANONYMIZED_TELEMETRY=false` 后导入秒过。
- **解法**：`app/__init__.py`（在 langchain 导入前执行）
  ```python
  os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
  os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
  ```
  `setdefault` 不覆盖显式启用。
- **注意**：本项不用 LangSmith；若未来启用 tracing，移除该 setdefault 或显式设 env。

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
