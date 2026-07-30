# S0：稳定 Chat 基线（current-release 技术附录）

> **路线门禁更新（2026-07-30）**：C3 仍是当前 Chat freeze 的来源，但 Agent 前新增
> C4 BM25 检索增强。本文下方任何“C3 后即可授权/进入 S1”旧措辞均以
> `C3 freeze + C4 manifest 通过 + 用户在 C4 后另行授权 S1` 为准；不得据旧措辞绕过 C4。
>
> **状态：FUTURE LOCKED / 仅验收。**
>
> 当前版本的 Chat 修复已经由 [`current-release/01-当前缺口修复.md`](../current-release/01-当前缺口修复.md)（C1）权威接管。C1 对 typed SSE、sequence、摘要 migration/触发、post-turn 事务、multipart、fresh bootstrap 和 AIReadMe 当前版本收尾拥有唯一实施解释权。本文件不得成为第二套实现方案；如与 C1/C2/C3 有任何差异，以 `current-release/` 为准。
>
> S0 现在只是未来 Chat → Agent 路线的“基线验收门禁”：复用已经冻结的当前 Chat，不再修改同一批代码。只有 C1、C2、C3 evidence 全部完成，且用户另行明确授权实施 Agent 路线后，才可执行本文件的复验与交接。未来 S1 才会增加 Project 隔离和固定 `local-single-user` sentinel；S0 不得把这些未来字段、配置或安全措辞倒灌进 C1–C3。

---

## 1. 本门禁的目标

S0 不产生新的产品能力，也不再修复当前版本。它只回答一个问题：

> 当前 Chat release 是否已经稳定到足以成为后续 Project 隔离和 Graph 重构的对照基线？

通过后，未来实施者可依赖：

1. typed SSE 的 cid、sequence、空白保真、warning、completed/failed 时序已经由 C1 固定。
2. assistant、summary、memory 的事务和缓存真相语义已经由 C1 固定。
3. multipart、fresh bootstrap、AIReadMe 当前能力已经由 C1 完成。
4. 七个现有功能域的 API、持久化、失败路径和前端契约已经由 C2 闭环。
5. OpenAPI、README、启动方式、版本、指标和冻结 commit 已由 C3 固定。
6. Agent、Tool、LangGraph、Run、Project 隔离与 sentinel actor 仍未实现，当前产品边界陈述真实。

用户可见结果与 current release 完全相同。S0 不得新增页面、事件、字段、migration 或依赖。

## 2. 权威来源与冲突规则

按以下优先级读取：

1. [`current-release/README.md`](../current-release/README.md)
2. [`current-release/01-当前缺口修复.md`](../current-release/01-当前缺口修复.md)
3. [`current-release/02-现有功能闭环验收.md`](../current-release/02-现有功能闭环验收.md)
4. [`current-release/03-版本冻结与交接.md`](../current-release/03-版本冻结与交接.md)
5. `current-release/evidence/C1/manifest.json`、`C2/manifest.json`、`C3/manifest.json` 及各自 validator
6. 本文件

具体约束：

- SSE 是否带 `id/sequence`、payload 精确字段：看 C1/OpenAPI/冻结测试，不在本文件重定义。
- 摘要使用哪个 migration、watermark/interval 和事务策略：看 C1 及实际 Alembic head。
- Compose 创建哪些库、端口、readiness：看 C1/C3 冻结文档。
- 当前 API 路径、参数名、错误包络：看 C2 OpenAPI 快照。
- 测试数量、覆盖率、性能：看 C3 实测指标，不复制旧的 `74 passed` 当成新证据。

禁止从本文件恢复被 C1/C2/C3 删除或替换的 legacy 路径。

## 3. 解锁条件

以下条件必须全部满足：

- [ ] `docs/roadmap/current-release/evidence/C1/manifest.json` 存在且 validator 通过
- [ ] `docs/roadmap/current-release/evidence/C2/manifest.json` 存在且 validator 通过
- [ ] `docs/roadmap/current-release/evidence/C3/manifest.json` 存在且 validator 通过
- [ ] C3 evidence 明确填写“当前版本是否完成：是”
- [ ] 当前 release 有精确冻结 commit 和 Alembic head
- [ ] 工作区没有未解释的红测、skip、warning 或未提交 hotfix
- [ ] 用户在 C3 完成后另行明确授权“实施 Agent 路线”

“允许评审 Agent 路线”不等于允许实施；路线文件存在也不等于授权。

任一条件不满足时：

- 停止 S0；
- 回到对应 C1/C2/C3 阶段；
- 不修改 `codeaware-py/app`、frontend、migration 或依赖；
- 不开始 S1。

## 4. 当前证据快照

本路线编写时观察到的旧基线缺口如下，仅用于说明为什么 C1 接管，不是待执行清单：

| 旧证据 | 已转交的权威阶段 |
|---|---|
| `ChatService.chat_stream()` 发送裸 token 和 `[DONE]` | C1-A |
| 前端 SSE parser 对行/payload `trim()` 并猜最新 cid | C1-A |
| Chat 未传 BackgroundTasks，摘要生产触发未接通 | C1-B |
| completed 发生在真实事务/post-turn 完成之前 | C1-A/C1-B |
| post-turn/RAG/Memory 错误静默 | C1-A/C1-B |
| 文件上传未声明 `UploadFile/File/Form` | C1-C |
| Compose `ai_center` 与 Python `ai_center_py` 不一致 | C1-D |
| AIReadMe 只把路径字符串传给 Prompt | C1-E |
| 当前七域契约、参数和 Prompt 写入口仍有缺口 | C2 |
| README/端口/session 命名/能力说明失真 | C3 |

复验时不得假定这些缺口仍存在，也不得按旧文件路径机械修改；应读取 C3 冻结 commit 的实际代码。

## 5. 范围与明确不做

### 5.1 本门禁允许的操作

- 读取 C1/C2/C3 evidence、OpenAPI 快照、release notes 和冻结 commit。
- 在隔离环境重新运行冻结的 verify、mocked demo、browser E2E 和可选 live smoke。
- 比较输出与 C3 指标。
- 将复验结论直接映射到 C1/C2/C3 原始 evidence 和 C3 freeze commit，不创建第四份阶段证据。
- 发现回归时记录并退回 current-release 修复。

### 5.2 本门禁禁止的操作

- 不修改后端、前端、migration、依赖、Prompt 或 Compose。
- 不重新设计 SSE/summary/post-turn。
- 不创建与 C1 冲突的 compatibility flag。
- 不增加 Project、LangGraph、Agent、Tool、Run、Checkpoint、Approval。
- 不增加 actor header、登录/RBAC、`REMOTE_ACCESS_ENABLED` 或伪造的远程安全能力；
  个人默认 S1/S2/S4/S5 及未重新规划的高级参考都保持 local single-user。
- 不把复验失败“顺便修掉”后继续 S1；失败说明 current release 未冻结。
- 不更新 Chat → Agent README 状态为已完成，除非所有复验通过且用户已授权路线实施。

## 6. 复验步骤

### 步骤 1：固定输入

记录：

```bash
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
git status --short
git rev-parse HEAD
(cd codeaware-py && uv run alembic heads)
(cd codeaware-py && python --version)
(cd codeaware-py/frontend && node --version)
(cd codeaware-py/frontend && npm --version)
```

HEAD 和 Alembic head 必须等于 C3 evidence 的冻结值。若不等，先解释差异。

### 步骤 2：执行 C3 非破坏性验证

以 C3 实际交付脚本名称为准，预期入口：

```bash
./codeaware-py/scripts/verify_current_release.sh
```

脚本必须使用隔离配置/数据库，不能删除用户现有 volume。

### 步骤 3：执行七域 mocked demo

以 C2 实际交付脚本为准：

```bash
./codeaware-py/scripts/demo_c2_mocked.sh
```

要求七域均打印 PASS，并且每域至少核验一次 PG、Redis、文件或后续读取 API。

### 步骤 4：执行浏览器与可选 live smoke

```bash
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
(cd codeaware-py/frontend && npm run test:e2e)
```

有明确凭据和授权时才运行：

```bash
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
(cd codeaware-py && uv run python scripts/run_tests_safe.py --live-eval -m live_eval tests/integration/test_current_release_live.py -q)
```

不得用 live 调用替代普通 deterministic tests，也不得在 evidence 中泄露 key/Prompt/绝对敏感路径。

### 步骤 5：核对未来路线边界

```bash
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
rg -n \
  'langgraph|StateGraph|ToolNode|AgentRun|ToolCall|Approval' \
  codeaware-py/app codeaware-py/pyproject.toml codeaware-py/uv.lock || true
```

当前 release 不应包含本路线后续能力。若 C1/C2 因准确命名在文档/测试字符串中出现术语，应人工区分，production import/model/table 仍必须不存在。

## 7. 可复制验收脚本

以下脚本只编排 C3 已交付命令，不写产品数据：

```bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"

test -f docs/roadmap/current-release/evidence/C1/manifest.json
test -f docs/roadmap/current-release/evidence/C2/manifest.json
test -f docs/roadmap/current-release/evidence/C3/manifest.json
(cd codeaware-py && uv run python scripts/validate_stage_evidence.py C1)
(cd codeaware-py && uv run python scripts/validate_stage_evidence.py C2)
(cd codeaware-py && uv run python scripts/validate_stage_evidence.py C3)

./codeaware-py/scripts/verify_current_release.sh
./codeaware-py/scripts/demo_c2_mocked.sh

(cd codeaware-py/frontend && npm run test:e2e)
printf 'freeze commit: %s\n' "$(git rev-parse HEAD)"
(cd codeaware-py && uv run alembic heads)
```

脚本统一位于 `codeaware-py/scripts/`；不得为了让命令通过而在仓库根再复制第二份脚本。

## 8. 测试与通过标准

必须直接复用 current release 的冻结命令：

```bash
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
(cd codeaware-py && uv lock --check)
(cd codeaware-py && uv run python scripts/run_tests_safe.py -q)
(cd codeaware-py && uv run python scripts/run_tests_safe.py --cov=app --cov-report=term-missing -q)
(cd codeaware-py && uv run python scripts/run_tests_safe.py tests/contracts tests/e2e -q)
(cd codeaware-py/frontend && npm run lint)
(cd codeaware-py/frontend && npm run test)
(cd codeaware-py/frontend && npm run build)
(cd codeaware-py/frontend && npm run test:e2e)
```

fresh bootstrap/Alembic upgrade 由 `run_tests_safe.py` 在本次一次性 PostgreSQL/Redis stack 中完成；禁止裸跑 pytest 或把 upgrade 指向开发/共享库。

通过标准：

- 测试数量、skip、覆盖率与 C3 基线一致或差异已合理解释；
- SSE 内容保真率 100%；
- 七域 mocked E2E 成功率 100%；
- fresh bootstrap 在隔离环境成功；
- Chat completed/failed/warning、summary/Redis fallback、multipart 和 AIReadMe snapshot 均有 C1/C2 证据；
- 无新增 Agent production dependency/model/table/API。

## 9. Definition of Done

- [ ] C1/C2/C3 evidence 和冻结 commit/head 均存在且一致
- [ ] verify_current_release 非破坏性脚本通过
- [ ] 后端全量、coverage、contracts、E2E 通过
- [ ] 前端 lint/test/build/browser E2E 通过
- [ ] 七域 mocked demo 可重复
- [ ] live smoke 按 C3 要求已有一次脱敏证据
- [ ] SSE/summary/post-turn/multipart/fresh bootstrap/AIReadMe 不另立冲突契约
- [ ] 当前 release 中没有 Agent/Tool/LangGraph/Run 实现
- [ ] 本门禁没有修改产品代码、schema、依赖或公开契约
- [ ] 用户已在 C3 后明确授权实施 Agent 路线
- [ ] C1/C2/C3 evidence 已足以支撑进入 S1 的结论，无独立 S0 evidence

## 10. 失败与回退

S0 不修改产品，因此没有 code/migration rollback。

复验失败时：

1. 不进入 S1；
2. 在对应的 current-release 回归记录中写明失败命令、冻结值、实际值和最小复现；
3. 将问题路由回 C1（真实链路）、C2（七域契约）或 C3（冻结/文档/环境）；
4. 修复后重新生成对应 C evidence 和冻结 commit；
5. 从本门禁第一步重新复验。

禁止通过更新 fixture、降低断言或跳过失败域来“完成”S0。

## 11. 证据交接

S0 不创建独立 `evidence/S0/manifest.json`。进入 S1 时直接引用：

- C1 evidence：Chat/SSE/summary/post-turn/multipart/fresh bootstrap 的实现证据；
- C2 evidence：七域契约、失败路径、OpenAPI 和前端闭环；
- C3 evidence：freeze commit、Alembic head、指标、回退与“当前版本完成”结论；
- 用户在 C3 之后发出的明确实施授权。

S1 evidence 的“前置基线”一节记录上述相对链接、SHA256 和本次复验命令即可。不要复制 C1 SSE frame、C2 七域输出或 C3 指标，避免出现第四份漂移真相。
