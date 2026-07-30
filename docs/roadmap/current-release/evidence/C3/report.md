# C3 当前版本冻结与交接报告

## 元信息

- stage：C3
- release：0.1.0
- route profile：current-release
- run_id：`20260730T133750Z-403b409b`
- baseline：`c54459885e2461e3453eed249846adf76ac296b2`
- implementation：`7b9bcc838a126bf2796f62f61275eb2c00da5edb`
- implementation parent：`9bb1b63c0da8ffedb3d30f185cc1560a79cddc04`
- validated head：`3f95543c1fb31e630e233332c1bfed850e855c21`
- dependency：C2 `5d20fa529315e37a1424fe92785e9c6086604421fdcea8b9f374aa527b5aa6e3`

## 结果与边界

文档、OpenAPI、配置、版本、fresh bootstrap、全量测试、七域 browser E2E、固定评测、
交接演示和 detached rollback 均通过。C2 已提交 live smoke 的命令与指标哈希重新验证；
本次没有重复产生真实 provider 调用。未实施 C4、Agent、工具调用或仓库写能力。

## 自动命令

| id | cwd | exit | log | SHA-256 |
|---|---|---:|---|---|
| current-release-verify | `.` | 0 | `artifacts/current-release-verify.log` | `c78ffc147544fe1d3e54bc134428d5df7e908d91d99f627a2ec444f6fa9c8dcf` |
| handoff-demo | `.` | 0 | `artifacts/handoff-demo.log` | `08c46a5aaf3e09e472f37686817cb57de9f8ae53403eda70efe9016d4aaf042c` |
| rollback | `.` | 0 | `artifacts/rollback.log` | `520d3d42b792590adad5d264123c060943a54db62aff8d274868d606aad230fd` |

## 量化基线

- 后端全量：264 passed，2 deselected。
- 后端覆盖率 TOTAL：90%。
- 前端：34 tests passed；lint/build 通过。
- Browser E2E：7 个 UI 功能域通过。
- Fresh bootstrap：17 秒；完整冻结验证：180 秒。
- 固定 fake Chat（20 样本）：首 token P50
  `0.047ms`、P95
  `0.066ms`；完整响应 P50
  `0.372ms`、P95
  `0.548ms`；SSE 保真率 100%。
- 30 条检索集：pg_trgm Recall@5
  `0.3333`，vector Recall@5
  `1.0`，当前 RRF Recall@5
  `1.0`。

固定 fake 延迟只用于相同环境回归对比，不是生产压测或真实网络 SLA。

## 契约、安全与回退

- 版本 `0.1.0` 在 pyproject、FastAPI/OpenAPI 和前端 package/lock 一致。
- Alembic 唯一 head/current 为 `0005`；迁移链与逻辑备份/恢复只作用于一次性数据库。
- secret、宿主路径、上传限制和 AIReadMe traversal/symlink 回归通过。
- 回退只在 detached C2 worktree 执行，主工作区与开发 Docker 资源未变化。

## 限制

- local-first、单用户、无认证/RBAC/多租户。
- per-conversation guard 仅支持单 worker；多 worker 前需 PostgreSQL lease。
- Unit Test 不执行生成代码；普通自动化使用 fake provider。
- 当前词法腿是 pg_trgm，不是 BM25；前端 bundle 仍有体积优化空间。
- 没有 Agent Tool loop、Citation、仓库索引、shell、patch、Git 写入或多 Agent。

## 结论与门禁

当前版本是否完成：是

是否允许实施 C4 BM25：是

是否允许“评审” Agent 路线：否

是否授权“实施” Agent 第一阶段：否

默认评审档案：personal-local-readonly

`result=passed`。该结论只形成 `IMPLEMENTATION_UNLOCKED:C4`；Agent 仍保持锁定。
