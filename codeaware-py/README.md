# CodeAware (Python)

Java → Python 重构版。结构迁移已完成，但当前 Chat 发布闭环仍须按 C1–C3 实施。

> 通用编码规则见上级目录 [AGENTS.md](../AGENTS.md)；权威设计见 [ADR](../docs/decisions/adr/)、[术语表](../docs/decisions/glossary.md)，当前实施入口见[升级总入口](../docs/roadmap/README.md)。

## 运行

> 以下是 C1 完成后的目标入口；fresh database/端口当前仍以
> [C1](../docs/roadmap/current-release/01-当前缺口修复.md)为准。

```bash
(cd codeaware-py && uv sync)
(cd codeaware-py && cp .env.example .env)
(cd codeaware-py && uv run uvicorn app.main:app --reload --port 8000)
```

- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

## 测试

> C1 的 fail-closed runner 完成前禁止裸跑 pytest。完成后统一使用：

```bash
(cd codeaware-py && uv run python scripts/run_tests_safe.py -v)
```

## 中间件

复用上级 `../docker-compose.yml`（PostgreSQL+pgvector / Redis / Ollama）：

```bash
cd .. && docker compose up -d             # 全起；仅 Ollama：docker compose up -d ollama
docker exec ai-center-ollama ollama pull bge-m3
```
