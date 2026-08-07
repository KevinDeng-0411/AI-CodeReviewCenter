# 同步端点 vs 流式端点：差异与答案缓存取舍

> 记录 `/api/chat/send`（同步）与 `/api/chat/send/stream`（流式）的实现差异，
> 以及答案缓存只作用于同步端点的设计决策（2026-08-07）。

## 1. 共同点

两个端点共享同一状态机（TurnCoordinator），前置流程完全一致：

```text
请求 → prepare_turn（存 USER 消息 + 会话 preflight + turn guard）
     → 错误处理（404 会话不存在 / 409 turn 进行中 / 500 启动失败）
     → 后续走同一套 RAG + rerank + LLM 生成
```

- 相同的 `ChatRequest` / `ChatResponseVO` 契约
- 相同的 RAG 链路（改写 → 混合检索 → rerank 精排 → prompt）
- 相同的后处理（摘要、记忆抽取、缓存刷新）
- 相同的 turn guard（同 cid 并发返回 409）

## 2. 差异点

| 维度 | `/api/chat/send`（同步） | `/api/chat/send/stream`（流式） |
|---|---|---|
| **响应格式** | JSON 信封 `Result[ChatResponseVO]` | typed SSE 事件流（8 事件协议 v1） |
| **首字节延迟** | 等全部生成完才返回 | chat.started 立即返回，token 逐块推 |
| **思考过程** | 不展示（drain 后丢弃 reasoning） | 实时展示 `reasoning.delta` |
| **引用来源** | 不展示 | 实时展示 `context.references` 卡片 |
| **答案缓存** | ✅ 有（精确匹配，TTL 5min） | ❌ 无 |
| **客户端中断** | 无中断概念（一次请求） | 支持 Abort，丢 partial 不伪造终态 |
| **turn guard 释放** | run_sync 结束自动释放 | StreamingResponse on_close 释放 |
| **协议错误处理** | 非 200 即错误 | 前端 SSE parser 逐事件校验（fail-closed） |

## 3. 答案缓存为什么只作用于同步端点

### 同步端点缓存（已实现）

```python
# chat.py send()
cache_key = MD5(message.strip())          # 精确匹配
cached = redis.get(cache_key)
if cached:
    return ChatResponseVO(reply=cached)   # 跳过整个生成链路
# miss → run_sync 正常生成 → setex(cache_key, 300, reply)
```

命中时从 **31s → 0.02s**（跳过 RAG + rerank + LLM），TTL 5 分钟，文档变更自动失效。

### 流式端点不缓存的原因

1. **引用来源丢失**：缓存的是纯文本 reply，无法回放 `context.references`（知识 chunk 卡片）。
   前端核心体验（来源可追溯）会退化。
2. **思考过程丢失**：`reasoning.delta` 是过程不是内容（不持久化），缓存后无源可回放。
3. **SSE 回放复杂**：需构造 chat.started → references → token.delta → completed 的合成流，
   与真实流的一致性维护成本高，且引入新的协议分支。
4. **收益边际**：流式端点本身首 token 已快（~1s），缓存省的是生成时间而非感知延迟
   （用户已看到流式输出）。同步端点的 31s 全阻塞才是缓存的高价值场景。

### 结论

> 答案缓存是**同步端点专属优化**：同步请求全链路阻塞（31s），缓存命中（0.02s）收益巨大；
> 流式端点首 token 已即时，缓存需牺牲引用/思考展示且回放复杂，收益边际——不做。

前端主流程走流式端点（引用+思考完整展示），同步端点主要服务 API 调用/程序化访问，
两者的能力边界由各自协议形态决定，非实现遗漏。

## 4. 实测数据

| 场景 | 同步（无缓存） | 同步（缓存命中） | 流式 |
|---|---|---|---|
| 端到端耗时 | 31.5s | **0.07s** | 首 token ~1s，流式生成 |
| 引用来源 | 无 | 无（缓存纯文本） | ✅ 实时卡片 |
| 思考过程 | 无 | 无 | ✅ 实时展示 |

## 5. 未来候选（当前不做）

- 流式缓存：缓存 reply + knowledge_refs + memory_refs 三元组，命中时合成 SSE 流回放
  （保留引用卡片，但放弃 reasoning）——收益需真实流量数据支撑再评估
