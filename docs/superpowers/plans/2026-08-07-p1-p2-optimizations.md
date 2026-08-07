# P1-P2 优化实施计划

## P1: 慢查询日志（>1s）

**改动**：`app/main.py` — 请求追踪中间件增加慢查询告警

```python
if elapsed_ms > 1000:
    logger.warning(
        "slow req=%s method=%s path=%s status=%d elapsed=%.0fms",
        request_id, request.method, request.url.path,
        response.status_code, elapsed_ms,
    )
```

已有 INFO 日志保留不变，额外加 WARNING 阈值判断。

## P1: 结构化日志（JSON）

**改动**：`app/core/logging.py` — 新建日志配置模块，替换默认的 logging 格式

使用 Python 标准库的 `logging` + 自定义 JSONFormatter，不引入 structlog（避免额外依赖）。

```python
import json
import logging
import sys


class JsonFormatter(logging.Formatter):
    """JSON 日志格式化器，每行一个 JSON 对象。"""
    def format(self, record: logging.LogRecord) -> str:
        obj = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "name": record.name,
            "msg": record.getMessage(),
        }
        if hasattr(record, "req"):
            obj["req"] = record.req
        return json.dumps(obj, ensure_ascii=False)


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(handlers=[handler], level=logging.INFO, force=True)
```

在 `app/main.py` 入口处调用 `setup_logging()`。

## P2: 拆 TurnCoordinator（870行 → 拆分）

### 现状
- `turn_coordinator.py` 870 行，包含：
  - 上下文构建（_build_context, _load_messages, _load_summary）
  - 模型流编排（run, run_sync）
  - Post-turn 处理（_post_turn_summary, _post_turn_extraction, _post_turn_cache）
  - 事务管理（_txn_user, acquire_turn, release_turn）

### 拆分方案

```
app/ai/services/
├── turn_coordinator.py      # 80行 → 薄编排层，协调子模块
├── context_builder.py       # 150行 → 上下文构建 + 短期/长期记忆 + RAG
├── stream_manager.py        # 200行 → SSE 事件流生成 + 模型调用
└── post_turn_processor.py   # 150行 → 摘要 + 记忆抽取 + 缓存刷新
```

### 接口定义

```python
# context_builder.py
class ContextBuilder:
    def __init__(self, chat_model, vector_recall, lexical_recall, query_rewriter, chunker)
    async def build(self, cid, message) -> tuple[str, list, dict]  # prompt, warnings, refs

# stream_manager.py
class StreamManager:
    def __init__(self, chat_model, redis, vector_recall)
    async def run(self, prepared, message, context) -> AsyncGenerator[ChatEvent, None]
    async def run_sync(self, prepared, message, context) -> TurnResult

# post_turn_processor.py
class PostTurnProcessor:
    def __init__(self, chat_model, redis, vector_recall)
    async def process(self, cid, warnings) -> list[dict]  # post_turn warnings
```

### 步骤
1. 提取 ContextBuilder（无回归风险，纯函数移动）
2. 提取 PostTurnProcessor（无回归风险，纯函数移动）
3. 提取 StreamManager（高风险，涉及 SSE 事件序列，需仔细验证）
4. TurnCoordinator 降为薄壳（调用子模块）

### 验证
- 315 测试全通过
- SSE 事件序列不变（chat.started → references → reasoning → token → completed）
- 同步端点结果不变