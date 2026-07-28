# ADR-0006: Record 是审计日志 + CR/UT 记录合并

- **状态**: Accepted
- **日期**: 2026-07-28
- **关联术语**: Code Review Record / Unit Test Record

## 背景

- **定性**:`code_review_records` / `unit_test_records` 均 append-only--[CodeReviewService.review](../ai-center-ai/src/main/java/com/aicenter/ai/service/CodeReviewService.java#L85) insert 后永不更新,只有 `listRecords`/`getRecordDetail` 读;无"重新评审/标记已解决/状态流转"任何生命周期行为。→ **审计日志(AI 操作事件流水),非领域实体**。
- **合并依据**:两表**无结构/基数差异**--均原子一行、公共列完全相同(id, project_name, file_path, source_code, prompt_template_id, ai_model, created_at),仅 `result` 负载不同(且都已是 TEXT:review_result 是 JSON、test_code 是代码串)。
- 套用 [ADR-0001](0001-memory-vs-knowledge-two-tables-shared-recall.md) 原则:**结构差异才撑得起分表;负载/内容差异只是字段级。** 此处无结构差异 → 合并。

## 决策

1. **Record = 审计日志**,不可变,无生命周期方法。
2. **合并** `code_review_records` + `unit_test_records` 为一张 `ai_operation_records`:
   - `(id, type[CODE_REVIEW/UNIT_TEST], project_name, file_path, source_code, result[TEXT/JSON], prompt_template_id, ai_model, metadata[JSON], created_at)`
   - type 特有字段进 `metadata` JSON:CR 的 4 个 count、UT 的 test_framework。避免稀疏列。
   - `result` 多态(CR 的评审 JSON / UT 的测试代码),本就是 TEXT。
3. `/api/code-review/records`、`/api/unit-test/records` 变为同一表按 `type` 过滤的视图。
4. `ai_readme_documents` **不并入**(按 section 存的生成文档,形状不同),单独留。

## 结果

- 两表合一,与 ADR-0001 分表原则**对称一致**(有结构差异→分[ADR-0001];无结构差异→合[本 ADR])。
- type 特有字段归入 metadata JSON,表结构干净。
- **未来若 CR record 获得生命周期**(如 issue 解决工作流),再 reconsider 拆分--YAGNI,现在不拆。
