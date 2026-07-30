# S4：只读工具 Agent

> **路线门禁更新（2026-07-30）**：C3 后已新增 C4 BM25。下方所有 C3-only 前置描述
> 均须同时验证 C4 manifest，不能借平台参考卡绕过 C4、S1 或 S2。
>
> **完整平台参考，非个人默认实施卡。** `personal-local-readonly` 的 S4 唯一权威是
> [精简 S4](personal/S4-只读工具Agent.md)，其直接依赖是 S2，不是 S3。后文关于 Graph、
> S3 evidence、4/6 默认预算和平台化 DoD 均不能扩大默认 S4 范围。
>
> **状态：Future / Locked（未来候选，当前版本禁止实施）**
>
> 本文不是当前版本任务，也不构成自动开工授权。只有同时满足以下条件，才允许由用户另行决定是否实施：
>
> 1. `docs/roadmap/current-release/evidence/C3/manifest.json` 已存在、validator 通过且结论为“当前版本完成、允许评审 Agent 路线”；
> 2. S1、S2 的 manifests 均存在且 validator 通过；只有显式选择 Graph profile 时才额外要求 S3；
> 3. 用户在 S2（或已选择的 S3）完成之后对 **S4** 给出新的、明确的实施授权。
>
> 任一条件不满足时，只能阅读和评审本文。S2 或可选 S3 完成都不代表自动进入 S4。

> 本阶段首次允许模型自主选择工具。工具只来自进程内的类型化 registry，且全部为 `R0_READ`。
> Agent 同步依附当前 Chat 请求，不持久化 Run；durable run、checkpoint、审批和写操作均属于后续阶段。
>
> S4 仍是 local single-user：actor 是服务端固定 sentinel，Project UUID 只做隔离，服务仅监听 loopback 且远程禁用。S4 不增加认证/RBAC，也不得重写 C1 的 Chat turn/post-turn/SSE 或 C2 API。

---

## 实施入口 / 本阶段闭环

公共类型、`ChatEventBase`、Tool/Citation 语义、API base path、sentinel 和错误码只以[公共契约](00-执行约定与公共契约.md)为准；本文只描述 S4 增量。

| 项目 | 唯一入口 |
|---|---|
| 前置 manifest | C1/C2/C3 + S1/S2；Graph profile 才加 S3；Runtime/UoW/event hashes、OpenAPI/Alembic head、S4 明确授权 |
| 唯一增量 | `mode=agent`、R0 Registry/Executor、受预算 loop、Citation whitelist/persistence、前端工具时间线 |
| 必测 | 4/6 预算；schema/risk/timeout；跨项目；sentinel 不可覆盖；事件 base；TurnCoordinator；刷新后 Citation |
| 演示 | disposable 项目数据中走一次有工具、无工具、伪造工具/Citation、预算耗尽和 feature-flag 回退 |
| 回退 | `READ_ONLY_AGENT_ENABLED=false`，保留 Chat/Citation；migration 往返只在 detached 临时 worktree + 一次性 PG/Redis 演练 |
| 下一步 | evidence 完整后交付 R0 Registry/Executor/Citation 给 S5；不得访问仓库、持久 Run 或执行写操作 |

## 1. 阶段目标

在 S2 service runtime（或明确选择的 S3 Graph profile）上新增 `mode=agent` 路径，使 DeepSeek 在严格预算内自主选择项目级只读 Knowledge 工具，并返回可验证 Citation、类型化工具事件和受控错误。

完成后应满足：

- `mode=chat` 仍运行当前已选择的 S2 service/S3 Graph runtime，行为不回归；
- `mode=agent` 使用 C3 后重新 live 验证为支持标准 tool calling 的 DeepSeek 模型，并固定 **non-thinking**；
- 工具仅从内部 `ToolRegistry` 获得，模型不能构造任意函数；
- Tool 输入、输出、风险、scope、超时和最大输出均有 schema；
- 最多 4 个模型回合、最多 6 次工具调用，服务端硬上限不可突破；
- ToolResult 产生的 Citation 由服务端创建并校验，模型不能编造；
- SSE 发出 `tool.started`、`tool.completed`、`citation.added`；
- 所有工具都只读，只能访问 header 选择的当前 Project；actor 始终是 `local-single-user`，不宣称真实用户授权。

本阶段完成后可以称为 **Read-only Agent**，不能称为 Repo-aware、Durable、Patch 或 Action Agent。

## 2. 可演示成果

用户在 Chat 页面选择“只读 Agent”，询问某项目知识库中的问题：

```text
“项目里缓存穿透的推荐处理方式是什么？请给出来源。”
```

可观察到：

1. `chat.started`；
2. 模型选择 `search_knowledge`；
3. `tool.started`，参数只显示脱敏摘要；
4. `tool.completed`，包含成功状态和 citation IDs；
5. 一个或多个 `citation.added`；
6. 模型基于 ToolResult 生成答案，并使用 `[citation:<id>]`；
7. `chat.completed` 包含 usage、工具次数、模型回合数和已验证 Citations；
8. 前端将 Citation 渲染为可查看的来源卡片。

再演示：

- 普通寒暄不调用工具；
- 请求不存在的工具得到 `TOOL_NOT_ALLOWED`；
- 伪造 Citation 不会进入最终返回；
- 达到工具预算后不再执行额外调用，并返回 `BUDGET_EXCEEDED`；
- 将模式切回 `chat` 后仍是当前稳定 Chat runtime。

## 3. 前置条件与阶段门禁

开始前必须确认：

- current-release C1 类型化 SSE 已完成；
- S1 header-only Project scope 在 Knowledge、Memory、Conversation 查询中强制执行，actor 为不可覆盖的 local sentinel，remote 仍禁用；
- S2 application port 可供 Tool handler 调用，handler 不需要直接写 SQL；
- S2 service runtime 与 C1 TurnCoordinator/UoW 回归已通过；Graph profile 才验证 S3 路径和 node trace；
- 直接依赖 evidence 明确证明没有残留重复消息写入；
- DeepSeek non-thinking tool calling 已使用 mock contract 验证；
- 当前全量测试与前端检查通过。

若 `project_id` 仍可缺省、可由模型 Tool 参数覆盖，禁止进入本阶段。

## 4. 历史现状证据（pre-C1/pre-S4，必须复核）

下列内容只说明 S4 新增能力，不是重做 C1/C2 的任务。解锁后以直接依赖 evidence 和 C3 OpenAPI 为准复核实际路径：

- `app/ai/config.py` 只有普通 `get_chat_model()`，没有专用 non-thinking Agent 模型工厂；
- `app/ai/services/chat.py` 由应用预先调用 RAG，模型本身不能选择工具；
- `app/ai/services/rag.py` 可提供 Knowledge 检索能力，但返回值尚不是公共 `ToolResult`；
- `app/ai/rag/hybrid_retriever.py` 返回 chunk、score、match type，可作为 Citation 来源；
- 当前没有 ToolDefinition、ToolResult、ToolError、ToolRegistry 或 ToolExecutor；
- 当前没有工具预算、模型回合预算或工具级 timeout/output limit；
- C1 冻结的 Chat 前端不展示工具时间线和 Citations；
- 当前没有 AgentRun/ToolCall 表，这一现状在 S4 保持不变。

实施者必须重新核验 C1–C3、S1、S2，以及仅在已选择时的 S3 实际代码；若前序阶段已移动文件，应使用新位置。

## 5. 范围

### 5.1 本阶段必须做

- 新增 `mode=chat|agent`，默认 `chat`；
- 新增独立 Agent 模型工厂，固定 non-thinking；
- 建立内部只读 Tool registry；
- 落地公共契约的 ToolDefinition、ToolResult、ToolError 和 Citation；
- 建立 Tool executor 的 scope、风险、schema、timeout、输出大小校验；
- 实现最多 4 模型回合、6 工具调用的 read-only loop；
- 注册首批 Knowledge 只读工具；
- 最终回答只允许引用本轮 ToolResult 返回的 Citation；
- 类型化输出工具和 Citation 事件；
- 在响应和 trace 中记录模型回合、工具次数、toolset 版本、token/成本、耗时；
- 前端支持 Agent 模式、工具事件和 Citation 卡片；
- 保留 Chat 模式和关闭 Agent 的 feature flag。
- 复用 S2 `ChatUnitOfWork` 和唯一 `TurnCoordinator`，将服务端验证后的 Citation snapshot 与 ASSISTANT 消息原子持久化；

### 5.2 明确不做

- 不访问本地仓库或任意文件路径；
- 不提供 shell、Git、网络请求、SQL、Redis、文件句柄给模型；
- 不加入 `R1_SANDBOX`、`R2_LOCAL_WRITE`、`R3_EXTERNAL_WRITE`；
- 不引入 MCP、A2A 或外部插件；
- 不使用 DeepSeek thinking tool calls；
- 不回传或存储 `reasoning_content`；
- 不使用 beta strict endpoint 作为首版依赖；
- 不新增 AgentRun、ToolCall、RunEvent、Artifact、Approval 表；
- 不使用 LangGraph checkpoint、暂停、恢复或 durable API；
- 不执行并行 Tool calls；首版按模型返回顺序串行执行，保证预算和事件可预测；
- 不允许 Tool handler 直接拼 SQL；
- 不允许 Tool output 成为 system/developer 指令。
- 不重写 C1 的 USER/ASSISTANT、summary/memory、commit/Redis/terminal 时序；Agent 只是插入受控 model/tool loop。

## 6. 模型和预算契约

### 6.1 Agent 模型工厂

新增独立工厂，不修改普通 Chat 的缓存实例：

```python
@lru_cache
def get_agent_chat_model() -> ChatOpenAI:
    return ChatOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_agent_model,
        temperature=settings.llm_agent_temperature,
        max_tokens=settings.llm_agent_max_tokens,
        timeout=settings.agent_model_timeout_seconds,
        extra_body={"thinking": {"type": "disabled"}},
    )
```

规则：

- 普通 Chat 模型配置不变；
- Agent 首版固定 `thinking.type=disabled`；
- 不把 API key、base URL 暴露给 ToolContext、事件或 trace；
- 通过标准 `bind_tools` / tool calling 使用 schema；
- Tool 消息必须把 provider 返回的不透明字符串 `tool_call_id` 原样回传；不得把它解析或改写成 UUID。应用内部另生成 `logical_tool_call_id`，S6 起按公共契约持久化二者的映射；
- 无需也不得保存 `reasoning_content`；
- 真实 DeepSeek 测试标记为 `live_eval` 或 `integration`，普通 CI 使用 Fake Tool-calling Model。

### 6.2 硬预算

服务端默认和首版硬上限：

| 预算 | 默认 | 硬上限 |
|---|---:|---:|
| 模型回合 | 4 | 4 |
| Tool calls | 6 | 6 |
| 总请求时间 | 300 秒 | 300 秒 |
| 单工具 timeout | 由 ToolDefinition 指定 | 不超过剩余总时间 |
| ToolResult 字节数 | 由 ToolDefinition 指定 | 由服务器统一上限再次约束 |

预算算法必须明确：

1. 每次调用模型前检查剩余模型回合；
2. 模型返回 N 个 tool calls 时，按顺序逐个检查剩余工具预算；
3. 超预算的 call 不执行、不发 `tool.started`；
4. 达模型或工具上限时停止循环；
5. 首版统一返回结构化 `BUDGET_EXCEEDED`，不额外偷用一次“总结回合”；
6. 已产生的 Citation 可随错误详情返回，但不能伪造完整成功回答；
7. timeout/cancel 后不继续执行剩余工具。

## 7. Tool 契约与内部 Registry

### 7.1 领域类型

严格复用公共契约：

```python
class ToolDefinition(BaseModel):
    name: str
    version: str
    description: str
    input_schema: dict
    output_schema: dict
    risk: Literal["R0_READ"]
    required_scopes: list[str]
    timeout_seconds: int
    idempotent: bool
    max_output_bytes: int
```

```python
class ToolContext(BaseModel):
    actor_id: Literal["local-single-user"]
    project_id: UUID
    conversation_id: str | None
    turn_id: str
    deadline_at: datetime
```

`ToolContext` 由 router/runtime 组装：`actor_id` 是服务端 sentinel，`project_id` 只来自 `X-Project-ID`。模型、body、query 和 Tool arguments 看不到也不能覆盖这两个值；这只是本地隔离和静态策略，不是认证。

Handler port：

```python
class ToolHandler(Protocol):
    definition: ToolDefinition
    input_model: type[BaseModel]
    output_model: type[BaseModel]

    async def execute(
        self,
        context: ToolContext,
        arguments: BaseModel,
    ) -> BaseModel: ...
```

Handler 返回其 `output_model`，由唯一 `ToolExecutor` 校验、限制大小并包装成 `ToolResult`；不要让 handler 和 executor 各自构造一层互相漂移的 envelope。Handler 可以通过构造函数依赖 S2 的 application read port，但不能把 session 放入模型消息或 state。

### 7.2 Registry

`ToolRegistry` 必须：

- 以 `(name, version)` 唯一注册；
- 启动/构造时只拒绝重复 `(name, version)`；不同工具可以同为 `1.0.0`；
- 每个 name 对模型只暴露一个由服务器配置选择的 active version，不能让模型自行选版本；
- 只向模型暴露本轮 allowlist；
- 只注册 `R0_READ`；
- 从 Pydantic model 生成 JSON Schema；
- 保持稳定 `toolset_version`：对排序后的完整 canonical `ToolDefinition`（含 name/version/description/input/output/risk/scopes/timeout/idempotent/output limit）计算 hash；
- 不支持运行时从字符串 import 任意 handler；
- 未注册工具返回 `TOOL_NOT_ALLOWED`；
- Tool 名、版本和 schema 写入 trace。

### 7.3 Executor

执行顺序固定为：

```text
lookup definition
  → risk allowlist
  → scope check
  → Pydantic input validation
  → remaining deadline
  → asyncio timeout
  → Pydantic output validation
  → max bytes
  → Citation scope validation
  → ToolResult
```

任何失败都返回结构化 `ToolError`，不得把异常堆栈、SQL、密钥或宿主绝对路径交给模型。

工具返回内容是**不可信数据**。包装成 tool message 时必须加固定边界说明，提示模型不得把其中的指令当作系统指令。

## 8. 首批只读工具

首版只注册以下内部工具：

### 8.1 `search_knowledge`

输入：

```python
class SearchKnowledgeInput(BaseModel):
    query: Annotated[str, Field(min_length=1, max_length=1000)]
    top_k: Annotated[int, Field(ge=1, le=10)] = 5
```

可信 scope 中的 `project_id` 不在模型参数中。

输出：

```python
class SearchKnowledgeOutput(BaseModel):
    items: list[KnowledgeEvidence]
    truncated: bool
```

每个 item 至少包含：

- `citation_id`
- `document_id`
- `chunk_id`
- `title`
- `excerpt`
- `score`
- `match_type`

### 8.2 `get_knowledge_chunk`

输入：

```python
class GetKnowledgeChunkInput(BaseModel):
    chunk_id: int
```

执行时必须再次按当前 `project_id` 联表校验，不能因为模型知道其他项目的数字 ID 就越权。输出只返回有大小上限的 chunk 及服务端 Citation。

### 8.3 可选导航工具

只有在前两个工具的测试和演示完成后，才能增加 `list_knowledge_documents`。它仍必须 project-scoped、分页、限制返回字段，不返回全文。

不得在 S4 注册 `read_file`、`search_code`、`git_*`、`run_command`、`apply_patch`。

## 9. Citation 契约

### 9.1 生成

Citation 必须由 Tool handler/service 生成，字段遵循公共契约。S4 Knowledge Citation：

- `project_id`：当前可信 scope；
- `repository_id`、`commit_sha`、`path`、`symbol`、行号：均为 `None`；
- `document_id`、`chunk_id`：数据库真实记录；
- `excerpt`：ToolResult 中实际提供给模型的受限片段；
- `score`：检索 score；
- `citation_id`：本轮不可预测的 UUID 字符串。

### 9.2 最终回答校验

Agent Prompt 规定使用：

```text
[citation:<citation_id>]
```

Runtime 维护本轮 `allowed_citation_ids`，最终输出经过 `CitationValidator`：

- whitelist 保存本轮成功 ToolResult 返回的完整 Citation snapshot；只允许这些 ID；
- 流式 `CitationFilteringSink` 可以立即透传普通文本，但从可能的 `[citation:` 前缀起必须缓冲到 `]` 再校验；合法 marker 原样发出，未知/伪造 marker 不进入 token stream，只在本轮内累计脱敏的结构化 `CITATION_REJECTED`；
- 最终 canonical reply 必须等于客户端拼接后的合法 `token.delta`，不能在 token 已发出后静默改写；
- 过滤时不得发明新事件或在模型流中途误发 `context.warning`；canonical ASSISTANT + valid `citations_json` transaction B commit 后，才把累计拒绝映射为既有 `post_turn.warning(component="citation_validation", code="CITATION_REJECTED")`，之后才允许 `chat.completed`；
- 前端只渲染服务端响应/事件中存在的 Citation；
- 不能根据模型写出的 document/path 自行创建 Citation；
- Tool 调用失败时不能生成成功 Citation；
- Citation excerpt 必须与当时 ToolResult 一致；
- validated citation list 与 ASSISTANT Message 在 transaction B 中原子写入 `messages.citations_json`；Conversation 查询从 PG 返回同一 snapshot，刷新后仍能重建来源卡；
- `citation.added` 只为 whitelist 中、且实际被 canonical reply 引用的 Citation 发出，并继承完整 `ChatEventBase`。

普通常识回答可以没有 Citation；凡模型声称依据项目知识库，应在 Agent Prompt 中要求引用。

## 10. Agent loop

建议新增 `ReadOnlyAgentRuntime`：

```text
TurnCoordinator transaction A: ensure Conversation + persist USER + commit
  → post-commit USER cache refresh
  → chat.started
  → build trusted Agent context
  → bind registry tool schemas
  → model turn
      ├─ final text → streaming Citation whitelist filter
      └─ tool calls
           → validate budgets
           → execute sequentially
           → append typed ToolResult messages
           → next model turn
  → transaction B: persist canonical ASSISTANT + citations_json + commit
  → post-commit ASSISTANT cache refresh
  → reuse C1/S2 bounded post-turn(summary + memory)
  → each post-turn PG write commits before its cache refresh
  → post_turn.warning* (including accumulated citation_validation/CITATION_REJECTED)
  → chat.completed
```

规则：

- 只能扩展 C1 的唯一 `TurnCoordinator`，不能另建一套 Agent conversation/message/summary/cache/terminal coordinator；
- Agent context 复用当前 active CHAT Prompt、短期历史和长期记忆策略；只关闭无条件 Knowledge 预取，由模型决定是否调用 Knowledge Tool；
- 系统 Prompt 与外部 ToolResult 明确分隔；
- 每轮 tool calls 全部计入预算，即使校验失败；
- 同一个 tool call ID 只能执行一次；
- S4 不把 loop checkpoint 到数据库；
- HTTP 断开或任务取消后停止循环；
- USER/ASSISTANT、context/post-turn warning、短 PG transaction、Redis post-commit 与 terminal 仍逐项遵循 C1/S2 和当前所选 runtime；
- ToolResult 不作为 Conversation Message 长期展示，避免污染普通对话历史；
- 只有经过 Citation whitelist filter 的 canonical assistant 回答才保存为 Message；validated Citation snapshot 与该 Message 原子保存；
- Citation filter 在 token 阶段只过滤并累计；`CITATION_REJECTED` 必须晚于 transaction B commit、以 `post_turn.warning(component="citation_validation")` 发出，且早于唯一 `chat.completed`；
- tool call/event 在 S6 前不持久化，但 Citation provenance 已随 Message 持久化，刷新后不得丢失；
- Agent 路径不得先由 ChatContextBuilder/可选 Graph 无条件搜索 Knowledge、再让工具重复搜索；是否调用工具由模型决定。

## 11. 类型化事件和 API

### 11.1 Chat 请求

在 S1 已有 header-only Project scope 基础上，公共 JSON body 只增加 `mode`：

```python
class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str
    mode: Literal["chat", "agent"] = "chat"
```

`project_id` 只来自 `X-Project-ID`，`actor_id` 只来自服务端 sentinel；body/query/Tool 参数均不得重复。`mode=agent` 还必须受 `READ_ONLY_AGENT_ENABLED` 和本地静态策略控制。未知 mode 返回 `INVALID_REQUEST`，flag 关闭返回稳定 `FEATURE_DISABLED`。API base path 与 envelope 继续使用 `/api` 和 C3 `Result[T]`。

### 11.2 Chat 响应

同步响应在保持原字段基础上增加可选：

```python
class ChatResponseVO(BaseModel):
    conversation_id: str
    reply: str
    citations: list[Citation] = Field(default_factory=list)
    usage: UsageSummary | None = None
```

Conversation/Message 查询响应也要返回 `citations`（无引用时为空数组），来源是 PG 中的 validated snapshot，不能只存在于当前页面内存。

### 11.3 事件

严格使用公共事件名：

```text
tool.started
tool.completed
citation.added
```

建议 payload：

```json
{
  "protocol_version": 1,
  "conversation_id": "...",
  "turn_id": "...",
  "sequence": 3,
  "tool_call_id": "...",
  "logical_tool_call_id": "...",
  "tool_name": "search_knowledge",
  "tool_version": "1.0.0",
  "arguments_summary": {"query_chars": 18, "top_k": 5}
}
```

```json
{
  "protocol_version": 1,
  "conversation_id": "...",
  "turn_id": "...",
  "sequence": 4,
  "tool_call_id": "...",
  "logical_tool_call_id": "...",
  "ok": true,
  "error": null,
  "citation_ids": ["..."],
  "duration_ms": 12
}
```

所有 Tool/Citation 事件继承公共 `ChatEventBase`，SSE `id=sequence`；`tool_call_id` 是 provider 原始字符串，`logical_tool_call_id` 是应用 UUID，二者不得互换。禁止用 request-only payload 另建协议。禁止在 `tool.started` 事件中回显完整敏感 query、系统 Prompt 或 scope 值。S6 之前事件不落 PG、不可重放，文档和 UI 必须如实标注；Citation snapshot 例外，它随 Message 持久化以支持刷新。

## 12. 文件级实施清单

| 文件 | 变更 |
|---|---|
| `codeaware-py/app/core/config.py` | Agent model、4/6 预算、timeout、output bytes、feature flag |
| `codeaware-py/app/ai/config.py` | 独立 `get_agent_chat_model()`，固定 non-thinking |
| `codeaware-py/app/models/message.py` | 增加 validated `citations_json` snapshot；不保存 ToolResult |
| `codeaware-py/alembic/versions/<next>_message_citations.py` | 从实施时实际 Alembic head 增加非空默认空数组的 Citation snapshot |
| `codeaware-py/app/schemas/chat.py` | `mode`、可选 Citations 和 usage |
| `codeaware-py/app/schemas/tools.py` | ToolDefinition、ToolResult、ToolError、ToolContext、各工具输入输出 |
| `codeaware-py/app/schemas/citations.py` | 公共 Citation 及 inline 引用校验类型 |
| `codeaware-py/app/schemas/events.py` | 类型化 tool/citation 事件 union；扩展 C1 已冻结的事件，不建第二套 |
| `codeaware-py/app/ai/tools/registry.py` | 内部 registry 和 toolset version |
| `codeaware-py/app/ai/tools/executor.py` | 风险/scope/schema/timeout/大小校验 |
| `codeaware-py/app/ai/tools/citations.py` | Citation factory、whitelist、streaming marker filter、validator |
| `codeaware-py/app/ai/tools/builtins/knowledge.py` | `search_knowledge`、`get_knowledge_chunk` |
| `codeaware-py/app/ai/agents/read_only.py` | 受预算的 non-thinking tool loop |
| C1 已交付的 `TurnCoordinator` 实际路径 | 扩展 agent mode；复用 transaction A/B、post-turn、cache 和 terminal，不复制 |
| `codeaware-py/app/api/v1/deps.py` | 请求级 registry/executor/runtime 注入 |
| `codeaware-py/app/api/v1/chat.py` | `mode` 路由，API 路径不变 |
| `codeaware-py/frontend/src/api/types.ts` | Agent mode、ToolEvent、Citation 类型 |
| `codeaware-py/frontend/src/api/client.ts` | 解析类型化 tool/citation SSE，不 trim token |
| `codeaware-py/frontend/src/pages/Chat.tsx` | Chat/Agent 模式、工具时间线、Citation 卡片 |
| `codeaware-py/tests/test_tool_registry.py` | 注册、schema、版本、allowlist |
| `codeaware-py/tests/test_tool_executor.py` | scope、风险、timeout、大小、错误 |
| `codeaware-py/tests/test_knowledge_tools.py` | project 隔离、结果和 Citation |
| `codeaware-py/tests/test_read_only_agent.py` | 模型循环、预算、non-thinking、伪造工具 |
| `codeaware-py/tests/test_agent_events.py` | 事件顺序和 payload |
| `codeaware-py/tests/test_agent_api.py` | mode 兼容、feature flag、同步/SSE |
| `codeaware-py/tests/test_agent_message_citations.py` | migration、原子保存、历史空数组、刷新恢复 |

## 13. 顺序化实施步骤

1. **冻结当前 Chat 回归集**：`mode=chat` 的所有 contract 测试保持通过。
2. **落地 schemas/migration**：先实现公共 Citation、ToolDefinition、ToolResult、ToolError、事件和 Message citation snapshot，不写 loop。
3. **实现 Registry**：注册空/静态 fake tools，验证 `(name,version)`、active version、非法风险和完整 toolset hash。
4. **实现 Executor**：用 fake handler 覆盖 scope、timeout、输出过大、Pydantic 输入输出错误。
5. **适配 Knowledge read port**：让 Tool handler 只调用 project-scoped application read service。
6. **实现 CitationFactory/Whitelist/FilteringSink**：确保 excerpt、chunk 和 project 一致，伪造 marker 在发 token 前被拒。
7. **实现 Agent 模型工厂**：单测断言 `thinking=disabled`，不影响普通 Chat 工厂。
8. **实现受预算 loop**：先 Fake Model，再作为 C1 `TurnCoordinator` 的一个 mode 接入；不得复制 turn lifecycle。
9. **发出类型化事件**：事件来自 Runtime/Executor，全部继承 `ChatEventBase`，不由模型构造。
10. **接入前端**：只根据白名单事件/PG Message Citation 显示来源，覆盖刷新恢复。
11. **运行 migration、离线全量测试**。
12. **最后运行显式 live DeepSeek 验证**，结果写 evidence，不纳入普通 CI。

## 14. 数据和迁移

S4 只新增一项面向用户历史的持久化：在 C3/S1 实际 Alembic head 后创建下一 revision，为 `messages` 增加：

```text
citations_json JSONB NOT NULL DEFAULT '[]'
```

规则：

- 只允许 ASSISTANT Message 保存服务端 whitelist 验证后的 `list[Citation]` snapshot；USER 必须为空数组；
- canonical reply 与 `citations_json` 在 C1 transaction B 中原子提交；
- 历史 Message 回填空数组，不伪造来源；
- Conversation/Message API 从 PG 返回 snapshot，前端刷新后可重建来源卡；
- migration 有 upgrade/downgrade 测试；downgrade 前明确会丢失 S4 Citation provenance，但不能删除 Message 文本；
- ToolCall、tool event 和 loop state 仍不持久化；无 AgentRun、RunEvent、Artifact、Approval。

除该字段外，不得借“审计”提前发明 S6 AgentRun 生命周期。若 C3 freeze commit 已有等价的通用 Message metadata 列，应复用并用 schema version 固定 Citation，而不是再加重复列。

## 15. 自动测试

### 15.1 Registry/Executor

- 重复 `(name,version)` 拒绝；不同 name 使用相同 version 合法；每个 name 只暴露配置选择的 active version；
- R1/R2/R3 工具无法注册到 S4 allowlist；
- 未注册工具返回 `TOOL_NOT_ALLOWED`；
- 模型/body/query 无法覆盖 header project 或 sentinel actor；
- 缺/未知 Project 分别返回公共 `INVALID_REQUEST` / `PROJECT_NOT_FOUND`；
- input/output schema 错误结构化返回；
- timeout 返回 `TOOL_TIMEOUT`；
- 超大结果返回 `TOOL_OUTPUT_TOO_LARGE`；
- 错误中不出现密钥、DB URL、绝对路径或堆栈；
- toolset version 对相同完整定义稳定，description/risk/scope/timeout/limit 任一变化都会改变 hash。

### 15.2 Agent loop

- 不需要工具时一个模型回合完成；
- 一次搜索后第二个模型回合完成；
- 多个 tool calls 顺序执行；
- 同一 tool_call_id 不重复执行；
- 第 7 个工具不执行；
- 第 5 个模型回合不发生；
- 达预算返回 `BUDGET_EXCEEDED`；
- timeout/cancel 后停止；
- 普通 Chat 工厂未被设置 non-thinking；
- Agent 工厂始终传 `thinking.type=disabled`；
- 不依赖 reasoning_content；
- ToolResult 内的恶意“忽略系统指令”只作为数据；
- 模型请求 shell/write 工具被拒绝。
- Agent 与 Chat 共用 TurnCoordinator；transaction A/B、post-turn、Redis post-commit 和 terminal 顺序与 C1 相同。

### 15.3 Citation/隔离

- A 项目不能读取 B 项目 chunk；
- 伪造其他项目 chunk ID 得到 scope denied/not found；
- Citation 的 excerpt 与 ToolResult 完全一致；
- 伪造 Citation ID 在 token 发出前被 filtering sink 拦截，不进入 canonical reply/final citations；
- 伪造 marker 的顺序断言为：过滤阶段无 warning 事件 → assistant/citations transaction B commit → `post_turn.warning(component="citation_validation", code="CITATION_REJECTED")` → `chat.completed`；
- 工具失败不发 `citation.added`；
- inline citation 和响应 citation list 一致；
- assistant + citations_json 原子提交；刷新 Conversation 后 Citation snapshot 与首次响应一致；
- 所有 tool/citation 事件含 protocol_version/conversation_id/turn_id/sequence 且 SSE id=sequence；
- `mode=chat` 不出现工具事件。

### 15.4 命令

```bash
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
(cd codeaware-py && uv run python scripts/run_tests_safe.py \
  tests/test_tool_registry.py \
  tests/test_tool_executor.py \
  tests/test_knowledge_tools.py \
  tests/test_read_only_agent.py \
  tests/test_agent_events.py \
  tests/test_agent_api.py \
  tests/test_agent_message_citations.py -q)

(cd codeaware-py && uv run python scripts/run_tests_safe.py -q)
(cd codeaware-py && uv run python scripts/run_tests_safe.py --cov=app --cov-report=term-missing -q)
```

```bash
(cd codeaware-py/frontend && npm run lint)
(cd codeaware-py/frontend && npm run build)
```

真实模型单独执行：

```bash
(cd codeaware-py && uv run python scripts/run_tests_safe.py --live-eval -m live_eval tests/live_eval/test_deepseek_read_only_agent.py -q)
```

如项目仍统一使用 `integration` marker，则沿用该名称，不同时创造两个含义重复的 marker。所有后端、migration roundtrip 和 live-eval 测试都必须由 safe runner 创建/校验本次一次性 PG/Redis；禁止裸跑 pytest/Alembic。

## 16. 可重复演示脚本

### 16.1 准备

完整演示由 `codeaware-py/scripts/demo_s4_read_only_agent.sh` 启动 disposable PG/Redis namespace，并生成一次性：

```bash
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
: "${CODEAWARE_DEMO_ISOLATED:?must point to safe-runner disposable stack}"
demo_suffix="$(python -c 'import uuid; print(uuid.uuid4().hex[:12])')"
```

脚本必须在 `trap` 中销毁整个 demo namespace；禁止复用固定 slug/conversation 或清理共享数据库。

1. 创建 `agent-a-${demo_suffix}`、`agent-b-${demo_suffix}`；
2. A 上传“缓存穿透使用布隆过滤器或缓存空值”的文档；
3. B 上传内容不同的文档；
4. 使用 A scope 启动 Chat；
5. 打开浏览器 Network/SSE 或项目事件调试面板。

### 16.2 正常路径

以 `mode=agent` 发送：

```text
项目建议怎样处理缓存穿透？请引用项目资料。
```

核验：

- 只调用 A 项目的 `search_knowledge`；
- 工具次数不超过 6；
- 模型回合不超过 4；
- 事件顺序符合公共契约；
- 答案 Citation 可展开并匹配 A 的 chunk；
- B 的内容不出现；
- trace 中有 model/toolset/prompt/index 版本和耗时。

### 16.3 无工具路径

发送“你好”，核验模型可以直接回答，工具次数为 0。

### 16.4 安全/预算路径

- Fake Model 请求 `run_shell`，得到 `TOOL_NOT_ALLOWED`；
- Fake Model 连续请求 7 次工具，第 7 次不执行并返回 `BUDGET_EXCEEDED`；
- Fake Model 在答案写入随机 Citation ID，前端不渲染该来源，并出现 warning。
- 刷新页面/重新读取 Conversation，合法 Citation 仍由 PG snapshot 恢复，伪造 marker 不出现。

### 16.5 回退

设置：

```env
READ_ONLY_AGENT_ENABLED=false
```

核验 `mode=chat` 正常，`mode=agent` 明确返回不可用错误，不静默降级成 Agent 成功。

## 17. Definition of Done

- [ ] C1–C3、S1/S2 及当前所选直接依赖 evidence 已核验
- [ ] `mode=chat` 默认且当前 Chat contract 无回归
- [ ] Agent 模型固定 DeepSeek non-thinking
- [ ] Registry 只包含内部 R0_READ 工具
- [ ] Registry 以 `(name,version)` 唯一、每 name 只暴露一个 active version，完整 definition hash 稳定
- [ ] 模型无法覆盖 sentinel actor/header project scope，remote 仍禁用
- [ ] Tool 输入输出均通过 Pydantic/schema 校验
- [ ] timeout、最大输出和统一错误码均已实现
- [ ] 模型最多 4 回合、工具最多 6 次
- [ ] 达预算时没有隐式额外模型调用
- [ ] ToolResult 被作为不可信数据处理
- [ ] Citation 由服务端创建、streaming whitelist 验证并与 ASSISTANT 原子持久化
- [ ] 伪造 Citation/Tool/跨项目访问测试通过
- [ ] SSE 工具和 Citation 事件继承完整 `ChatEventBase`
- [ ] 前端能展示工具时间线和来源，刷新后由 PG 恢复 Citation
- [ ] Agent/Chat 共用 C1 TurnCoordinator，transaction A/B、post-turn、Redis/terminal 无回归
- [ ] 无 AgentRun、ToolCall、RunEvent、Artifact、Approval 表
- [ ] 无文件、Git、shell、网络或写工具
- [ ] 普通 CI 不访问真实 DeepSeek/Ollama
- [ ] Python 全量测试和覆盖率检查通过
- [ ] 前端 lint/build 通过
- [ ] feature flag 回退已验证
- [ ] 本阶段实现/验收位于记录 base commit 的 detached 临时 worktree，用户当前工作树未变化
- [ ] safe runner 精确清理本次一次性 PG/Redis，stack identity/cleanup report 已进入 manifest
- [ ] `evidence/S4/manifest.json`、`report.md` 和哈希引用产物已完成，validator 通过

## 18. 回滚

立即回退：

```env
READ_ONLY_AGENT_ENABLED=false
CHAT_RUNTIME=graph
```

回退后：

- `mode=chat` 继续使用当前 S2 service runtime；只有 Graph profile 已选择时才使用 S3；
- `mode=agent` 返回明确的 feature disabled 错误；
- 不删除 Conversation/Message；
- 立即 feature rollback 不需要数据库 downgrade；`citations_json` 保留为向后兼容的只读历史数据；
- 可保留 schemas 和前端兼容类型。

若彻底移除，只能在从记录 base commit 创建的 detached 临时 worktree + safe runner 的另一套一次性 PG/Redis 中验证反向补丁：

1. 先关闭 feature flag；
2. 删除 Agent runtime、registry、executor、built-in tools；
3. 删除独立 Agent 模型工厂和相关配置；
4. 移除前端 Agent 开关但保留类型化 Chat SSE；
5. 运行当前所选 Chat runtime contract；
6. 若确认可丢弃所有 Citation provenance，只在一次性数据库执行 S4 downgrade roundtrip；Message 文本必须保留；
7. 不恢复裸 token SSE。

禁止在用户当前工作树直接 `git revert`、`checkout/reset/clean` 或运行 downgrade；开发/共享/生产库默认不 downgrade，只记录备份恢复与前向修复方案。

## 19. 验收证据与交接

生成唯一机器入口 `evidence/S4/manifest.json`、人类可读 `report.md` 和 manifest 哈希引用的产物；旧式单文件 evidence、Markdown 勾选或未被 manifest 引用的文件不能解锁 S5。最后从仓库根运行 `(cd codeaware-py && uv run python scripts/validate_stage_evidence.py S4)`。清单额外记录：

- Registry 中全部工具 name/version/risk/scope/schema hash；
- DeepSeek non-thinking 配置证据；
- 4/6 预算边界测试；
- 工具事件完整样本；
- Citation 生成、streaming whitelist、`citations_json`、刷新恢复和前端卡片对照；
- 跨项目、伪造工具、伪造 Citation、恶意 ToolResult 安全测试；
- migration upgrade/downgrade 与 feature flag 回退；
- runtime、model、Prompt、toolset、index 版本；
- 平均/最大模型回合、工具次数、token、时延；
- 明确声明“Tool/Event 未持久化、Message Citation 已持久化、Run 不可恢复、工具无仓库访问”。

交给 S5 的稳定接口：

- `ToolDefinition` / `ToolResult` / `ToolError`；
- `ToolRegistry` / `ToolExecutor`；
- `ToolContext` 和可信 scope 注入；
- `CitationFactory` / `CitationValidator` / `CitationFilteringSink`、本轮 whitelist 与 `messages.citations_json` 原子持久化；
- `ReadOnlyAgentRuntime` 的预算和事件出口；
- 只读工具注册方式。
