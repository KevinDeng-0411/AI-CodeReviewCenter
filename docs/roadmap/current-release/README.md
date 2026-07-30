# 当前版本收尾计划

> 这是当前应优先实施的计划。目标是把已承诺的 Python Chat 应用真正闭环；Agent 仅存在于另一目录的未来方向文档中。

- 制定日期：2026-07-29
- 当前证据基线：C2 后端 `251 passed, 2 deselected`、覆盖率 `90%`、API
  contract/e2e `38 passed`、七域 browser E2E 与真实 DeepSeek/Ollama smoke 通过；
  见 [C2 Evidence](evidence/C2/report.md)
- 当前产品边界：FastAPI + LangChain + DeepSeek 的 Chat/RAG/Memory 与四类薄工具
- 完成原则：修复真实链路，不以 mock 单测或文档中的 `[x]` 代替可运行演示

## 1. 当前必须完成的顺序

| 阶段 | 当前交付 | 状态 | 实施卡 |
|---|---|---|---|
| C1 | 修复已确认的真实链路缺口 | **已完成**（[manifest](evidence/C1/manifest.json) 已验证） | [01-当前缺口修复](01-当前缺口修复.md) |
| C2 | 现有功能全链路闭环验收 | **已完成**（[manifest](evidence/C2/manifest.json) 已验证） | [02-现有功能闭环验收](02-现有功能闭环验收.md) |
| C3 | 文档、启动方式和版本基线冻结 | **下一阶段，未开始** | [03-版本冻结与交接](03-版本冻结与交接.md) |

依赖关系：

```text
C1 → C2 → C3 → Agent 路线仅进入“可评审”
```

C3 完成也不表示必须升级 Agent；它只表示当前版本已经交付，不再阻塞后续方向评估。

## 2. 当前版本完成后的用户体验

用户应能从空环境完成：

1. 启动 PostgreSQL/pgvector、Redis、Ollama，执行 Alembic。
2. 打开前端并使用 Code Review、Unit Test、AIReadMe、Chat、Knowledge、Memory、Prompt。
3. 上传文本或文件，检索并在 Chat 中使用知识。
4. 创建新流式会话并立即获得真实 `conversation_id`。
5. 多轮聊天达到阈值后看到摘要已写入 PG 和 Redis。
6. 刷新页面后继续同一会话，回答的空格和换行不丢失。
7. 按文档复现测试和演示，看到的 API 与 OpenAPI 一致。

## 3. 当前不做事项

- 不安装或接入 LangGraph。
- 不加入模型自主选工具。
- 不创建 AgentRun/ToolCall/Artifact/Approval 表。
- 不执行模型生成的 shell 或 patch。
- 不做 MCP、多 Agent、Git push/PR。
- 不为追求“主流技术栈”替换已满足当前规模的 FastAPI、React/Vite 或 pgvector。
- 不在当前修复中引入多租户大改；项目隔离留在未来路线第一前置阶段。

## 4. 执行协议

每个模型只能实施 C1、C2、C3 中的一项：

1. 读根目录 `AGENTS.md`、`docs/INDEX.md`、本文件和当前阶段卡。
2. 所有可复制命令都从仓库根目录执行；脚本必须自行解析仓库根，不能依赖调用者上一次 `cd` 的状态。
3. 保存实施前 `git status`、测试、OpenAPI 和运行环境证据。
4. 先通过本节的测试安全门，再补失败测试和修实现；不得降低现有断言或静默吞异常。
5. 普通 CI 使用 fake LLM/embedder；真实依赖走显式 integration/live 标记。
6. 演示从用户入口开始，以数据库、Redis、API 或 UI 结果结束。
7. 按[阶段证据清单与解锁规则](../证据清单与解锁规则.md)生成 `evidence/Cx/report.md`、`evidence/Cx/manifest.json` 及其哈希引用产物。
8. 从仓库根运行 `(cd codeaware-py && uv run python scripts/validate_stage_evidence.py Cx)`；只有验证器通过后才更新本表状态。

### 4.1 仓库根命令约定

每段命令都必须能单独复制，统一以以下两行开始：

```bash
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
```

需要进入子目录时使用子 shell，例如：

```bash
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
(cd codeaware-py/frontend && npm run lint)
```

不得先 `cd codeaware-py`，再在下一段执行 `cd codeaware-py/frontend`。当前版本脚本统一位于 `codeaware-py/scripts/`；shell 入口从仓库根以 `./codeaware-py/scripts/<name>.sh` 调用，Python 入口以 `(cd codeaware-py && uv run python scripts/<name>.py ...)` 调用。

### 4.2 测试数据安全门

当前测试 fixture 会执行建表/删表、Alembic downgrade 和 Redis `flushdb`。C1 已交付并验证
fail-closed runner；此后仍然**禁止直接运行裸 `uv run pytest`、固定测试库上的 migration
roundtrip，或任何未验证目标的清理命令**。

所有后端测试必须通过 C1 交付的 `codeaware-py/scripts/run_tests_safe.py` 执行。该入口必须在导入 `app` 或 `pytest` 前：

- 为每次运行创建带随机 `stack_id` 的一次性 PostgreSQL/Redis 环境，以及独立的应用测试库和 migration roundtrip 库；
- 在执行任何 `drop_all`、`downgrade`、`flushdb` 或 fixture cleanup 前，验证 host/port、数据库名、Redis 实例和 `stack_id` 均属于本次一次性环境；
- 明确拒绝 `ai_center`、`ai_center_py`、固定共享测试库、Redis DB 0、Redis 开发实例和未知远程地址；
- 只在安全检查通过后由脚本内部设置 destructive-fixture 授权变量，调用者不能靠手工导出变量跳过校验；
- 无论正常、失败或中断，都只清理本次精确命名的容器、网络和 volume；不得对默认 Compose project 或开发者现有 volume 执行 `down -v`；
- 安全检查失败或清理不完整时返回非零，不得继续运行测试或打印 PASS。

演示、browser E2E、migration 回退和备份/恢复演练同样只能使用这套一次性环境。仅用数据前缀区分 fixture 不构成隔离。

## 5. 当前版本完成定义

- C1、C2、C3 的 `evidence/Cx/manifest.json` 均通过 `validate_stage_evidence.py`，报告及产物哈希可复现；
- 空环境启动不需要人工猜库名、端口或迁移顺序；
- 后端测试、演示和回退只能命中一次性 PG/Redis，安全门能对开发/未知目标 fail closed；
- 后端测试、前端 lint/build/关键交互测试通过；
- 7 个功能域均有成功和失败闭环；
- README、OpenAPI、前端请求和实际后端契约一致；
- 已知限制真实披露，AIReadMe 不再假装读取了实际仓库；
- 当前版本有可回退的基线 commit；
- Agent 路线仍默认关闭。
