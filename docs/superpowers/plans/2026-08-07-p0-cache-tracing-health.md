# P0 优化：答案缓存 + 请求追踪 + 健康检查

## 三项改动

### 1. 答案缓存（同步端点）

**目标**：完全相同的查询 -> 直接返回缓存的回答，跳过 embedding + 检索 + LLM 生成。

**范围**：仅 `/api/chat/send`（同步端点）。流式端点 `/api/chat/send/stream` 不缓存（SSE 事件回放复杂，且流式需要展示引用来源和思考过程）。

**文件**：
- `app/api/v1/chat.py` - `send()` 方法加缓存检查
- `app/api/v1/knowledge.py` - 上传/删除文档时失效缓存

**逻辑**：

```python
# chat.py send() 方法，prepare_turn 之后：
import hashlib

cache_key = f"answer:{hashlib.md5(req.message.strip().encode()).hexdigest()}"
cached = await redis_client.get(cache_key)
if cached:
    return Result.ok(ChatResponseVO(
        conversation_id=prepared.conversation_id,
        reply=cached,
        warnings=[],
    ))

# 正常处理
result = await coordinator.run_sync(prepared, req.message)
# 缓存回复
await redis_client.setex(cache_key, 300, result.reply)  # 5 分钟 TTL
```

**失效**：

```python
# knowledge.py upload/delete 后：
async for key in redis_client.scan_iter("answer:*"):
    await redis_client.delete(key)
```

**trade-off**：缓存命中时不保存 ASSISTANT 消息到 PG（会话历史缺这条）。换取最大速度（1ms vs 420ms）。可接受因为：相同问题的答案已在前一轮对话中持久化。

### 2. 请求追踪中间件

**目标**：每个请求有唯一 X-Request-ID，日志可串联。

**文件**：`app/main.py`

**逻辑**：

```python
@app.middleware("http")
async def request_tracing(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid4().hex[:12]
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "req=%s method=%s path=%s status=%d elapsed=%.0fms",
        request_id, request.method, request.url.path,
        response.status_code, elapsed_ms,
    )
    response.headers["X-Request-ID"] = request_id
    return response
```

- 优先读请求头 `X-Request-ID`（支持上下游传递）
- 没有则生成 12 位 hex
- 响应头带回
- 日志记录方法、路径、状态码、耗时

### 3. 健康检查细化（加 DeepSeek）

**目标**：`/health/ready` 增加 DeepSeek API 可达性检查。

**文件**：`app/api/v1/system_health.py`

**逻辑**：

```python
async def _check_deepseek() -> None:
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY not configured")
    async with httpx.AsyncClient(timeout=_READINESS_TIMEOUT_SECONDS) as client:
        response = await client.get(
            f"{settings.llm_base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        )
        response.raise_for_status()
```

更新 `readiness()`：

```python
postgres, redis, ollama, deepseek = await asyncio.gather(
    _bounded(_check_postgres),
    _bounded(_check_redis),
    _bounded(_check_ollama),
    _bounded(_check_deepseek),
)
checks = {"postgres": postgres, "redis": redis, "ollama": ollama, "deepseek": deepseek}
```

## 验证

```bash
# 答案缓存
curl -X POST http://localhost:8000/api/chat/send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"conversation_id":null,"message":"缓存击穿怎么解决"}'
# 第一次：~420ms（正常处理）
# 第二次：~1ms（缓存命中）

# 请求追踪
curl -v http://localhost:8000/health 2>&1 | grep X-Request-ID
# 响应头包含 X-Request-ID

# 健康检查
curl http://localhost:8000/health/ready
# 返回 postgres/redis/ollama/deepseek 各自状态
```

## 测试

- 答案缓存：测试环境 `CODEAWARE_TESTING=1` 仍走缓存逻辑（Redis 可用），验证命中/未命中
- 请求追踪：验证响应头有 X-Request-ID，日志有 req= 字段
- 健康检查：验证 4 个依赖各自 up/down 状态
- 回归：315 测试全通过