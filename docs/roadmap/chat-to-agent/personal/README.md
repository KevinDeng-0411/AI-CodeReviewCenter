# 个人项目默认路线：本机只读仓库 Agent

> **路线档案：`personal-local-readonly`。当前状态：`FUTURE_LOCKED`。**
>
> 这是 CodeAware 在个人项目场景下的默认 Agent 实施入口。当前仍必须先完成
> [C1–C3](../../current-release/README.md)；C3 只解锁评审，不能自动开始本路线。

## 1. 默认交付目标

最终交付一个：

> 能按项目隔离知识和记忆、能自主选择只读工具、能读取本地 Git 仓库并返回
> commit/path/line 引用，但不会执行代码、修改仓库、创建提交或访问远程系统的
> **本机单用户 Repo-aware Read-only Agent**。

不以 LangGraph、Celery、沙箱、审批、多 Agent 或 MCP 的数量衡量完成度。

## 2. 唯一默认顺序

```text
C1 → C2 → C3
  → 用户明确授权 S1
  → S1-lite 项目隔离
  → 用户明确授权 S2
  → S2-lite Agent 必需分层
  → 用户明确授权 S4
  → S4-lite 只读工具 Agent
  → 用户明确授权 S5
  → S5-lite 本地仓库感知
  → 默认路线完成
```

| 阶段 | 用户可见成果 | 实施卡 | 直接依赖 |
|---|---|---|---|
| S1-lite | 切换项目后 Chat、Knowledge、Memory 和记录不串数据 | [S1](S1-精简项目隔离.md) | C3 |
| S2-lite | Chat 行为不变，但模型、上下文、存储和工具端口可替换 | [S2](S2-轻量分层.md) | S1 |
| S4-lite | 模型可在预算内自主调用项目知识只读工具并给出引用 | [S4](S4-只读工具Agent.md) | S2 |
| S5-lite | Agent 可检索固定 Git commit，并返回文件与行号引用 | [S5](S5-仓库感知Agent.md) | S4 |

编号保留 S4/S5 是为了与既有能力语义兼容；**S3 缺失是合法的“未选择”**，不得生成
假的 S3 manifest，也不得把 S3 当作 S4 前置。

## 3. 精简但不能删除的底线

- C1–C3 全部 evidence 通过，且每张 S 卡都在其全部直接依赖 evidence 形成后重新取得用户授权。
- 固定 `actor_id="local-single-user"`、loopback-only、`REMOTE_ACCESS_ENABLED=false`。
- `X-Project-ID` 只做数据隔离，不宣称登录、认证或成员授权。
- S2 保留唯一 TurnCoordinator、短事务 UoW 和 PG commit-first/Redis post-commit。
- S4 只有 R0 只读 allowlist，强制 schema、scope、预算、timeout、输出上限和 Citation 校验。
- S5 仓库只能由本机 CLI 注册，扫描固定 commit，不执行 hook、shell、构建、测试或网络。
- 所有测试使用 C1 的安全执行器和一次性 PG/Redis/fixture；阶段只由 manifest 判定完成。

## 4. 默认明确不做

- S3 LangGraph Workflow。
- S6 durable Run、Celery、checkpoint、事件回放。
- S7 patch 执行与 Docker sandbox。
- S8 自动创建 branch/commit。
- S9 GitHub/GitLab 写入、MCP、远程身份和多 Agent。
- Tree-sitter/symbol graph、并行工具、planner/reflection。

这些内容保留为[条件型扩展参考](可选升级触发条件.md)，没有真实需求指标时不得进入实施。

## 5. 证据与完成声明

默认路线需要且只需要以下 Agent manifests：

```text
evidence/S1/manifest.json
evidence/S2/manifest.json
evidence/S4/manifest.json
evidence/S5/manifest.json
```

每个 manifest 必须写：

```json
{
  "route_profile": "personal-local-readonly"
}
```

依赖校验按 `C3 → S1 → S2 → S4 → S5` 的能力 DAG，不按阶段编号减一推导。

S5 通过后只能声明：

```text
personal-local-readonly: completed
本机单用户 Repo-aware Read-only Agent
```

不得声明 Durable、Patch、Action、Remote 或 Multi-agent。
