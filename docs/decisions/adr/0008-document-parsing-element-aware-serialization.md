# ADR-0008: 文档解析元素感知序列化（C5）

- **状态**: Accepted
- **日期**: 2026-08-03
- **关联术语**: Knowledge Document, Chunk, SemanticChunker
- **上游**: 兑现 [ADR-0002](0002-knowledge-document-parent-child.md) 父子建模与 C1-C 阶段卡“元素感知分块”的原始意图

## 背景

C1-C 引入 `unstructured` 作为文档解析库，初衷是“先理解、后分割”：`partition()` 把
原始文档解析成带语义标签的 Elements（Title / NarrativeText / ListItem / Table …），
`chunk_by_title()` 在元素级别智能组合，而非对纯文本硬切。

但实际链路只用了它一半：

```text
document_parser.parse()  -> partition() -> Elements
                                       -> str(e.text)  # 只取文本，丢弃元素类型
                                       -> "\n\n".join  # 压成纯文本
semantic_chunker.chunk()  -> partition_md(纯文本)  # 重新解析，结构已丢失
                                       -> chunk_by_title
```

对真实 Markdown，`#` 标题存在于文本层，二次 `partition_md` 仍能识别 Title，分块按章节
切；对 DOCX / HTML / PDF，`partition()` 解析时识别到的标题层级在 `str(e.text)` 处被压平，
`chunk_by_title` 的“章节感知”空转，退化为 500 字定长滑窗。当前用例 100% 是 Markdown，
所以实际检索未受影响，但这是“选了 unstructured 却没用全”的设计意图缺口。

## 决策

### 1. str 契约 + 元素类型感知序列化（方案 A）

`DocumentParserService.parse()` 仍返回 `str`（冻结契约，`knowledge.py`、`RagService`、
两个 monkeypatch 测试零改动），但在内部把元素类型显式编回文本：

```python
@staticmethod
def _serialize(elements) -> str:
    parts = []
    for e in elements:
        text = (getattr(e, "text", None) or "").strip()
        if not text:
            continue
        if e.category == "Title":
            parts.append(f"# {text}")      # Title -> markdown 一级标题
        elif e.category == "ListItem":
            parts.append(f"- {text}")      # ListItem -> markdown 列表
        else:
            parts.append(text)             # NarrativeText / Table / PageBreak 原样
    return "\n\n".join(parts)
```

`SemanticChunker` 不动（继续 `partition_md` + `chunk_by_title`）。`partition_md("# 缓存")`
返回 `Title('缓存')`（已剥离 `#`），serializer 补回 `# ` 后 chunker 二次解析恰好还原为
正确 Title，**无双重前缀**。

不采用“元素直通”方案（`parse()` 返回 `list[Element]`、chunker 消费元素）：波及
`knowledge.py` 用法、`RagService.upload_document` 签名、全部 `SemanticChunker()` 构造点、
两个 monkeypatch 契约；而 `Document.content` 列存储侧仍要序列化，收益被抵消。

### 2. PDF 文字版：pypdf 文本层探针 + unstructured fast

PDF 从 pypdf 纯文本层升级为 unstructured `strategy="fast"`（pdfminer 布局启发式元素）：

```python
def _parse_pdf_sync(self, file_content: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_content))
    if not any((page.extract_text() or "").strip() for page in reader.pages):
        return ""                              # 扫描版 -> 路由层新错误码
    elements = partition(file=io.BytesIO(file_content),
                         content_type="application/pdf", strategy="fast")
    return self._serialize(elements)
```

pypdf 保留为**文本层探针**：损坏 PDF -> `PdfReadError` -> `FILE_PARSE_FAILED`（行为不变）；
合法但无文本层 -> 返回 `""` -> 路由层 `KNOWLEDGE_PDF_NO_TEXT_LAYER`。扫描版零 pdfminer
成本，且错误语义精确区分“损坏”与“扫描版”。

### 3. 扫描版显式拒绝，不引 OCR

无文本层 PDF 返回 `""`，路由层映射为新错误码 `KNOWLEDGE_PDF_NO_TEXT_LAYER`，不静默产出空
知识、不引入 tesseract / 视觉模型。与 `document_parser.py` 既定约束（“不启用 OCR、视觉
模型或后台 Worker”）一致。

### 4. 依赖最小子集

不安装 `unstructured[pdf]`（带入 `unstructured-inference` + `google-cloud-vision` 视觉
模型，违反约束）。仅 pin 最小四件套：`pdfminer-six`（fast 提取）、`pi-heif`（pdf.py 顶层
导入）、`pdf2image`（过 `_PartitionerLoader` importable 检查，fast 路径不调用）、
`pillow`（pdf.py 顶层导入）。fast 路径不需要系统 poppler。

## 结果

- DOCX / HTML 标题层级与列表结构能穿到分块层，不再退化为定长滑窗；PDF 走布局启发式元素。
- str 契约冻结，生产调用链与 monkeypatch 测试零改动。
- 扫描版 PDF 显式失败，fail-closed，不留空知识。
- 检索质量门禁：自包含 before/after 对比（新 `tests/eval/test_c5_chunking_quality.py`），
  不修改共享 `golden_retrieval.py`，避免扰动 C3/C4 的 35 条基线。

## 遗留

- **`#` 转义残余风险**：NarrativeText 以 `#` 开头（如 `#hashtag`、代码片段）会被 chunker
  二次 `partition_md` 误判为标题。该风险与“用户直接上传 md”的现状完全同构，不引入新错误
  类别；只给 Title 元素加前缀即最小面。
- **标题层级扁平化**：DOCX 各级 Heading、PDF 大标题在 unstructured 中均为 `Title` category
  （无级别信息），serializer 统一编为一级 `#`。`chunk_by_title` 切分只依赖边界、不依赖层级，
  不影响分块正确性。
- **PDF 启发式标题漏切**：fast 策略的 `is_possible_title`（≤12 词、无结尾标点）会把长章节
  标题落成 NarrativeText，失去分块边界。这是 unstructured 自身文本块启发式的局限，记入 C5
  限制；需要版面模型（hi_res）才能改善，但 hi_res 引入视觉模型，超出 C5 边界。
- **`test_bm25_upsert_index_consistency` flaky**：C4 遗留的 Tantivy 未提交可见性问题，
  C5 evidence 不依赖它，index-lifecycle 改用 bm25_ready 的 create/drop + 手动 DDL probe 作证。
