# CodeAware

AI 驱动的研发效能平台。当前目标实现位于 `codeaware-py/`，核心域是 Chat：多轮对话、
短期窗口与增量摘要、长期记忆、Knowledge RAG 和版本化 Prompt 在同一条问答链路中收敛。
Code Review、Unit Test、AIReadMe 是复用同一 AI 基建的薄工具。

仓库中的 `ai-center-*` Java 模块是迁移前的 legacy 参考，不再作为当前 API、启动方式或
阶段验收依据。

## 当前状态

- 当前版本：`0.1.0`
- Python HTTP 契约：27 个 paths、29 个 operations，以
  [OpenAPI 快照](codeaware-py/openapi/current-release.json)为准
- C1 真实缺口修复：[Evidence](docs/roadmap/current-release/evidence/C1/report.md)
- C2 七域 API/持久化/UI 闭环：[Evidence](docs/roadmap/current-release/evidence/C2/report.md)
- C3 版本冻结与交接：[Evidence](docs/roadmap/current-release/evidence/C3/report.md)
- 当前冻结基线：C3 已完成
- 下一阶段：C4 真实 BM25 词法召回增强，未开始
- Agent：未来方向，尚未实现且保持锁定

完整顺序见[当前版本与检索增强路线](docs/roadmap/current-release/README.md)。

## 已实现能力

| 领域 | 当前能力 |
|---|---|
| Chat | 同步/typed SSE、多轮持久化、取消/并发保护、PG 真相源与 Redis 缓存 |
| 短期记忆 | 最近消息窗口、增量摘要、水位线、PG/Redis 一致性与 fallback |
| 长期记忆 | FACT/REFERENCE 原子事实、bge-m3 向量召回、对话来源追踪 |
| Knowledge / RAG | 文本与文件上传、Document/Chunk 父子表、pgvector + `pg_trgm` + RRF |
| Prompt | 四类模板、append-only 版本、预览、激活和回滚 |
| Code Review | 选定/active Prompt、Pydantic 结构化结果、审计记录 |
| Unit Test | 生成并保存 JUnit5 测试代码；不执行生成代码 |
| AIReadMe | allowlist 内有界只读快照、稳定 hash、版本递增 |

当前关键词腿是 PostgreSQL `pg_trgm similarity`，属于模糊字符串召回，**不是 BM25**。
真正的 BM25 实施边界见[C4 计划](docs/roadmap/current-release/04-BM25检索增强.md)。

## 技术栈

- Python 3.12、FastAPI、Pydantic v2
- LangChain model/embedding adapter、DeepSeek
- SQLAlchemy 2.0 async、Alembic、asyncpg
- PostgreSQL 16、pgvector、`pg_trgm`
- Redis 7、Ollama bge-m3（1024 维）
- React 19、Vite、TypeScript、Vitest、Playwright
- uv、pytest、httpx

## 快速启动

需要 Docker Desktop/Compose、Python 3.12、uv 和 Node.js/npm；七域浏览器验收还需要
Chrome。所有命令从仓库根执行。全新 Compose volume 会创建 Java `ai_center` 和 Python
`ai_center_py`；已有 volume 用幂等脚本补建 Python 数据库，不删除现有数据。

```bash
docker compose up -d
./codeaware-py/scripts/ensure_python_db.sh
docker compose exec ollama ollama pull bge-m3
(cd codeaware-py && cp .env.example .env)
# 编辑 codeaware-py/.env，填写有效 LLM_API_KEY
(cd codeaware-py && uv sync)
(cd codeaware-py && uv run alembic upgrade head)
(cd codeaware-py && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000)
```

另开终端启动前端：

```bash
(cd codeaware-py/frontend && npm ci)
(cd codeaware-py/frontend && npm run dev)
```

- 前端：http://localhost:5173
- OpenAPI：http://localhost:8000/docs
- liveness：http://localhost:8000/health/live
- readiness：http://localhost:8000/health/ready
- AI 依赖诊断：http://localhost:8000/api/ai/health

## typed SSE 示例

新会话的 `conversation_id` 由服务端创建并在 `chat.started` 中返回：

```bash
curl -N http://localhost:8000/api/chat/send/stream \
  -H 'Content-Type: application/json' \
  -d '{"conversation_id":null,"message":"解释当前 RAG 完整链路"}'
```

响应是版本化事件，不是裸 token 或 `[DONE]`：

```text
id: 1
event: chat.started
data: {"protocol_version":1,"conversation_id":"...","turn_id":"...","sequence":1,"created":true}

id: 2
event: token.delta
data: {"protocol_version":1,"conversation_id":"...","turn_id":"...","sequence":2,"delta":"..."}

event: chat.completed
data: {"protocol_version":1,"conversation_id":"...","turn_id":"...","sequence":4,"assistant_message_id":1,"warning_count":0}
```

后续请求把该 `conversation_id` 原样传回；项目中不使用 `session_id`。

## 安全测试与演示

后端测试禁止裸跑 `pytest`。安全执行器会创建带随机 identity 的一次性 PostgreSQL/Redis，
拒绝开发库、Redis DB 0、远程目标和伪造 sentinel，并在成功、失败或中断后精确清理。

```bash
./codeaware-py/scripts/verify_current_release.sh
(cd codeaware-py && uv run python scripts/run_tests_safe.py -q)
(cd codeaware-py && uv run python scripts/run_tests_safe.py --cov=app --cov-report=term-missing -q)
(cd codeaware-py/frontend && npm run test)
(cd codeaware-py/frontend && npm run lint)
(cd codeaware-py/frontend && npm run build)
./codeaware-py/scripts/demo_c2_mocked.sh
./codeaware-py/scripts/demo_c3_handoff.sh
```

空 volume 验证：

```bash
./codeaware-py/scripts/verify_fresh_bootstrap.sh
```

真实 DeepSeek/Ollama smoke 会产生实际 API 调用，只在本地显式执行：

```bash
./codeaware-py/scripts/demo_c2_live.sh
```

冻结版本的安全回退演练只使用 detached 临时 worktree 和一次性数据库：

```bash
./codeaware-py/scripts/verify_c3_rollback.sh
```

完整预期输出和交接顺序见[C3 交接运行手册](docs/roadmap/current-release/C3-交接运行手册.md)，
版本变化与限制见[0.1.0 发布说明](docs/releases/0.1.0.md)。

## AIReadMe 与文件安全

AIReadMe 快照默认关闭。启用时 `LOCAL_PROJECT_ROOTS` 只能配置专用、无敏感信息的服务端
绝对目录；扫描拒绝越界、symlink、密钥、二进制、超限文件和项目命令执行。

Knowledge 文件上传支持 PDF、DOCX、HTML、Markdown、TXT，默认限制为 5 MiB 原始文件和
200,000 个解析后字符。上传内容不会被执行。

## 当前限制

- local-first、单用户；尚无认证、RBAC 或多租户隔离。
- 同一会话 turn guard 是进程内实现，当前只支持单 worker；多 worker 前需改为 PG lease。
- Unit Test 只生成并保存测试源码，不运行测试。
- 普通 CI 使用 fake LLM/embedder；真实依赖只由显式 live smoke 验证。
- Knowledge 词法腿当前是 `pg_trgm`，C4 才实施真实 BM25。
- 没有 Agent Tool loop、Citation、仓库索引、shell、patch、Git 写入或多 Agent。

## 文档入口

- 通用开发规则：[AGENTS.md](AGENTS.md)
- 文档索引：[docs/INDEX.md](docs/INDEX.md)
- ADR：[docs/decisions/adr/](docs/decisions/adr/)
- 当前路线：[docs/roadmap/current-release/README.md](docs/roadmap/current-release/README.md)
- 面试准备：[docs/interview/面试准备指南.md](docs/interview/面试准备指南.md)
- DeepSeek 集成：[docs/integration/deepseek-notes.md](docs/integration/deepseek-notes.md)
- 当前发布说明：[docs/releases/0.1.0.md](docs/releases/0.1.0.md)
- Java → Python 历史迁移：[docs/migration/Python重构迁移文档.md](docs/migration/Python重构迁移文档.md)
- Java legacy 模块：`java-legacy/ai-center-common`、`ai-center-model`、`ai-center-ai`、`ai-center-server`
