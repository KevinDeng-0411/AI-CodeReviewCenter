# ADR-0011: jieba 中文分词优化 BM25 检索

**状态**: 已实施
**日期**: 2026-08-05
**决策者**: Kevin

## 背景

ParadeDB BM25 `default` tokenizer 不拆连续中文字符。例如"缓存雪崩大量key同时失效方案"被当作单个 token，查询"缓存雪崩"无法匹配。BM25 腿对中文基本残废，全靠向量腿（R@5=1.000）兜底。

额外发现：C4 基线评测用的是 `chinese_compatible` tokenizer，但生产迁移 0006 用的是 `default`——已公布的评测数据不反映生产实际行为。

## 方案评估

| 方案 | 原理 | 中文效果 | 稀有标识符 | 权衡 |
|---|---|---|---|---|
| `chinese_compatible` tokenizer | 字符 n-gram（`缓` `存` `雪` `崩`） | BM25 R@5=0.250 | MRR 可能降到 0.812 | ParadeDB 内置，但字符级切分不如词典语义 |
| **jieba 应用层预处理** | 词典分词（`缓存` `雪崩` `大量`）→ 空格连接 → `default` tokenizer 自然切分 | 预期 R@5≥0.500 | 不变（纯英文/数字原样通过） | 纯 Python 零 C 扩展，改动面小 |
| 直接改 `chunk_content` | jieba 分词后取代原文 | 同上 | 不变 | 污染向量嵌入语义 |

## 决策

选择 **jieba 应用层预处理**——新列 `chunk_content_segmented` 存分词文本，BM25 索引建其上。

- 新列：向量嵌入仍读 `chunk_content`（原文），不受影响
- 新列不为空：迁移 0009 回填 COPY 原文；后续可 offline jieba 重填
- ParadeDB 每表仅一个 BM25 索引：迁移 0010 删旧 `ix_kc_chunk_content_bm25` 换新 `ix_kc_chunk_content_segmented_bm25`
- 查询时：含 CJK 字符时 jieba 分词后执行 `@@@` 查询
- 回退：pg_trgm 索引 `ix_kc_chunk_content_trgm` 仍在，改 `RAG_LEXICAL_BACKEND=pg_trgm` 即回退

## 改动范围

| 文件 | 改动 |
|---|---|
| `pyproject.toml` | `+jieba>=0.42` |
| `app/ai/rag/chinese_segmenter.py` | 新建：`segment_chinese()` + `_has_cjk()` |
| `app/models/knowledge_chunk.py` | `+chunk_content_segmented` 列 |
| `app/ai/services/rag.py` | `upload_document` 写入 `chunk_content_segmented` |
| `app/ai/rag/lexical_recall.py` | `Bm25LexicalRecall.search` 含 CJK 时 jieba 分词查询 |
| `alembic/versions/0009*.py` | 加列 + COPY 回填 |
| `alembic/versions/0010*.py` | 删旧 BM25 + 建新 BM25 on segmented |

## 评测门禁

- `bm25` on `chunk_content_segmented` 中文精确 R@5 ≥ 0.500
- fused MRR 不降（≥ 0.934）
- rare_identifier MRR 不降（1.000）
- 评测脚本：`scripts/eval_jieba_quick.py`

## 不做

- 不换 `chinese_compatible`（字符 n-gram，语义弱于词典分词）
- 不做 jieba 自定义词典（通用词典先跑，不够再加）
- 不删 `chunk_content` 上的 pg_trgm GIN 索引（保留回退）
