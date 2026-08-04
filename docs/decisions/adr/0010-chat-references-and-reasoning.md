# ADR-0010: Chat 引用与思考过程增强

- **状态**: Accepted（已规划，待实施）
- **日期**: 2026-08-04
- **关联术语**: typed SSE, Reranker(参考 [ADR-0009](0009-reranker-deferred.md)), Reference, Reasoning
- **上游**: C1 typed SSE 协议、C4 BM25 混合检索、C5 文档解析

## 背景

当前 Chat 的 RAG 链路把检索到的知识 chunk + 长期记忆塞进 prompt，LLM 生成回答后流式
下发 `token.delta`。两个缺口：

1. **回答不可溯源**：用户只看到回答，不知道依据了哪条知识/记忆。RAG 是黑盒，无法验证
   回答是否 grounded。
2. **思考过程不可见**：DeepSeek v4-flash 支持 `reasoning_content`（思考链），但当前
   [turn_coordinator.py:268](../../../codeaware-py/app/ai/services/turn_coordinator.py#L268)
   只读 `chunk.content`，思考被丢弃。

## 决策

### 1. 引用（参考来源）：新增 `context.references` SSE 事件

检索结果（知识 ScoredChunk + 记忆召回）在 LLM 调用**之前**就已可用（TurnCoordinator
line 504-534）。新增第 7 个 SSE 事件 `context.references`，在 `chat.started` 之后、
`token.delta` 之前下发，前端渲染来源卡片。

- **payload**：`knowledge_refs`（document_id/title/chunk 摘要片段/match_type/score）+
  `memory_refs`（content/memory_type/相似度）
- **展示**：摘要形式来源卡片（标题 + ~80-120 字 chunk 片段 + match_type 徽标），
  点击 inline 展开看完整 chunk。v1 **不跳转原文**（跳 Knowledge 页文档详情是额外前端工作）。
- **措辞**：前端叫"参考来源"（被检索并注入 prompt），不是"引用"（不依赖 LLM 显式 cite，
  稳健且诚实）。
- **match_type 价值**：知识 ref 带 vector/keyword/both，可视化混合检索哪条腿命中。

### 2. 思考过程：新增 `reasoning.delta` SSE 事件 + 折叠窗

- **捕获**：v4-flash 的 `reasoning_content` 流式成新事件 `reasoning.delta`（和
  `token.delta` 分开），前端渲染可折叠"思考过程"窗。
- **交互**：reasoning 流式时思考窗展开（"思考中…"）；`token.delta` 开始（答案开始）
  自动折叠，标题变"已思考 Xs"；用户随时点击展开/折叠。
- **不持久化**：reasoning 只流式展示，**不写 PG 消息表**。思考是过程不是内容，历史消息
  刷新后只显示答案--与 DeepSeek web/Claude 一致。需历史可复盘再加 schema，v1 不做。

### 3. 关键约束：ChatOpenAI 不提取 reasoning_content -> 切 ChatDeepSeek

langchain-openai 1.4.1 的 `ChatOpenAI` 明确**不提取/不保留**第三方 provider 的
`reasoning_content`（官方文档：用 `ChatDeepSeek` 等 provider-specific 子类）。当前
`get_chat_model()` 用 `ChatOpenAI` 指向 DeepSeek API。

因此思考过程功能**前置依赖**：
1. 安装 `langchain-deepseek`，`get_chat_model()` 从 `ChatOpenAI` 切到 `ChatDeepSeek`
   （同一 DeepSeek API，provider-specific 子类提取 reasoning_content）
2. **spike 验证**：确认 `ChatDeepSeek.astream()` 的 chunk 里 reasoning_content 可取
   （字段位置：`additional_kwargs` / 专用字段，需实测确认）
3. TurnCoordinator line 268 改读取逻辑：reasoning_content 分流到 `reasoning.delta`，
   content 到 `token.delta`

若 spike 发现 ChatDeepSeek 也不提取 reasoning_content，则思考过程功能降级或改用原始
openai 客户端直连（绕过 langchain 流式）。此风险记入遗留。

### 4. SSE 协议扩展

typed SSE 协议新增第 7/8 个事件（`context.references` + `reasoning.delta`），注册于
[chat_events.py](../../../codeaware-py/app/schemas/chat_events.py#L87-L92) 的
`event_name -> schema` dict。`protocol_version` 是否 bump 视现有版本语义而定（加事件
属向后兼容的 minor 变更，规划时确认）。

### 5. 降密度

沿用 C5 决策：不产出 evidence manifest，完成标志 = 测试通过 + demo（来源卡片 + 思考折叠
可演示）。

## 结果

- Chat 回答可溯源：每轮下发参考来源（知识 chunk + 记忆），前端来源卡片。
- 思考过程可见：reasoning_content 流式展示，可折叠。
- typed SSE 协议从 6 事件扩展到 8 事件。
- 依赖新增 `langchain-deepseek`（仅思考过程需要；若思考降级则不引入）。

## 遗留

- **ChatDeepSeek reasoning_content spike**：实施第一步必须验证 ChatDeepSeek 是否真的
  提取 reasoning_content。若不提取，思考过程改原始客户端或降级。
- **protocol_version bump**：规划时确认现有版本语义，决定是否升版本号。
- **引用 v1 不跳转原文**：后续可加"查看原文"链接到 Knowledge 页文档详情。
- **思考不持久化**：若需历史复盘思考，后续加 schema 存 reasoning。
- 引用功能与思考功能可独立交付：引用不依赖 langchain-deepseek，可先做；思考依赖 spike
  结果。
