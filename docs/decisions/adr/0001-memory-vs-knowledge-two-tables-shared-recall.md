# ADR-0001: Long-term Memory 与 Knowledge Document 分表 + 共享向量召回基建

- **状态**: Accepted
- **日期**: 2026-07-28
- **更新**: 2026-07-29 — 「起源差异」（对话内生 vs 外部策展）落地实现：Chat 达 2 轮后自动从对话抽取原子事实写入 `long_term_memories`（`memory_type=FACT`、`conversation_id` 关联、`meta.source=conversation`）。Memory 不再仅手动录入，与 Knowledge（外部上传文档-分块）的起源分野真正可观察。
- **更新**: 2026-07-30 - C4-A BM25 spike：词法腿当前为 pg_trgm similarity（模糊三元组，非真 BM25）。spike 验证 ParadeDB pg_search v0.12.0 + chinese_compatible tokenizer 可与 pgvector 0.8.2 共存于 PG16（自建镜像 codeaware/pgvector-pgsearch:pg16-v0.12.0）。BM25 索引 + INSERT + 中文/英文查询 + EXPLAIN 均通过；v0.25.0 因 INSERT 回归被拒。C4 成功后词法腿默认切 BM25，pg_trgm 保留为 RAG_LEXICAL_BACKEND=pg_trgm 回退。Memory 纯向量策略不受影响。
- **C3 基线指标（35 golden cases，真实 bge-m3）**: pg_trgm R@5=0.543 MRR@10=0.529（中文精确=0.0，语义改写=0.0，稀有标识符=1.0）; vector R@5=0.957 MRR@10=0.920; fused R@5=0.957 MRR@10=0.906（pg_trgm 噪声略拖累 MRR）。基线产物见 tests/eval/artifacts/baseline_c3_pg_trgm.json。C4 BM25 目标：词法腿 R@5 大幅提升、fused MRR 不再被拖累。
- **关联术语**: Long-term Memory, Knowledge Document, VectorRecallService
- **更新**: 2026-07-31 - C4 BM25 完成。词法腿从 pg_trgm 升级为 ParadeDB pg_search v0.12.0 BM25（default tokenizer）。C3/C4 三路对照门禁全部通过：C4 fused R@5=0.957≥0.957，稀有标识符 MRR 1.000>0.938，语义改写 R@5 0.786≥0.786。中文精确类 R@5 从 0.0 升到 0.25，fused MRR@10 从 0.906 升到 0.934（摆脱 pg_trgm 噪声）。LexicalRecallPort 接口+pg_trgm 回退/BM25 默认，rag_lexical_backend=pg_trgm 保留。

## 背景

Java 版 `LongTermMemoryManager` 与 `RagService` 各自维护一套"文本 -> bge-m3 向量化 -> pgvector 存储(UUID 反查) -> 语义召回"逻辑,且 `long_term_memories` 与 `knowledge_documents` 两表结构高度相似(content + embedding + 语义召回),引发"是否重复设计"的质疑。

梳理出 4 个真实差异:① 分块(Knowledge 分块、Memory 原子)② 作用域(session vs project)③ 检索方式(纯向量 vs 混合)④ 录入形态(小知识 vs 文档)。

## 决策

1. **保留两张表**。本质区别是**聚合结构不同**:Long-term Memory 是**原子事实**(1 content = 1 行,无分块);Knowledge Document 是**文档-分块父子结构**(1 文档 -> N chunk)。此结构差异足以支撑分表;作用域 / 检索方式 / 录入形态均为字段或策略级差异,不构成分表理由。

2. **共享向量召回基建**:Python 版抽取一个 `VectorRecallService`(embed + 内联 pgvector 存储 + cosine 检索),Memory 与 Knowledge 各自为薄表并调用它。检索策略(纯向量 / 混合 BM25+向量)作为该服务的**参数/策略**,而非各自复制一套 embed+store+recall。Java 版两处复制此逻辑(见 [LongTermMemoryManager.java:50](../../../ai-center-ai/src/main/java/com/aicenter/ai/memory/LongTermMemoryManager.java#L50) / [RagService.java:57](../../../ai-center-ai/src/main/java/com/aicenter/ai/service/RagService.java#L57)),Python 版不再复制。

3. **两表均内联 pgvector `Vector(1024)`**,消除 Java 版 UUID 反向索引(关联 ADR-0002)。

## 结果

- 两表(`long_term_memories` / `knowledge_documents`)+ 一个共享 `VectorRecallService`。
- Memory:原子、per-session 来源、默认纯向量召回(事实太短,BM25 无意义--此为策略默认,可在服务参数调整)。
- Knowledge:分块、per-project、混合召回。
- **命名清理**:Java 版 `MemoryType.KNOWLEDGE` 枚举值与 `KnowledgeDocument` 概念冲突,Python 版重命名枚举(如 `FACT` / `REFERENCE`),消除歧义。
- **遗留子决策**:检索策略按实体可配,"Memory 是否也需关键词检索"留待验证(默认否)。

## 待办(本 ADR 衍生)

> ⚠️ Q4 断言 Knowledge 有"文档->分块父子结构",但当前 `knowledge_documents` schema **无父 Document 实体**--每行就是一个 chunk,`title`/`content` 在同文档的所有 chunk 行里重复,父子关系是隐式的、靠 title 字符串凑的。这与 ADR-0001 的核心论断(结构差异)相矛盾。是否补一个 `documents` 父实体?见下一轮 grilling(Chunk 术语)。