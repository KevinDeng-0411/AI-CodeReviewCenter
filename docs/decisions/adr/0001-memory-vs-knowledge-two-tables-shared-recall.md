# ADR-0001: Long-term Memory 与 Knowledge Document 分表 + 共享向量召回基建

- **状态**: Accepted
- **日期**: 2026-07-28
- **关联术语**: Long-term Memory, Knowledge Document, VectorRecallService

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
