# CodeAware (Python)

Java → Python 重构版。C1-A 至 C1-E 已实现并通过定向及全量验证；当前发布闭环仍须完成 C1 总演示/evidence，再按 C2、C3 继续实施。

> 通用编码规则见上级目录 [AGENTS.md](../AGENTS.md)；权威设计见 [ADR](../docs/decisions/adr/)、[术语表](../docs/decisions/glossary.md)，当前实施入口见[升级总入口](../docs/roadmap/README.md)。

## 运行

全新 Compose volume 会创建 `ai_center` 与 `ai_center_py`；已有 volume 可从仓库根运行
`./codeaware-py/scripts/ensure_python_db.sh` 幂等补建 Python 数据库。

```bash
(cd codeaware-py && uv sync)
(cd codeaware-py && cp .env.example .env)
(cd codeaware-py && uv run uvicorn app.main:app --reload --port 8000)
```

- API 文档：http://localhost:8000/docs
- 存活检查：http://localhost:8000/health/live
- 就绪检查：http://localhost:8000/health/ready

AIReadMe 的本地项目快照默认关闭且没有隐式目录。仅在服务端 `.env` 中显式配置后启用：

```dotenv
AI_README_SNAPSHOT_ENABLED=true
LOCAL_PROJECT_ROOTS=["/absolute/server/project-root"]
```

请求目录必须位于上述白名单中；前端会先读取
`GET /api/ai-readme/capabilities`，能力不可用时不允许生成。

## 测试

禁止裸跑 pytest；统一使用 fail-closed 一次性环境：

```bash
(cd codeaware-py && uv run python scripts/run_tests_safe.py -v)
```

## 中间件

复用上级 `../docker-compose.yml`（PostgreSQL+pgvector / Redis / Ollama）：

```bash
cd .. && docker compose up -d             # 全起；仅 Ollama：docker compose up -d ollama
docker compose exec ollama ollama pull bge-m3
```

完整 fresh-volume 启动验证：

```bash
cd ..
./codeaware-py/scripts/verify_fresh_bootstrap.sh
```
