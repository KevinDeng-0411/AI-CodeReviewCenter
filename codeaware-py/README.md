# CodeAware (Python)

Java -> Python 重构版。当前阶段：**P0 骨架**。

> 权威设计见上级目录 `docs/adr/` + `docs/glossary.md` + `docs/Python重构迁移文档.md` + `CLAUDE.md`。

## 运行

```bash
cd codeaware-py
uv sync                                   # 装依赖（uv 会按 .python-version 拉 3.12）
cp .env.example .env                      # 填 LLM_API_KEY（P0 不调用 LLM，可暂留占位）
uv run uvicorn app.main:app --reload --port 8080   # 对齐 Java 版端口 8080
```

- API 文档：http://localhost:8080/docs
- 健康检查：http://localhost:8080/health

## 测试

```bash
uv run pytest -v
```

## 中间件

复用上级 `../docker-compose.yml`（PostgreSQL+pgvector / Redis / Ollama）：

```bash
cd .. && docker compose up -d             # 全起；仅 Ollama：docker compose up -d ollama
docker exec ai-center-ollama ollama pull bge-m3
```
