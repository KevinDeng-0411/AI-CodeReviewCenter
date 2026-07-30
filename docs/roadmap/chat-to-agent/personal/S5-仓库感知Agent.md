# S5-lite：本地只读仓库感知 Agent

> **状态：Future / Locked。路线档案：`personal-local-readonly`。**
>
> 只有 S4 manifest 通过且用户在其后明确授权 S5，才能实施。

## 1. 达成的功能

用户通过本机 CLI 注册并索引 Git 仓库后，Agent 能围绕固定 commit 搜索代码、读取指定
行并返回 `repository/commit/path/line` Citation。

完成本阶段即完成个人项目默认路线。

## 2. 最小实施范围

- 新增 `Repository`：
  - 非空 `project_id/name/root_path`，nullable `current_snapshot_id`；
  - `(project_id, name)` 与 `(id, project_id)` 唯一。
  - `root_path` 是 CLI 写入的 canonical 服务端字段，不进入 HTTP schema、模型上下文、
    普通日志或响应。
- 新增 `RepositorySnapshot`：
  - 非空 `project_id/repository_id/commit_sha/index_version/status`；
  - status 仅为 `SCANNING | READY | FAILED`；
  - `(repository_id, commit_sha, index_version)`、`(id, project_id)` 和
    `(id, repository_id, project_id)` 唯一；
  - `(repository_id, project_id)` 复合 FK 指向同 Project 的 Repository。
- `Repository.current_snapshot_id` 使用
  `(current_snapshot_id, id, project_id) → RepositorySnapshot(id, repository_id, project_id)`
  复合 FK，只能显式指向 READY snapshot。
- 扩展现有 Document：
  - `repository_snapshot_id`
  - `path`
  - `language`
  - `content_hash`
  - `line_count`
- Repository Document 保留 S1 非空 `project_id`，要求
  `(repository_snapshot_id, project_id)` 复合 FK 和
  `(repository_snapshot_id, path)` 部分唯一；manual Knowledge 的 repository 字段保持空。
- 扩展 KnowledgeChunk：
  - `start_line`
  - `end_line`
  - `content_hash`
- Repository Chunk 必须满足
  `1 <= start_line <= end_line <= Document.line_count`；project/snapshot/path 继续从父
  Document 派生，不复制第二份 provenance。
- 复用现有全文、chunk、pgvector 和混合检索，不新增 Symbol/Reference graph。
- 唯一注册/索引入口是本机 admin CLI：
  - `repositories register`
  - `repositories index`
- Scanner 复用 C1 allowlist/redaction，读取完整 immutable commit SHA。
- Git 调用只允许参数数组形式的受控 plumbing，例如 `ls-tree`、`cat-file --batch`；
  不使用 shell，不执行 checkout、hook、filter、构建或网络；Git 子进程清理继承环境、
  system/global config、replace refs 和外部协议。
- 首版只支持 Python、TypeScript/JavaScript、Markdown 的有界行窗口切分。
- 固定文件数、总字节、单文件大小、timeout、binary/secret denylist。
- `(repository, commit, index_version)` 幂等；READY snapshot 及其 Document/Chunk 不可修改。
- 扫描/embedding 在事务外形成有界 DTO；一个短事务写入完整 Document/Chunk、把 snapshot
  置 READY 并 CAS 更新 current pointer。失败时用独立短事务置 FAILED，旧 READY 和 current
  pointer 保持不变。
- S4 增加三个 R0 工具：
  - `list_repository_tree`
  - `search_code`
  - `read_file_lines`
- S4 的 `search_knowledge` 必须排除 `source_type="REPOSITORY"`；Repository Chunk 只能经
  已锁定 `repository_snapshot_id` 的仓库工具读取，不能混入普通项目知识召回。
- HTTP 只接收 `repository_id`，不接收 `local_path`；服务端锁定 current snapshot。
- `search_code` Citation 引用持久 Chunk；`read_file_lines` 可引用任意受限行窗口，此时
  `document_id` 必填、`chunk_id` 可空。两者都固定 snapshot、commit、index version、
  path、start/end line，并随 Message 保存。
- `REPOSITORY_TOOLS_ENABLED=false` 时不注册仓库工具、拒绝新的 register/index，并让带
  `repository_id` 的 Agent 请求返回 `FEATURE_DISABLED`；既有索引保留，S4 Knowledge
  Agent 仍正常。

## 3. 不做事项

- 不扫描未提交 worktree，不 fetch submodule/LFS。
- 不引入 Tree-sitter、symbol graph 或 reference graph。
- 不做 AIReadMe 仓库化；后续有独立需求再评审。
- 不做后台队列、durable indexing、AgentRun 或 checkpoint。
- 不提供 diff、patch、shell、构建、测试或任何仓库写入。
- 不向模型、API 响应或普通日志暴露宿主绝对路径。

## 4. 自动测试

必须覆盖：

- allowed-root 外路径、symlink 逃逸、`../`、secret/binary/超限文件被拒绝。
- scanner 未执行 shell、hook、filter、构建或网络。
- 同 commit/index 重扫不重复；失败扫描不替换旧 READY snapshot。
- 复合 FK/唯一键拒绝跨 Project current pointer、重复 path 和 scope 漂移；READY 发布
  失败不留下可检索的部分 Document/Chunk。
- 新旧 commit snapshot 可并存，旧消息仍指向旧 commit。
- vector/keyword 两条腿都先过滤 `repository_snapshot_id`。
- 普通 `search_knowledge` 的两条检索腿都不会返回 Repository Document。
- Citation excerpt 可从对应 Git blob 行精确复算。
- 跨 Project/repository/snapshot 查询被拒绝。
- 源仓库 refs、index、status 和 worktree 内容在扫描前后不变。
- `REMOTE_ACCESS_ENABLED`、durable、patch、shell、R2/R3、MCP 和 multi-agent
  配置/路由不存在或 fail closed，不能只隐藏前端入口。

## 5. 可复制演示

```text
safe runner 创建一次性 Git fixture 和唯一 commit
→ CLI register/index
→ Agent 调用 search_code/read_file_lines
→ 返回精确 commit/path/line Citation
→ 修改未提交 worktree，旧回答不变
→ 新 commit/index 后新问题使用新 snapshot
→ 关闭 repository tools，仓库请求返回 FEATURE_DISABLED，S4 Knowledge Agent 仍正常
```

## 6. 阶段完成条件

- `repository-provenance`
- `scanner-security`
- `index-idempotency`
- `tool-citation`
- `source-unchanged`
- `profile-safety-locks`
- `rollback`

以上 check 被 `evidence/S5/manifest.json` 引用并通过。完成声明只能是：
**本机单用户 Repo-aware Read-only Agent**。
