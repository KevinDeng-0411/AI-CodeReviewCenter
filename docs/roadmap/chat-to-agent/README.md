# CodeAware：个人项目 Chat → Agent 路线

> **当前状态：`FUTURE_LOCKED`。**
>
> 本路线是 C1–C3 完成后的未来方向，不是当前代码任务。默认交付档已经收缩为
> [`personal-local-readonly`](personal/README.md)：精简 S1、精简 S2、跳过 S3，
> 再实施 S4、S5，并在本机只读仓库 Agent 处结束。

## 1. 当前决策

个人项目不默认承担 LangGraph 双运行时、Celery/checkpoint、Docker sandbox、审批状态机、
远程身份、MCP 和多 Agent 的长期维护成本。

唯一默认顺序：

```text
C1 → C2 → C3
  → S1-lite 项目隔离
  → S2-lite 轻量分层
  → S4-lite 只读工具 Agent
  → S5-lite 仓库感知 Agent
  → 默认路线完成
```

这条路线的终点是：

> **本机单用户 Repo-aware Read-only Agent**

它可以检索项目知识和固定 Git commit、返回来源引用，但不能运行模型生成内容、修改仓库、
创建提交、push、建立 PR 或访问远程系统。

## 2. 启动前硬门禁

进入 S1 前必须同时满足：

1. [当前版本 C1、C2、C3](../current-release/README.md) manifests 全部验证通过。
2. C3 明确当前 Chat 版本已交付并给出 `REVIEW_UNLOCKED`。
3. 用户在 C3 evidence 形成后明确授权“实施 S1”。
4. 实施者重新核对 freeze commit、OpenAPI 和 Alembic head。

C3 只允许评审，不构成 Agent 实施授权。以后 S2、S4、S5 都需要在其直接依赖 manifest
形成后重新取得当前卡的明确授权。

## 3. 默认阶段

| 阶段 | 交付物 | 状态 | 权威实施卡 |
|---|---|---|---|
| S1-lite | Project 数据与检索隔离 | 未来，锁定 | [精简 S1](personal/S1-精简项目隔离.md) |
| S2-lite | ReplyEngine、上下文、read ports 与短事务边界 | 未来，锁定 | [精简 S2](personal/S2-轻量分层.md) |
| S4-lite | 无 LangGraph 的有界 R0 工具循环与 Citation | 未来，锁定 | [精简 S4](personal/S4-只读工具Agent.md) |
| S5-lite | 固定 commit 的只读代码检索与行号引用 | 未来，锁定 | [精简 S5](personal/S5-仓库感知Agent.md) |

依赖是能力 DAG，不按编号推导：

```text
C3 → S1 → S2 → S4 → S5
```

因此：

- S4 的直接依赖是 S2，不是 S3。
- S3 缺失是合法状态，不能生成 `skipped` 或虚假通过 manifest。
- S5 的直接依赖只有 S4。
- S5 完成后默认停止，不自动请求 S6。

## 4. 部署与安全边界

默认 S1/S2/S4/S5 全部是 local-only：

```text
actor_id = "local-single-user"
REMOTE_ACCESS_ENABLED = false
bind host = 127.0.0.1 / ::1
```

- `X-Project-ID` 是隔离选择器，不是认证凭据。
- 本地仓库只能由 admin CLI 从 allowed roots 注册。
- 只允许 R0 只读工具；不存在 shell、patch、Git 写入或外部写 API。
- S4/S5 不创建 durable AgentRun/checkpoint，不承诺断线恢复和事件 replay。
- 所有阶段仍使用 safe runner、一次性 PG/Redis/fixture、manifest 哈希和回退证据。

## 5. 实施协议

每次只领取一张默认阶段卡：

1. 验证 C1–C3 和当前卡全部直接依赖。
2. 验证用户授权发生在所有直接依赖 evidence 之后。
3. 阅读根 `AGENTS.md`、本文件、[个人路线总览](personal/README.md)、当前精简卡、
   [公共契约](00-执行约定与公共契约.md)中与当前卡相关的子集，以及证据规则。
4. 只实现精简卡“最小实施范围”，平台参考卡不能扩大本阶段 DoD。
5. 完成自动测试、可复制演示、数据/事件核验和 feature-flag 回退。
6. 生成 `evidence/Sx/report.md`、`manifest.json` 和哈希引用产物。
7. 只有 validator 通过，才可请求下一张默认卡授权。

manifest 必须声明：

```json
{
  "route_profile": "personal-local-readonly"
}
```

## 6. 高阶平台参考

以下文档保留技术设计价值，但**不再是个人默认路线的实施卡**：

| 参考 | 默认状态 |
|---|---|
| [完整 S1 项目隔离](02-项目作用域隔离.md) | 平台化扩展参考 |
| [完整 S2 Graph-ready 分层](03-Graph前分层重构.md) | 平台化扩展参考 |
| [S3 确定性 LangGraph](04-确定性LangGraph.md) | 未选择；不能作为 S4 硬前置 |
| [完整 S4 工具 Agent](05-只读工具Agent.md) | 平台化扩展参考 |
| [完整 S5 仓库 Agent](06-仓库感知Agent.md) | 平台化扩展参考 |
| [S6 Durable Run](07-可恢复AgentRun.md) | 条件型参考 |
| [S7 Sandbox Patch](08-沙箱补丁Agent.md) | 条件型参考 |
| [S8 Approval/Local Action](09-审批式行动Agent.md) | 条件型参考 |
| [S9 生态与多 Agent](10-生态集成与多Agent.md) | 条件型参考 |

是否值得重新启用这些能力，只看[可选升级触发条件](personal/可选升级触发条件.md)。触发后要先
修订路线、阶段卡和证据 DAG，再单独取得实施授权；不能直接执行旧平台卡。

## 7. 完成标准

默认路线完成需要：

- C1/C2/C3/S1/S2/S4/S5 manifests 全部通过；
- 两个 Project 的知识、记忆、会话和检索无串数据；
- 模型能选择 `search_knowledge`，预算和 Citation 校验生效；
- 本地仓库按 immutable commit 建索引；
- 答案引用可复算到 commit/path/line；
- 关闭 Agent/Repository feature flags 后稳定退回 Chat；
- durable、patch、shell、R2/R3、remote、MCP、多 Agent 路径不存在或硬关闭。

完成后不得把产品描述为 Durable、Patch 或 Action Agent。
