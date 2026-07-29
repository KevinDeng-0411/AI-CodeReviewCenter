# S8：审批式行动 Agent

> **状态：Future / Locked（未来候选，当前版本禁止实施）。**
>
> 只有 current-release C3 evidence、S1–S7 evidence 全部通过，并且用户在这些阶段完成后对 S8 另行明确授权，才能开工。C3 或前置阶段完成均不自动授权本阶段。
>
> 本阶段首次引入 `R2_LOCAL_WRITE`：用户明确批准后，以隔离物化和 Git plumbing 创建本地分支和 commit。S8 只允许 local-only 闭环；远程或多用户环境必须硬关闭 R2，直到 S9-C 身份/多租户 evidence 完成。永不自动 push、建 PR 或 merge。
>
> **实施入口 / 本阶段闭环：** 仅在 S7 安全验证 evidence 与本阶段单独授权通过后，执行 `不可变 ActionManifest → WAITING_APPROVAL → 本地用户决定 → ActionExecution lease → Git ref CAS → reconciliation/审计`；拒绝、过期、取消、篡改和远程模式均不得产生写入。
>
> **契约来源：** Run、State、Tool、Event、Artifact、Approval、Risk 和错误的公共语义以[公共契约](00-执行约定与公共契约.md)为准；本文只定义 S8 的 JCS manifest、双期限、本地 R2 和 Git action saga 增量。

## 1. 阶段结果

完成后，S7 已验证的 patch 会形成精确审批请求：

```text
已验证 PatchArtifact
  → Run 暂停 WAITING_APPROVAL
  → 用户查看不可变 ActionManifest、diff、验证证据和双期限
  → 批准：恢复原 Step，以 CAS 创建 agent/<run> 分支和本地 commit
  → 拒绝：Run 终止，不产生 Git 写入
```

批准不是“让 Agent 继续自由决定”，而是授权一次已经冻结的动作。

## 2. 开工门槛

- S7 的 `evidence/S7/manifest.json` 存在，且 `(cd codeaware-py && uv run python scripts/validate_stage_evidence.py S7)` 通过，清单证明原工作区不变、sandbox 约束和 Artifact hash 有效。
- S6 的 WAITING 状态恢复、事件回放和幂等机制可复用。
- Repository 有稳定 root、base commit 和本地写权限配置。
- local 模式有稳定 actor；本阶段 evidence 只能证明 local-only R2。任何远程/多人部署必须保持 R2 disabled，并在 S9-C 完成真实认证授权后重新做远程启用验收。

## 3. 范围

### 必须完成

- `approval_requests` 和 `approval_decisions`。
- JCS 规范化的不可变 `ActionManifest`，精确绑定动作、验证证据和双期限。
- `action_executions` 执行租约、状态机、Git CAS 与崩溃 reconciliation。
- `WAITING_APPROVAL` checkpoint 暂停与精确恢复。
- 审批查询、批准、拒绝 API。
- 前端审批卡：diff、验证、影响、目标 repo、base commit、过期时间。
- 复用 S7 安全 materializer，在不执行仓库 hook/filter 的前提下创建唯一 `agent/<run-id>` 分支和 commit。
- 参数/hash/base commit/actor/过期/幂等的再次校验。
- 批准、拒绝、过期、篡改、双击和 stale base 的闭环。

### 明确不做

- 不修改用户活动工作树或切换其当前 branch。
- 不 push、不创建远程 PR、不评论、不 merge。
- 不允许永久“全部批准”。
- 不允许批准后重新规划、更换 patch、命令、仓库或 base commit。
- 不以仅有一个 UI 用户为由跳过后端授权。
- 不把 MCP annotation 或模型自报的风险级别当授权依据。

## 4. 数据模型

新增下一序号 Alembic revision。

### `approval_requests`

| 字段 | 说明 |
|---|---|
| `id` | UUID PK |
| `run_id`、`step_id` | FK，非空 |
| `project_id`、`requested_by`、`approver_policy` | 授权主体、允许决策者和策略版本 |
| `manifest_version` | ActionManifest schema 版本 |
| `manifest_jcs`、`manifest_hash` | RFC 8785/JCS UTF-8 bytes 及 SHA-256；JSONB 仅供查询 |
| `summary`、`impact` | 给人看的说明，不替代精确字段 |
| `status` | `PENDING / APPROVED / REJECTED / EXPIRED / CONSUMED` |
| `decision_expires_at` | 尚未决策时的审批期限 |
| `execution_deadline` | 批准后的最晚动作截止时间；不能由 Worker 放宽 |
| `created_at`、`consumed_at` | 时间 |

一个 `(run_id, step_id)` 只能有一个有效 PENDING 请求。

`ActionManifest` 至少精确包含：

```json
{
  "manifest_version": "git-commit/v1",
  "tool": {"name": "git_commit", "version": "..."},
  "scope": {
    "project_id": "...",
    "repository_id": "...",
    "requested_by": "local-single-user",
    "approver_policy_version": "...",
    "required_scopes": ["repository:write"]
  },
  "git": {
    "source_ref": "refs/heads/main",
    "expected_base_commit": "<40-char-sha>",
    "target_ref": "refs/heads/agent/<run-id>",
    "commit_message": "...",
    "author_name": "...",
    "author_email": "...",
    "commit_timestamp": "..."
  },
  "patch": {"artifact_id": "...", "content_hash": "..."},
  "validation": {
    "report_artifact_id": "...",
    "report_hash": "...",
    "image_digest": "sha256:...",
    "profile_id": "...",
    "profile_version": "...",
    "argv_hash": "...",
    "harness_hash": "..."
  },
  "decision_expires_at": "...",
  "execution_deadline": "..."
}
```

敏感值只保存 secret handle，不写明文。UI 的 diff、命令、目标 ref、验证结果和期限必须全部从 manifest 及其不可变 Artifact 派生，不能从可变 summary 拼装。

### `approval_decisions`

append-only，保存 approval、decision、decided_by、decided_at、可选 reason、`manifest_hash`、客户端/审计信息。一个 approval 最多一个终局 decision；不得通过更新旧 decision 改写历史。

### `action_executions`

保存 `id`、唯一 `approval_id`、`manifest_hash`、`state`、attempt、lease owner/expiry、期望/实际 ref、prepared commit/tree SHA、错误与时间。状态机：

```text
PREPARED → EXECUTING | EXPIRED
EXECUTING → SUCCEEDED | FAILED | UNKNOWN | EXPIRED
UNKNOWN → EXECUTING | SUCCEEDED | FAILED | EXPIRED（仅 reconciliation）
```

Worker 必须先以条件更新取得 lease，再接触 Git。lease 过期只允许新的 Worker 进入 reconciliation；不能假设前一个执行者尚未产生副作用。任何到 `EXPIRED` 的迁移都必须发生在 execution deadline 之后，且由 reconciliation 精确确认 target ref 未创建；仅凭超时或 lease 过期不能进入 `EXPIRED`。

Hash 规则必须集中在一个函数：

```text
RFC 8785 JSON Canonicalization Scheme
  → 持久化完全相同的 UTF-8 bytes
  → SHA-256
```

测试需提供跨语言/跨进程固定向量，不能依赖 Python `repr()` 或从 JSONB 任意重序列化后再猜测原 hash。

## 5. 目标模块

```text
app/models/approval.py
app/models/action_execution.py
app/schemas/approval.py
app/schemas/action_manifest.py
app/repositories/approvals.py
app/repositories/action_executions.py
app/ai/approvals/service.py
app/ai/approvals/policy.py
app/ai/actions/git_commit.py
app/ai/actions/reconcile.py
app/api/v1/approvals.py
frontend/src/api/approvals.ts
frontend/src/features/approvals/
```

`app/api/v1/` 是现有 Python 包目录名，不代表公开 URL 版本前缀；本阶段所有公开路由统一挂在 `/api`。

`GitCommitAction` 作为版本化 Tool 注册：

```text
risk = R2_LOCAL_WRITE
idempotent = true（以 approval_id + manifest_hash 为逻辑键，并通过执行记录和 Git ref CAS 调和）
required_scopes = ["repository:write"]
```

它只能接收服务端保存的 approval/action-execution ID，不接收任意宿主路径、任意 patch 文本或 shell 命令。“idempotent”表示可检测并采纳已完成结果，不表示 Git 与 PostgreSQL 是一个原子事务。

## 6. 实施顺序

### 6.1 Actor 与授权

- local-only 模式使用公共 sentinel `local-single-user`，只监听受信本地边界，并在 UI/evidence 明示。
- 一旦服务监听非本地受信环境或存在多用户，R2 必须硬关闭；仅“已有登录页”不构成启用条件，必须等 S9-C 的 JWT/OIDC、tenant/project membership、RBAC scope、审计和跨租户测试全部完成。
- S8 不声称存在远程认证上下文。服务端从可信 local execution context 注入固定 `actor_id="local-single-user"`；body/header/cookie 自报的 actor 一律忽略并拒绝冲突值。
- 只有 S9-C 完成后，远程 actor 才能从已验签 claims 与服务端 membership/RBAC 计算；该远程路径不属于 S8 evidence。
- 创建审批和做决定的 actor 均以服务端解析值写入审计。

### 6.2 创建审批并暂停

S7 patch 验证通过后：

1. 选择固定 `GitCommitAction` 版本、source/target ref、commit metadata 和 approver policy。
2. 从服务端读取 Patch/TestReport 原始 bytes 并复算 hash，锁定 image/profile/argv/harness 证据。
3. 写出 JCS `ActionManifest` bytes/hash；设置 `decision_expires_at` 和更晚但有界的 `execution_deadline`。
4. 在一个事务内创建 Approval、把 Run 改为 `WAITING_APPROVAL`、写 `approval.required` 和 S6 outbox。
5. LangGraph 使用 durable interrupt/checkpoint 停在当前写 Step。
6. Worker 释放资源；等待不能占用进程或数据库连接。

审批 payload 可展示摘要，但完整参数由后端按 approval ID 查询。

### 6.3 审批 API

```http
GET  /api/approvals/{approval_id}
POST /api/approvals/{approval_id}/approve
POST /api/approvals/{approval_id}/reject
```

approve/reject 必须使用幂等请求键，并保存请求 hash，防止同 key 不同 decision。approve 在锁内再次验证：

1. 当前 actor 具备目标 project/repository 的 `repository:write`。
2. actor 符合 manifest 固定的 approver policy；Approval 仍 PENDING、`decision_expires_at` 未到且未消费。
3. Run 仍 `WAITING_APPROVAL`，step/checkpoint 相同。
4. 保存的 JCS bytes 复算后与 `manifest_hash` 相同；tool/version、scope、source/target ref 和 commit metadata 未变化。
5. Patch/TestReport 原始内容 hash、sandbox image、profile/argv/harness 均与 manifest 相同，权威验证成功。
6. repository 的 `source_ref` 当前仍等于 `expected_base_commit`，`target_ref` 不存在或已是本 approval 的目标 commit。
7. `execution_deadline` 尚未到；批准不能自动延长执行期限。

任一不符返回公共错误码；`STALE_BASE_COMMIT` 必须重新生成/验证/审批，不能静默 rebase。

批准事务在同一行锁/条件更新内写 Decision、Approval 状态、`PREPARED` ActionExecution，把 Run 从 `WAITING_APPROVAL` 转为 `RUNNING`，并写公共 `run.status` 事件和 S6 outbox 恢复信号。批准决定本身通过 append-only Decision 与审批 API 响应读取，不另造未冻结的事件名。这样状态迁移严格遵循公共状态机；若 Run 已不是 `WAITING_APPROVAL`，整笔事务失败。实际 Git 动作仍由 Worker 执行，且恢复原 Step，不再次调用模型生成参数。若事务成功但 Worker 信号丢失，由 outbox/reconciliation 恢复。

### 6.4 执行精确 Git 动作

Worker 消费已批准 Approval：

1. 以条件更新领取 ActionExecution lease；如果记录为 `UNKNOWN` 或 lease 过期，先 reconciliation，不能直接重做。
2. 再次执行 manifest hash、scope、双期限、Artifact、验证证据和 source/target ref 校验。
3. 复用 S7 安全 materializer，在隔离 runner 中应用已批准 Artifact；不执行仓库 hook/filter/config 程序。
4. 运行 manifest 冻结的 image/profile/argv/harness；不能加入新命令或用候选树替换权威验证。
5. 使用无 hook 的 Git plumbing 生成 parent=`expected_base_commit` 的 tree/commit object；commit message、author 和 timestamp 来自 manifest，并包含 run/approval ID trailer。
6. 在触碰 ref 前先把 prepared commit/tree SHA 持久化到 ActionExecution。目标 ref 使用完整唯一 `refs/heads/agent/<run-id>`。
7. 先 reconciliation：若 target ref 已等于 prepared commit 且 manifest/trailer/tree 匹配，视为幂等成功；若 target 指向其他值，返回冲突。target 尚不存在时，使用 `git update-ref --stdin` ref transaction（或经测试的等价原子多-ref API）在同一事务执行 `verify <source_ref> <expected_base_commit>` 与 `create <target_ref> <prepared_commit>`。source ref 并发移动或 target 被抢占时整笔失败并返回 `STALE_BASE_COMMIT`/冲突，绝不只校验 target、绝不覆盖或 force。
8. ref CAS 后在一个 PG 事务把 ActionExecution 标为 `SUCCEEDED`、Approval 标为 `CONSUMED`、把已处于 `RUNNING` 的 Run 标为 `COMPLETED`，写 ToolResult/事件/outbox；禁止从 `WAITING_APPROVAL` 直接跳到 `COMPLETED`。
9. 若在 ref CAS 后、PG 成功前崩溃，reconciliation 读取 ref、commit trailer、tree 和 manifest，采纳已完成结果；不得创建第二 commit。若无法确定外部状态，标为 `UNKNOWN` 并停止自动重试。
10. 移除任务 snapshot/overlay；保留本地 branch 和 commit 供用户检查。

在实际执行 ref CAS 前再次检查 `execution_deadline`；截止后只能采纳截止前已经完成的匹配 ref，不能新建 ref。活动工作树及源仓库 config/hooks/index/worktree metadata 必须保持不变。

### 6.5 拒绝、过期与取消

- Reject：写 append-only Decision，Run 进入 `REJECTED`，绝不执行 action。
- Decision expire：只对 PENDING 审批按 `decision_expires_at` 原子标记 `EXPIRED`；过期批准返回 `APPROVAL_EXPIRED`。
- Execution deadline：已 APPROVED 但尚未执行的动作到期后不得新建 Git ref；reconciliation 只可采纳到期前已完成且精确匹配的结果。确认 ref 未创建后，把 ActionExecution 标为 `EXPIRED`、Run 从 `RUNNING` 标为 `FAILED` 并写稳定的 `ACTION_EXECUTION_EXPIRED` 错误/事件；不得让 Run 永久停在 `RUNNING`。
- Cancel：等待审批时允许取消，进入 `CANCELLED`。
- ActionExecution 已进入 `EXECUTING/UNKNOWN` 时，Cancel 只记录请求并触发 reconciliation；在确认 ref 未创建前不能把 Run 宣告 `CANCELLED`。若精确 ref 已成功 CAS，则必须采纳并审计已发生结果，不能删除 ref 来伪装未执行。
- 双击 approve：只允许一个 Decision 和一个 ActionExecution；重复请求返回同一决定/结果，不创建第二 commit。
- approve 与 reject 并发：数据库锁/条件更新保证仅一个胜出。
- 批准成功但 Worker 尚未领取时，Run 必须可观测为 `RUNNING`；outbox/reconciliation 恢复执行后才可进入 `COMPLETED`，不得跳过中间状态。

### 6.6 前端

审批卡至少显示：

- project/repository、base commit；
- source ref、精确 target ref、manifest hash 和允许的 approver policy；
- changed files、完整 diff 与 Artifact hash 的短显示；
- TestReport hash、sandbox image digest、validation profile/version、argv/harness hash 和结果；
- 将创建的 branch、commit 动作；
- 明确的“不会 push/merge”；
- decision expiry 与 execution deadline 两个倒计时、Approve/Reject；
- 成功后的 branch/commit SHA，拒绝/过期后的终态。

前端按钮状态不是安全边界；所有验证必须在 API 和 Worker 重做。前端展示字段必须由同一 ActionManifest 解析，不能用自由 summary 替代 manifest 内容。

## 7. 自动测试

新增建议：

```text
tests/test_approval_policy.py
tests/test_approval_api.py
tests/test_approval_hash.py
tests/test_action_manifest.py
tests/test_action_execution.py
tests/test_git_commit_action.py
tests/integration/test_approval_resume.py
tests/integration/test_approval_races.py
tests/security/test_action_scope.py
```

必须覆盖：

- 未批准时没有 branch/commit。
- actor 跨 project 或无 scope 时被拒绝。
- S8 始终由可信 local context 注入 `local-single-user`；body/header/cookie 伪造 actor 不能改变审计主体。
- JCS 跨语言固定向量一致；tool/version/scope/ref/commit metadata、Patch/TestReport、image/profile/argv/harness 或双期限任一篡改均被拒绝。
- base commit stale 返回 `STALE_BASE_COMMIT`。
- source ref 在初次校验后、ref transaction 前并发移动时，`verify source + create target` 整笔失败且 target 不存在。
- 批准恢复原 checkpoint，不重新调用模型规划写参数。
- 双 approve、approve/reject 竞争只产生一个决定。
- reject、expire、cancel 均不执行 Git action。
- Worker 在 prepared commit 前、ref CAS 前、ref CAS 后/PG 成功前分别崩溃时，reconciliation 最多采纳一个目标 commit。
- 两个 Worker 竞争 ActionExecution lease 时只有一个能执行；`UNKNOWN` 不会被盲重试。
- approve 事务原子产生 `WAITING_APPROVAL → RUNNING`，执行成功只产生 `RUNNING → COMPLETED`；事件、数据库状态和回放顺序一致。
- branch 名冲突不会覆盖既有 branch。
- 成功 commit 的 tree 与批准 patch 一致。
- 恶意 hook/filter/config fixture 在 commit 流程中不会于宿主执行。
- decision expiry 与 execution deadline 语义分别生效；截止后不创建新 ref，且只有 reconciliation 确认 ref 未创建时 ActionExecution 才能按定义迁移到 `EXPIRED`、Run 进入带 `ACTION_EXECUTION_EXPIRED` 的 `FAILED`。
- 活动工作树及源仓库 config/hooks/index/worktree metadata 不变。
- S8 在所有 remote/multi-user mode 下无条件禁用 R2；只有后续 S9-C evidence 才能改变远程门禁。

验收：

```bash
(cd codeaware-py && uv run python scripts/run_tests_safe.py -q)
(cd codeaware-py && uv run python scripts/run_tests_safe.py -m integration tests/integration/test_approval_resume.py tests/integration/test_approval_races.py -q)
```

```bash
(cd codeaware-py/frontend && npm run lint)
(cd codeaware-py/frontend && npm run build)
(cd codeaware-py/frontend && npm run test)
(cd codeaware-py/frontend && npm run test:e2e)
```

所有后端测试、迁移 roundtrip、CAS/崩溃 failpoint 和演示只能使用 `run_tests_safe.py` 校验的本次一次性 PG/Redis 与隔离 fixture repo；不得裸跑 pytest/Alembic 或对用户仓库/开发数据库执行。

## 8. 可复制演示

实现 `codeaware-py/scripts/demo_s8_approval_action.sh`，使用隔离 fixture repo。

崩溃 failpoint 只允许由 integration/test 配置启用，默认关闭且不能成为生产 API 参数。

### 批准路径

1. 创建并跑完 S7 patch 验证。
2. 展示 Run=`WAITING_APPROVAL`、JCS manifest/hash、双期限、审批卡和 repo 初始 refs/status/config/hooks/index/worktree metadata。
3. 批准精确 Approval。
4. 在原子 `verify source + create target` ref transaction 已成功、PG 尚未标记 SUCCEEDED 的 failpoint 终止 Worker，然后重启。
5. 等待 reconciliation 和 `run.completed`。
6. 核验 `agent/<run-id>` 仅有一个 ref/commit，commit tree、trailer 和 manifest 等于批准内容，ActionExecution=`SUCCEEDED`。
7. 核验活动工作树及源仓库 config/hooks/index/worktree metadata 未改变。
8. 核验远程 refs 无变化且没有 push/PR。

### 拒绝路径

1. 创建第二个同类 Run。
2. Reject。
3. 核验 Run=`REJECTED`，没有对应 branch/commit。

### 防篡改路径

在测试 fixture 中分别改变 Patch/TestReport hash、image/profile/argv/harness、source ref 或执行期限，approve/execute 必须失败，并且 Git refs 零变化。

另以 remote mode 启动同一版本，证明 S8 R2 入口被硬关闭并指向 S9-C 前置条件。演示证据保存 Run/Approval/manifest/ActionExecution/Artifact/branch/commit ID；不要保存 token 或完整敏感源码。

## 9. Definition of Done

- [ ] JCS ActionManifest 精确绑定 tool/version/scope、source/target ref、commit metadata、Patch/TestReport、image/profile/argv/harness 和双期限。
- [ ] WAITING_APPROVAL 可跨进程等待和恢复。
- [ ] 未批准、拒绝、过期、取消和不匹配均无 Git 写入。
- [ ] 批准后只恢复原 Step，不重新规划动作。
- [ ] ActionExecution lease、Git 多-ref transaction（原子 verify source + create target）和 reconciliation 证明最多一个决定、一个目标 commit；source-ref TOCTOU 与 ref/PG 故障窗口可恢复。
- [ ] 只创建本地 `agent/*` branch/commit，不 push/PR/merge。
- [ ] 活动工作树及源仓库 Git 配置/metadata 保持不变，仓库 hook/filter 不在宿主执行。
- [ ] 本地身份策略有闭环；S8 remote/multi-user R2 始终关闭并有自动测试。
- [ ] 后端、前端、integration、安全测试及双路径演示通过。
- [ ] 本阶段实现与验收位于记录 base commit 的临时实施 Git worktree；它不等于批准后有意保留的 `agent/<run-id>` 产物分支。
- [ ] `run_tests_safe.py` 创建、校验并精确清理一次性 PG/Redis/fixture-repo stack；manifest 引用 stack identity、CAS failpoint 和 cleanup report。
- [ ] 已生成 `evidence/S8/report.md`、`evidence/S8/manifest.json` 及其哈希引用产物。
- [ ] `(cd codeaware-py && uv run python scripts/validate_stage_evidence.py S8)` 通过；Markdown 勾选或未被 manifest 引用的文件不解锁 S9。

S8 完成后，系统才可按总路线称为“受控研发协作 Agent”。

## 10. 回退与交接

运行时可关闭 R2 Tool，系统立即退回 S7 patch-only Agent，已有审计保留。

对演示生成的精确 branch：

1. 先验证名称、commit 和 approval ID。
2. 移除关联临时 snapshot/overlay，并确认 ActionExecution 不在 `EXECUTING/UNKNOWN`。
3. 仅在用户确认不再需要后删除该 branch；不得用通配符批量删除 `agent/*`。

生产数据 migration 默认不 downgrade；迁移往返只在 safe runner 的一次性数据库执行。从临时实施 worktree 保留 evidence/patch 后移除该精确 worktree，一次性 stack 仅按已验证 identity 清理；不得把自动清理扩展到用户确认要保留的 `agent/<run-id>` 分支。S9-C 完成前远程 R2/R3 均保持关闭；S9 任何远程写操作都必须建立新的 R3 ActionManifest/Approval，不能复用本阶段的 R2 决定。
