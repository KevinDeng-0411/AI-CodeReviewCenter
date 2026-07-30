# CodeAware Python 0.1.0

当前目标实现。核心域为 Chat，Code Review、Unit Test、AIReadMe、Knowledge、Memory 和
Prompt 复用 FastAPI/LangChain/SQLAlchemy/pgvector/Redis 基建。

- C1 Evidence：[报告](../docs/roadmap/current-release/evidence/C1/report.md)
- C2 Evidence：[报告](../docs/roadmap/current-release/evidence/C2/report.md)
- 当前阶段：C3 版本冻结
- 下一阶段：C4 BM25；Agent 仍未实现

通用编码和安全规则见上级 [AGENTS.md](../AGENTS.md)，文档入口见
[docs/INDEX.md](../docs/INDEX.md)。

## 环境准备

从仓库根执行：

```bash
docker compose up -d
./codeaware-py/scripts/ensure_python_db.sh
docker compose exec ollama ollama pull bge-m3
(cd codeaware-py && cp .env.example .env)
(cd codeaware-py && uv sync)
(cd codeaware-py && uv run alembic upgrade head)
```

`.env` 至少填写有效 `LLM_API_KEY`。默认连接：

| 依赖 | 地址 / 数据库 |
|---|---|
| PostgreSQL | `localhost:5433 / ai_center_py` |
| Redis | `localhost:6380 / DB 0` |
| Ollama | `http://localhost:11434` |
| DeepSeek | `https://api.deepseek.com/v1` |

全新 volume 会同时创建 Java `ai_center` 和 Python `ai_center_py`；已有 volume 只通过
`ensure_python_db.sh` 幂等补建，不需要删除 volume。

## 启动

后端：

```bash
(cd codeaware-py && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000)
```

前端：

```bash
(cd codeaware-py/frontend && npm ci)
(cd codeaware-py/frontend && npm run dev)
```

- 前端：http://localhost:5173
- OpenAPI：http://localhost:8000/docs
- `/health/live`：进程存活
- `/health/ready`：PostgreSQL、Redis、Ollama readiness
- `/api/ai/health`：真实 LLM/Embedding/pgvector 诊断

## 测试

禁止裸跑 pytest、手工 migration downgrade 或对固定数据库执行 destructive fixture。
所有后端测试统一通过 fail-closed 安全执行器：

```bash
(cd codeaware-py && uv run python scripts/run_tests_safe.py -q)
(cd codeaware-py && uv run python scripts/run_tests_safe.py --cov=app --cov-report=term-missing -q)
(cd codeaware-py && uv run python scripts/run_tests_safe.py tests/contracts tests/e2e -q)
(cd codeaware-py && uv run python scripts/run_tests_safe.py --browser-e2e)
```

前端：

```bash
(cd codeaware-py/frontend && npm run test)
(cd codeaware-py/frontend && npm run lint)
(cd codeaware-py/frontend && npm run build)
```

Fresh bootstrap：

```bash
./codeaware-py/scripts/verify_fresh_bootstrap.sh
```

七域 mocked 演示：

```bash
./codeaware-py/scripts/demo_c2_mocked.sh
```

真实依赖 smoke（显式产生 DeepSeek 调用）：

```bash
./codeaware-py/scripts/demo_c2_live.sh
```

## 本地能力安全边界

AIReadMe 快照默认关闭且没有隐式宿主目录。启用时：

```dotenv
AI_README_SNAPSHOT_ENABLED=true
LOCAL_PROJECT_ROOTS=["/absolute/server/fixture-root"]
```

只允许专用无敏感 fixture；请求根和嵌套 symlink、越界路径、密钥/证书、二进制与超限
内容均被拒绝。服务不会运行项目命令或保存完整 snapshot。

Knowledge 文件上传支持 PDF、DOCX、HTML、Markdown、TXT，默认上限为 5 MiB 原始文件与
200,000 个解析字符。

当前检索为 `pg_trgm + pgvector + RRF`；`pg_trgm` 不是 BM25。C4 之前不得宣称已经实现
BM25、rerank 或 Agent。
