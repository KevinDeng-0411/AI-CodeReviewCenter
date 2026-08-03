# C4 BM25 词法召回增强报告

## 元信息

- stage：C4
- route profile：current-release
- run_id：`20260803T160931Z-de9dfbc5`
- baseline（C3 冻结）：`3f95543c1fb31e630e233332c1bfed850e855c21`
- implementation：`a2a85b4cbca685d7cc70f7461f177e98b579b36e`
- implementation parent：`ce6bf19cc0781923d2b8dca0dc292805d82f0b2a`
- validated head：`5025041d9293ad0cd6b0ff17a48676ade7580de1`
- dependency：C3 `7b044150c94c21c51cf2740e7609c1ec952638e5283834adfebb7628a6e48dfb`

## 结果与边界

ParadeDB pg_search v0.12.0 BM25 词法召回接入 LexicalRecallPort（ABC），与 pgvector 向量
经 RRF 融合。三路对照（C3 pg_trgm / C4 BM25 only / C4 fused）在固定 35 条 golden set
上完成；四个质量门禁全部通过。`rag_lexical_backend` 默认仍 `pg_trgm`，C4 通过后可切
`bm25`。未引入 OCR、视觉模型或异步索引 Worker；0006 只加索引，回退 = DROP INDEX + 配置切回。

## 自动命令

| id | cwd | exit | log | SHA-256 |
|---|---|---:|---|---|
| bm25-retriever | `codeaware-py` | 0 | `artifacts/bm25-retriever.log` | `3c90192cdd14ceaa04756f61030bafd1caf4b9a83ea5ce3bd9aa283ce9740e24` |
| rollback | `.` | 0 | `artifacts/rollback.log` | `6e496c6512e45585f70304b4551a86c0505048721a51d5a0e8305b6316ae8258` |

## 三路对照与门禁

| 指标 | C3 pg_trgm | C4 BM25 only | C4 fused |
|---|---|---|---|
| Recall@5 | 0.543 | 0.600 | 0.957 |
| MRR@10 | 0.529 | 0.600 | 0.934 |

- G1 fused Recall@5：C4 0.957 ≥ C3 0.957 → PASS
- G2 稀有标识符 MRR：C4 1.000 > C3 pg_trgm 0.938 → PASS
- G3 语义改写 Recall@5：C4 0.786 ≥ vector-only 0.786 → PASS
- 时序：C4 fused 5.876s，C3 fused 6.581s（不超 2x）→ PASS

中文精确 Recall@5：C3 pg_trgm 0.000 → C4 fused 1.000；
fused MRR 由 C3 0.906 升至 C4 0.934。

## 契约、安全与回退

- Alembic 唯一 head/current 为 `0006`；0006 仅建 BM25 索引，无数据迁移。
- BM25 扩展/索引不可用时 Bm25LexicalRecall 返回空，HybridRetriever 降级纯向量（不伪造 keyword）。
- 回退在 detached C3 冻结 worktree + 一次性数据库验证：pg_trgm 检索仍可用，主工作区与开发 Docker 资源不变。

## 限制

- BM25 default tokenizer 对中文按非字母切分，中文精确 R@5 仅 0.25（fused 已由向量补足至 1.0）。
- fused MRR 0.934，语义改写腿仍依赖向量。
- local single-user，无 Agent/工具循环。

## 结论与门禁

当前 C4 是否完成：是

是否允许"评审" Agent 路线：是（仅评审，不构成实施授权）

是否授权"实施" Agent 第一阶段：否

默认评审档案：personal-local-readonly

`result=passed`。该结论形成 `REVIEW_UNLOCKED:Agent`；Agent 实施仍需用户在 C4 后另行明确授权。
