# ADR-0002: Knowledge Document 父子建模 (documents + knowledge_chunks)

- **状态**: Accepted
- **日期**: 2026-07-28
- **关联术语**: Knowledge Document, Chunk
- **上游**: 细化 [ADR-0001](0001-memory-vs-knowledge-two-tables-shared-recall.md) 的"待办"

## 背景

ADR-0001 用"文档->分块父子聚合结构"作为 Knowledge 与 Memory 分表的本质理由。但 Java 版 `knowledge_documents` 是**扁平 chunk 表**,无父实体,且由此产生三个功能缺陷:

1. **全文冗余**:[RagService.java:49](../../../ai-center-ai/src/main/java/com/aicenter/ai/service/RagService.java#L49) 每个 chunk 行都 `.setContent(content)` 存完整正文,一篇文档切 N 块就存 N 份全文。
2. **删除粒度错位**:[RagService.java:99](../../../ai-center-ai/src/main/java/com/aicenter/ai/service/RagService.java#L99) `deleteDocument(id)` 实为删一行 chunk,`DELETE /api/knowledge/{id}` 删不掉整篇文档。
3. **无文档身份**:重复上传直接再插 N 行,无去重/覆盖语义。

结论:"父子结构"在论断里有、在 schema 里没有,自相矛盾。

## 决策

把父子聚合结构**显式建模**,Python 版 `knowledge_documents` 单表拆为两张:

- **`documents`(父表)**:`id, title, source_type, project_name, content`(全文,只存一次), `created_at`
- **`knowledge_chunks`(子表)**:`id, document_id`(FK), `chunk_index, chunk_content, embedding`(内联 `Vector(1024)`), `created_at`
- 关系:1 document -> N chunks,父删则子级联删。
- `VectorRecallService`(ADR-0001)作用在 `knowledge_chunks.embedding` 上(只对 chunk 向量化,不对全文)。

## 结果

- 三个缺陷全部消除:全文存一次;删除/更新/去重均以**文档身份**为单位;重复上传按 `title+project` upsert(替换其 chunks)。
- ADR-0001 的"结构"论断现与 schema 一致,Knowledge Document 术语转 🟢。
- Java 单表 `knowledge_documents` -> Python 两表(`documents` + `knowledge_chunks`)。**数据迁移时需做一次归并**(按 title 聚合 chunk 行,提取父记录)。
- Memory 不受影响(原子,无父子,ADR-0001)。

## 遗留

- 文档**不做版本化**(上传即 upsert 替换),区别于 PromptTemplate 的版本化(见后续 grilling)。若未来需文档版本,再加 `version` 列,非现在。
