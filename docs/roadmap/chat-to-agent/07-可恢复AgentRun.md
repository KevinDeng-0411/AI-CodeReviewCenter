# S6：可恢复 Agent Run

> **条件型平台参考，个人默认不实施。** S5 完成不会自动解锁 S6。只有同步 HTTP 生命周期、
> 断线恢复、取消/重试或后台任务出现量化需求，并先修订路线/证据 DAG 后，才能请求 S6 授权。
>
> **状态：Future / Locked（未来候选，当前版本禁止实施）。**
>
> 只有默认 S5 evidence 通过、durable 触发条件有真实数据、路线与 evidence schema 已重新
> 修订，并且用户随后对 S6 另行明确授权，才能开工。S5 完成不自动授权本阶段；未选择 S3
> 不构成阻塞。
>
> 本阶段把 S4–S5 的同步只读 Agent 升级为可持久化、可取消、可重连、可恢复的任务运行时。它不增加写仓库能力。
>
> **实施入口 / 本阶段闭环：** 仅在 S5 evidence 与本阶段单独授权通过后，从同步只读 Agent 入口接入 `Run → Worker → checkpoint/领域幂等 → outbox/PG 事件 → 无缝重连 → 故障恢复`；以确定性 failpoint 证明无丢事件和无重复逻辑调用后才交接 S7。
>
> **契约来源：** Run、State、Tool、Event、Artifact、Approval、Risk 和错误的公共语义以[公共契约](00-执行约定与公共契约.md)为准；本文只定义 S6 的持久化、outbox、恢复和 API 增量。若正文与公共契约冲突，必须先修文档/ADR，不能由实现自行选择。

## 1. 阶段结果

完成后，用户可以启动一个 Agent 任务、断开浏览器、重启 Worker，再次连接后继续收到事件；已成功的 Tool Call、消息和产物不会因为重投递而重复生成。

本阶段的演示闭环是：

```text
创建 Run
  → Worker 执行模型和只读工具
  → 中途终止 Worker
  → 重启 Worker
  → 从 checkpoint 恢复
  → 客户端按 sequence 回放事件
  → Run 完成且无重复副作用
```

## 2. 开工门槛

- S5 的 `evidence/S5/manifest.json` 存在，且 `(cd codeaware-py && uv run python scripts/validate_stage_evidence.py S5)` 通过。
- S4 的 ToolDefinition、ToolResult、预算和错误码已稳定。
- S5 的仓库索引具有 `project_id / repository_id / revision` 作用域。
- 普通 Chat API 仍可独立运行。
- 记录开始 commit、现有测试数和同步 Agent 演示结果。

若 S5 尚未闭环，不得用本阶段顺便重写检索或工具。

## 3. 范围

### 必须完成

- `AgentRun / AgentStep / ToolCall / RunEvent / OutboxMessage` PostgreSQL 持久化。
- LangGraph PostgreSQL checkpointer。
- Celery Worker；Redis 只作 broker、实时通知和短期缓存。
- 新 Agent Run API、typed event 持久化与 `Last-Event-ID` 回放。
- 取消、显式重试、超时、Worker 故障恢复和幂等去重。
- 仓库索引任务从 Web 请求迁到同一 Worker 基础设施。
- OpenTelemetry trace，并输出到本地自托管 Phoenix。
- 前端 Run 时间线、断线重连、取消和重试入口。

### 明确不做

- 不生成或执行 patch。
- 不增加审批。
- 不创建分支、commit、push 或 PR。
- 不做多 Agent。
- 不把 Redis、Celery result backend 或 LangGraph checkpoint 当业务真相源。
- 不删除 Chat 兼容 API。

## 4. 数据模型

新增下一序号 Alembic revision；不要手写生产库 DDL。建议模型文件：

```text
app/models/agent_run.py
app/models/agent_step.py
app/models/tool_call.py
app/models/run_event.py
app/models/outbox_message.py
```

最低字段：

### `agent_runs`

| 字段 | 约束 |
|---|---|
| `id` | UUID PK |
| `project_id` | FK，非空，索引 |
| `conversation_id`、`turn_id` | 非空；复用或创建同项目 Conversation，并为全部 RunEvent 提供完整 `ChatEventBase` |
| `repository_id` | 可空，属于同一 project |
| `actor_id` | 非空；local 模式使用稳定本地 actor |
| `idempotency_key` | 非空 |
| `request_hash` | 规范化请求的 SHA-256；用于识别同 key 不同请求 |
| `mode` | `chat / agent`；本阶段不接受 `patch` |
| `status` | 公共契约状态机 |
| `task` | 原始任务 |
| `base_commit` | 可空 |
| `runtime_version` | graph/runtime 版本 |
| `model_name`、`prompt_version`、`toolset_version`、`index_revision` | 可追溯版本 |
| `budget`、`usage`、`result`、`error` | JSONB |
| `next_event_sequence` | 非空；事务内原子递增，禁止 `MAX(sequence)+1` |
| `cancel_requested_at` | 可空 |
| `started_at`、`finished_at`、`created_at`、`updated_at` | 时间 |

唯一约束：

```text
(project_id, actor_id, idempotency_key)
```

### `agent_steps`

保存 `run_id`、稳定 `step_key`、节点名、attempt、status、输入/输出摘要、错误、起止时间。`(run_id, step_key, attempt)` 唯一。

### `tool_calls`

遵守公共契约，`tool_calls` 至少保存 `run_id`、`step_id`、跨 attempt 稳定的 `logical_step_key` 和 `logical_tool_call_id`、tool name/version、canonical arguments、`arguments_hash`、`invocation_fingerprint`、status、结果/错误、citation ids、幂等键、起止时间。`invocation_fingerprint` 是稳定编码的 `tool_name + tool_version + arguments_hash` 的 SHA-256。

另建 `tool_call_provider_refs` 显式保存 provider 协议映射，至少包含 `run_id`、`logical_tool_call_id`、`model_round_key`、原样 `provider_tool_call_id TEXT`、`observed_attempt` 和时间。约束：

```text
(run_id, model_round_key, provider_tool_call_id) unique
(run_id, logical_tool_call_id, model_round_key) unique
```

唯一约束：

```text
(run_id, logical_step_key, logical_tool_call_id)
```

`logical_tool_call_id` 在首次准备调用、尚未执行 Tool 前持久化；Worker 重投递、checkpoint 恢复和 attempt 递增都必须复用它。`provider_tool_call_id` 只为模型协议关联原样保存，不能代替 logical ID；provider 恢复时给出不同原始 ID，就为新的 `model_round_key` 追加映射，不得修改历史映射或重复执行同一 logical call。logical ID 也不能只用参数 hash 代替：同一 Step 合法地以相同参数调用同一 Tool 两次时，两次调用应有不同 logical ID；同一逻辑调用重试时，即使 `step_id/attempt` 改变也应保持同一 logical ID。重复投递遇到已完成记录且 fingerprint 相同时返回已保存结果，不再次调用工具；同一 logical ID 再次出现但 tool name/version/canonical arguments hash 任一不同，必须返回稳定的 `IDEMPOTENCY_MISMATCH`，不能复用旧结果或覆盖原记录。对具有外部副作用的 provider 还必须把该 logical ID 映射为 provider 幂等键。

### Agent 消息与 post-turn 幂等字段

S6 migration 同步扩展现有 Message：

- `agent_run_id UUID NULL`，外键指向 `agent_runs.id`；
- `logical_turn TEXT NULL`，由 graph/use case 在第一次准备消息时生成并写入 checkpoint；
- check constraint：二者必须同时为空或同时非空；
- partial unique index：`(agent_run_id, role, logical_turn) WHERE agent_run_id IS NOT NULL`。

Run 创建事务写用户消息，最终回答事务写 assistant 消息；两者都用稳定 `logical_turn`。`save_message` 采用 insert-on-conflict 后读取旧行并比较 `project_id/conversation_id/content_hash/citations_hash`：完全相同则复用，任一不同返回 `IDEMPOTENCY_MISMATCH`，不能覆盖。assistant Message、对应 `run_event` 与 outbox 在同一 UoW 提交，避免“消息已写但完成事件丢失”。

长期记忆写入同样增加 nullable `source_run_id/source_effect_key` partial unique constraint，或使用等价、受数据库唯一约束保护的 durable effect ledger；实现者必须在 migration 与报告中选择并冻结一种，不能只靠进程锁。Conversation summary 继续复用 C1 的 committed-message watermark/CAS，因此相同 Run 的 post-turn 重放不会重复推进摘要。非 Agent Chat 数据不填这些字段。

### `run_events`

保存 `run_id`、`sequence`、`event_type`、JSONB payload、`created_at`；`(run_id, sequence)` 唯一。payload 必须包含公共 `protocol_version/conversation_id/turn_id/sequence` 与本阶段新增的 `run_id`，其中 payload sequence 必须等于行 sequence 和 SSE id。sequence 必须通过锁定 Run 行或 `UPDATE ... SET next_event_sequence = next_event_sequence + 1 RETURNING` 在同一数据库事务中分配，不能用进程内计数器或 `MAX(sequence)+1`。

### `outbox_messages`

保存待投递的 Run task 和事件通知，至少包含 `id`、`topic`、`aggregate_id`、`dedupe_key`、payload、status、attempt、`available_at`、`published_at` 和错误摘要；`dedupe_key` 唯一。领域状态、对应 `run_event` 与 outbox 必须在同一事务中提交。Dispatcher 可重复发布，消费者只把通知视为“去 PG 拉取”的唤醒信号。

## 5. 目标模块

建议按下列边界实现；若 S2 已采用不同名称，只做机械映射并在证据文档记录。

```text
app/schemas/agent_run.py
app/repositories/agent_runs.py
app/repositories/run_events.py
app/ai/runtime/run_service.py
app/ai/runtime/durable_graph.py
app/ai/runtime/checkpoint.py
app/ai/runtime/idempotency.py
app/ai/infra/event_bus.py
app/ai/infra/outbox.py
app/api/v1/agent_runs.py
app/workers/celery_app.py
app/workers/tasks/agent_runs.py
app/workers/tasks/indexing.py
```

前端建议新增：

```text
frontend/src/api/agentRuns.ts
frontend/src/features/agent-runs/
frontend/src/types/runEvents.ts
```

`app/api/v1/` 是现有 Python 包目录名，不代表公开 URL 版本前缀；本阶段所有公开路由统一挂在 `/api`。

## 6. 实施顺序

### 6.1 冻结版本与状态

1. 更新 `pyproject.toml`，加入兼容版本的 `langgraph`、PostgreSQL checkpointer、Celery、OpenTelemetry SDK/OTLP exporter和 Phoenix 接入包。
2. 使用 `uv lock` 固定解析结果；证据文件记录实际版本。
3. Graph State 只保存公共契约中的 ID 和 JSON；大型结果继续留在数据库。
4. 为 graph/runtime/toolset 建立显式版本常量，恢复旧 Run 时使用创建时版本。无法加载旧版本时明确失败，不静默改用新图。

### 6.2 创建 Run

实现：

```http
POST /api/agent-runs
Idempotency-Key: <client-generated-key>
X-Project-ID: <uuid>
```

router 将 JSON body、`X-Project-ID`、`Idempotency-Key` 和服务端可信 local context 注入的 `local-single-user` sentinel 组装为公共 application `AgentRunRequest`；project/key/actor 不在 body 重复出现。S9-C 之前不得把这里描述成远程认证。事务内：

1. 解析 actor 和 project scope。
2. 对除传输字段外的规范化请求计算 `request_hash`，以 `(project_id, actor_id, idempotency_key)` 查重。
3. key 已存在且 hash 相同时返回原 `run_id`；key 相同但 hash 不同返回 `IDEMPOTENCY_MISMATCH`，不得静默复用旧 Run。
4. 通过 C1/S2 的项目化 Conversation port 校验传入 cid；未传时创建新 Conversation。服务端生成本 Run 的 `turn_id`，二者在 Run 上均非空。
5. 创建 `PENDING` Run，并按本节 Message 唯一键写入一次用户消息；同时写首条 `run.started`/状态事件和 enqueue outbox。每条事件继承完整 `ChatEventBase` 并额外带 `run_id`。
6. transaction commit 后由 outbox dispatcher 投递 Celery task；API 不直接承担唯一一次投递。

定时 reconciliation 扫描长期 `PENDING` 且没有有效 task/outbox 的 Run 作为兜底。Outbox 和扫描都可能重复投递，因此 Worker 仍必须按 Run/Step logical ID 去重；不能让数据库任务永久丢失。

### 6.3 Worker 与 checkpoint

1. Celery 使用 Redis broker；业务结果仍写 PG。
2. Worker 每次 task/step 通过 `AsyncSessionLocal` 创建自己的 session，严禁传递 FastAPI 请求 session。
3. 以 `run_id` 作为 LangGraph thread/checkpoint 标识。
4. task 开始时用行锁或租约把 `PENDING` 原子转为 `RUNNING`。
5. 每个模型节点、工具节点和业务写节点都必须可重入。Tool 节点采用 `prepare logical call → 执行/查询 provider → 持久化结果与事件 → checkpoint` 协议；若领域结果已成功而 checkpoint 未写入，恢复时返回已保存结果；若 checkpoint 已写但领域事务失败，则按同一 logical ID 重入。
6. Celery 启用 late acknowledgment 和 worker-lost 重投递；超时区分 soft/hard timeout。
7. 每个节点边界检查 `cancel_requested_at`；工具运行期间尽可能传播取消，不能在 `CANCELLED` 后写成功事件。

checkpoint 表由官方 Postgres saver 管理，领域表由 Alembic 管理；二者不能互相替代，也不假设两者天然处于同一原子事务。实现必须显式覆盖“领域成功/checkpoint 失败”和“checkpoint 成功/领域失败”两个方向。

### 6.4 事件写入与回放

新增：

```http
GET /api/agent-runs/{run_id}
GET /api/agent-runs/{run_id}/events
POST /api/agent-runs/{run_id}/cancel
POST /api/agent-runs/{run_id}/retry
```

事件流程：

1. 在一次 PG 事务中完成领域状态变更、分配 sequence、写 `run_events` 和 notification outbox。
2. Outbox dispatcher 在 commit 后把 `{run_id, sequence}` 发布到 Redis channel/stream；若进程在 commit 后、publish 前退出，未发布 outbox 会被重新投递。
3. SSE 连接先建立 Redis 订阅并缓冲通知，再读取 PG 当前 high-water sequence；不得采用“先查 PG、后订阅”的有缝切换。
4. 从 PG 回放 `Last-Event-ID < sequence <= high-water`，随后消费缓冲通知；每次通知都只触发按 `sequence > last_seen` 查询 PG，不直接信任通知 payload。
5. 即使没有 Redis 通知，SSE heartbeat/短周期轮询也必须从 PG 补拉；检测到 sequence 缺口立即回 PG。Redis 停机或丢通知只能增加延迟，不能造成永久漏事件。
6. Run 已终止时，确认已回放至 PG 最新终态 sequence 且没有缺口后关闭连接。

`Last-Event-ID` 必须按本 Run 的非负有界整数校验；大于当前 high-water 的值返回结构化冲突，不能令客户端永久等待。

连接断开不取消 Run。前端用 `run_id` 恢复时间线，不从 UI 本地状态猜测任务结果。

### 6.5 取消与重试

- Cancel 在同一事务写 `cancel_requested_at`、`run.status` 和 outbox；Worker 通过条件更新竞争终态，确认停下后再以同一事务写 `CANCELLED` 和事件。
- 只有标记为可重试的 `FAILED` 可通过 retry 回到 `PENDING`。
- retry 保留同一 run、递增 attempt，并从合法 checkpoint 恢复。
- 终态 Run 不自动重启；`COMPLETED` 的重复 retry 返回冲突。
- 模型超时和 Tool timeout 分开记录，不能对已成功的副作用节点盲重试。

### 6.6 索引任务迁移

把 S5 同步索引入口改为创建 `indexing` job 并由 Worker 执行：

- API 返回 job/run id，不持有长 HTTP 请求；
- 每个文件按 `content_hash + revision` 幂等；
- 可查询进度、取消和重试；
- 失败保留上一版可用索引，只有完整成功后切换 current revision。

此处只迁移执行方式，不改 S5 的 scanner、chunking 和检索语义。

### 6.7 Trace

为 API 创建、排队、graph node、模型、检索、工具、checkpoint、事件和 Worker attempt 建立关联 span。最少标签见公共契约第 11 节。

- 本地 compose 增加 Phoenix/OTLP 接收端。
- 默认不记录完整 Prompt、源码、API key、数据库 URL。
- `trace_id` 写入 Run，前端仅展示安全的诊断 ID。

## 7. 自动测试

新增建议：

```text
tests/test_agent_run_api.py
tests/test_run_events.py
tests/test_run_idempotency.py
tests/test_run_cancellation.py
tests/test_durable_graph.py
tests/integration/test_worker_recovery.py
tests/integration/test_event_replay.py
tests/integration/test_index_job.py
```

必须覆盖：

- 相同 Idempotency-Key 并发请求只创建一个 Run。
- 相同 Idempotency-Key 但请求 hash 不同返回 `IDEMPOTENCY_MISMATCH`。
- 未传 conversation_id 时只创建一个同项目 Conversation/turn；全部 RunEvent 的完整 `ChatEventBase + run_id` 与行 sequence/SSE id 一致。
- 重复 Celery 投递不重复消息、记忆和 ToolCall；Message partial unique constraint、内容/hash 冲突分支及记忆 durable effect 唯一键均被真实数据库并发测试命中。
- provider 原始 `tool_call_id` 可为任意非空字符串并能原样回传；`tool_call_provider_refs` 与内部 UUID `logical_tool_call_id` 的映射在恢复/新 model round 后仍正确，历史映射不可变，二者不能被当作唯一键互换。
- Worker 在工具完成后被终止，重启后复用结果。
- checkpoint 写入成功但领域事务失败时能安全重入。
- 领域事务成功但 checkpoint 写入失败时按同一 `logical_tool_call_id` 复用结果；同 Step 两次相同参数的真实调用不会被误合并。
- 同一 `logical_tool_call_id` 的 tool name、version 或 canonical arguments hash 变化时返回 `IDEMPOTENCY_MISMATCH`，旧结果和调用记录保持不变。
- `Last-Event-ID` 从任意 sequence 回放连续且无重复。
- 事件 commit 后、Redis publish 前崩溃时由 outbox 补投。
- PG 回放与 Redis 订阅切换窗口内产生事件时仍无缺口；Redis 通知丢失且之后没有新事件时仍由 heartbeat 从 PG 补齐。
- 取消与工具完成竞争时只有一个合法终态。
- 终态不可自动恢复；不可重试错误被拒绝。
- Worker 不复用请求级 session。
- 已存在资源与当前本地 project context 不一致时返回 `PROJECT_SCOPE_MISMATCH`；不存在时返回 `PROJECT_NOT_FOUND`，不得用本地隔离语义宣称完成远程授权。

验收命令：

```bash
(cd codeaware-py && uv run python scripts/run_tests_safe.py -q)
(cd codeaware-py && uv run python scripts/run_tests_safe.py -m integration tests/integration/test_worker_recovery.py tests/integration/test_event_replay.py -q)
```

```bash
(cd codeaware-py/frontend && npm run lint)
(cd codeaware-py/frontend && npm run build)
(cd codeaware-py/frontend && npm run test)
```

所有后端测试、迁移 roundtrip、Worker/Redis 故障注入和演示只能使用 `run_tests_safe.py` 创建并校验的本次一次性 PG/Redis/queue namespace；不得裸跑 pytest/Alembic 或指向开发、共享、生产数据库。

## 8. 可复制演示

实现者应提供 `codeaware-py/scripts/demo_s6_durable_run.sh`，内部完成以下步骤并在证据中保存输出：

下列 failpoint 只允许由 integration/test 配置启用，默认关闭且不能暴露为生产 HTTP 参数；evidence 必须记录启用点和一次性触发次数。

1. 启动 PostgreSQL、Redis、Phoenix、API 和 Worker。
2. 为已完成 S5 索引的 project 创建只读 Agent Run。
3. 订阅事件并记录最后 sequence。
4. 对 fixture Tool 开启一次性 failpoint：领域 ToolCall 成功提交后、checkpoint 写入前终止 Worker；记录 fixture provider 的 logical-call 计数。
5. 执行 `docker compose up -d worker`，证明恢复后复用同一 `logical_tool_call_id`。
6. 再开启一次性 failpoint：终态 RunEvent/outbox 提交后、Redis publish 前终止 dispatcher，然后重启 dispatcher。
7. 用保存的 sequence 作为 `Last-Event-ID` 重连，并在“已订阅、PG high-water 尚未读取”屏障处并发写入一个事件。
8. 等到 `run.completed`。
9. SQL 核验每个 logical ToolCall 只有一条成功结果、fixture provider 计数为 1、outbox 最终发布且 event sequence 连续。

演示输出必须同时展示：

- Worker 重启前后的同一 `run_id`；
- checkpoint 恢复位置；
- 回放事件与新事件无缺口；
- 相同 `logical_tool_call_id` 的 ToolCall 未重复执行，且不是仅靠数据库覆盖掩盖重复 provider 调用；
- outbox commit/publish 故障后，终态事件仍能在没有后续 Redis 通知时被补拉；
- 最终回答仍有 S5 的代码引用。

普通 Chat 也必须再演示一次，证明兼容路径未被 durable runtime 破坏。

## 9. Definition of Done

- [ ] Run/Step/ToolCall/Event/outbox 领域表、checkpoint 和迁移可从空库创建。
- [ ] 创建、查询、事件、取消、重试 API 与 OpenAPI 一致。
- [ ] 每个 Run 都有非空 conversation_id/turn_id；所有 RunEvent 继承完整 `ChatEventBase` 并额外带 run_id。
- [ ] Worker 重启后从 checkpoint 恢复；稳定 logical call、Run/Tool fingerprint mismatch 和双向事务/checkpoint 故障均通过。
- [ ] PG 是 Run/Event 真相源；停 Redis 后历史仍可查询。
- [ ] SSE 采用无缝订阅/回放切换，并通过 outbox 与 PG heartbeat 在 Redis 丢失时无缺口回放。
- [ ] 索引 Job 已离开 Web 请求生命周期。
- [ ] Trace 可在本地 Phoenix 按 `run_id` 查到，敏感内容已脱敏。
- [ ] Chat 兼容回归、后端、前端和故障测试全部通过。
- [ ] 本阶段实现与验收位于记录 base commit 的临时实施 Git worktree；用户主工作树未被切换、覆盖或清理。
- [ ] `run_tests_safe.py` 为本阶段创建、校验并精确清理一次性 PG/Redis/queue stack；manifest 引用 stack identity 和 cleanup report，未连接开发/共享/生产数据。
- [ ] 已生成 `evidence/S6/report.md`、`evidence/S6/manifest.json` 及其哈希引用产物。
- [ ] `(cd codeaware-py && uv run python scripts/validate_stage_evidence.py S6)` 通过；Markdown 勾选或未被 manifest 引用的文件不解锁 S7。
- [ ] 没有 patch、审批或仓库写入能力。

## 10. 回退与交接

应用回退：

- 关闭 durable Agent 入口和 Worker，只保留现有 Chat API。
- 未完成 Run 标记为 `CANCELLED` 或保留待后续恢复，不删除审计记录。
- 生产/共享库不做自动 downgrade；迁移往返只在 `run_tests_safe.py` 校验的一次性数据库执行。
- 代码回退先关闭 feature flag，再从临时实施 worktree 保留 evidence/patch 后移除该精确 worktree；不得 reset、checkout 或清理用户主工作树。
- 一次性 PG/Redis/queue 只按 safe runner 生成并校验的 stack identity 精确销毁，禁止按名称前缀或共享 volume 批量清理。

交给 S7 的稳定接口：

- `RunService`、状态机和幂等键；
- durable graph/checkpoint；
- `ToolCall` 和 Risk 定义；
- typed/replayable events；
- Worker、Artifact 引用位和 trace。
