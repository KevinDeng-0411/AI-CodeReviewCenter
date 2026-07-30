# C2 现有功能闭环验收报告

## 元信息

- stage：C2
- route profile：current-release
- run_id：`20260730T124801Z-2fada115`
- baseline：`094ede8b24ee396b860461f62e34ea5a31cee96c`
- implementation：`cd217c8817ed81ddb19fc8268d350300e57cae91`
- implementation parent：`2aaf35f7c75088bd84f37afc7be5f14feab72bc3`
- validated head：`3f521ea69cf01c8a2971f6d58be60bb96582391a`
- dependency：C1 `15161eaa91897cfb74506385f1da292340e54b11e4b9b65753eb4f3a575e1fef`

## 结果与边界

七个现有功能域的 API 成功/失败/边界/持久化闭环、七域浏览器成功路径与可见失败、
一次真实 DeepSeek/Ollama smoke、迁移往返和 detached rollback 均通过。未实施 C3、
Agent、工具调用或仓库写入。

## 自动命令

| id | cwd | exit | log | SHA-256 |
|---|---|---:|---|---|
| dependency-lock | `codeaware-py` | 0 | `artifacts/dependency-lock.log` | `5321339c73c6402dee13c3a5dd7b266f5bfb9c0dafc59bf9016558d0bfb7c670` |
| compose-config | `.` | 0 | `artifacts/compose-config.log` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| c2-mocked-demo | `.` | 0 | `artifacts/c2-mocked-demo.log` | `98b1a7434f6d6b2e6f70e3178c05de8b99b949c859ecf9679eea87fbea837a93` |
| backend-full | `codeaware-py` | 0 | `artifacts/backend-full.log` | `a2becbe2a7936995227e8e7e980a6da71121bac1ba029868c1f07fc600878e3e` |
| backend-coverage | `codeaware-py` | 0 | `artifacts/backend-coverage.log` | `66feb427da4204b00c65fcb371e79470f88b9bcbe016e3d5df9679106bb840a6` |
| api-e2e | `codeaware-py` | 0 | `artifacts/api-e2e.log` | `1ba50215ec0d587d4e2ac3e25df06ef50d043c198da64f8233a3040b23ebf769` |
| frontend-install | `codeaware-py/frontend` | 0 | `artifacts/frontend-install.log` | `cdca58e30174759e8bd34e1fdda566d0e95a3b23c01544f7d93ae77e6a338e3c` |
| frontend-test | `codeaware-py/frontend` | 0 | `artifacts/frontend-test.log` | `04d229520324b8a3e24bbd5bc5e057a3bded91ca1bfcb54c45ec8dfbcc57039c` |
| frontend-lint | `codeaware-py/frontend` | 0 | `artifacts/frontend-lint.log` | `a158119ae505ca8b2400122fd9341710f7cf751fe0d558c8cb5049990f44ffce` |
| frontend-build | `codeaware-py/frontend` | 0 | `artifacts/frontend-build.log` | `99c96773f2a7fecaf11b587444d163c965610d0a3eb9df76d825fbc8b5bfbdf8` |
| browser-e2e | `codeaware-py` | 0 | `artifacts/browser-e2e.log` | `41a6b8732c6a6fe2a65d32919a7dbf100aa876ce97064c46da3aff501821e6b2` |
| live-smoke | `.` | 0 | `artifacts/live-smoke.log` | `4603532ea16882f40a65cc5c3c81493596fe7b1b1cab286c17356d1afef57f5f` |
| rollback | `.` | 0 | `artifacts/rollback.log` | `ac16ab1139008269adcef1cdb402023720472e7bee445a6edd7d4d32e30174b2` |

## 量化结果

- 后端全量：251 passed，2 deselected。
- API contract/e2e：38 passed。
- 覆盖率报告 TOTAL：90%（记录结果，不作为全局 90% 目标）。
- 浏览器：7 个现有 UI 功能域全部通过。
- Live：模型 `deepseek-v4-flash`、embedding
  `bge-m3` 1024 维、Knowledge `both` 命中、AIReadMe v1。
- 成本记录：真实 LLM 调用 3 次；保存 provider token usage。provider 未返回 billed amount，
  因此不硬编码未经验证的价格。

## 契约与回退

- Alembic 唯一 head/current：`0005`。
- OpenAPI：`artifacts/openapi.json`。
- 回退在 detached C1 baseline worktree 和随机一次性数据库验证；主工作区与开发 Docker
  资源指纹未变化。

## 限制

- live smoke 只证明最小真实连通性和结构，不做模型输出逐字质量评估。
- browser E2E 使用真实 FastAPI/PG/Redis 与受控 fake 模型，不向浏览器注入 API key。
- 当前 per-conversation turn guard 仍为本机单 worker 约束。
- 全局 bundle 仍有体积优化空间，属于 C3 交接记录，不在 C2 扩展产品范围。

## 结论

`result=passed`。该结论只解锁当前版本 C3，不解锁任何 Agent 实施。
