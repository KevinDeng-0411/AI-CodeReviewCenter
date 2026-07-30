# S3：确定性 LangGraph Workflow

> **条件型平台参考，个人默认不实施。** S3 不再是 S4 的硬前置，也不创建 skipped/passed
> manifest。只有在 S2 后、S4 前出现[明确触发条件](personal/可选升级触发条件.md)，并先
> 修订路线、阶段卡与证据 DAG 后，本文件才可作为设计输入；S4/S5 已完成后不得直接执行旧卡。
>
> **状态：Future / Locked（未来候选，当前版本禁止实施）**
>
> 本文不是当前版本任务，也不构成自动开工授权。只有同时满足以下条件，才允许由用户另行决定是否实施：
>
> 1. `docs/roadmap/current-release/evidence/C3/manifest.json` 已存在、validator 通过且结论为“当前版本完成、允许评审 Agent 路线”；
> 2. S1、S2 的 `evidence/S1/manifest.json`、`evidence/S2/manifest.json` 均存在、validator 通过且可复现；当前 Chat 基线直接引用 C1–C3 manifests，不另建 S0 evidence；
> 3. 路线、阶段卡和证据 DAG 已纳入 S3，且用户在上述 S2 evidence 形成、这些修订完成
>    之后，对 **S3** 给出新的、明确的实施授权。
>
> 任一条件不满足时，只能阅读和评审本文，不能安装 LangGraph、修改代码、创建迁移或把本阶段并入当前版本。C3 完成也只代表具备评审条件，不代表默认进入 S3。

> 本阶段只把 S2 已分层的 Chat 编排迁移到固定节点、固定边的 LangGraph Workflow。
> **LangGraph 在本阶段不是 Agent**：模型不能选择节点、工具或下一步，也不存在工具循环。
>
> S3 延续公共契约的 local single-user sentinel、loopback-only 和 header-only Project scope。它不增加认证/RBAC，不允许远程访问，也不重新实现 C1 的 ChatEvent、summary/post-turn 或 C2 API。

---

## 实施入口 / 本阶段闭环

公共类型、`ChatEventBase`、API base path、sentinel 和错误语义只以[公共契约](00-执行约定与公共契约.md)为准；本文只描述 S3 的确定性 Graph 增量。

| 项目 | 唯一入口 |
|---|---|
| 前置 manifest | C1/C2/C3 + S1/S2 manifest/validator、S2 ports/UoW hashes、OpenAPI、Alembic head、S3 明确授权 |
| 唯一增量 | `ChatRuntime` adapter、固定 Graph state/nodes/edges、节点 trace、`service|graph` 临时回退 |
| 必测 | 两 runtime 的 Prompt/SSE/DB/UoW/warning parity；固定边；一次写入；sentinel/header 不变 |
| 演示 | 独立 fixture Conversation 分别走 service/graph，业务输出相同且 Graph 多出固定节点 trace |
| 回退 | `CHAT_RUNTIME=service`；代码反向验证只在 detached 临时 worktree + 一次性 PG/Redis，无数据删除 |
| 下一步 | evidence 完整后交给 S4 Runtime/event sink；不得把 Workflow 宣称 Agent 或提前注册 Tool |

## 1. 阶段目标

在不改变现有 DeepSeek 模型、Prompt、上下文内容、消息持久化语义和 Chat API 的前提下，交付一条可切换的确定性 Graph 运行路径，并用 `service | graph` 双运行时契约测试证明行为等价。

完成后，系统具备：

- 固定、可观察的 Chat 节点和边；
- Graph 节点级 trace；
- `service` 与 `graph` 两种运行时的等价测试和回退开关；
- S4 可以复用的 Runtime 接口和类型化事件出口。

完成本阶段后仍只能称为 **Workflow**，不得在页面、README、接口或交接材料中称为 Agent。

## 2. 可演示成果

同一套测试数据和 Fake LLM 分别以 `CHAT_RUNTIME=service`、`CHAT_RUNTIME=graph` 运行，得到：

1. 相同的规范化 Prompt；
2. 相同的 assistant 回复；
3. 相同的用户消息、助手消息保存次数；
4. 相同的类型化 SSE 业务事件和顺序；
5. 相同的 RAG、长期记忆、短期记忆与 Prompt 版本；
6. 相同的非致命 warning 和致命错误语义；
7. Graph 路径额外产生节点 trace，但不改变客户端业务 payload。

人工演示时可在两个运行时之间切换并发送相同问题；Graph trace 应明确显示：

```text
START
  → prepare_turn
  → assemble_context
  → render_prompt
  → generate_reply
  → persist_reply
  → post_turn
  → END
```

边是固定的。除统一错误终止外，不允许模型、Prompt 内容或模型响应决定下一节点。

## 3. 前置条件与阶段门禁

开始前必须确认 current-release C1–C3、S1、S2 已完成并有对应 evidence：

- current-release C1 已将裸 SSE token / `[DONE]` 升级为公共契约中的类型化事件；
- S1 的 Chat、Knowledge、Memory、Conversation 已强制携带并校验 `project_id`；
- S2 已将 Chat 编排与 ORM、Redis、模型 client 分离，存在可 mock 的 use case / port；
- S2 的业务入口已经返回类型化 reply、warning、usage 和 UoW 结果，而不是依靠吞异常；S3 可在这些稳定值之上定义唯一 `ChatTurnResult` adapter，不得复制业务 service；
- 当前全量 Python 测试、覆盖率检查、前端 lint/build 可通过；
- 当前 Git 修改已经记录，不能覆盖其他阶段或用户修改。

若 S2 的实际类名与本文建议名不同，应复用 S2 已落地接口并做机械映射，不得创建第二套重复的领域 service。

实施前运行：

```bash
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
(cd codeaware-py && uv run python scripts/run_tests_safe.py -q)
(cd codeaware-py && uv run python scripts/run_tests_safe.py --cov=app --cov-report=term-missing -q)
```

```bash
(cd codeaware-py/frontend && npm run lint)
(cd codeaware-py/frontend && npm run build)
```

## 4. 历史现状证据（pre-C1，必须复核）

下列内容只是路线写作时的历史快照。C1/C2/S1/S2 已修复或移动的项只做回归映射，不能在 S3 重做：

- `app/ai/services/chat.py` 同时负责创建 Conversation、保存消息、拼装三级上下文、调用模型、流式输出、保存回复和抽取长期记忆；
- `app/api/v1/deps.py` 在请求依赖中直接组装 Chat 的全部基础设施；
- `app/api/v1/chat.py` 直接依赖 `ChatService`；
- `app/ai/services/chat.py` 的 RAG 和长期记忆异常存在静默 `except Exception: pass`；
- 当前 Graph/LangGraph 依赖和 Graph 节点尚不存在；
- 当前 Chat 已有同步和流式两条入口，迁移必须同时覆盖；
- 当前 PG 是消息真相源，Redis 只是短期缓存，Graph 不得改变这一 ADR。

实现模型必须在 evidence 中引用实际文件和测试输出；不能只用本文描述代替仓库核验。

## 5. 范围

### 5.1 本阶段必须做

- 添加并锁定 LangGraph Python 依赖；
- 定义统一 `ChatRuntime` port；
- 保留 S2 的 service 编排，作为 `ServiceChatRuntime`；
- 新增确定性 `GraphChatRuntime`；
- 新增 Graph state、节点、固定边和编译工厂；
- 同步和流式 Chat 都通过 runtime port 调用；
- 增加 `CHAT_RUNTIME=service|graph` 配置；
- 为两个运行时建立行为契约测试；
- Graph 节点建立 trace，记录 runtime、模型、Prompt、索引版本和节点耗时；
- 在完成证据后将默认运行时切到 `graph`，但保留 `service` 回退至 S4 稳定。

### 5.2 明确不做

- 不定义或注册任何 Tool；
- 不让模型选择节点、边、工具或路由；
- 不加入循环、反思、自主规划、多 Agent、handoff；
- 不新增 `AgentRun`、`ToolCall`、`RunEvent`、`Artifact`、`Approval` 表；
- 不加入 LangGraph checkpointer 或 `MemorySaver`；
- 不实现暂停、恢复、重试、审批或持久化 Run；
- 不改 DeepSeek 模型、temperature、Prompt 模板或上下文排序；
- 不切换 thinking/non-thinking 模式；
- 不新增 `/api/agent-runs`；
- 不改 Java 版；
- 不并行调用真实 `service` 和 `graph` 作为在线 shadow，避免重复模型成本和重复消息写入。

## 6. 稳定接口与状态

### 6.1 Runtime port

若 S2 尚未以等价形式定义，新增：

```python
class ChatRuntime(Protocol):
    name: str

    async def run(
        self,
        turn: ChatTurnInput,
        event_sink: ChatEventSink,
    ) -> ChatTurnResult: ...
```

约束：

- `ChatTurnInput` 是内部 command：`actor_id` 固定为 `Literal["local-single-user"]`，`project_id` 来自 router 解析的 `X-Project-ID`，另含可选 `conversation_id` 和用户消息；公共 JSON body 不重复 actor/project；
- `ChatRuntime` 不向 router 泄漏 ORM、SQLAlchemy session、Redis 或 LangChain message 对象；
- `ChatTurnResult` 至少包含 `conversation_id`、`reply`、`usage`、warning 和本轮引用；
- 同步 adapter 传入 collecting sink，流式 adapter 传入 queue sink；二者都只调用同一个 `run()`，不能维护 `invoke/stream` 两套节点逻辑；
- `ChatEventSink` 只接收公共契约 `ChatEventBase` discriminated union，不接收预格式化 SSE 字符串；
- runtime 内部创建并消费 S2 `ChatUnitOfWork`；router 不持有 session，节点不自行提交。

### 6.2 Graph state

新增独立的 `ChatWorkflowState`，不要将它命名为 `AgentState`：

```python
class ChatWorkflowState(TypedDict, total=False):
    turn_id: str
    actor_id: Literal["local-single-user"]
    project_id: str
    conversation_id: str
    user_message: str
    context_refs: list[str]
    context_payload: dict
    rendered_prompt: str
    final_answer: str
    usage: dict
    warnings: list[dict]
    error: dict | None
```

规则：

- State 只能放 ID 和可 JSON 序列化值；
- 不放 ORM、session、Redis、模型 client、service、callback 或文件句柄；
- `context_payload`、Prompt 和回答必须沿用 S2 的长度上限；
- 本阶段不 checkpoint，state 仅存在于本次进程内；
- 节点依赖通过构造函数、运行时 context 或显式 port 注入，不写入 state；
- 节点返回增量更新，不原地修改共享对象；
- 不把 state 写入 Conversation/Message 表。

### 6.3 固定节点职责

| 节点 | 唯一职责 | 禁止事项 |
|---|---|---|
| `prepare_turn` | 校验 scope、创建/读取 Conversation、幂等保存 USER 消息 | 不加载 RAG，不调用模型 |
| `assemble_context` | 调用 S2 context use case，按既定顺序加载长期记忆、RAG、短期记忆 | 不拼 Prompt，不吞异常 |
| `render_prompt` | 用当前激活的 CHAT Prompt 和相同参数渲染 | 不更换 Prompt 或模型 |
| `generate_reply` | 恰好调用一次当前 Chat 模型，产生 token/usage | 不调用工具，不决定下一节点 |
| `persist_reply` | 幂等保存 ASSISTANT 消息 | 不抽取记忆，不重复保存 USER |
| `post_turn` | 执行 S2 已有摘要/长期记忆后处理并产生 warning | 失败不能改写已生成回复 |

图必须显式使用固定边：

```python
builder.add_edge(START, "prepare_turn")
builder.add_edge("prepare_turn", "assemble_context")
builder.add_edge("assemble_context", "render_prompt")
builder.add_edge("render_prompt", "generate_reply")
builder.add_edge("generate_reply", "persist_reply")
builder.add_edge("persist_reply", "post_turn")
builder.add_edge("post_turn", END)
```

允许基础设施异常统一终止 Graph，但不允许用 `add_conditional_edges` 根据模型输出路由。若错误处理必须使用条件边，只能读取服务端产生的结构化 `error.code`，且 evidence 必须证明模型内容无法影响分支。

### 6.4 流式适配

Graph runtime 通过 queue sink 输出 current-release C1 已定义的 `ChatEventBase` 事件；HTTP streaming adapter 只负责编码：

- `chat.started`
- `context.warning`
- `token.delta`
- `post_turn.warning`
- `chat.completed`
- `chat.failed`

推荐实现：

1. streaming adapter 创建仅在本请求生效的 `asyncio.Queue[ChatEvent]`；
2. Graph 在独立 task 中执行；
3. `generate_reply` 节点通过注入的 event sink 把 token 放入 queue；
4. adapter async generator 从 queue 读取并交给现有 SSE encoder；
5. Graph 正常或异常结束时必须产生唯一终态事件并结束 task；
6. 客户端断开时取消当前 S3 Graph task、rollback UoW 并释放资源；
7. 每个事件都保留完整 `protocol_version + conversation_id + turn_id + sequence`，SSE `id=sequence`；可选 transport `request_id` 只能留在 trace/log correlation，不能进入事件身份、状态幂等键或替代 `turn_id`。

S6 之前 HTTP 连接仍承载同步执行；本阶段不要伪装成 durable run。S6 会将“连接生命周期”和“Run 生命周期”分离。

## 7. 文件级实施清单

以下为建议路径；若 S2 已建立等价目录，必须扩展现有文件而不是复制：

| 文件 | 变更 |
|---|---|
| `codeaware-py/pyproject.toml` | 添加 LangGraph 依赖 |
| `codeaware-py/uv.lock` | 用 `uv lock`/`uv sync` 更新锁文件 |
| `codeaware-py/app/core/config.py` | 增加 `chat_runtime: Literal["service", "graph"]`，完成阶段后默认 `graph` |
| `codeaware-py/app/ai/runtime/chat_runtime.py` | `ChatRuntime`、`ServiceChatRuntime`、运行时选择器 |
| `codeaware-py/app/ai/workflows/chat_state.py` | `ChatWorkflowState` |
| `codeaware-py/app/ai/workflows/chat_nodes.py` | 六个薄节点；只调用 S2 use case/port |
| `codeaware-py/app/ai/workflows/chat_graph.py` | 固定边、Graph 编译和 `GraphChatRuntime` |
| `codeaware-py/app/ai/observability/tracing.py` | 若 S2 尚无 trace port，增加最小节点 span 接口；不得持久化敏感全文 |
| `codeaware-py/app/api/v1/deps.py` | 按配置注入 `ChatRuntime`，请求 session 不得被全局缓存 |
| `codeaware-py/app/api/v1/chat.py` | 只依赖 runtime/use case port；API 路径和 envelope 不变 |
| `codeaware-py/tests/test_chat_graph.py` | 图结构、节点输入输出、失败终止测试 |
| `codeaware-py/tests/test_chat_runtime_contract.py` | service/graph 参数化契约测试 |
| `codeaware-py/tests/test_chat_sse_runtime_contract.py` | 两运行时 SSE 事件等价测试 |
| `codeaware-py/tests/test_chat_runtime_config.py` | 配置选择、非法配置、回退测试 |

不要让 `chat_nodes.py` 导入 `app.models`、`sqlalchemy` 或 `app.db`。这些访问必须留在 S2 的 repository/service adapter 中。

## 8. 顺序化实施步骤

### 步骤 1：冻结 S2 行为样本

用 Fake LLM、Fake embedder 和固定数据库 fixture 保存以下 golden 信息：

- 渲染后的完整 Prompt hash；
- USER/ASSISTANT 消息内容和逻辑轮次；
- Context 各部分的顺序；
- SSE 事件类型、业务 payload 和 token 原样拼接结果；
- RAG/长期记忆失败时的 warning；
- 模型超时和空输出的错误码；
- usage 汇总。

golden 不得包含随机 request ID、时间戳或 trace ID。

### 步骤 2：引入 Runtime port

先用 `ServiceChatRuntime` 包住 S2 已有编排并让现有测试全部通过。此时不加入 Graph，证明 port 本身没有改变行为。

### 步骤 3：实现 state 和薄节点

- 每个节点只调一个 S2 use case 或 port；
- 每个节点单测正常、异常和空值；
- 非致命错误按 C1 phase 映射：context 构建降级为 `context.warning`，ASSISTANT commit 后的 post-turn/cache 降级为 `post_turn.warning`；
- 致命错误映射到公共错误码；
- 节点不得 `commit()`；事务边界沿用 S2 application service；
- `prepare_turn` 和 `persist_reply` 必须保持 S2 幂等规则。

### 步骤 4：编译固定 Graph

- 显式声明全部节点和固定边；
- 不配置 checkpointer；
- 不使用模型内容做条件路由；
- Graph 编译对象不能闭包捕获已关闭的 request session；
- 若每请求构造 Graph，记录构造成本；若缓存 Graph，所有节点依赖必须是无状态 port 或通过 runtime context 注入。

### 步骤 5：接入同步入口

设置 `CHAT_RUNTIME=graph` 后，`POST /api/chat/send` 走 Graph；响应 envelope 和字段与 service 路径一致。

### 步骤 6：接入流式入口

统一由 SSE encoder 把 `ChatEvent` 编码为：

```text
id: 2
event: token.delta
data: {"protocol_version":1,"conversation_id":"...","turn_id":"...","sequence":2,"delta":"原始 token"}

```

不得在 Graph 节点中手拼 `data:` 行，不得对 token `strip()`/`trim()`，不得用 `request_id` 替换公共 base 字段。

### 步骤 7：建立双运行时契约测试

所有核心场景用：

```python
@pytest.mark.parametrize("runtime_name", ["service", "graph"])
```

两条路径分别使用隔离的 conversation/transaction，不能让一次测试把同一条消息保存两次。等价比较时只规范化随机 ID、时间戳、trace/runtime 元数据，不能忽略业务字段。

### 步骤 8：观察后切默认值

先以 `service` 为默认完成自动测试，再以 `graph` 运行完整测试和演示。所有证据通过后，配置默认值切为 `graph`，并保留 `CHAT_RUNTIME=service` 到 S4 稳定。

## 9. 数据、接口和迁移

### 9.1 数据库

本阶段预期 **无 Alembic migration**。

若实现需要新增 `AgentRun`、checkpoint、ToolCall 或 RunEvent 表，说明范围已经越过 S3，应停止并退回本文边界。

### 9.2 API

保持：

- `POST /api/chat/send`
- `POST /api/chat/send/stream`
- Conversation 查询和删除接口

请求和响应必须与 S2/C3 兼容：base path 仍为 `/api`，Project scope 只来自 `X-Project-ID`，JSON 继续使用冻结的 `Result[T]` envelope。Runtime 名只写 trace/内部指标，不要求成为公开业务字段；body 不新增 actor/project。

### 9.3 配置

新增：

```env
CHAT_RUNTIME=graph
```

非法值必须在启动期由 settings 校验失败，不能静默回落。

## 10. 自动测试

### 10.1 必测场景

1. 固定边恰好包含预期节点，不存在模型条件边；
2. 每个节点只执行一次；
3. 同步 service/graph 的 Prompt hash、回复、usage、warning 等价；
4. 流式 service/graph 的 token 不丢空格、不合并、不 `trim()`；
5. 两运行时所有事件都继承 `ChatEventBase`，`id == sequence`，且没有 request-only envelope；
6. USER 和 ASSISTANT 各保存一次；
7. Redis miss 时仍遵循 PG fallback；
8. RAG 无结果、长期记忆无结果正常完成；
9. RAG/长期记忆非致命失败产生相同 warning；
10. Prompt 不存在时保持 S2 已确定的 fallback 或错误行为；
11. 模型超时、模型异常、空输出映射相同错误；
12. assistant 保存失败不产生伪 `chat.completed`；
13. post-turn 失败不丢失已持久化回答，并产生 warning；
14. Graph state 中不存在 session/model/Redis/ORM；
15. actor 始终为 sentinel、project 只来自 header、remote 仍禁用；
16. `CHAT_RUNTIME=service` 可立即回退；
17. 普通 CI 不访问真实 DeepSeek、Ollama。

### 10.2 命令

```bash
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
(cd codeaware-py && CHAT_RUNTIME=service uv run python scripts/run_tests_safe.py \
  tests/test_chat_runtime_contract.py \
  tests/test_chat_sse_runtime_contract.py -q)

(cd codeaware-py && CHAT_RUNTIME=graph uv run python scripts/run_tests_safe.py \
  tests/test_chat_graph.py \
  tests/test_chat_runtime_contract.py \
  tests/test_chat_sse_runtime_contract.py \
  tests/test_chat_runtime_config.py -q)

(cd codeaware-py && CHAT_RUNTIME=graph uv run python scripts/run_tests_safe.py -q)
(cd codeaware-py && CHAT_RUNTIME=graph uv run python scripts/run_tests_safe.py --cov=app --cov-report=term-missing -q)
```

```bash
(cd codeaware-py/frontend && npm run lint)
(cd codeaware-py/frontend && npm run build)
```

所有后端测试与 runtime parity 故障注入都由 safe runner 创建/校验本次一次性 PG/Redis；禁止裸跑 pytest。

## 11. 可重复演示脚本

### 11.1 前置

1. 由 `run_tests_safe.py` 创建并校验带唯一 stack identity 的一次性 PostgreSQL/Redis；演示 project/conversation/knowledge/memory 均使用随机 UUID 后缀，禁止复用开发数据；
2. 执行 Alembic upgrade；
3. 在同一项目中准备一条可召回 Knowledge 和一条长期记忆；
4. 使用同一 Prompt 版本、模型和索引版本；
5. 准备两个独立 Conversation，避免消息历史互相污染。

### 11.2 Service 路径

```bash
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
: "${CODEAWARE_DEMO_ISOLATED:?must point to safe-runner disposable stack}"
(cd codeaware-py && CHAT_RUNTIME=service uv run uvicorn app.main:app --port 8000)
```

调用 Chat 同步和流式接口，保存：

- HTTP 响应；
- SSE 业务事件；
- Conversation/Message 查询结果；
- Prompt hash、usage、warning、trace 摘要。

### 11.3 Graph 路径

停止进程后：

```bash
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
: "${CODEAWARE_DEMO_ISOLATED:?must point to safe-runner disposable stack}"
(cd codeaware-py && CHAT_RUNTIME=graph uv run uvicorn app.main:app --port 8000)
```

对隔离 Conversation 发送同样问题，保存同样信息。展示 Graph trace 的六个节点均出现且顺序固定。

### 11.4 故障演示

用可控 fake 或故障注入令 RAG 超时：

- 两运行时都应继续回答；
- 都产生相同 `context.warning`；
- 不出现裸堆栈或静默丢失；
- Graph 不得因此走模型决定的替代节点。

## 12. Definition of Done

- [ ] C1–C3、S1、S2 evidence 已核验
- [ ] LangGraph 依赖和 lock 文件已提交
- [ ] Graph 只有固定节点、固定边，没有工具和模型路由
- [ ] service/graph 共用 S2 use case/port，没有复制业务逻辑
- [ ] 同步和流式入口都通过 `ChatRuntime`
- [ ] 双运行时 golden contract 全部通过
- [ ] 两 runtime 共用单一 `run()+event sink`，没有 invoke/stream 双业务编排
- [ ] 所有事件继承公共 `ChatEventBase`，保留 protocol_version/conversation_id/turn_id/sequence 且 SSE id=sequence
- [ ] USER/ASSISTANT 消息无重复写入
- [ ] Graph state 不含 ORM、session、Redis、模型 client
- [ ] Graph 未配置 checkpointer，未新增 Agent 相关表
- [ ] Graph 节点 trace 可见且敏感正文默认不落 trace
- [ ] Python 全量测试和覆盖率检查通过
- [ ] 前端 lint/build 通过
- [ ] `CHAT_RUNTIME=service` 回退已实际验证
- [ ] 默认运行时在完成证据后切为 `graph`
- [ ] 没有对外把 S3 称为 Agent
- [ ] local sentinel、header-only Project scope 和 remote-disabled 均未改变
- [ ] 未重做 C1/C2 的 SSE、post-turn、API 或 AIReadMe
- [ ] 本阶段实现/验收位于记录 base commit 的 detached 临时 worktree，用户当前工作树未变化
- [ ] safe runner 精确清理本次一次性 PG/Redis，stack identity/cleanup report 已进入 manifest
- [ ] `evidence/S3/manifest.json`、`report.md` 和哈希引用产物已完成，validator 通过

## 13. 回滚

首选无数据回滚：

```env
CHAT_RUNTIME=service
```

重启 Web 进程后验证同步、流式 Chat 和 Conversation 查询。由于本阶段无数据库迁移，切换 runtime 不应修改或丢失数据。

代码回退演练只允许在从记录 base commit 创建的 detached 临时 worktree + safe runner 的另一套一次性 PG/Redis 中进行：

1. 先切回 `service`；
2. 验证 Chat；
3. 在临时 worktree 应用反向补丁并验证 Graph 依赖、state、nodes、factory 已退出；
4. 更新 lock 文件；
5. 不回滚 C1–C3、S1–S2 的公共事件和分层接口。

禁止在用户当前工作树直接 `git revert`、`checkout/reset/clean`，禁止通过删除 Conversation/Message 数据来“回滚” Graph；临时 worktree/stack 必须按精确 identity 清理并写入 manifest。

## 14. 验收证据与交接

生成唯一机器入口 `evidence/S3/manifest.json`、人类可读 `report.md` 和 manifest 哈希引用的产物；旧式单文件 evidence、Markdown 勾选或未被 manifest 引用的文件不能解锁 S4。最后从仓库根运行 `(cd codeaware-py && uv run python scripts/validate_stage_evidence.py S3)`。清单额外附上：

- service/graph 测试矩阵；
- 两运行时 Prompt hash 对照；
- 两运行时规范化事件 diff；
- 消息保存次数和数据库查询证据；
- Graph 可视化或节点/边清单；
- 节点 trace 截图或脱敏导出；
- `CHAT_RUNTIME=service` 回退记录；
- runtime、模型、Prompt、index 版本；
- 明确声明“本阶段无 Tool、无 AgentRun、无 checkpoint”。

交给 S4 的稳定接口：

- `ChatRuntime`；
- 类型化 `ChatEvent` / event sink；
- Graph state 和节点注入方式；
- 节点 trace 规范；
- `service|graph` 回退开关。

S4 可以新增只读工具循环，但不得把本阶段固定 Chat Graph 偷换成“已经完成 Agent”的证据。
