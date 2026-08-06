# 检索与查询质量演进报告

> 本文档追踪 CodeAware 项目从 C3 基线到当前版本的检索质量与查询质量完整演进历程，包含每个阶段的优化动机、方法、数据结果和关键决策。
> 评估基线：35 条 golden 查询用例，15 篇 fixture 文档，真实 bge-m3 embedding（Ollama 本地 Metal GPU，128ms/次），真实 DeepSeek v4-flash。

---

## 目录

1. [C3 基线：pg_trgm + 纯向量](#1-c3-基线pg_trgm--纯向量)
2. [C4：BM25 词法检索升级](#2-c4bm25-词法检索升级)
3. [jieba 中文分词](#3-jieba-中文分词)
4. [top_k 敏感性分析](#4-top_k-敏感性分析)
5. [LangGraph 智能路由 + 自我纠错](#5-langgraph-智能路由--自我纠错)
6. [RAGAS 生成层质量评估](#6-ragas-生成层质量评估)
7. [全阶段对比总表](#7-全阶段对比总表)
8. [关键决策一览](#8-关键决策一览)

---

## 1. C3 基线：pg_trgm + 纯向量

### 背景

项目初期，词法检索使用 PostgreSQL 内置的 `pg_trgm`（三元组模糊匹配），向量检索使用 `pgvector` HNSW cosine 索引。两条腿各自独立，最终通过 RRF（Reciprocal Rank Fusion）融合。

### 数据

| 检索腿 | R@5 | MRR@10 |
|---|---|---|
| **pg_trgm 词法** | **0.543** | **0.529** |
| 纯向量（bge-m3） | 0.957 | 0.920 |
| **fused 混合** | **0.957** | **0.906** |

### 按类别（pg_trgm 词法腿）

| 类别 | n | R@5 | MRR | 说明 |
|---|---|---|---|---|
| chinese_exact | 8 | **0.000** | 0.000 | 中文精确查询完全不可用 |
| english_natural | 7 | 0.857 | 0.857 | 英文自然语言尚可 |
| rare_identifier | 8 | 1.000 | 0.938 | 代码标识符可精确匹配 |
| semantic_paraphrase | 7 | **0.000** | 0.000 | 语义改写完全不可用 |
| negative | 5 | 1.000 | 1.000 | 负例 1.0（无期望文档，不计分） |

### 诊断

- **pg_trgm 对中文基本无效**：三元组匹配不适合 CJK 字符，chinese_exact 和 semantic_paraphrase 全部 0.0
- **向量腿单独已很强**（R@5=0.957）——但混合 fused 反而比纯向量略低（0.957→0.906），说明 pg_trgm 词法腿在 RRF 中引入了噪声
- **混合检索退化**：fused R@5=0.957 与纯向量持平，但 MRR 从 0.920 降到 0.906——词法腿的低质量排序拖累了首位命中

### 延迟

| 组件 | 延迟 |
|---|---|
| pg_trgm 词法 | 35ms |
| 纯向量（含 Ollama CPU embedding） | 6,026ms |
| fused 混合 | 6,581ms |

> **结论**：向量腿是当前检索质量的主力，词法腿（pg_trgm）不贡献正向收益，反而引入噪声。**词法检索需要替换。**

---

## 2. C4：BM25 词法检索升级

### 背景

用 ParadeDB `pg_search` BM25 替代 `pg_trgm`。BM25 是经典概率检索模型，对中文的默认 tokenizer 有一定支持。

### 改进过程

| 阶段 | 词法 R@5 | 混合 R@5 | 混合 MRR |
|---|---|---|---|
| C3 pg_trgm | 0.543 | 0.957 | 0.906 |
| C4 BM25（default tokenizer） | 0.600 | 0.957 | 0.934 |
| C4 BM25 + jieba 分词 | 0.943 | 0.986 | 0.938 |

### 按类别（BM25 default 词法腿）

| 类别 | n | R@5 | 与 pg_trgm 对比 |
|---|---|---|---|
| chinese_exact | 8 | 0.250 | 0.000 → **0.250**（改善但不够） |
| english_natural | 7 | 0.857 | 持平 |
| rare_identifier | 8 | 1.000 | 持平 |
| semantic_paraphrase | 7 | 0.000 | 0.000（无改善） |
| negative | 5 | 1.000 | 1.000 |

### 分析与决策

- BM25 default tokenizer 对中文精确查询有改善（0.000→0.250），但 R@5=0.250 仍远不能满足需求
- semantic_paraphrase 类别（语义改写）仍为 0.000——这是词法检索的固有局限，需要依赖向量腿
- 混合 fused 的 MRR 从 0.906 提升到 0.934（+0.028），因为 BM25 的噪声比 pg_trgm 低
- **核心瓶颈明确**：中文分词是词法检索的短板，需要引入 jieba

### 延迟

| 组件 | 延迟 |
|---|---|
| BM25 词法 | 90ms（比 pg_trgm 35ms 慢，但可接受） |
| fused 混合 | 5,876ms（瓶颈仍在向量 embedding） |

---

## 3. jieba 中文分词

### 背景

BM25 的 default tokenizer 对中文支持不足。引入 jieba 分词器，在文档入库时生成 `segmented` 列（jieba 分词结果），BM25 索引建在 `segmented` 列上。

### 对比：default tokenizer vs jieba 分词

| 指标 | BM25 default（content 列） | BM25 + jieba（segmented 列） |
|---|---|---|
| **词法 R@5** | 0.600 | **0.943** |
| 词法 MRR | 0.571 | 0.852 |
| 中文精确 chinese_exact R@5 | 0.250 | **1.000** |
| 英文 natural R@5 | 0.857 | 0.857（持平） |
| 语义改写 semantic_paraphrase R@5 | 0.000 | **0.857** |
| 稀有标识符 R@5 | 1.000 | 1.000（持平） |

### 质量门禁（全部通过）

| 门禁 | 结果 |
|---|---|
| 中文精确 chinese_exact R@5 有改善或持平 | ✅ 0.250 → 1.000 |
| 中文精确 R@5 ≥ 0.5 | ✅ 1.000 |
| 稀有标识符 MRR 不降级 | ✅ 持平 1.000 |
| BM25 整体 R@5 不降级 | ✅ 0.600 → 0.943 |

### 延迟

jieba 分词仅在入库时执行一次，查询时无额外开销。BM25 查询延迟 ~144ms（default 90ms vs jieba 144ms，略有增加）。

### 最终混合检索（BM25+jieba + vector RRF）

| 类别 | n | R@5 | MRR@10 |
|---|---|---|---|
| **chinese_exact** | 8 | **1.000** | 0.812 |
| **english_natural** | 7 | **1.000** | 1.000 |
| **rare_identifier** | 8 | **1.000** | 1.000 |
| **semantic_paraphrase** | 7 | **0.929** | 0.905 |
| **negative** | 5 | **1.000** | 1.000 |
| **总体** | 35 | **0.986** | **0.938** |

> **结论**：jieba 让中文 BM25 从"残废"变"可用"，中文精确查询从 0.25 跳到 1.000，语义改写也从 0.000 跳到 0.857。这是全项目投入产出比最高的优化。

---

## 4. top_k 敏感性分析

### 背景

检索层 `top_k` 决定最终注入 prompt 的文档块数量。此前是经验值 k=5，需要数据验证。

### 方法

扫描 `top_k ∈ {3, 5, 8, 10, 15}`，35 条 golden cases，生产路径 `HybridRetriever.search_by_vector`。

### 数据

| top_k | R@5 | MRR@10 | avg 实际条数 | 估算 prompt token |
|---|---|---|---|---|
| **3** | 0.986 | 0.938 | 3.0 | 900 |
| **5（当前）** | **0.986** | **0.938** | 5.0 | 1,500 |
| 8 | 0.986 | 0.938 | 8.0 | 2,400 |
| 10 | 0.986 | 0.910 | 10.0 | 3,000 |
| 15 | 0.986 | 0.952 | 15.0 | 4,500 |

### 决策：保持 k=5

1. **R@5 在 k=3 已饱和（0.986）**——检索质量不是 top_k 限制的，前 3 条已含正确答案
2. **MRR 无单调提升**——3/5/8 都是 0.938，波动是 35 条样本噪声
3. **token 成本线性增长**——900→4,500 token，k=8+ 是纯浪费
4. **为什么不降到 3**：R@5 虽饱和，但 3 条没有安全边际。真实查询比 golden 更难，MRR 波动说明 3 和 5 可能互换——省 600 token 不值得冒险

---

## 5. LangGraph 智能路由 + 自我纠错

### 背景

ADR-0015 引入 LangGraph StateGraph 编排检索层：
- **智能路由**：DeepSeek 判断用户问题是否需要检索（retrieve/direct）
- **自我纠错**：检索结果不理想时自动改写查询重试

### 路由准确率

| 类别 | 数量 | 预期 | 实际 | 结果 |
|---|---|---|---|---|
| 技术/项目问题 → retrieve | 30 | retrieve | 30 retrieve | ✅ |
| negative 技术问题（Python GIL/K8s）→ retrieve | 2 | retrieve | 2 retrieve | ✅ |
| negative 常识（天气/美食/投资）→ direct | 3 | direct | 3 direct | ✅ |
| **总体** | **35** | — | — | **1.000** |

**修复说明**：此前 eval 报告 0.914 并非真实路由成绩——`with_structured_output(method="json_mode")` 要求 prompt 含 "json" 字眼，原 prompt 缺失导致 DeepSeek 每次都返回 400 错误，降级 retrieve。修复 prompt 后真实决策生效，35/35 全对。

### 自我纠错统计

| 指标 | 修复前（分数差阈值，已废弃） | 修复后（match_type 检测） |
|---|---|---|
| 重试触发率 | 0.906（29/32） | **0.0**（0/32） |
| 平均重试次数 | 1.812 | 0.0 |
| 重试后 docs | 全部 = 5 | 全部 = 5（首检即满意） |

**说明**：修复后 32 条检索查询全部 `retries=0`、`docs_count=5`——命中查询评估满意、不触发重试，符合 match_type 检测的设计预期。弱检索重试路径由 mock 单元测试覆盖。

### 路由收益

- **direct 路径**：3 条常识问题跳过检索，省去 ~5.9s 检索延迟
- **retrieve 路径**：即使失败/不确定也降级 retrieve（宁可多检索不漏），零漏检风险

---

## 6. RAGAS 生成层质量评估

### 背景

检索准 ≠ 答案好。需要评估生成层：回答有没有编造（Faithfulness）、切不切题（Answer Relevancy）。

### 方法

自实现 RAGAS 指标（不引入 ragas 库依赖），用 DeepSeek 做 judge，bge-m3 做 embedding。

| 指标 | 定义 | 依赖 ground truth |
|---|---|---|
| Faithfulness | 回答的主张中被检索 context 支撑的比例（0-1） | ❌ 无 |
| Answer Relevancy | 反向生成问题与原问题的 embedding 相似度（0-1） | ❌ 无 |

### 结果

| 指标 | mean | n |
|---|---|---|
| **Faithfulness** | **0.939** | 31（4 条 judge 解析失败） |
| **Answer Relevancy** | **0.812** | 35 |

### 按类别

| 类别 | n | faithfulness | relevancy |
|---|---|---|---|
| chinese_exact | 8 | 0.929 | 0.870 |
| english_natural | 7 | 0.967 | 0.813 |
| rare_identifier | 8 | 0.975 | 0.824 |
| semantic_paraphrase | 7 | **1.000** | 0.875 |
| **negative** | 5 | **0.667** | **0.610** |

### 解读

1. **整体健康**：Faithfulness 0.939——回答基本被检索 context 支撑，编造少
2. **negative 类最弱**（0.667/0.610）：无关查询检索不到相关 context，模型硬答导致主张无支撑、回答跑题——这是 RAG 对无关查询的已知弱项
3. **Answer Relevancy 0.812**：整体切题，语义改写类最高（0.875，改写查询命中更准）
4. **4 条 judge 解析失败**：回答过短或负例导致 judge JSON 不完整，不影响整体趋势

---

## 7. 全阶段对比总表

### 检索质量

| 阶段 | 词法方案 | 混合 R@5 | 混合 MRR | 中文精确 R@5 | 语义改写 R@5 |
|---|---|---|---|---|---|
| C3 基线 | pg_trgm | 0.957 | 0.906 | 0.000 | 0.000 |
| C4 BM25 | BM25 default | 0.957 | 0.934 | 0.250 | 0.000 |
| C4 + jieba | BM25 + jieba | **0.986** | **0.938** | **1.000** | **0.929** |
| + LangGraph 路由 | 同上 | 1.000（路由准确率） | — | — | — |
| + Ollama Metal GPU | 同上 | 同上 | 同上 | 同上 | 同上 |

### 延迟（2026-08-06 更新）

| 阶段 | 组件 | 延迟 | 提升 |
|---|---|---|---|
| 异步任务（Celery） | 文档上传（6 chunks） | 35.1s → **1.0s** | 35x |
| 异步任务（Celery） | Chat 完成事件 | 14s 阻塞 → **1ms** | 立即返回 |
| Ollama Metal GPU | 单次 embedding | 5,800ms → **128ms** | 45x |
| 检索总延迟 | BM25+vector+RRF | 6,000ms → **~420ms** | 14x |

### 生成质量

| 指标 | 值 |
|---|---|
| Faithfulness | 0.939 |
| Answer Relevancy | 0.812 |

### 延迟

| 组件 | 延迟 | 瓶颈 |
|---|---|---|
| BM25 词法检索 | ~90ms | — |
| 向量 embedding（Ollama Metal GPU） | **~128ms** | — |
| 向量 embedding（Docker CPU，历史） | ~5,800ms | 🔴 **原主要瓶颈，已消除** |
| pgvector HNSW 查询 | ~200ms | — |
| RRF 融合 | <1ms | — |
| **单次检索总延迟** | **~420ms** | 较之前 ~6,000ms 提升 14x |
| Router 判断 | ~300ms | LLM 单次调用 |
| Chat 生成（首 token） | ~1,000ms | DeepSeek API |

### 成本

| 组件 | 成本 |
|---|---|
| 向量 embedding | 免费（本地 Ollama CPU） |
| BM25 检索 | 免费（本地 PostgreSQL） |
| Router 判断 | ~¥0.0003/次（DeepSeek API） |
| Chat 生成 | ~¥0.003/次（DeepSeek API） |
| 记忆抽取 | ~¥0.001/次（DeepSeek API） |

---

## 8. 关键决策一览

| 决策 | 选项 | 选择 | 理由 |
|---|---|---|---|
| 词法检索引擎 | pg_trgm / BM25 / pg_trgm 回退 | **ParadeDB BM25 + jieba** | pg_trgm 中文几乎不可用（R@5=0.000），BM25+jieba 中文 R@5=1.000 |
| 中文分词 | 不处理 / jieba / 其他 | **jieba** | 投入最小，收益最大（中文 BM25 R@5 0.25→1.000） |
| top_k | 3/5/8/10/15 | **5** | R@5 在 k=3 已饱和，但 3 条无安全边际；5 是质量+成本+冗余的平衡 |
| Reranker | 加 / 不加 | **暂缓**（ADR-0009） | MRR 0.934 已高，门禁收益仅 +0.01，torch 拖依赖 |
| 意图识别 | 加 / 不加 | **不做** | 90% 查询是知识问题，加分类引入漏检风险 |
| 检索增强 | LangGraph / 固定流程 | **LangGraph StateGraph**（ADR-0015） | 智能路由省延迟（direct 省 ~5.9s），自我纠错防弱检索 |
| 评估方式 | ragas 库 / 自实现 | **自实现** | 不堆依赖，逻辑完全可控 |

---

## 附录：相关文档

| 文档 | 内容 |
|---|---|
| [ADR-0008](../decisions/adr/0008-document-parsing-element-aware-serialization.md) | 元素感知分块 |
| [ADR-0009](../decisions/adr/0009-reranker-deferred.md) | Reranker 暂缓决策 |
| [ADR-0011](../decisions/adr/0011-jieba-chinese-bm25-segmentation.md) | jieba 中文分词 |
| [ADR-0012](../decisions/adr/0012-topk-sensitivity-keep-5.md) | top_k 敏感性分析 |
| [ADR-0015](../decisions/adr/0015-langgraph-retrieval-enhancement.md) | LangGraph 检索增强 |
| [topk-sensitivity.md](topk-sensitivity.md) | top_k 敏感性详细报告 |
| [ragas-eval.md](ragas-eval.md) | RAGAS 生成质量评估 |
| [rag-graph-eval.md](rag-graph-eval.md) | LangGraph 路由+纠错评估 |
| 原始数据：`codeaware-py/tests/eval/artifacts/` | 各阶段 JSON 评估数据 |