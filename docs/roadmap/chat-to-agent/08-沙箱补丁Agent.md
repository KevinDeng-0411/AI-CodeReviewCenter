# S7：沙箱补丁 Agent

> **状态：Future / Locked（未来候选，当前版本禁止实施）。**
>
> 只有 current-release C3 evidence、S1–S6 evidence 全部通过，并且用户在这些阶段完成后对 S7 另行明确授权，才能开工。C3 或前置阶段完成均不自动授权本阶段。
>
> 本阶段允许 Agent 生成补丁并在隔离环境验证，但源仓库、活动工作树和远程系统必须保持不变。风险等级仅到 `R1_SANDBOX`。
>
> **实施入口 / 本阶段闭环：** 仅在 S6 durable evidence 与本阶段单独授权通过后，执行 `固定 base commit → 安全物化 snapshot → 生成/校验 patch → 独立 rootless runner + 只读权威验证 → 版本化 Artifact → 证明源仓库零变化`；不产生 branch、commit 或远程写。
>
> **契约来源：** Run、State、Tool、Event、Artifact、Approval、Risk 和错误的公共语义以[公共契约](00-执行约定与公共契约.md)为准；本文只定义 S7 的 patch、materializer、runner 和验证证据增量。

## 1. 阶段结果

完成后，用户提交一个小型改动任务，Agent 能：

```text
定位代码证据
  → 生成绑定 base commit 的统一 diff
  → 从 base commit 安全物化一次性源码快照
  → 在独立 rootless runner 运行允许的检查
  → 最多两轮修复
  → 返回版本化 patch + test report
```

演示结束时，原工作区 `git status --porcelain` 与开始前完全一致；没有 branch、commit、push 或 PR。

## 2. 开工门槛

- S6 的 `evidence/S6/manifest.json` 存在，且 `(cd codeaware-py && uv run python scripts/validate_stage_evidence.py S6)` 通过，清单证明确认 Worker 故障恢复与事件回放成功。
- Run、ToolCall、RunEvent、Artifact 引用、幂等和取消语义已稳定。
- S5 能固定 `repository_id + base_commit` 并给出 path/line 引用。
- 执行环境可运行 Docker；CI 能使用单独的 integration job。
- 管理员已确定本项目验证命令，不接受用户或模型提供的任意 shell。

## 3. 范围

### 必须完成

- `PatchArtifact` 与 `TestReportArtifact` 持久化和下载。
- 不触发宿主 hook/filter 的一次性源码快照与有界可写 overlay。
- `SandboxRunner` port 与 Docker adapter。
- 预构建、固定 digest 的项目 sandbox image。
- 独立 rootless runner、禁网、只读 rootfs、最小权限、磁盘/inode 配额和资源预算。
- 管理员配置的验证 profile。
- 与候选源码分离、只读挂载的权威验证套件。
- 最多两次修复，所有 patch/test report 均版本化。
- 前端 diff、日志摘要、测试结果和失败原因展示。

### 明确不做

- 不修改用户活动工作树。
- 不创建本地分支或 commit。
- 不 push、建 PR、评论或合并。
- 不向模型提供 shell、Docker socket、宿主路径或云凭证。
- 不在宿主 checkout 不可信 commit，不执行仓库 hook、filter、外部 diff、签名或 fsmonitor 程序。
- 不允许模型/用户提交 `bash -c`、管道、重定向或任意命令字符串。
- 不在 FastAPI Web 进程直接运行 Docker/subprocess。
- 不把 sandbox 输出当可信指令再次注入 system/developer prompt。

## 4. 数据与契约

若 S6 只预留了 Artifact ID，本阶段新增 `artifacts` 表：

| 字段 | 约束 |
|---|---|
| `id` | UUID PK |
| `run_id` | FK，非空 |
| `kind` | `patch / test_report / log` |
| `version` | 同 run+kind 单调递增 |
| `content_hash` | SHA-256 |
| `media_type` | patch 使用 `text/x-diff` |
| `storage_uri` | 受控相对/对象存储 URI，不暴露宿主绝对路径 |
| `metadata` | base commit、验证 profile、大小、摘要 |
| `created_at` | DB 时间 |

唯一约束为 `(run_id, kind, version)`。

`PatchArtifact` 的 metadata 至少包含：

```json
{
  "repository_id": "...",
  "base_commit": "<40-char-sha>",
  "changed_paths": ["..."],
  "additions": 12,
  "deletions": 3,
  "generator_turn": 1
}
```

diff 必须是相对 `base_commit` 的标准 unified diff。禁止绝对路径、`../`、`.git/`、符号链接逃逸、submodule 指针和二进制 patch；首版可明确拒绝 rename。

新增读取接口：

```http
GET /api/artifacts/{artifact_id}
GET /api/agent-runs/{run_id}/artifacts
```

两者都必须检查 project/actor scope。

## 5. 目标模块

```text
app/models/artifact.py
app/schemas/artifact.py
app/repositories/artifacts.py
app/ai/artifacts/store.py
app/ai/patching/diff_validator.py
app/ai/patching/patch_service.py
app/ai/sandbox/source_materializer.py
app/ai/sandbox/port.py
app/ai/sandbox/docker_runner.py
app/ai/sandbox/profiles.py
app/workers/tasks/patch_runs.py
app/api/v1/artifacts.py
sandbox/Dockerfile
sandbox/profiles.yaml
```

`app/api/v1/` 是现有 Python 包目录名，不代表公开 URL 版本前缀；本阶段所有公开路由统一挂在 `/api`。

生产边界必须保留 `SandboxRunner` 抽象。Docker adapter 只在独立 rootless runner 中可用；Web/普通 Worker 进程不得接触 Docker socket。生产部署必须把 runner 放在独立主机、VM 或等价受限服务；本地开发至少使用 rootless engine。任何环境都不能把无保护的宿主 Docker socket 挂进 API/Worker 容器。

## 6. 实施顺序

### 6.1 固定任务输入

S7 开放 `AgentRunRequest.mode="patch"`，创建时强制：

- `repository_id` 存在且属于 project；
- `base_commit` 是已索引且仍存在的完整 commit SHA；
- `base_commit` 可从管理员登记的允许 ref 到达，不能只因对象库中“存在”就接受；
- 服务端锁定 toolset、sandbox image digest、validation profile/version、权威验证套件 hash、受保护路径策略和预算；
- 源仓库路径来自服务端 Repository 配置，不能来自请求自由文本。

### 6.2 生成和校验 patch

1. 模型读取 S5 工具返回的代码和 citation。
2. 模型输出结构化 patch 候选，不获得写文件或 shell 工具。
3. `DiffValidator` 解析 diff，校验 path、大小、文件数、扩展名和 base commit。
4. 合法内容写为新 `patch` Artifact，再发 `artifact.created`。
5. 非法 patch 返回结构化错误；不能尝试在宿主仓库“看看能否应用”。

建议首版硬限制：

- 最多 10 个文件；
- diff 最大 256 KiB；
- 禁止 `.env`、密钥目录、`.git/`、lock/二进制文件，除非管理员显式 allowlist；
- 禁止修改 runner 配置、权威验证套件、profile 和受保护基线；允许修改项目自有测试时，报告必须单独列出，且不能替代外部权威验证；
- 生成轮数与公共预算共同受限。

实际值由配置记录到 evidence，不允许客户端放宽。

### 6.3 安全物化一次性源码

仓库内容、仓库本地配置和 hooks 都按不可信输入处理。`SourceMaterializer`：

1. 验证服务端登记的 repository root，以及 `base_commit` 可从允许 ref 到达。
2. 普通 API/Worker 不执行 `git worktree add/checkout`；使用不触发 checkout hook、smudge/clean filter、external diff、签名或 fsmonitor 的受控对象读取/归档路径，把精确 commit 导出为 immutable snapshot。
3. Git 子进程必须清空 system/global config 和可继承 Git 环境，使用空 `core.hooksPath`，禁用外部 filter/diff/fsmonitor、submodule 和签名；实际解包、路径校验和 patch 应用都在 runner 内进行。
4. runner 再次校验归档 entry 与解包后 realpath，拒绝绝对路径、`..`、symlink/hardlink 逃逸、设备文件和大小/inode 超限。
5. 只读挂载 base snapshot，在任务专用、带磁盘与 inode 配额的可写 overlay 中应用 patch，并用安全 diff parser/checker 验证；不把 linked-worktree `.git` 文件或宿主绝对路径带入容器。
6. 记录 snapshot/overlay ID、base tree hash 和 materializer version，不把绝对路径发送给模型或客户端。
7. 无论成功、失败、取消或 Worker 重投递，都只按受控 task ID 清理本系统拥有的 snapshot/overlay。

Worker 恢复时先检查旧 lease/snapshot/overlay 状态；不得并发复用同一可写目录。整个 S7 过程中，源仓库工作区与 `.git` 的 refs、config、hooks、index 和 worktree metadata 都必须保持不变。

### 6.4 Docker sandbox

每次验证使用新容器，最低策略：

```text
network = none
root filesystem = read-only
rootless engine + user namespace
capabilities = drop ALL
no-new-privileges = true
non-root user
host pid/ipc/user namespaces = forbidden
devices + Docker socket = none
seccomp/AppArmor(or equivalent) = default deny profile
base snapshot + authoritative verifier = read-only mounts
writable overlay = task-owned, disk/inode quota
tmpfs = bounded /tmp
CPU / memory / pids / wall-clock timeout = hard limit
stdout+stderr = byte limit
image = pinned digest
secrets = none
```

依赖在预构建 image 中准备；运行期不联网安装包或执行 dependency sync/install hook。只允许选择管理员定义的命令数组，例如：

```yaml
profiles:
  python_fast:
    commands:
      - ["uv", "run", "--no-sync", "pytest", "-q", "tests/test_target.py"]
      - ["uv", "run", "--no-sync", "ruff", "check", "app", "tests"]
```

请求只能传 `profile_id`；命令不经 shell 展开。profile/version、argv、image digest 和权威验证套件 hash 一起写入 TestReport。若当前项目尚无 ruff 命令，profile 只放真实可运行命令，不能为了文档伪造通过。

权威验证套件存放在候选 snapshot/overlay 之外并只读挂载；候选 patch 可以按产品规则修改项目测试，但不能覆盖、删除或替换用于判定通过的权威 harness。若没有独立 harness，报告必须明确降级为“仅项目自测”，不得作为后续 S8 可审批证据。

### 6.5 有限修复循环

```text
patch v1 → report v1
  ├─ pass → 完成
  └─ fail → 将受限、脱敏错误摘要交给模型
             → patch v2 → report v2
                 ├─ pass → 完成
                 └─ fail → FAILED（不再修复）
```

- 最多两次 patch 版本（初版 + 一次修复），除非公共配置明确把“修复轮数”定义为 2；实现时必须固定一种计数语义并测试。
- 每一版 immutable，不覆盖 v1。
- 日志超限先截断并标记，完整允许部分写 log Artifact。
- 测试通过只表示 sandbox profile 通过，不等于可以写源仓库。

### 6.6 事件和前端

沿用 S6 事件，至少发：

- `artifact.created`；
- sandbox/tool 的 `tool.started`、`tool.completed`；
- 每一验证 profile 的结构化状态；
- 预算耗尽、超时、patch apply 失败的 `run.failed`。

前端显示 base commit、changed paths、diff、每版测试摘要、使用的 image/profile 和“尚未写入仓库”提示。

## 7. 自动测试

新增建议：

```text
tests/test_diff_validator.py
tests/test_artifact_store.py
tests/test_patch_run_budget.py
tests/test_source_materializer.py
tests/integration/test_docker_sandbox.py
tests/integration/test_patch_agent_e2e.py
tests/security/test_sandbox_boundaries.py
```

必须覆盖：

- 合法 diff 应用成功，Artifact hash 与内容一致。
- `../`、绝对路径、`.git`、symlink 逃逸、超大 diff 被拒绝。
- 带恶意 checkout/commit hook、filter、fsmonitor、external diff 或本地 Git config 的 fixture 不会在宿主执行任何程序。
- patch 冲突返回 `PATCH_APPLY_FAILED`。
- sandbox 超时、OOM/pid/output 超限映射为结构化错误。
- sandbox 无网络、无宿主根目录/绝对路径、无密钥、非 root；磁盘与 inode 耗尽被硬限制。
- 非 allowlist command/profile 被拒绝。
- patch 修改/替换项目测试不能覆盖只读权威验证套件或伪造通过。
- Worker 重投递不重复版本或并发复用 snapshot/overlay。
- 取消后容器、snapshot 和 overlay 被清理。
- 修复循环严格停在预算上限。
- 任何成功/失败路径后，活动工作树内容和状态不变。

验收：

```bash
(cd codeaware-py && uv run python scripts/run_tests_safe.py -q)
(cd codeaware-py && uv run python scripts/run_tests_safe.py -m integration tests/integration/test_docker_sandbox.py tests/integration/test_patch_agent_e2e.py -q)
```

```bash
(cd codeaware-py/frontend && npm run lint)
(cd codeaware-py/frontend && npm run build)
(cd codeaware-py/frontend && npm run test)
```

所有后端测试、runner 故障注入和演示只能使用 `run_tests_safe.py` 校验的本次一次性 PG/Redis 与任务 namespace；不得裸跑 pytest 或连接开发/共享数据库。这里的“实施临时 Git worktree”只用于隔离本阶段代码修改，不能替代 6.3 对不可信候选源码的 snapshot materializer。

## 8. 可复制演示

实现 `codeaware-py/scripts/demo_s7_patch_agent.sh`，选择一个专用 fixture repository，不直接拿用户未提交改动的仓库做演示。

脚本必须：

1. 保存 fixture repo 的 `HEAD`、`git status --porcelain`、`git for-each-ref`、local config、hooks/index/worktree metadata 和文件哈希。
2. 创建 `mode=patch` Run，请求一个小而可验证的测试改动。
3. 输出 `artifact.created → sandbox started → test report → run.completed` 时间线。
4. 下载最终 patch 和 test report，校验服务端 content hash。
5. 展示 patch 中的 path/line 和测试通过结果。
6. 再次比较原 repo 的 HEAD、status、refs、local config、hooks/index/worktree metadata 和文件哈希。
7. SQL 核验 v1/v2 产物未覆盖、Run 预算未超限。

演示成功条件：

```text
patch artifact 可下载
validation profile 通过
原 repo HEAD 相同
原 repo status 相同
原 repo 文件哈希相同
原 repo .git refs/config/hooks/index/worktree metadata 相同
不存在 agent/* 分支
```

另演示一个非法路径 patch 被拒绝、一个超时/磁盘耗尽验证被终止，以及恶意 hook/filter fixture 未在宿主产生哨兵文件。演示还应修改候选树中的项目测试，证明只读权威 harness 仍按原规则失败。

## 9. Definition of Done

- [ ] Patch/TestReport Artifact 可追溯、版本化且 hash 可验证。
- [ ] 所有 patch 都绑定 repository 和完整 base commit。
- [ ] 不可信 commit 通过安全 materializer 导出；宿主不执行仓库 hooks/filters/config 程序，也不产生 linked-worktree 元数据。
- [ ] 独立 rootless runner 满足禁网、只读 rootfs、非 root、seccomp/userns、磁盘/inode 和其他资源限制。
- [ ] 仅管理员 allowlist 的 argv 可执行，无 shell 字符串入口。
- [ ] 权威验证套件在候选树外只读挂载；修改项目测试不能替换验收依据。
- [ ] 失败、取消、重试后容器/snapshot/overlay 均可回收。
- [ ] 修复循环有硬上限。
- [ ] 活动工作树和源仓库 `.git` refs/config/hooks/index/worktree metadata 没有变化。
- [ ] 后端、前端、integration 和 security 测试通过。
- [ ] 本阶段实现与验收位于记录 base commit 的临时实施 Git worktree；它与 runtime 的不可信 snapshot/overlay 严格分离，用户主工作树未改变。
- [ ] `run_tests_safe.py` 创建、校验并精确清理一次性 PG/Redis/task stack；manifest 引用 stack identity 和 cleanup report。
- [ ] 已生成 `evidence/S7/report.md`、`evidence/S7/manifest.json` 及其哈希引用产物。
- [ ] `(cd codeaware-py && uv run python scripts/validate_stage_evidence.py S7)` 通过；Markdown 勾选或未被 manifest 引用的文件不解锁 S8。
- [ ] 没有 R2/R3 写能力或审批假象。

## 10. 回退与交接

- 关闭 `patch` mode 和 R1 sandbox tools，保留 S6 只读 durable Agent。
- 清理经校验属于 CodeAware 的临时容器、snapshot 和 overlay；不对用户仓库执行广域删除。
- Artifact/Run 审计保留；生产/共享库不自动 downgrade，迁移往返只在 safe runner 的一次性数据库执行。
- 从临时实施 worktree 保留 evidence/patch 后移除该精确 worktree；一次性 PG/Redis/task stack 仅按已验证 identity 清理，不 reset 用户主工作树或删除共享 volume。
- S8 只能消费本阶段已验证且 hash/base commit 均未变化的 PatchArtifact。
