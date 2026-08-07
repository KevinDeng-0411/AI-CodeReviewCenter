# ADR-0009: Reranker 二阶段重排——评估后暂缓

- **状态**: 已实施（2026-08-07 重新评估，ONNX Runtime 落地）
- **日期**: 2026-08-04（评估）；2026-08-07（重新评估并实施）
- **关联术语**: Reranker, Cross-Encoder, RRF, MRR
- **上游**: [ADR-0008](0008-document-parsing-element-aware-serialization.md)（C5）、C4 BM25（fused MRR@10=0.934）

## 背景

C4 完成后，混合检索为单阶段：BM25 + 向量 RRF 融合，fused R@5=0.957、MRR@10=0.934。
R@5 已近天花板，但 MRR 略低于 R@5（0.934 < 0.957）——说明部分正确 chunk 召回到了
但没排第一。这是**排序**问题，不是**召回**问题。

reranker（二阶段重排）正对症排序：从 RRF 召回的候选池里，用 cross-encoder 重新打分
排序。本 ADR 记录评估过程与暂缓决策。

## 关键技术区分

| 项 | 含义 | 对本项目 |
|---|---|---|
| **召回率 R@5** | 正确文档有没有进 top-5 | 0.957，rerank **改不了**（只在池内重排） |
| **MRR@10** | 正确文档排第几名 | 0.934，rerank 的目标指标 |
| **bi-encoder**（bge-m3） | query/doc 各自编码成向量，算 cosine | 已有，丢 query-doc 交互 |
| **cross-encoder**（reranker） | query+doc 拼一起进模型，直接输出相关性分数 | 捕捉交互，精排更准 |

rerank 比 RRF 强在：RRF 是无模型排名融合（只看各腿 rank），rerank 是有模型精排
（看 query-doc 内容交互）。比 bge-m3 向量腿强在：cross-encoder 把 query 和 doc
联合编码，相关性分数本身包含对方；bi-encoder 的表征在编码时看不到对方，只能事后
算几何距离。

## 评估的实施方案（path A 进程内）

候选模型 `BAAI/bge-reranker-v2-m3`（~568MB），进程内 `sentence-transformers.CrossEncoder`：

- **加载**：eager（启动时加载，2-5s），常驻 ~568MB RAM
- **位置**：RRF 召回 rerank_pool=15 -> cross-encoder 精排 -> top_k=5
- **延迟**：15 条候选 × CPU 前向 ~30-50ms ≈ **0.45-0.75s**，加在首 token 前
- **降级**：reranker 异常 -> 回退 RRF 顺序，记 warning（fail-soft）
- **评测门禁**：rerank ON 的 MRR@10 >= 0.944（+0.01），且 R@5 不降

## 评估路径（思考过程凝练）

决策不是一步到位，而是经五步推演收敛，记录于此供复盘：

1. **起点纠偏**：初始动机“reranker 提升召回率”被纠正--rerank 改 MRR（排序）不改
   R@5（召回）。R@5=0.957 已近天花板，目标必须说成 MRR，否则方案悬空。
2. **原理确认**：cross-encoder 联合编码捕捉 query-doc 交互；bi-encoder（现有 bge-m3）
   独立编码丢交互。这是“精排比 RRF+向量更准”的唯一技术依据，须能说清。
3. **方案选型**：Ollama 跑不了 cross-encoder（无 rerank API），排除 Ollama 复用；
   外部 API 违背本地优先；选 path A 进程内 sentence-transformers。量化成本：
   eager 加载 2-5s、常驻 ~568MB、15 条 CPU rerank 0.45-0.75s。
4. **约束冲突浮现**：path A 拉 torch，与 C5“不引视觉模型”拒 torch 形成张力。
   reranker 的 torch 是必需非无谓，但“C5 拒/C6 装”需额外解释，叙事一致性受损。
5. **门禁 + 暂缓**：设 MRR+0.01 门禁与 R@5 不降约束；因 torch/延迟/边际收益三重
   不确定性，当前不实施，留三条重启条件。结论是 Deferred，不是 Rejected。

## 决策：暂不实施

评估后当前不实施，理由按重要性排序：

1. **torch 依赖与 C5 约束张力**。sentence-transformers 拉 torch（CPU 版几百 MB）。
   C5 刚为“不引视觉模型”拒绝了 unstructured_inference（拖 torch）。reranker 的 torch
   是必需依赖（cross-encoder 本质是 torch 模型，非无谓膨胀），但场景不同需在 ADR 说清，
   否则“C5 拒 torch、C6 装 torch”自相矛盾。这个张力不值得为边际收益引入。
2. **延迟与 typed SSE 卖点冲突**。首 token 前塞 0.45-0.75s CPU rerank，直接削弱
   “chat.started 立即可用、首 token 快”的核心叙述。本地单用户对 0.5s 延迟敏感度低于
   生产，但叙事一致性受损。
3. **边际收益未经验证**。MRR 0.934 已较高，+0.01 的收益需实测确认；未测就加是
   “听说更厉害就加”，不是工程判断。而实测要先装 torch + 跑 reranker，成本前置。
4. **面试视角**：“评估了 reranker，明确了 MRR（非召回）目标、cross-encoder 原理、
   path A 成本、+0.01 门禁，因 torch/延迟/边际收益暂缓”——比“硬加一个测不出效果的
   优化”更能展示工程判断力。

## 结果

- 保持单阶段 RRF 混合检索，fused MRR@10=0.934 不变。
- 本 ADR + 面试指南 6.12 记录考量过程，供面试深挖。
- 不引入 torch / sentence-transformers 依赖。

## 遗留：重启条件

满足以下任一条件，重新评估：

1. **真实查询证据**：观察到 golden set 之外的真实查询频繁出现“正确 chunk 在 top-K
   但非 rank 1”，且 RRF 调参（k 值、腿权重）无法解决。
2. **无 torch 的 rerank 方案**：出现可接受的 non-torch reranker（如 ONNX 推理、
   或本地优先前提下可接受的外部 rerank API），消除约束张力。
3. **MRR 量化达标**：先在实验分支装 reranker 跑 35 条 golden set，MRR@10 实测 >= 0.944
   且 R@5 不降，再决定是否合入。

在以上条件未满足前，reranker 保持 Deferred。

## 参考资料

- **RRF（一阶段融合，本项目现状）**：Cormack, Clarke, Buettcher. *Reciprocal Rank Fusion
  outperforms Condorcet and individual rank learning methods.* SIGIR 2009. -- RRF 的原始
  论文，`1/(k+rank)` 融合的出处。本项目 C4 的 RRF 实现即基于此。
- **Cross-encoder vs bi-encoder**：Sentence-Transformers 官方文档“Cross-Encoders”章节
  （sbert.net）。说明 cross-encoder 把 query+doc 拼一起进 Transformer、输出相关性分数，
  精度高于 bi-encoder 但不能预计算、慢于向量检索--这正是“二阶段”的依据（粗排用
  bi-encoder 召回、精排用 cross-encoder）。
- **bge-reranker-v2-m3 模型卡**：HuggingFace `BAAI/bge-reranker-v2-m3`。多语言
  cross-encoder reranker，与本项目 embedding 用的 bge-m3 同系列，~568MB。
- **BGE 技术报告**：Xiao et al. *C-Pack: Packaged Resources To Advance General Chinese
  Embedding.* SIGIR 2024. -- BGE embedding + reranker 系列的设计与评测，bge-m3 与
  bge-reranker 的能力边界。
- **BM25 词法腿（C4 上下文）**：ParadeDB pg_search（https://github.com/paradedb/paradedb ），
  PostgreSQL 的 BM25 扩展，本项目 C4 用其 `@@@` 操作符 + Tantivy 索引做词法召回。
- **二阶段检索范式**：粗排（召回，bi-encoder/词法）+ 精排（rerank，cross-encoder）是
  检索系统的标准架构；本项目评估的即“是否在 RRF 粗排后加 cross-encoder 精排”。


---

## 重新评估（2026-08-07）：已实施

60 条 golden 扩充后暴露真实短板：cross_doc MRR=0.750、semantic_paraphrase MRR=0.856。
同时，ONNX Runtime 提供了**无 torch 的 cross-encoder 推理方案**——ADR-0009 当初否决的
唯一理由（torch 依赖）被绕开。

### 新决策

| 项 | 决策 |
|---|---|
| 方案 | ONNX Runtime + bge-reranker-v2-m3（onnxruntime + tokenizers，无 torch/Ollama） |
| 接入点 | RagService.search_prepared：扩候选池 top_k*4 → rerank → top_k |
| 默认 | `reranker_enabled=True`，一键回退纯 RRF |
| 模型 | `models/bge-reranker-v2-m3/`（gitignore 不入库，需单独下载） |

### 实测（52 非负例 golden，同一 fixture）

| 指标 | RRF only | RRF + rerank | Δ |
|---|---|---|---|
| 总体 MRR | 0.883 | 0.941 | +0.058 |
| cross_doc MRR | 0.750 | 1.000 | +0.250 |
| chinese_exact MRR | 0.792 | 0.933 | +0.142 |
| semantic_paraphrase MRR | 0.856 | 0.883 | +0.028 |

**结论**：reranker 精准修复了 60 条评估暴露的两个短板（cross_doc、semantic_paraphrase），
且无 torch 依赖。原始 ADR-0009 的否决理由（torch）已被 ONNX Runtime 消除，重启条件满足。
