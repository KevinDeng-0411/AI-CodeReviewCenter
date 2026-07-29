# CodeAware：Chat → Agent 渐进升级路线（未来方向）

> 本路线是当前版本交付后的后续目标与方向，不是当前实施任务。当前必须先完成[当前版本收尾计划](../current-release/README.md)；即使收尾完成，也要用户另行明确授权，才能开始任何 Agent 代码改造。
>
> 面向后续开发模型：任何 Chat → Agent 相关实现，必须先读本文件、[公共契约](00-执行约定与公共契约.md)、[证据与解锁规则](../证据清单与解锁规则.md)和当前阶段文档。
>
> - 制定日期：2026-07-29
> - 当前基线：Python/FastAPI Chat；短期记忆 + 长期记忆 + RAG + SSE，但仍有 C1 已确认缺口
> - 已知测试快照：`74 passed, 1 deselected`，全局覆盖率 92%；前端 lint/build 可通过；这不等于当前版本已闭环
> - 核心原则：一次只实施一个阶段；每阶段都必须能独立运行、测试、演示、回退
> - 当前状态：**`FUTURE_LOCKED`，整条 Agent 路线仅供方向参考**

---

## 1. 最终目标

把当前“系统预先拼好上下文、模型只负责回答”的 Chat，逐步升级为：

```text
用户任务
  → Agent 判断是否需要工具
  → 按项目/仓库检索证据
  → 形成计划或补丁
  → 在隔离环境验证
  → 需要写入时暂停并请求审批
  → 审批后产生可回退的本地分支/提交
  → 返回答案、引用、补丁和测试证据
```

最终系统仍以 **单 Agent** 为默认。多 Agent、MCP、GitHub/GitLab PR 属于完成安全单 Agent 之后的扩展，不得提前引入。

## 2. 阶段定义

| 概念 | 本项目中的严格定义 |
|---|---|
| Chat | 应用固定拼接记忆/RAG/历史，模型仅生成答案 |
| Workflow | 固定节点和固定边的确定性流程；即使使用 LangGraph，也不等于 Agent |
| Read-only Agent | 模型可在受限轮数内自主选择只读工具，但不能修改仓库或外部系统 |
| Repo-aware Agent | 能读取本地仓库、检索符号和文件，并给出 commit/path/line 引用 |
| Durable Agent | Run、Step、Tool Call 和事件可持久化，进程中断后可恢复 |
| Patch Agent | 能生成补丁并在隔离环境验证，但不写入源仓库 |
| Action Agent | 经人工批准后，执行与审批内容完全一致的受控写操作 |

## 3. 启动前硬门禁

在进入下表 S1 前，必须同时满足：

1. [当前版本 C1、C2、C3](../current-release/README.md) 均有通过的 evidence。
2. C3 明确写明当前 Chat 版本已完成。
3. 证据验证器给出 `REVIEW_UNLOCKED`。
4. 用户在 C3 之后另行明确授权“实施 S1”；“文档已经写好”或一次性批准整条路线不构成授权。
5. 实施者重新核对仓库现状；未来路线中的建议路径若已变化，只做有记录的机械映射。

前三项只允许正式评审；第四项成立后才形成 `IMPLEMENTATION_UNLOCKED:S1`。以后每个 S 阶段都需要前一阶段 manifest 通过且用户重新明确授权。门禁未满足时，可以修改本路线文档，但不得安装 LangGraph、建 Agent 表、开放 Tool 或实现 sandbox/审批。

当前 Chat 的修复细节以[current-release/C1](../current-release/01-当前缺口修复.md)为准；[稳定 Chat 基线附录](01-稳定Chat基线.md)不得形成第二套冲突方案。

### S1–S8 的运行边界

S1–S8 只交付 **本机单用户模式**：

- 使用不可由请求伪造的固定 sentinel actor；`project_id` 仅是数据隔离键，不代表认证或成员资格。
- 只监听 loopback 或受信本地入口；远程部署、多人共享和 R2/R3 写能力全部关闭。
- 本地仓库注册/扫描走管理员 CLI 或受控配置，不向普通 HTTP API 暴露任意 `local_path`。
- 远程身份、项目成员关系和外部写权限在 S9-C 独立补齐；完成前不得把本地证据解释成远程安全证明。

## 4. 未来唯一实施顺序

| 阶段 | 交付物 | 状态 | 详细实施卡 |
|---|---|---|---|
| S1 | 项目级数据与检索隔离 | 未来，锁定 | [02-项目作用域隔离](02-项目作用域隔离.md) |
| S2 | Graph-ready 分层 | 未来，锁定 | [03-Graph前分层重构](03-Graph前分层重构.md) |
| S3 | 确定性 LangGraph Workflow | 未来，锁定 | [04-确定性LangGraph](04-确定性LangGraph.md) |
| S4 | 只读工具 Agent | 未来，锁定 | [05-只读工具Agent](05-只读工具Agent.md) |
| S5 | 本地仓库感知 Agent | 未来，锁定 | [06-仓库感知Agent](06-仓库感知Agent.md) |
| S6 | 可恢复 Agent Run | 未来，锁定 | [07-可恢复AgentRun](07-可恢复AgentRun.md) |
| S7 | 沙箱补丁 Agent | 未来，锁定 | [08-沙箱补丁Agent](08-沙箱补丁Agent.md) |
| S8 | 审批式行动 Agent | 未来，锁定 | [09-审批式行动Agent](09-审批式行动Agent.md) |
| S9 | Git/MCP/多 Agent 扩展 | 未来，条件触发且锁定 | [10-生态集成与多Agent](10-生态集成与多Agent.md) |

### 阶段依赖

```text
当前版本 C1 → C2 → C3
  → 用户明确授权 S1
  → S1 → 每阶段重新授权 → S2 → S3 → S4 → S5 → S6 → S7 → S8
                                                               └→ S9-A/B/C/D（逐卡授权，可选）
```

不得跳过：

- 当前版本 C1–C3 未闭环时，不能开始 S1。
- S1 之前不能开放工具，因为当前 Knowledge、Memory、Conversation 缺少严格项目隔离。
- S2 之前不能上 Graph，否则只会把数据库和业务耦合搬进节点。
- S3 只是 Workflow，不能对外宣称完成 Agent。
- S6 之前不能加入需要暂停/恢复的审批写操作。
- S7 之前不能执行模型生成的代码或命令。
- S8 之前不能修改源仓库、创建提交或调用外部写 API。
- 没有单 Agent 评测数据时不能进入多 Agent。

## 5. 后续模型的执行协议

每个实施模型只领取一个阶段，并严格执行：

1. 先运行统一验证器确认当前版本 C1–C3、全部前置 S 阶段和当前阶段授权，再阅读根目录 `AGENTS.md`、`docs/INDEX.md`、本总览、公共契约、当前阶段卡和相关 ADR。
2. 检查 Git 状态，保留用户已有修改，不覆盖与当前阶段无关的内容。
3. 运行阶段文档中的“实施前基线”；基线失败时先记录，不得把既有失败误算为本阶段回归。
4. 只修改当前阶段“允许范围”内的模块，不顺手实现下一阶段。
5. 数据库、公共 API 或核心状态变化必须新增 Alembic migration，并同步 schema/types。
6. 运行当前阶段要求的单测、集成测试、前端检查和演示。
7. 按[验收证据模板](验收证据模板.md)生成报告与产物，写入唯一的 `evidence/Sx/manifest.json`。
8. 只有统一证据验证器通过，才把上表状态改为“已完成”；这只允许请求用户授权下一阶段，不会自动解锁。
9. 若失败，保留阶段为“未完成”，记录阻塞点，不得用降低断言、吞异常或跳过测试伪造闭环。

## 6. 每阶段必须形成的闭环

```text
需求边界
  → 实现
  → 自动测试
  → 可重复演示
  → 观察持久化/事件/产物
  → 验证回退
  → manifest 引用的可校验证据
  → 才能进入下一阶段
```

每阶段至少交付：

- 一条用户可感知的完整路径，或一条可验证的行为等价路径；
- 正常、异常、边界和回退测试；
- 一个无需阅读源码即可复现的演示；
- 明确的“不做事项”；
- 下一阶段可依赖的稳定接口。

## 7. 全局测试命令

实施模型应从仓库根按阶段运行以下命令，不得把真实 DeepSeek/Ollama 调用放入普通 CI。C1 安全执行器未完成前禁止直接运行 pytest：

```bash
(cd codeaware-py && uv run python scripts/run_tests_safe.py -q)
(cd codeaware-py && uv run python scripts/run_tests_safe.py --cov=app --cov-report=term-missing -q)
```

```bash
(cd codeaware-py/frontend && npm run lint)
(cd codeaware-py/frontend && npm run build)
```

后续新增：

```bash
(cd codeaware-py/frontend && npm run test)
(cd codeaware-py/frontend && npm run test:e2e)
```

真实模型、真实 embedding、Docker sandbox 和故障恢复测试使用 `integration` 或 `live_eval` 标记单独运行。

## 8. 全局不做事项

- 不把“安装 LangGraph”当作 Agent 交付。
- 不让 Graph 节点、Tool handler 直接写 SQL。
- 不把 Run checkpoint、Conversation、Memory 混成同一张表或同一生命周期。
- 不让模型直接获得 SQLAlchemy session、Redis client、文件句柄、shell 或长期密钥。
- 不用裸字符串承载工具输入输出、SSE 事件或审批内容。
- 不静默吞掉检索、工具、审批和 sandbox 错误。
- 不在 FastAPI Web 进程执行模型生成的 shell。
- 不为展示技术标签提前替换 pgvector、React/Vite 或 FastAPI。
- 不长期保留多套重复运行路径；兼容路径必须写明删除阶段。

## 9. 完成标准

S8 完成后，CodeAware 才可称为“本机单用户、受控研发协作 Agent”：

- 模型能自主选择只读工具；
- 回答和补丁均能引用具体仓库证据；
- Run 可取消、重试、重连和恢复；
- 补丁先在隔离环境验证；
- 未经批准不产生源仓库写入；
- 批准后只执行被批准的精确操作；
- 每个步骤都有 trace、事件、审计和测试证据；
- 随时可以退回只读 Agent 或稳定 Chat。

远程或多人环境仍必须保持关闭，直到 S9-C 身份与授权边界通过独立验收。
