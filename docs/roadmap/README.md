# CodeAware 升级总入口

> 本目录把“当前必须完成的版本收尾”和“未来 Chat → Agent 方向”严格分开。后续模型不得直接从 Agent 文档挑功能实施。
>
> 技术栈、AI 搜索能力和 Agent 工程能力的选型理由见[技术选型与能力地图](技术选型与能力地图.md)。
> 需要交给其他编码模型时，复制[单阶段任务模板](模型实施任务模板.md)，一次只领取一个阶段。
> 所有阶段完成判定统一遵循[证据清单与解锁规则](证据清单与解锁规则.md)，文档勾选框不能代替机器可校验证据。
>
> **当前状态（2026-07-30）**：C1、C2 已形成并通过机器验证的 Evidence
>（[C1](current-release/evidence/C1/report.md) /
> [C2](current-release/evidence/C2/report.md)）；C3 尚未开始，下一项实际开发只能是
> C3。个人 Agent 默认路线虽已收缩为
> `S1-lite → S2-lite → S4-lite → S5-lite`，但在 C3 完成及另行授权前仍保持锁定。

## 1. 两条轨道

| 顺序 | 轨道 | 性质 | 入口 | 当前动作 |
|---|---|---|---|---|
| 1 | 当前版本收尾 | 当前必须完成 | [current-release](current-release/README.md) | 逐卡实施、演示、验收 |
| 2 | 个人项目 Chat → Agent | 后续默认方向 | [personal-local-readonly](chat-to-agent/personal/README.md) | S1-lite→S2-lite→S4-lite→S5-lite，保持锁定 |

```text
当前缺口修复
  → 现有 7 个功能域全链路验收
  → 当前版本冻结与证据交接
  → 才允许评审未来 Agent 第一个阶段
```

## 2. 硬门禁

Chat → Agent 进入正式评审前，必须同时存在并通过验证：

- `current-release/evidence/C1/manifest.json`
- `current-release/evidence/C2/manifest.json`
- `current-release/evidence/C3/manifest.json`
- C3 证据中的“允许评审 Agent 路线”结论为是
- 当前版本所有普通测试、前端检查和空环境启动均通过

这只形成 `REVIEW_UNLOCKED`。首次 Agent 代码实施还必须在 C3 之后取得用户对 **S1** 的明确授权，形成 `IMPLEMENTATION_UNLOCKED:S1`；以后每张默认卡都要在其全部直接依赖证据形成后重新授权。默认能力 DAG 是 `C3 → S1 → S2 → S4 → S5`，不按编号连续性推导。缺少任一项时：

- 可以阅读、评审和调整 Agent 方向文档；
- 不得安装 LangGraph、创建 Agent 表、开放 Tool、sandbox 或审批写操作；
- 不得以“为 Agent 铺路”为由扩大当前修复范围。

## 3. 文档权威边界

- ADR 管长期领域语义；`current-release/` 是当前实现和验收的唯一执行权威。
- `migration/` 是迁移历史与背景，不直接下发当前任务。
- 获得授权后，`chat-to-agent/personal/` 的当前精简卡是默认实施权威；
  `chat-to-agent/00` 只约束该卡实际使用的公共类型和安全边界。
- `chat-to-agent/02` 至 `10` 是完整平台参考，不能扩大个人默认卡的范围；
  S3/S6–S9 必须先满足触发条件、修订路线与证据 DAG，才可另行请求授权。
- 具体冲突处理和解锁状态见[证据清单与解锁规则](证据清单与解锁规则.md)。

若文档冲突，实施模型必须暂停，先修正文档或新增 ADR，不得自行挑选解释。

## 4. 对实施模型的要求

1. 一次只领取一张阶段卡。
2. 开工前验证前置 evidence，不用“代码看起来完成”代替证据。
3. 只改阶段允许范围；用户工作区的其他修改保持不动。
4. 每阶段必须有自动测试、可复制演示、持久化/事件核验和回退。
5. 按对应模板落盘，并由证据验证器通过后，才允许更新阶段状态。
6. 当前版本未冻结前，最终汇报必须使用“Chat 应用”，不能宣称 Agent。
