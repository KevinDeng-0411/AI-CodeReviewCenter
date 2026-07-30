# S5：本地仓库感知 Agent

> **路线门禁更新（2026-07-30）**：C3 后已新增 C4 BM25。下方所有 C3-only 前置描述
> 均须同时验证 C4 manifest。
>
> **完整平台参考，非个人默认实施卡。** `personal-local-readonly` 的 S5 唯一权威是
> [精简 S5](personal/S5-仓库感知Agent.md)。默认不实现 Tree-sitter、Symbol 表、AIReadMe
> 仓库化或 durable 交接；S5 完成即结束默认路线。
>
> **状态：Future / Locked（未来候选，当前版本禁止实施）**
>
> 本文不是当前版本任务，也不构成自动开工授权。只有同时满足以下条件，才允许由用户另行决定是否实施：
>
> 1. `docs/roadmap/current-release/evidence/C3/manifest.json` 已存在，且 evidence validator 结论为“当前版本完成、允许评审 Agent 路线”；
> 2. 默认 profile 的 S1、S2、S4 manifests 均存在且 validator 通过；S3 仅在显式选择 Graph profile 时出现；
> 3. 用户在 C3 和所有前置 Agent 阶段完成之后对 **S5** 给出新的、明确的实施授权。
>
> 任一条件不满足时，只能阅读和评审本文，不能注册/扫描仓库、创建源码索引迁移、开放代码工具或把本阶段并入当前版本。C3 或任一前置阶段完成均不代表默认进入 S5。

> 本阶段把 S4 的只读 Agent 从通用 Knowledge 扩展到“指定仓库的指定提交”。
> 所有证据必须绑定 `project/repository/commit/path/line/symbol`，所有源码访问必须经过安全 scanner 和只读 repository port。
>
> S5 仍是 local single-user、loopback-only、remote-disabled。`X-Project-ID` 只隔离数据，actor 是服务端 sentinel。宿主 `local_path` 只能由本机 admin CLI 注册，不能通过普通 HTTP 输入；S5 不新增认证/RBAC。
>
> S5 是 C3/C1 AIReadMe 安全 snapshot 之后的未来增量：必须复用其 allowlist、canonical path、symlink、secret、大小和 redaction primitives，并迁移到 Git snapshot provenance；不得保留第二套 path scanner 或重做 C1。

---

## 实施入口 / 本阶段闭环

公共类型、Citation、Tool/Event、API base path、sentinel 和错误码只以[公共契约](00-执行约定与公共契约.md)为准；本文只描述 S5 增量。

| 项目 | 唯一入口 |
|---|---|
| 前置 manifest | C1/C2/C3 + S1/S2/S4；Graph profile 才加 S3；C1 scanner inventory、S4 Citation migration、OpenAPI/Alembic head、S5 明确授权 |
| 唯一增量 | 本地 admin CLI 注册、immutable Git snapshot/index、snapshot-scoped R0 tools、repo-aware AIReadMe provenance |
| 必测 | allowed-root/Git object 安全；snapshot FK/index version；重扫幂等；跨 scope；blob/citation 复算；旧 AIReadMe 迁移 |
| 演示 | disposable repo + 唯一 commit fixture：register CLI→scan→Agent citation→AIReadMe→new snapshot stale→flag 回退 |
| 回退 | 先关 repository tools；current snapshot 指回旧 READY；schema 往返只在 detached 临时 worktree + 一次性 PG/Redis 演练 |
| 下一步 | 个人默认路线完成；不得自动进入 S6，不得加入 durable Run、patch、shell 或写仓库 |

## 1. 阶段目标

建立本地 Git 仓库的安全注册、不可变 commit 扫描、代码符号索引和只读代码工具，使 Agent 能围绕一个确定的 `base_commit` 回答仓库问题，并生成带精确源码引用的 AIReadMe。

完成后应满足：

- 仓库属于唯一 project，访问受 actor/project scope 约束；
- 扫描基于已解析的不可变 commit SHA，不直接信任工作区相对路径；
- 文件、chunk、symbol 均绑定唯一 immutable `repository_snapshot_id`，commit/index version 由 Snapshot 派生；
- Citation 至少带 repository snapshot、commit、index version、path、line，可选 symbol；
- Agent 只能使用只读代码工具；
- AIReadMe 从同一仓库索引生成、持久化来源 commit 和 Citations，并能判断 stale；
- scanner 不执行仓库代码、hooks、构建、网络或 shell；
- S4 的模型/工具预算和类型化事件保持有效。

完成本阶段后可称为 **Repo-aware Read-only Agent**，仍不能称为 Durable、Patch 或 Action Agent。

## 2. 可演示成果

注册当前 CodeAware 本地仓库并扫描一个明确 commit 后，用户询问：

```text
“ChatService 怎样整合短期记忆、长期记忆和 RAG？请指出具体文件和行号。”
```

系统应：

1. 锁定请求中的 `repository_id` 和 `base_commit`；
2. 调用 `search_code` 找到相关 symbol/chunk；
3. 按需调用 `get_symbol` 或 `read_file_lines`；
4. 返回包含 commit、路径、起止行和 symbol 的 Citation；
5. 前端来源卡片展示 `path:start-end @ short_sha`；
6. 回答引用的 excerpt 与该 commit 中 Git blob 的对应行完全一致。

AIReadMe 演示应形成：

```text
register repository
  → scan immutable commit
  → build file/chunk/symbol index
  → generate AIReadMe from indexed evidence
  → validate citations
  → save repository_id + commit + index_version
  → display freshness/stale state
```

## 3. 前置条件与阶段门禁

开始前必须确认：

- S1 header-only Project scope 和 local sentinel 已强制执行，remote 仍禁用；
- S2 已存在不直接暴露 ORM 的 application read port；
- 当前 S2 service/可选 S3 Graph runtime 与 typed SSE 稳定；
- S4 Registry、Executor、CitationValidator、4/6 预算和 non-thinking 模型已完成；
- S4 security tests 能拒绝未注册工具、跨项目 chunk 和伪造 Citation；
- `READ_ONLY_AGENT_ENABLED=false` 回退已验证；
- 真实模型不参与普通 CI；
- 当前全量测试通过并有 S4 evidence。

若 S4 Tool handler 仍能直接访问任意 path、session 或 shell，先修正 S4，不能在其上增加仓库能力。

## 4. 历史现状证据与 C1 继承点

下列路径来自 pre-C1 快照，不能直接当作 S5 修改清单。解锁时先以 C3 freeze commit 建 inventory：

- `app/models/document.py` 只有 `project_name`，没有 repository、commit、path、language 或 content hash；
- `app/models/knowledge_chunk.py` 没有 symbol 和行号；
- `app/ai/rag/semantic_chunker.py` 使用 Markdown/text 的 `unstructured.chunk_by_title`，不适合源码符号边界；
- `app/ai/services/rag.py` 的检索结果没有 commit/path/line 级 Citation；
- `app/ai/infra/vector_recall.py` 查询没有 repository/commit filter；
- 当前没有 Repository、RepositorySnapshot、RepositorySymbol 数据模型；
- pre-C1 `app/ai/services/ai_readme.py` 曾只接收 `project_path`；C1 已负责交付安全有界的本地 project snapshot，S5 必须复用并迁移该实现，而不是再次修同一个缺口；
- `app/models/ai_readme_document.py` 没有 repository/commit/index/citation/freshness 信息；
- 当前没有 Tree-sitter/等价 AST parser；
- 当前没有只读 Git object reader 和 scanner 安全预算。

实施前把 C1 scanner 的 path canonicalization、allowed roots、symlink/secret/binary/size/token/redaction tests 映射到 S5 的 Git reader/scanner；迁移完成后删除或封装旧文件入口，production 中只能有一个安全策略实现。本阶段只新增 immutable commit/index/symbol provenance，不得仅在 Prompt 中要求模型“猜测文件路径和行号”。

## 5. 范围

### 5.1 本阶段必须做

- 建立 Repository 和不可变 Snapshot/Commit 模型；
- 通过本机 admin CLI 注册本地仓库，并限制在配置的 allowed roots；HTTP 不接受 `local_path`；
- 复用 C1 AIReadMe snapshot 的 canonical path/allowlist/symlink/secret/limit/redaction primitives，迁移后只有一个 production scanner policy；
- 用安全 Git object reader 扫描已提交内容；
- 以 path、language、content hash 保存文件元数据；
- 用 AST/symbol-aware 策略生成带行号的 code chunks；
- 保存 symbol 定义索引；
- 检索强制首先过滤唯一 `repository_snapshot_id`，再校验 project/repository/commit/index version 一致；
- 注册仓库只读 tools；
- 生成 repository-aware Citation；
- 让 AIReadMe 从索引和相同 read port 取证，保存 commit/citations/index version；
- 前端展示代码来源和 AIReadMe freshness；
- 支持重新扫描同一 commit 的幂等性和新 commit 的版本并存；
- 为 scanner 的路径穿越、symlink、二进制、大文件、secret、预算和命令注入建立测试。

### 5.2 明确不做

- 不读取 allowed roots 之外的路径；
- 不默认扫描未提交 worktree；
- 不执行仓库代码、测试、构建、Git hook 或任意 shell；
- 不运行包管理器，不下载依赖，不访问网络；
- 不执行 submodule/LFS fetch；
- 不提供 patch、文件写入、branch、commit、push 或 PR 工具；
- 不实现 SCIP 全语义引用图作为硬门槛；首版只要求可靠 symbol 定义，引用搜索可后续增强；
- 不新增 durable AgentRun/checkpoint；
- 不创建 Artifact 表；AIReadMe 继续使用现有领域表；
- 不让模型提供可信 `project_id`、`repository_id` 或 `base_commit`；
- 不让普通 HTTP body/query 提供可独立生效的 `project_id`、actor 或宿主 `local_path`；
- 不用当前 worktree 文件覆盖已索引 commit 证据；
- 不为此阶段替换 PostgreSQL/pgvector；
- 不扫描 Java legacy 仓库作为默认，除非演示显式选择。
- 不开放远程监听；如需远程/多人访问，先停用 repository tools 并进入独立 Identity/ProjectMembership 阶段。

## 6. 数据模型

### 6.1 Repository

建议新增：

```python
class Repository(Base):
    __tablename__ = "repositories"

    id: UUID
    project_id: UUID
    name: str
    root_path: str
    default_branch: str | None
    current_snapshot_id: UUID | None
    is_enabled: bool
    created_at: datetime
    updated_at: datetime
```

约束：

- `(project_id, name)` 唯一；
- `(id, project_id)` 另建唯一键，供后续复合 FK 保证 scope 一致；
- `root_path` 保存 canonical server path，仅管理员/服务内部可见；
- `root_path` 只能由 local admin CLI 写入，任何 HTTP schema/OpenAPI 都不得出现该字段；
- API、错误和 trace 不返回完整宿主绝对路径；
- 路径注册前必须通过 allowed root 和 Git root 校验；
- Repository 删除首版建议软禁用，避免误删历史 Citation。

### 6.2 RepositorySnapshot

```python
class RepositorySnapshot(Base):
    __tablename__ = "repository_snapshots"

    id: UUID
    project_id: UUID
    repository_id: UUID
    commit_sha: str
    branch_name: str | None
    tree_hash: str
    index_version: str
    status: Literal["SCANNING", "READY", "FAILED"]
    attempt_count: int
    lease_expires_at: datetime | None
    last_heartbeat_at: datetime | None
    file_count: int
    symbol_count: int
    indexed_bytes: int
    error_code: str | None
    started_at: datetime
    completed_at: datetime | None
```

约束：

- `(repository_id, commit_sha, index_version)` 唯一；
- `(id, project_id)` 与 `(id, repository_id, project_id)` 唯一；`(repository_id, project_id)` 复合 FK 指向同一 Project 的 Repository，禁止重复 scope 漂移；
- commit 必须先解析为完整 SHA，再写入；
- `READY` 后视为不可变；
- 扫描失败不能替换已有 READY snapshot；
- 同一 tuple 的 `FAILED -> SCANNING` 重试必须持有行锁、递增 `attempt_count` 并取得新 lease；stale `SCANNING` 只能经 compare-and-set reclaim，不能另建违反唯一约束的影子行；
- error 只保存结构化 code/脱敏摘要，不保存源码或绝对路径；
- `repositories.current_snapshot_id` 在创建 Snapshot 表后增加复合 FK `(current_snapshot_id,id,project_id) -> repository_snapshots(id,repository_id,project_id)`；
- current snapshot 只能在 READY 后用条件更新显式切换；禁止“查询最新 READY”猜 current，因为同 commit 可有多个 index version；
- 每次 Agent 请求把 repository + requested commit 解析成唯一 READY `snapshot_id` 并锁定，后续查询只用该 ID。

### 6.3 扩展 Document

S1 已存在且非空的 `Document.project_id` 保持不变，绝不能再次新增为 nullable。现有 manual Knowledge 保持兼容，只新增：

```text
repository_snapshot_id
path
language
content_hash
size_bytes
line_count
```

约束：

- `source_type="REPOSITORY"` 时 `repository_snapshot_id/path/content_hash` 非空；manual 文档三者为 NULL；
- `(repository_snapshot_id, path)` 部分唯一，因此同 commit 的新 index version 可以并存；
- `(repository_snapshot_id, project_id)` 复合 FK 指向 Snapshot，保证 Document 的既有 project_id 与 snapshot scope 一致；
- `(id, repository_snapshot_id)` 唯一，供 Chunk/Symbol provenance 校验；
- `content` 仍只在 Document 父表保存一次；
- repository/commit/index version 全部由 Snapshot 派生，Document 不重复保存；
- API 不返回 `root_path`。

### 6.4 扩展 KnowledgeChunk

Chunk 继续通过 `document_id` 继承 project/snapshot/path/language；不要复制 repository/commit/path/language。只新增源码位置字段：

```text
symbol
symbol_kind
start_line
end_line
content_hash
```

约束：

- repository chunk 必须有完整 start/end line，且父 Document 必须属于 READY snapshot；
- `1 <= start_line <= end_line <= document.line_count`；
- 建立 `(document_id, start_line)` 与 `(document_id, symbol)` 索引；
- 向量和关键词索引沿用现有表；
- 检索 SQL 必须在 ANN/关键词两条腿上都应用相同 scope filter。

### 6.5 RepositorySymbol

```python
class RepositorySymbol(Base):
    __tablename__ = "repository_symbols"

    id: UUID
    repository_snapshot_id: UUID
    document_id: int
    name: str
    qualified_name: str | None
    kind: str
    signature: str | None
    start_line: int
    end_line: int
    parent_symbol_id: UUID | None
```

索引：

- `(repository_snapshot_id, name)`；
- `(repository_snapshot_id, qualified_name)`；
- `(document_id, start_line)`；
- 可选 `pg_trgm` 用于符号模糊查找。

`(document_id, repository_snapshot_id)` 复合 FK 指向同一 snapshot 的 Document；`parent_symbol_id` 也必须约束在同一 snapshot。path/language/content hash 从父 Document 派生，不能再存一份可能漂移的副本。首版 symbol 表记录定义，不宣称具备完整类型解析或跨语言引用图。

### 6.6 扩展 AiReadmeDocument

S1 已存在且非空的 `AiReadmeDocument.project_id` 保持不变。为历史行兼容，新增以下 nullable provenance：

```text
repository_id
repository_snapshot_id
content_hash
citations_json
```

规则：

- 新生成的 repo-aware README 必须填充 repository/snapshot；commit/index version 从 Snapshot 派生并返回；
- `(repository_snapshot_id, project_id)` 和 `(repository_snapshot_id, repository_id, project_id)` 使用复合 FK 保证 scope/provenance 一致；
- `citations_json` 保存已验证 Citation 的快照，不保存模型伪造来源；
- `(repository_id, version, section)` 唯一，README version 对同一 repository 单调递增且同 version 各 section provenance 一致；
- `repository.current_snapshot_id != README.repository_snapshot_id` 时 API 返回 `stale=true`；
- 历史非 repo README 字段保持 NULL，可继续读取。

## 7. Scanner 安全契约

### 7.1 路径注册

配置：

```env
REPOSITORY_ALLOWED_ROOTS=/srv/codeaware/repos
REPOSITORY_SCAN_MAX_FILES=10000
REPOSITORY_SCAN_MAX_TOTAL_BYTES=104857600
REPOSITORY_SCAN_MAX_FILE_BYTES=1048576
REPOSITORY_SCAN_TIMEOUT_SECONDS=60
REPOSITORY_SCAN_MAX_SYMBOLS=100000
```

本节只由 local admin CLI 调用；`user_path` 是本机操作者的 CLI 参数，不是 HTTP/模型输入。实现优先复用 C1 snapshot scanner 的同名安全函数。注册步骤：

1. `Path(user_path).resolve(strict=True)`；
2. 解析后的路径必须位于某个已 canonicalize 的 allowed root 内；
3. 拒绝 allowed root 本身为 `/`、用户 HOME 或未配置的宽泛目录；
4. 用 `asyncio.create_subprocess_exec("git", "-C", path, "rev-parse", "--show-toplevel", ...)` 或等价参数数组 API；绝不调用 shell；
5. 返回 root 再次 canonicalize，并重新校验 allowed root；
6. 不接受 symlink 逃逸；
7. 不向客户端回显 canonical absolute path。

### 7.2 基于 Git object 扫描

默认不遍历当前 worktree。推荐：

1. 对 ref 先做长度/NUL/控制字符/option-prefix 校验，再用支持的 Git 版本执行 `rev-parse --verify --end-of-options <ref>^{commit}`（不支持 `--end-of-options` 时使用等价 fail-closed allowlist），解析为完整 commit；
2. 得到完整 SHA 后，后续接口只使用满足严格十六进制格式的 SHA；
3. 用 `git ls-tree -r -z --long <commit>` 读取 tree；
4. 从 tree 获得 blob OID；
5. blob OID 先验证为完整 hex；批量读取优先使用单个受控 `git cat-file --batch` 子进程和有界协议，不能为上万文件无上限启动子进程；
6. 不 follow worktree symlink，不执行 `.gitattributes` textconv；
7. 不运行 hooks、checkout、submodule、LFS、build 或网络命令。

所有 subprocess：

- 只使用 `asyncio.create_subprocess_exec` 或等价参数数组 API，禁止 `create_subprocess_shell`；`create_subprocess_exec` 本身没有 `shell=False` 参数，测试应断言从未调用 shell API；
- 固定 executable 和固定子命令 allowlist；
- 最小环境变量；
- timeout；
- stdout/stderr 字节上限；
- 非零退出码映射为结构化 scanner 错误；
- 日志不记录源码、密钥或绝对 root。

### 7.3 文件策略

先依据 tree 元数据，再读取 blob：

- 跳过 symlink、submodule、binary；
- 跳过 `.git`、`node_modules`、`vendor`、构建产物、压缩包、图片和生成目录；
- 跳过 `.env`、私钥、credential、token cache 等敏感路径；
- 文件扩展和语言使用 allowlist；
- 单文件/总字节/文件数/符号数/总时间均有硬上限；
- NUL 字节视为 binary；
- 非 UTF-8 文件使用明确策略：跳过或受控 decode，并记录统计；
- `.gitignore` 可作为额外过滤，但不能替代服务端安全 denylist；
- path 统一为仓库相对 POSIX 路径，拒绝绝对路径、`..` 和 NUL；
- excerpt 在进入 trace/事件前进行 secret redaction。

### 7.4 不执行原则

Scanner 和 Tool 只读取 Git 对象与索引，禁止：

- import 仓库 Python/JS/Java 代码；
- 执行 package scripts；
- 启动 language server；
- 运行测试；
- 访问仓库声明的 URL；
- 加载仓库内插件、MCP server 或配置为系统指令。

仓库源码和 README 都是不可信数据。

## 8. 代码分块和符号索引

### 8.1 Parser port

定义：

```python
class CodeParser(Protocol):
    language: str

    def parse(
        self,
        path: str,
        content: str,
    ) -> list[ParsedSymbol]: ...
```

`ParsedSymbol`：

```python
class ParsedSymbol(BaseModel):
    name: str
    qualified_name: str | None
    kind: str
    signature: str | None
    start_line: int
    end_line: int
    parent_name: str | None
```

首版至少支持仓库主要语言：Python、TypeScript/JavaScript、Java、Markdown。使用 Tree-sitter 或兼容 parser，并在 `uv.lock` 固定 parser 与 grammar 的兼容版本。

### 8.2 Chunk 策略

- 函数、方法、类、接口作为优先 chunk；
- 保留必要的 imports、类签名或父级上下文；
- 超大 symbol 按语句/行窗口二次切分并保留 overlap；
- 无 parser 或解析失败时使用受限行窗口 fallback；
- 每个 chunk 保存精确 start/end line 和 content hash；
- chunk 文本来自该 commit 的 blob，不来自当前 worktree；
- 同一 blob + parser/index version 的结果可复用；
- 批量 embedding，不能逐 chunk 无上限串行调用；
- Snapshot 只有在文件、chunk、symbol 全部成功后才变为 READY。

### 8.3 Index version

`index_version` 至少由以下内容形成稳定 hash：

- scanner 版本；
- parser/grammar 版本；
- chunk 策略版本；
- embedding model/dimension；
- ignore/allowlist 策略版本。

修改任一内容都必须生成新 index version，不在原 READY snapshot 上静默改写。

## 9. Repository read port 与只读工具

### 9.1 可信 ToolContext

在 S4 `ToolContext` 基础上增加：

```python
class RepositoryToolContext(ToolContext):
    repository_id: UUID
    repository_snapshot_id: UUID
    base_commit: str
    index_version: str
```

`repository_id` 和可选 requested commit 由 Chat body 提供后，服务端在当前 header Project 内解析为唯一 READY `repository_snapshot_id + base_commit + index_version` 并固定；模型工具参数不能提供或覆盖这些字段。

执行前统一校验：

- repository 属于 project；
- actor 等于 local sentinel，且本地静态策略允许 repository read；
- repository_snapshot_id 对应同 project/repository 的 READY snapshot，commit/index 与该行一致；
- Tool 查询首要过滤 snapshot_id；project/repository/commit 只作为复合校验和展示字段；
- 结果 Citation 与 context 完全一致。

### 9.2 `list_repository_tree`

模型输入：

```python
class ListRepositoryTreeInput(BaseModel):
    path_prefix: str = ""
    max_depth: int = Field(default=2, ge=1, le=4)
    limit: int = Field(default=200, ge=1, le=500)
```

只返回相对 path、language、size、symbol count，不返回 root path 或全文。`path_prefix` 必须标准化并拒绝绝对路径、`..`、NUL。

### 9.3 `search_code`

模型输入：

```python
class SearchCodeInput(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    language: str | None = None
    path_prefix: str | None = None
    symbol: str | None = None
    top_k: int = Field(default=8, ge=1, le=20)
```

检索要求：

- identifier/symbol 精确或模糊腿；
- 现有 lexical + vector 混合召回；
- 两条腿都应用相同 `repository_snapshot_id` filter，不能只按 commit 文本；
- RRF/融合后去重；
- 每项返回服务端 Citation；
- 不允许 query 构造成 SQL/regex 注入；
- `path_prefix` 使用参数化条件，不接受任意正则。

### 9.4 `get_symbol`

输入 symbol ID 或精确 name；必须限制在当前 snapshot。返回 signature、定义 excerpt、path/line 和 Citation。重名时返回候选列表，不跨 snapshot 猜测。

### 9.5 `read_file_lines`

模型输入：

```python
class ReadFileLinesInput(BaseModel):
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
```

限制：

- path 必须命中当前 snapshot 的 Document；
- `end_line >= start_line`；
- 每次最多 200 行和 ToolDefinition 字节上限；
- 不回退到宿主 `open(path)`；
- 内容来自索引 Document 或对应 commit blob；
- 返回行号前缀和精确 Citation；
- 读取被策略排除的 secret/binary 文件必须拒绝。

首版不注册 `run_command`、`git_diff`、`git_status`、`write_file`、`apply_patch` 或网络工具。

## 10. Citation 与回答约束

Repository Citation 必须完整：

```python
Citation(
    project_id=...,
    repository_id=...,
    repository_snapshot_id=...,
    commit_sha=...,
    index_version=...,
    document_id=...,
    chunk_id=...,
    path="codeaware-py/app/ai/services/chat.py",
    symbol="ChatService._build_context_prompt",
    start_line=...,
    end_line=...,
    excerpt=...,
    score=...,
)
```

这些完整 snapshot 继续复用 S4 的 whitelist/filter 与 `messages.citations_json` transaction B 原子持久化；历史回答读取自己的 immutable snapshot，不随 repository current pointer 变化。

验证：

- snapshot_id 必须等于本轮固定 snapshot，commit/index version 必须由该 Snapshot 派生；
- path 和 line 必须来自索引记录；
- excerpt 必须能从 Document/blob 对应行重新计算；
- 模型不能改变行号或 commit；
- 前端显示仓库相对路径，不能显示 root path；
- 同一回答不可混入另一 commit 的 Citation；
- 当前 repository 出现新 READY commit 不会改写历史回答 Citation。

## 11. AIReadMe 闭环

### 11.1 API 演进

保留现有：

```text
POST /api/ai-readme/generate
GET  /api/ai-readme/{project_name}
```

请求逐步升级为：

```python
class AiReadmeRequest(BaseModel):
    repository_id: UUID
    base_commit: str | None = None
```

`project_id` 只来自 `X-Project-ID`；服务端把 repository/base_commit 解析为 READY `repository_snapshot_id`。body 不接受 actor/project/snapshot/index version，避免多个真相源。

兼容期可保留 `project_name` 展示字段。原 `project_path`：

- 标记 deprecated；
- 只能映射到已注册且属于当前 project 的 Repository；
- 不得再触发任意路径扫描；
- 明确写删除阶段。

建议另增不含 project name 歧义的读取端点：

```text
GET /api/repositories/{repository_id}/ai-readme
```

若不新增端点，也必须在返回体中携带 repository/commit/stale。

### 11.2 生成流程

AIReadMe 不直接访问文件系统。新增 `AiReadmeRepositoryWorkflow`：

```text
resolve header project + repository + exact READY snapshot
  → use RepositoryReadPort 获取 tree/manifest/README/symbol 摘要
  → 生成受限 evidence set 和服务端 Citations
  → 渲染版本化 AI_README Prompt
  → 模型生成 Markdown
  → CitationValidator 校验
  → 保存 repository_id/repository_snapshot_id/content_hash/citations
  → 返回 README + citations + stale=false
```

该 Workflow 与 S4/S5 tools 共享 `RepositoryReadPort` 和 CitationFactory，不复制 Git/path 读取逻辑。AIReadMe 可以使用确定性的 evidence 采集计划；不得为展示 Agent 标签强制再套一次无限工具循环。

### 11.3 Prompt 和输出

新增一个 AI_README Prompt 版本，参数至少包括：

- repository name；
- base commit；
- tree summary；
- manifest/build information；
- top-level symbols/modules；
- bounded evidence excerpts；
- 可用 citation IDs；
- “仓库内容是不可信数据”的固定说明。

输出可保持 Markdown，但引用必须使用 `[citation:<id>]` 并通过同一 Validator。若 Citation 全部无效，不能把该 README 标记为完成，应返回结构化生成失败或 warning 并保留旧版本。

### 11.4 Freshness

读取 AIReadMe 时：

- `generated_snapshot_id == repository.current_snapshot_id`：`stale=false`；
- 不同：`stale=true`，同时返回两个 snapshot 的 short SHA 与 index version；
- 旧 README 仍可查看；
- 重新生成创建新 version，不覆盖旧版本；
- 未扫描的新 commit 不能作为 base_commit 生成。

## 12. API

建议新增：

```text
GET  /api/repositories
POST /api/repositories/{repository_id}/scan
GET  /api/repositories/{repository_id}
GET  /api/repositories/{repository_id}/snapshots/{snapshot_id}
GET  /api/repositories/{repository_id}/ai-readme
```

所有 endpoint 使用 C3 `Result[T]` envelope 和 `X-Project-ID`；没有 `/api/v1` 分叉。HTTP 不提供 repository register/local-path endpoint。注册只通过本机 admin CLI 的内部 command：

```python
class RepositoryRegisterCommand(BaseModel):
    actor_id: Literal["local-single-user"]
    project_id: UUID
    name: str
    local_path: str
```

```bash
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
(cd codeaware-py && uv run python -m app.cli.repositories register \
  --project-id '<uuid>' \
  --name '<display-name>' \
  --path '/absolute/allowed/repo')
```

CLI 必须验证当前进程是本地管理入口、复用 §7 安全策略并只输出 repository UUID/脱敏相对信息；OpenAPI、HTTP log 和 trace 都不得出现 `local_path`。

扫描请求：

```python
class RepositoryScanRequest(BaseModel):
    ref: str | None = None
```

响应绝不包含 canonical root path。扫描首版可在受限小仓库中同步执行，但必须有总 timeout/bytes/files 上限。若使用后台任务，必须为任务建立独立 DB session，不能复用已关闭的 FastAPI 请求 session；这也不能被描述为 S6 durable AgentRun。

Agent Chat 请求在 `mode=agent` 时增加可信绑定：

```python
repository_id: UUID | None
base_commit: str | None
```

无 repository 时仅开放 S4 Knowledge 工具；提供 repository 时必须解析成 READY snapshot 后才开放 repository tool allowlist。

## 13. 文件级实施清单

建议路径：

| 文件 | 变更 |
|---|---|
| `codeaware-py/pyproject.toml` / `uv.lock` | 添加并锁定 Tree-sitter 和首版语言 grammar |
| `codeaware-py/app/core/config.py` | allowed roots、scanner 文件/字节/时间/符号预算 |
| `codeaware-py/app/models/repository.py` | Repository |
| `codeaware-py/app/models/repository_snapshot.py` | Snapshot/commit/index 状态 |
| `codeaware-py/app/models/repository_symbol.py` | symbol 定义 |
| `codeaware-py/app/models/document.py` | 保留 S1 project_id，增加 snapshot/path/language/hash 元数据 |
| `codeaware-py/app/models/knowledge_chunk.py` | 只增加 symbol/line/hash，通过 Document 继承 snapshot |
| `codeaware-py/app/models/ai_readme_document.py` | 保留 S1 project_id，增加 repository/snapshot/citations/hash |
| `codeaware-py/app/models/__init__.py` | 导出新模型，保证 Alembic metadata 可见 |
| `codeaware-py/alembic/versions/<next>_repository_index.py` | 表、字段、约束、索引、Prompt 版本迁移 |
| `codeaware-py/app/schemas/repository.py` | 注册、扫描、snapshot、tree、symbol DTO |
| `codeaware-py/app/schemas/ai_readme.py` | repo-aware 请求/响应、stale、citations |
| `codeaware-py/app/ai/repository/git_reader.py` | 固定 Git 子命令、Git object 读取 |
| C1 `project_snapshot` 实际模块 + `app/ai/repository/scanner.py` | 提取并复用一个 allowed-root/symlink/secret/limit/redaction policy；删除重复 production scanner |
| `codeaware-py/app/ai/repository/parsers.py` | CodeParser registry / Tree-sitter adapter |
| `codeaware-py/app/ai/repository/chunker.py` | symbol-aware chunk 和 fallback |
| `codeaware-py/app/ai/repository/indexer.py` | snapshot 事务、批量 embedding、READY/FAILED |
| `codeaware-py/app/ai/repository/service.py` | project-scoped RepositoryReadPort |
| `codeaware-py/app/ai/tools/builtins/repository.py` | tree/search/symbol/read-line R0 tools |
| `codeaware-py/app/ai/services/ai_readme.py` | 使用 RepositoryReadPort/CitationValidator |
| `codeaware-py/app/cli/repositories.py` | local admin register/disable；唯一接受宿主 path 的入口 |
| `codeaware-py/app/api/v1/repositories.py` | list、扫描、snapshot 查询 API；不接受 local path |
| `codeaware-py/app/api/v1/ai_readme.py` | repo-aware 生成/读取 |
| `codeaware-py/app/api/v1/deps.py` | repository service 和 tools 请求级注入 |
| `codeaware-py/app/main.py` | 注册 repository router |
| `codeaware-py/frontend/src/api/types.ts` | RepositoryCitation、snapshot、stale |
| `codeaware-py/frontend/src/api/client.ts` | repository/AIReadMe API |
| `codeaware-py/frontend/src/pages/Chat.tsx` | repository/commit 选择、代码 Citation |
| `codeaware-py/frontend/src/pages/AiReadme.tsx` | 从已注册 repo 生成、展示 commit/stale/citations |

建议测试：

```text
tests/test_git_reader.py
tests/test_repository_scanner_security.py
tests/test_code_parser.py
tests/test_repository_indexer.py
tests/test_repository_migration.py
tests/test_repository_tools.py
tests/test_repository_citations.py
tests/test_repo_aware_agent.py
tests/test_ai_readme_repository.py
tests/test_repository_api.py
```

## 14. Alembic migration 步骤

使用当前 `head` 的下一个 revision，不能假设固定编号。升级顺序：

1. 创建 `repositories`；
2. 创建 `repository_snapshots`；
3. 为 `repositories` 增加 nullable `current_snapshot_id`，在 Snapshot 表存在后添加同 repo/project 的复合 FK；
4. 为 `documents` 增加 nullable `repository_snapshot_id/path/language/hash/size/line`；保留 S1 non-null project_id；
5. 为 `knowledge_chunks` 只增加 symbol/line/hash，不复制 project/repository/commit/path；
6. 创建只有 snapshot/document provenance 的 `repository_symbols`；
7. 为 `ai_readme_documents` 增加 nullable repository/snapshot/citations/hash；保留 S1 non-null project_id；
8. 创建 §6 的复合 FK、唯一约束、普通索引和必要的部分索引，证明同 commit 不同 index version 可并存；
9. 插入新 AI_README Prompt 版本并按 ADR-0005 激活，旧版本保留；
10. 不修改现有 manual Document/Chunk 内容；
11. 不伪造历史 AIReadMe 的 snapshot/commit，历史 provenance 保持 NULL。

迁移测试必须验证：

- 从当前 head upgrade 成功；
- 新空库 upgrade 成功；
- 现有文档和 AIReadMe 可读；
- S1 的 Document/AiReadme `project_id` 仍 non-null，未重复添加/降为 nullable；
- 同 commit 两个 index version 的 Document/Chunk/Symbol 并存且 current snapshot 指针精确；
- 所有 Document/Symbol/AIReadMe 的 composite FK 拒绝跨 project/repository/snapshot 组合；
- downgrade 能恢复旧 schema；
- downgrade 会删除新的 repo index 数据，evidence 明确说明这一数据影响；
- Prompt 每 type 仍恰好一个 active。

## 15. 顺序化实施步骤

### 步骤 1：数据和 migration

先落模型、约束、migration 和 migration tests，不接模型、不扫描真实仓库。

### 步骤 2：安全 Git reader

仅实现：

- resolve root；
- resolve commit；
- list tree；
- read blob。

所有命令用 fake subprocess/临时 Git repo 测试；拒绝 shell 字符和 ref/path 注入。

### 步骤 3：Scanner

实现 allowlist/denylist、binary、secret、size、count、timeout 和 symlink 策略。扫描结果先输出纯 DTO，不写数据库。

### 步骤 4：Parser/chunker

对首版语言解析 symbol 和精确行号；解析失败走受限 fallback。用固定 fixture 断言 blob 行与 chunk 行一致。

### 步骤 5：Indexer

- 以 `(repository_id, commit_sha, index_version)` 查找 tuple：READY 直接复用；有效 lease 的 SCANNING 返回 in-progress；FAILED 或 stale SCANNING 只在行锁/CAS 成功后递增 attempt 并进入 SCANNING；
- scanner、parser 和批量 embedding 在数据库事务之外生成有界纯 DTO；任何外部模型/网络等待期间不持有事务；
- 在一个受配额约束的 PG 事务中写入该 snapshot 的 Document/Chunk/Symbol、把 snapshot 置 READY，并条件更新 `repository.current_snapshot_id`；事务失败不得留下部分索引；
- 扫描/解析/embedding 失败时，用独立短事务把本 attempt 置 FAILED，并保证旧 READY/current pointer 不受影响；
- READY 行和其 Document/Chunk/Symbol 永不可原地重写；同一 commit 的新 parser/chunker/embedding 只能产生新 `index_version` tuple；
- 同一 tuple 重复调用和 Worker 重投递均幂等。

### 步骤 6：RepositoryReadPort

实现 tree/search/symbol/read-lines，所有查询首先显式带唯一 `repository_snapshot_id`，再以 project/repository/commit/index version 做复合一致性校验。为每条 SQL/port 测试跨 scope 与跨 snapshot 隔离。

### 步骤 7：R0 tools

通过 S4 Registry 注册四个工具，复用 S4 executor、预算、事件和 CitationValidator。不创建第二个执行器。

### 步骤 8：Repo-aware Agent

Agent 启动前解析 repository/base_commit，并把可信值放 ToolContext；模型只看允许的 read tool schemas。

### 步骤 9：AIReadMe 闭环

AIReadMe 从同一 RepositoryReadPort 获取 evidence，保存 commit/index/citations；前端展示 freshness。

### 步骤 10：安全、全量和演示

先跑 local temp-repo tests，再跑全量测试；最后才扫描一个真实允许目录中的已提交 commit。

## 16. 自动测试

### 16.1 Scanner 安全

- allowed root 外路径拒绝；
- `..`、绝对 path prefix、NUL 拒绝；
- symlink 逃逸拒绝；
- 仓库根解析后再次校验；
- ref/commit 命令注入字符串不执行；
- subprocess 只调用参数数组 API，并断言从未调用 `create_subprocess_shell` 或其他 shell API；
- hook、submodule、LFS、网络、build 不执行；
- binary、大文件、secret 路径、vendor/build 目录跳过；
- 文件数、总字节、单文件、符号数、timeout 生效；
- stdout/stderr 超限结构化失败；
- 日志和 API 不含 root path、源码或 secret；
- malicious README/源码指令只作为数据。

### 16.2 Index

- 同 commit + index version 重扫幂等；
- 新 commit 创建新 snapshot；
- 同 commit + 新 index version 创建并存的新 snapshot，旧 READY 仍不可变；
- FAILED/stale-SCANNING 重试只复用同一 tuple、递增 attempt 且不产生重复行；
- 失败 snapshot 不替换旧 READY；
- path、line、symbol 与 Git blob 一致；
- parser 失败 fallback 可用；
- manual Knowledge 不受影响；
- repository 检索两条腿都首先限制 `repository_snapshot_id`；
- A snapshot 查询不到 B project/repository/commit/index snapshot 内容；
- READY 前不能用于 Agent；
- index version 改变会生成新索引。

### 16.3 Tools/Citation

- trusted context 不能被模型参数覆盖；
- tree 结果分页和深度受限；
- search_code 返回当前 commit；
- 重名 symbol 返回候选；
- read_file_lines 最多 200 行；
- excluded secret/binary 不能读取；
- Citation excerpt 可从 blob 精确复算；
- 伪造 path/line/commit Citation 被拒；
- 不存在任何 R1/R2/R3 仓库工具；
- S4 4/6 预算仍生效。

### 16.4 AIReadMe

- 未 READY commit 不能生成；
- 生成记录包含 repo/commit/index/citations/hash；
- citations 全部来自 evidence set；
- 重新生成 version +1，不覆盖旧版本；
- 新 READY commit 后旧 README `stale=true`；
- arbitrary `project_path` 不能扫描；
- 跨项目不能读取或生成；
- 生成失败不破坏旧 README；
- 普通历史 AIReadMe 仍可读取。

### 16.5 命令

以下均从仓库根执行；safe runner 为每次后端/migration 检查创建并验证唯一的一次性 PG/Redis/fixture-repo stack：

```bash
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
(cd codeaware-py && uv run python scripts/run_tests_safe.py \
  tests/test_git_reader.py \
  tests/test_repository_scanner_security.py \
  tests/test_code_parser.py \
  tests/test_repository_indexer.py \
  tests/test_repository_migration.py \
  tests/test_repository_tools.py \
  tests/test_repository_citations.py \
  tests/test_repo_aware_agent.py \
  tests/test_ai_readme_repository.py \
  tests/test_repository_api.py -q)
(cd codeaware-py && uv run python scripts/run_tests_safe.py -q)
(cd codeaware-py && uv run python scripts/run_tests_safe.py --cov=app --cov-report=term-missing -q)
```

```bash
(cd codeaware-py/frontend && npm run lint)
(cd codeaware-py/frontend && npm run build)
```

真实 DeepSeek 可选：

```bash
(cd codeaware-py && uv run python scripts/run_tests_safe.py --live-eval -m live_eval tests/live_eval/test_repo_aware_agent.py -q)
```

Scanner 集成测试使用 safe runner 创建的本地临时 Git repo，不需要网络，也不应标记为真实模型 integration。禁止裸跑 pytest/Alembic；migration upgrade/downgrade roundtrip 只能由同一 runner 命中本次 stack identity。

## 17. 可重复演示脚本

### 17.1 启动配置

将 allowed root 设置为包含本项目的最小父目录，不能使用 `/` 或 HOME：

```env
REPOSITORY_ALLOWED_ROOTS=/absolute/minimal/demo-root
READ_ONLY_AGENT_ENABLED=true
```

取得演示 commit：

```bash
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
git rev-parse HEAD
```

只把完整 SHA 记入演示记录，不依赖未提交 worktree。

### 17.2 注册与扫描

1. 让 `run_tests_safe.py` 创建一次性 PG/Redis 和位于最小 allowed root 下、名称带随机 UUID 的 disposable Git fixture；
2. 创建/选择一个带随机 UUID 后缀的 project；
3. 从仓库根调用 §12 的本机 admin CLI 注册 fixture；普通 HTTP/OpenAPI 仍不存在 register/local-path 输入；
4. CLI 输出确认不含 canonical root path；
5. 用完整 SHA 调用 scan；
6. 查询 snapshot，确认 `READY`、file/symbol/byte 数量和 index version；
7. 重复 scan，确认不重复创建数据；以新 index version 扫相同 commit，确认两个 immutable snapshot 并存且 current pointer 精确。

### 17.3 Agent 问答

选择 repository 和 base commit，以 `mode=agent` 询问：

```text
ChatService 如何组合长期记忆、RAG 和对话历史？请给出代码证据。
```

展示：

- tool.started/completed；
- search/get-symbol/read-lines 选择过程；
- 最终 path/line/symbol/commit Citation；
- Git blob 对应行与 excerpt 对照；
- 4/6 预算和总耗时。

### 17.4 AIReadMe

1. 对同一 repository/commit 生成 AIReadMe；
2. 展示 README、Citation、commit 和 `stale=false`；
3. 扫描另一个 commit；
4. 再读取旧 README，展示 `stale=true`；
5. 重新生成，得到新 version 和 `stale=false`；
6. 历史版本仍可查看。

### 17.5 安全与回退

- 尝试注册 allowed root 外路径，应明确拒绝；
- 尝试读取 `../../.env`，工具拒绝且不泄露路径；
- 设置 `REPOSITORY_TOOLS_ENABLED=false`，Knowledge Agent 和 Chat 仍正常；
- 历史 Citation 仍可展示。

演示结束必须由 safe runner 按精确 stack/fixture identity 清理本次一次性 PG、Redis 和 Git repo；UUID 前缀不能作为清理授权，任一 cleanup 失败则演示失败。

## 18. Definition of Done

- [ ] C1–C3、S1/S2/S4 及当前所选依赖 evidence 已核验
- [ ] Repository 与 Snapshot 有 project scope 和唯一约束
- [ ] commit 在扫描前解析为完整、不可变 SHA
- [ ] scanner 默认读取 Git object，不读取未提交 worktree
- [ ] allowed roots、symlink、path traversal、secret、binary 和资源预算测试通过
- [ ] scanner 不执行 shell、hooks、代码、构建、网络、submodule/LFS fetch
- [ ] 首版主要语言可生成 symbol 和精确行号
- [ ] Document/Chunk/Symbol 只以 immutable snapshot 绑定 provenance，同 commit 多 index version 可并存且 READY 不可变
- [ ] manual Knowledge 和历史 AIReadMe 向后兼容
- [ ] 检索的 lexical/vector 两条腿都先过滤唯一 `repository_snapshot_id`
- [ ] 四个仓库工具全部是 R0_READ；actor 固定 sentinel，remote 仍硬关闭
- [ ] ToolContext 的 repo/snapshot/commit/index version 不能被模型覆盖
- [ ] Citation snapshot/commit/index/path/line 与 excerpt 可从 Snapshot/blob 精确复算并随 Message 持久化
- [ ] 前端不暴露 root path
- [ ] AIReadMe 记录 commit/index/citations 并能判断 stale
- [ ] arbitrary `project_path` 不能触发扫描
- [ ] 重扫幂等，失败不破坏旧 READY
- [ ] S4 4/6 预算、non-thinking 和 typed events 无回归
- [ ] 无 AgentRun/checkpoint、patch、shell 或写工具
- [ ] Alembic upgrade/downgrade roundtrip 仅在 detached 临时 worktree 的一次性数据库中通过
- [ ] Python 全量测试和覆盖率检查通过
- [ ] 前端 lint/build 通过
- [ ] repository tools feature flag 回退已验证
- [ ] 本阶段实现/验收位于记录 base commit 的 detached 临时 worktree，用户当前工作树未变化
- [ ] `run_tests_safe.py` 创建、校验并精确清理本次一次性 PG/Redis/fixture-repo stack
- [ ] `evidence/S5/manifest.json`、`report.md` 和哈希引用产物已完成
- [ ] `(cd codeaware-py && uv run python scripts/validate_stage_evidence.py S5)` 通过

## 19. 回滚

### 19.1 功能回退

```env
REPOSITORY_TOOLS_ENABLED=false
READ_ONLY_AGENT_ENABLED=true
```

效果：

- 禁止注册、扫描和仓库工具；
- S4 Knowledge Agent 保持可用；
- `mode=chat` 保持可用；
- 历史 Repository、Snapshot、AIReadMe 和 Citation 数据只读保留；
- 不删除源码索引。

### 19.2 索引版本回退

若新 parser/chunker 有问题：

1. 停止把新 index version 设为 current；
2. 将 repository current snapshot 指回旧 READY version；
3. 验证 Agent 固定旧 commit/index 可回答；
4. 保留失败 snapshot 结构化原因；
5. 不在原 READY 行上覆盖数据。

### 19.3 Schema downgrade

生产/开发/共享数据库默认不 downgrade；只记录备份恢复和前向修复方案。需要验证 schema 往返时，必须从记录的 base commit 创建另一个 detached 临时 worktree，并由 `run_tests_safe.py` 创建、校验另一套一次性 PG/Redis 后执行；明确 downgrade 会删除 Repository/Snapshot/Symbol 和新增 provenance 字段。不得在用户当前工作树直接 `git revert` 或运行 downgrade，也不得为了回退 Agent 删除原有 manual documents、knowledge chunks 或历史非 repo AIReadMe。

## 20. 验收证据与交接

生成唯一机器入口 `evidence/S5/manifest.json`、人类可读 `report.md` 和 manifest 哈希引用的产物；旧式单文件 evidence、单独 Markdown 勾选或未被 manifest 引用的输出不构成证据。最后必须从仓库根运行 `(cd codeaware-py && uv run python scripts/validate_stage_evidence.py S5)`。清单额外覆盖：

- allowed roots 配置摘要，不记录敏感绝对目录；
- scanner 命令 allowlist 和“从未调用 shell API”证据；
- path traversal、symlink、secret、binary、预算测试；
- repository/snapshot/schema 迁移前后结构；
- commit、tree hash、index version、文件/符号/字节统计；
- 同 commit 重扫幂等证据；
- 失败 snapshot 不影响旧 READY 的证据；
- search_code/get_symbol/read_file_lines 事件样本；
- Citation 与 `git cat-file` 行内容的脱敏对照；
- 跨 project/repository/snapshot/commit/index version 隔离测试；
- AIReadMe version/commit/citations/stale 闭环；
- feature flag 和旧 snapshot 回退；
- 模型、Prompt、toolset、index/scanner/parser 版本；
- 平均/最大工具次数、模型回合、token 和时延；
- 明确声明“无 shell、无写工具、无 durable Run、无 checkpoint”。
- detached 实施/回退 worktree 的 base/validated commit、一次性 stack identity、safe-runner target guard 与精确 cleanup report。

若未来满足 durable 触发条件，可供重新规划 S6 的稳定接口：

- Repository/Snapshot/Symbol 数据模型；
- 安全 Git object reader 和 scanner；
- RepositoryReadPort；
- snapshot-first、project/repository/commit/index-consistent 的只读 tools；
- repository-aware Citation；
- index version 和 READY/FAILED 语义；
- AIReadMe provenance/freshness 闭环；
- S4/S5 的类型化事件出口。

S5 完成不自动授权 S6。若未来重新规划 S6，它只负责把 Agent Run、Step、ToolCall 和事件
变为可持久、可恢复；不得借持久化之名放宽本阶段的仓库安全边界。
