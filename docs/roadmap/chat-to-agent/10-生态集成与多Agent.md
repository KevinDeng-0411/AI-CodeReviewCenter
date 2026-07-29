# S9：生态集成与多 Agent（条件型扩展）

> **状态：Future / Locked（可选方向，当前版本禁止实施）。**
>
> 只有 current-release C3 evidence、S1–S8 evidence 全部通过、评测达到本文门槛，并且用户对所选 S9 子卡另行明确授权，才能开工。不能用一次笼统授权同时启用 Git、MCP、远程身份和多 Agent。
>
> 本文件不是必须整包实施的下一阶段，而是 S8 稳定后的四张独立扩展卡。每次只选择一张，先写 ADR 和评测门槛，再形成自己的测试、演示、回滚和 evidence。
>
> **实施入口 / 本阶段闭环：** 仅在 local-only S8 evidence、业务触发条件、所选子卡 ADR/指标和该子卡单独授权均通过后，选择 A/B/C/D 之一，完成 `最小扩展 → 越权/故障/幂等或统计验证 → 真实隔离演示 → feature flag 回退 → evidence`；完成一张不代表其他子卡获授权。
>
> **契约来源：** Run、State、Tool、Event、Artifact、Approval、Risk 和错误的公共语义以[公共契约](00-执行约定与公共契约.md)为准；本文只定义 S9 各独立生态/身份/多 Agent 增量。协议 adapter、provider 或 child-run 不得旁路公共契约。

## 1. 进入条件

只有满足以下条件，才可启动任一扩展：

- S8 的 `evidence/S8/manifest.json` 存在，且 `(cd codeaware-py && uv run python scripts/validate_stage_evidence.py S8)` 通过；清单明确其 R2 仅为 local-only。任何远程/multi-user 部署继续硬关闭 R2/R3，直到 S9-C 完成。
- 至少有一组覆盖真实目标场景的离线任务集和 S8 单 Agent 基线。
- 未授权本地/远程写入拦截率为 100%。
- Tool、Run 恢复、approval mismatch/stale-base 回归集全部通过。
- 已观察到具体业务需求，而不是为了展示框架或协议。

每张扩展卡新增一个 ADR，必须记录：

- 用户问题与为什么现有 S8 不能满足；
- 替代方案；
- 权限/威胁模型；
- 成功、成本、P95 时延和回退门槛；
- 固定的协议、provider、toolset 和 prompt 版本。

没有 ADR 和基线指标，不得编码。

## 2. 共同边界

- FastAPI、React/Vite、PostgreSQL/pgvector 不因本阶段自动替换。
- 所有外部 Tool 仍映射到公共 ToolDefinition、Risk、scope、timeout、幂等和审计。
- 所有外部写操作都是 `R3_EXTERNAL_WRITE`，逐次审批。
- R3 复用 S8 的 JCS ActionManifest、双期限、ActionExecution lease/outbox/reconciliation；外部系统不支持原子事务时必须记录 `UNKNOWN` 并查询真实远端状态，不能盲重试。
- 远程身份、tenant/project membership 和最小权限短期凭证必须端到端传递。
- MCP/A2A 的能力声明和风险 hint 只能作为元数据，不能代替本地策略。
- 任何扩展都可通过 feature flag/allowlist 独立关闭，关闭后退回 S8。

## 3. S9-A：GitHub/GitLab 草稿 PR 集成

### 触发条件

用户确实需要把 S8 的本地 commit 交付到远程代码托管，而手动 push/PR 已成为可度量瓶颈。

若 CodeAware 服务本身是远程或多用户部署，必须先完成 S9-C；local-only 服务可使用绑定当前本地 actor、正确 audience/scope 的短期 provider OAuth 凭证，但这不放宽 S8 的远程 R2 门禁。

### 最小交付

```text
S8 本地 commit
  → 生成新的 R3 Approval
  → 用户批准精确 remote/repo/branch/commit/title/body
  → 使用短期凭证 push 新 branch
  → 创建 draft PR
  → 保存 remote URL/ID 和审计
```

新增 provider port，例如：

```text
app/ai/integrations/git_provider.py
app/ai/integrations/github.py
app/ai/integrations/gitlab.py
```

首个实现只选当前真实使用的一个 provider，不同时做两个。写工具拆分为 `push_branch` 和 `create_draft_pull_request` 两个独立 R3 动作；是否需要两次审批由 ADR 明确，至少 ActionManifest 必须分别覆盖两次动作的精确参数、source/target ref、expected OID、PR base/head、title/body hash、凭证 audience/scope 和预期影响。两步之间的部分成功通过各自 ActionExecution reconciliation 呈现，不能把“push 成功、PR 失败”伪装成全失败后盲重做。

要求：

- OAuth App/GitHub App 或等价短期 installation token；不保存用户长期 PAT。
- 校验 token audience、scope、组织/repo allowlist。
- remote URL 来自服务端配置，不能由模型传任意 URL。
- 只 push `agent/<run>` 新分支，禁止 force push、默认分支和受保护分支。
- 只创建 draft PR；禁止自动 merge、approve 或修改 branch protection。
- API 超时/重试使用 provider 幂等键；若 provider 不支持，则以稳定 remote ref/marker 查询并采纳已创建资源。无法确认时标为 `UNKNOWN`，等待人工或 reconciliation，避免重复 PR。

### 测试与演示

- 用 provider fake 跑普通 CI；真实 sandbox organization 标 `integration`。
- 覆盖 token/scope 错误、重复投递、目标仓库不匹配、branch 已存在、provider timeout。
- 演示：批准 → 新远程 branch → 一个 draft PR；拒绝 → 无远程变化。
- 回退：禁用 provider 和 R3 scope；远程 branch/PR 的关闭或删除由用户明确决定，不自动清理。

## 4. S9-B：受控 MCP Client

### 触发条件

需要接入多个独立工具服务，内部 Tool Registry 的原生 adapter 维护成本已经有明确证据。

### 角色决定

首期 CodeAware 是 **MCP client**，不是把全部能力立刻发布为 server：

```text
MCP server
  → discovery
  → 本地 allowlist/schema 校验
  → 映射为内部 ToolDefinition
  → 本地 scope/risk/approval policy
  → ToolCall 审计
```

MCP 不能绕过 S4–S8 已建立的工具治理。实现：

- **实施当天重新核对官方 Versioning、最终规范 tag/changelog、SDK release 和 conformance 状态。** 只固定标记为 Current/GA 且所选 SDK 已稳定支持的协议版本；RC/draft、预发布 SDK 或博客预计日期不能作为生产版本依据。
- 在 lockfile/ADR/evidence 同时固定 protocol version、SDK package/version、conformance suite commit/result。若使用 Tasks/MCP Apps 等 extension，分别固定 extension ID/version；不能把扩展版本等同 core 版本。
- 版本协商和 legacy/current transport 差异只留在 adapter；不要把候选草案字段写死到领域模型。未共同支持固定版本时 fail closed，不静默降到未评审版本。
- 仅连接管理员登记的稳定 `connector_id + server identity + transport + origin`；server 自报 name 不能充当唯一身份。
- 工具按需发现和加载，不能把所有 schema 每轮塞入模型上下文。
- MCP Tool 不保证提供独立 version，且 name 只在单 server 内唯一。内部 ToolDefinition.version 必须由 `connector_id + protocol_version + canonical tool schema hash` 生成；以 connector namespace 解决重名，并对 name/input/output schema/annotations 做本地快照和变更检测。
- output schema 缺失时把结果规范化为受限 opaque envelope/Artifact，不伪造强类型输出。JSON Schema 校验必须拒绝自动解析外部 `$ref`，限制 schema 大小、深度、正则/编译时间和验证资源。
- 未知/变化的工具默认禁用。
- `readOnlyHint/destructiveHint` 不可信；Risk 由本地策略决定。
- OAuth 使用正确 audience/scope，禁止 token passthrough。
- HTTP transport 防 SSRF、DNS rebinding、redirect、私网/metadata IP 和任意 egress；本地 stdio server 使用明确 executable/argv/environment allowlist。
- MCP 返回内容视为不可信数据，不能成为 system 指令。

首个闭环只接一个 R0 测试 server 和一个工具。测试协议不兼容、schema/connector identity 变化、跨 server 重名、外部 `$ref`/schema bomb、恶意提示内容、超时、大输出、断线、越权和 server 替换。演示必须输出实际固定的 protocol/SDK/conformance/schema hash，并证明禁用 MCP 后同一系统仍可使用内部工具完成基础任务。

### 后续只读 MCP Server

只有出现“IDE/其他 Agent 需要消费 CodeAware 检索”的真实需求时，另立 ADR 输出 server。首批仅暴露：

- `search_code`
- `read_code`
- `find_symbol`
- `search_knowledge`

每次请求必须解析真实身份和 project/repository scope。S9 首版 server 不暴露 patch、shell、approval 或 Git 写工具。

## 5. S9-C：远程部署身份与多租户治理

### 触发条件

服务不再是单机 local-only，或需要两名以上用户/组织共同使用。

S8 的完成只证明 local-only R2，不授权远程写。S9-C 实施和验收期间，所有远程 R2/R3 feature flag 与 scope 必须保持关闭；只有本卡 DoD/evidence 完成后，才能另行授权某个远程写卡并重新跑其审批与越权测试。

### 最小交付

- OIDC/JWT 验签、issuer/audience/expiry 校验；
- `users / organizations / memberships / roles`，以及 project/repository membership；
- scopes 从后端 RBAC 计算，不相信请求自报；
- tenant/project 过滤在 SQL、vector、cache key、Artifact、Run、Tool 和 trace 全链路生效；
- 服务到 Git/MCP/runner 使用最小权限短期凭证；
- 配额覆盖并发 Run、模型 token/成本、工具次数、索引量和 Artifact 保留期；
- 管理员 kill switch、审计导出和数据删除。

必须以两个 tenant 的同名 project/repo/文档/用户 fixture 做隔离测试，并包含向量召回、SSE 回放、Artifact 下载、Approval 和 R3 Tool。任何跨租户命中都阻断上线。

该扩展是远程 R2/R3 的前置，不是可以晚补的 UI 登录页。S9-C 完成本身只建立身份治理，不自动打开任何写能力；启用 S9-A 或远程 R2 仍需单独授权和 evidence。

## 6. S9-D：评测驱动的多 Agent

### 触发条件

只有 S8 单 Agent 的 trace/eval 证明至少一种问题持续存在：

- 工具过多导致选择准确率显著下降；
- 不同任务需要严格隔离的上下文或权限；
- 可独立子任务的并行执行能明显降低总时延；
- 专业审查任务由独立 specialist 明显提高最终环境结果。

“角色听起来合理”不是证据。

### 基线实验

实验前在 ADR 预注册任务来源、主要指标、样本量/功效分析、随机种子、重复次数、统计方法和采用门槛。至少准备 50 个有代表性的配对任务；若功效分析需要更多样本，以更大值为准。数据分为：

- development set：允许调 prompt/router；
- held-out set：冻结后只用于最终决策，不得按结果继续调参；
- zero-tolerance safety set：未授权写入、跨 tenant/scope、审批绕过、预算逃逸和 prompt injection 等对抗轨迹；任一漏拦截即失败，不能用“估计 100%”替代确定性策略测试。

单 Agent 与候选多 Agent 使用完全相同的任务、模型、工具/index 版本和环境快照，按任务配对、随机顺序并重复运行：

| 指标 | 单 Agent 基线 | 候选多 Agent |
|---|---:|---:|
| 最终环境任务成功率 | 必填 | 必填 |
| Citation/patch 正确率 | 必填 | 必填 |
| 安全策略通过/阻断 | 必填 | 必填 |
| P50/P95 时延 | 必填 | 必填 |
| 每成功任务 token/成本 | 必填 | 必填 |
| 重复工具调用和失败恢复 | 必填 | 必填 |

报告每任务配对差值、均值/方差、95% 置信区间和失败轨迹；离散成功率使用配对 bootstrap、置换检验或 ADR 预注册的等价方法。建议最低要求：主要成功指标提升的置信区间下界达到预注册门槛（不能仅看点估计），Citation/patch 正确率无劣于预注册界限，成本和 P95 不超过基线 1.5 倍。若目标是并行降时延，则成功率/Citation/patch 必须满足非劣，时延改善的置信区间达到预注册门槛。Safety set 必须零违规。

### 首选模式

使用 manager-as-tools/supervisor：

```text
Manager
  ├─ Repo Researcher（R0，窄代码上下文）
  ├─ Test Planner（R0，结构化测试计划）
  └─ Reviewer（只读 patch/test artifacts）
```

- specialist 是版本化工具，只接收窄、结构化输入并返回 schema 化结果/Artifact ID。
- Manager 持有最终回答；specialist 不共享整段 Conversation。
- 全局预算由 Run 统一分配，创建 child 前在 PG 原子预留，完成/取消后结算；子 Agent 不能各自获得无限轮数或超卖同一预算。
- 共享 cancellation、trace、Tool/Approval/Risk 和 Artifact 契约。
- 首版不使用自由 group chat、swarm 或无限 handoff。
- 写动作仍只有一个审批后的 S8/S9-A action path，specialist 无写权限。

### Durable child-run 契约

specialist 可实现为受限 child AgentRun 或内部 AgentCall，但必须持久化：

```text
parent_run_id
logical_child_call_id
specialist_name/version
input_hash + toolset/prompt/index version
reserved_budget + usage
attempt + status + checkpoint/thread id
result/artifact ids + error
created/started/finished timestamps
```

- `(parent_run_id, logical_child_call_id)` 唯一；ID 在 dispatch 前持久化，Manager/Worker 重投递和 attempt 递增都复用它。
- 已完成 child 返回已保存结果；同输入 hash 不会重复调用 specialist，同 key 不同 input hash 返回 mismatch。
- parent cancel 传播到所有非终态 child；child 终态不反向覆盖已取消 parent。Manager 恢复时从 PG 枚举 child，不从内存猜测完成情况。
- parent/child 各自事件有单调 sequence，并通过 `parent_run_id/logical_child_call_id` 关联；跨 stream UI 合并不改变各自真相顺序。
- 并行 fan-out 使用有界并发；聚合节点按 logical child ID 去重，只有全部 required child 达合法终态或降级策略明确时才继续。
- specialist 永久限制为 R0；它不能产生 Approval、R2/R3 Tool 或把未验证自然语言变成写参数。

### 验收、演示与回退

- 按预注册方案运行 held-out 配对评测，保存原始逐任务结果、统计脚本、置信区间和失败轨迹。
- 自动测试覆盖重复 dispatch、同 key 不同 input、预算竞争、parent/child 取消竞争、聚合去重和事件回放。
- 可复制演示在 child 已完成/parent checkpoint 前终止 Manager，再在 specialist 执行中终止 child Worker；恢复后证明 logical child 未重复、预算未超发、事件无缺口且最终 Artifact/环境结果一致。
- 演示同时运行同一任务的 single-agent baseline，展示触发问题及预注册主要指标，而不是只展示角色对话。
- Safety set 任一违规、主要指标/非劣门槛未通过或 durable failpoint 未闭环，均不得上线。
- 关闭 multi-agent flag 后退回同一 S8 single-agent runtime。
- 未达到预先门槛就删除/冻结实验路径，不以“已有代码”为理由上线。

## 7. A2A 的边界

只有 Agent 位于不同服务、团队或组织，且需要远程发现、长任务状态和跨边界身份时才考虑 A2A。项目进程内的 manager/specialist 继续使用普通 typed call/graph node。

A2A 与 MCP 分工：

```text
Agent ↔ Tool：MCP
远程 Agent ↔ 远程 Agent：A2A
进程内模块：函数 / port / graph
```

采用前必须单独 ADR、固定协议版本、定义 Agent Card 信任、身份、任务幂等、事件恢复和数据边界。

## 8. 每张扩展卡的闭环模板

每次只实施 S9-A/B/C/D 中的一张：

1. 新增 `docs/decisions/adr/NNNN-*.md`。
2. 记录 S8 基线和该扩展的进入指标。
3. 实现最小 provider/protocol/pattern，不顺带实现其他卡。
4. 普通测试使用 fake；真实外部系统用隔离 integration 环境。
5. 完成一条成功、一条拒绝/失败、一条回退演示；写操作或 durable child 还必须注入外部成功/PG 未完成的崩溃窗口并完成 reconciliation。
6. 验证关闭 feature flag 后 S8 全部测试仍通过。
7. 按所选子卡生成独立机器入口 `evidence/S9-<card>/manifest.json`、`report.md` 和哈希引用产物，例如 `evidence/S9-B/manifest.json`；manifest 的 `stage`/`selected_card` 必须同时为 `S9-B`/`B`。各子卡互不覆盖，未选择 card 保持未开始。

通用命令：

```bash
(cd codeaware-py && uv run python scripts/run_tests_safe.py -q)
(cd codeaware-py && uv run python scripts/run_tests_safe.py -m integration <本扩展的隔离集成测试> -q)
```

```bash
(cd codeaware-py/frontend && npm run lint)
(cd codeaware-py/frontend && npm run build)
(cd codeaware-py/frontend && npm run test)
(cd codeaware-py/frontend && npm run test:e2e)
```

所有后端测试、provider/child-run 故障注入和真实隔离演示必须经 `run_tests_safe.py` 的 target guard，使用本次一次性 PG/Redis/queue namespace；不得裸跑 pytest 或复用开发/共享数据库。

## 9. Definition of Done

对被选中的扩展卡：

- [ ] 有经批准的 ADR、威胁模型、进入/退出指标。
- [ ] 公共 Run/Tool/Event/Artifact/Approval 契约未被旁路。
- [ ] 成功、越权、失败、重试、幂等和回退测试通过。
- [ ] 真实隔离环境演示可重复。
- [ ] feature flag 关闭后完整退回 S8。
- [ ] 指标达到 ADR 预设门槛。
- [ ] 本子卡实现与验收位于记录 base commit 的临时实施 Git worktree；用户主工作树和未选择子卡未改变。
- [ ] `run_tests_safe.py` 创建、校验并精确清理一次性 PG/Redis/queue/provider-fake stack；manifest 引用 stack identity 和 cleanup report。
- [ ] S9-A（若选择）复用 ActionManifest/ActionExecution，并闭环 provider timeout/UNKNOWN/部分成功。
- [ ] S9-B（若选择）记录实施当日复核的 Current/GA protocol、稳定 SDK、conformance 和 synthetic tool version；RC/draft 未进入生产。
- [ ] S9-C（若选择）证明身份治理完成前远程 R2/R3 始终关闭，完成本卡也不自动打开写能力。
- [ ] S9-D（若选择）预注册 paired held-out 统计门槛、zero-tolerance safety set 和 durable child-run failpoint 全部通过。
- [ ] 已生成 `evidence/S9-<card>/report.md`、`evidence/S9-<card>/manifest.json` 及其哈希引用产物；先前已完成子卡的 manifest 未被覆盖。
- [ ] `(cd codeaware-py && uv run python scripts/validate_stage_evidence.py S9-<card>)` 通过；Markdown 勾选或未被 manifest 引用的文件不构成完成。

未被选择的扩展仍保持“未开始”，不得因完成其中一张卡宣称已完成全部生态平台或多 Agent。

## 10. 回退与清理

- 先关闭所选 card 的 feature flag/allowlist/scope，验证完整退回同一 S8 local-only runtime；S9-C 回退后远程 R2/R3 立即恢复为硬关闭。
- 远端 branch/PR、外部资源和审计记录不自动删除；任何清理由用户对精确资源另行授权。
- 生产/共享库不自动 downgrade；迁移往返只在 `run_tests_safe.py` 校验的一次性数据库执行。
- 从临时实施 worktree 保留 evidence/patch 后移除该精确 worktree；一次性 PG/Redis/queue/provider-fake stack 仅按 safe runner 验证的 identity 清理，不 reset 用户主工作树、不按前缀删除资源。
