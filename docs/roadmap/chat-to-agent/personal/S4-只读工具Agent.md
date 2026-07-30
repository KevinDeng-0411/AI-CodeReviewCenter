# S4-lite：无 LangGraph 的只读工具 Agent

> **状态：Future / Locked。路线档案：`personal-local-readonly`。**
>
> 直接依赖 S2，不依赖 S3。只有 S2 manifest 通过且用户在其后明确授权 S4，才能实施。

## 1. 达成的功能

Chat 增加 `mode=chat|agent`。在 Agent 模式下，模型可以在硬预算内自主决定是否调用当前
Project 的知识检索工具，并返回服务端验证、刷新后仍存在的 Citation。

完成本阶段后，产品才首次可以称为 **Read-only Agent**。

## 2. 最小实施范围

- 默认仍为 `mode=chat`，复用 S2 `PlainChatReplyEngine`。
- 新增进程内 `ToolRegistry`、`ToolExecutor` 和 `AgentReplyEngine`。
- 首版只注册一个 R0 工具：`search_knowledge`。
- Agent 模式继续使用 Conversation/Memory，但不得由 `ChatContextBuilder` 预先执行
  Knowledge/RAG；项目知识只能经 `search_knowledge` 获取。Chat 模式的现有 eager RAG
  行为保持不变。
- 使用普通有界循环，不安装 LangGraph：

```text
最多 3 次模型调用
  → 没有 tool call：结束
  → 有 tool call：校验后顺序执行
最多 4 次工具调用
```

- 服务端硬上限仍不得高于 4 个模型回合/6 个工具调用。
- 单次模型调用默认且最多 120 秒，整轮使用 monotonic 300 秒硬 deadline；每次模型和工具
  调用都使用剩余 deadline，timeout 不自动重试，并计入 `budget-loop`。
- 客户端断连必须取消当前模型/工具 await，不转入后台任务；transaction B 未提交时不保存
  ASSISTANT/Citation，已提交的 canonical 结果则保留。
- 工具强制 Pydantic input/output、R0 allowlist、project scope、timeout 和最大输出。
- Tool 参数不能覆盖 ProjectScope/actor。
- ToolResult 作为不可信数据回传模型，不能变成 system instruction。
- 使用独立、non-thinking、支持 tool calling 的模型配置；普通 Chat 模型不变。
- 服务端生成 Citation ID，最终引用只能来自本轮成功 ToolResult 的 whitelist。最终模型
  文本必须先完整缓冲、过滤伪造 marker 并形成 canonical answer，之后才允许发
  `token.delta`。
- 只新增 `messages.citations_json JSONB NOT NULL DEFAULT '[]'`；USER 必须为空数组，
  ASSISTANT 只保存服务端验证后的 Citation snapshot，不持久化 ToolResult。
- Citation 与 canonical ASSISTANT Message 在 transaction B 原子保存。固定事件顺序为
  `transaction B commit` → `citation.added*` → `token.delta*` →
  `post_turn.warning*`（含 `CITATION_REJECTED`）→ `chat.completed`；客户端拼接的全部
  delta 必须逐字等于持久化内容。
- SSE 复用 C1 `ChatEventBase`，增加 `tool.started`、`tool.completed`、`citation.added`。
- `READ_ONLY_AGENT_ENABLED=false` 时 `mode=chat` 仍正常，`mode=agent` 必须返回
  `FEATURE_DISABLED`，不得静默降级或调用模型/工具。

## 3. 不做事项

- 不做 LangGraph、planner、reflection、多 Agent 或并行工具。
- 不创建 AgentRun/ToolCall/RunEvent/checkpoint 表。
- 不提供文件、Git、shell、网络或写工具。
- 不自动重试模型工具循环，不启用 thinking tool loop。
- S6 前事件不持久化、不可 replay；UI 必须如实展示这一限制。

## 4. 自动测试

必须覆盖：

- 无工具回答、一次工具回答和多轮预算终止。
- Agent 普通寒暄不会发生隐藏的 Knowledge 查询；项目知识回答必须能对应到本轮
  `search_knowledge` ToolResult。
- 未注册工具返回 `TOOL_NOT_ALLOWED`。
- timeout、超大输出、schema 错误均稳定失败。
- 每次模型 timeout、整轮 deadline 和客户端断连都会终止活动调用，且不遗留后台任务或
  半写 ASSISTANT/Citation。
- 跨 Project 查询和伪造 actor/project 被拒绝。
- 伪造 Citation 在第一个 `token.delta` 前被过滤并产生可观测 warning；delta 拼接值与
  DB canonical ASSISTANT 完全相等。
- 事件断言为 transaction B 先提交，之后只为 canonical answer 实际引用的白名单来源发送
  `citation.added`；`CITATION_REJECTED` 只能作为 `post_turn.warning` 且早于唯一
  `chat.completed`。
- Agent 与 Chat 共用同一个 TurnCoordinator，ASSISTANT 不重复写入。
- 完整 C1 event base、terminal 顺序、空格/换行和摘要行为不回归。
- 刷新 Conversation 后 Citation 仍可读取。
- 普通 CI 使用 fake；另有一次显式真实 DeepSeek tool-calling smoke。

## 5. 可复制演示

```text
普通寒暄 → 不调用工具
项目知识问题 → search_knowledge → Citation → 最终回答
请求不存在工具 → TOOL_NOT_ALLOWED
伪造 Citation → 被过滤
超过 3/4 预算 → BUDGET_EXCEEDED
关闭 feature flag → mode=agent 返回 FEATURE_DISABLED，mode=chat 正常
```

## 6. 阶段完成条件

- `tool-governance`
- `budget-loop`
- `citation-persistence`
- `chat-runtime-regression`
- `security-negative`
- `rollback`

以上 check 被 `evidence/S4/manifest.json` 引用并通过；其直接依赖必须是 S2，而不是 S3。
