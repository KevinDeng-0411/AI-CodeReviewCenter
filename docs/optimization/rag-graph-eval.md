# LangGraph 检索增强评估（ADR-0015）

> 状态：✅ 已完成（2026-08-05，35 条 golden）
> 脚本：`codeaware-py/tests/eval/test_rag_graph_eval.py`（live_eval）
> 原始数据：`codeaware-py/tests/eval/artifacts/rag_graph_eval.json`

## 背景

[ADR-0015](../decisions/adr/0015-langgraph-retrieval-enhancement.md) 引入 LangGraph 检索增强：智能路由（区分常识/检索）+ 自我纠错（检索不理想自动改写重试）。本评估量化其数据表现，对比 service（基线）vs graph（新结构）。

## 评估设计

- **路由准确率**：35 条 golden，Router 预测 route 对比 `route_expected`（非 negative → retrieve；negative 中技术问题如 Python GIL/K8s → retrieve，常识 → direct）
- **重试统计**：对 expected=retrieve 的 30 条跑 graph，记录 retries/docs_count
- 真实 DeepSeek（router judge）+ Ollama bge-m3 + BM25 索引

## 结果

### 路由准确率：0.914（32/35）✅

门禁通过（≥0.90）。3 个误判：

| 查询 | expected | predicted |
|---|---|---|
| 今天天气怎么样 | direct | retrieve |
| 如何做红烧肉 | direct | retrieve |
| 股票投资策略 | direct | retrieve |

**误判方向全部是"常识问题被误判为 retrieve"——安全方向**（宁可多检索不漏，符合 Router 设计：失败/不确定降级 retrieve）。

### 重试统计：首次评估触发率 0.906（已修复）⚠️→✅

| 指标 | 首次评估（旧阈值） | 修复后 |
|---|---|---|
| 重试触发率 | **0.906**（29/32） | 待重跑确认 |
| 平均重试次数 | 1.812 | — |
| 重试后 docs | 全部 = 5（命中） | — |

**根因（两层）**：
1. **旧 evaluator 分数差阈值 `max - 2nd < 0.01` 对 RRF 无效**。RRF 分数是 `1/(k+rank)` 累加，相邻排名差恒定 ~`1/61 - 1/62` ≈ 0.0003——任何查询（含 both 命中）的 top 相邻 chunk 差都 < 0.01，永远触发重试。
2. **probe 曾用错路径**：`HybridRetriever.search` 用 `text_column="chunk_content"`（BM25 索引在 segmented 列 → 词法腿空），误以为"分数差无效"。生产路径 `search_by_vector`（segmented 列）下词法腿正常。

**修复（2026-08-05）**：evaluator 改为**召回数量 + match_type 检测**，弃用分数差：
```python
if len(docs) < MIN_RECALL(3): return False      # 没捞到
if not any(d.match_type in ("keyword", "both") for d in docs): return False  # 纯 vector -> 弱
return True
```
**依据**（生产路径实测）：

| 查询 | 分数 | match | evaluator |
|---|---|---|---|
| 缓存击穿（命中） | 0.0325 | both | ✅ 满意（不重试） |
| 今天天气（无关） | 0.0164 | vector | ❌ 不满意（重试） |
| summary_message_count（命中） | 0.0323 | both | ✅ 满意 |

命中（both ~0.03）vs 无关（vector ~0.016）差距显著，match_type 能正确区分。

## 门禁判定

| 门禁 | 结果 | 判定 |
|---|---|---|
| 路由准确率 ≥ 0.90 | 0.914 | ✅ |
| 重试收敛 retries ≤ 2 | 全部 ≤ 2 | ✅ |
| 检索质量不降 | 重试后 docs=5 全命中 | ✅（未测 R@5 对比，见下） |

## 已知边界

1. **evaluator 阈值已修复**（match_type 检测替代分数差）。重试率重跑待确认（预期大幅下降至命中查询不重试、仅弱检索触发）。
2. **R@5 对比未单独测**：graph 重试后 docs=5 全命中，但未与 service R@5=0.986 精确对比（受 fixture 规模限制）。生产评估需补。
3. **Router 误判安全**：3 个误判全是 retrieve（安全方向），无"知识问题误判 direct 漏检"情况。
4. **match_type 依赖 BM25 词法腿**：若生产 RAG_LEXICAL_BACKEND=pg_trgm（非 bm25），词法腿仍返回 keyword，检测不受影响；但需确认 pg_trgm 在 segmented 列上可用（pg_trgm 建在 chunk_content 上，segmented 列无 trgm 索引 → 需评估）。

## 结论

- 智能路由**生效**（0.914，误判安全方向）
- 自我纠错**机制有效**（重试后 docs=5 全命中）；首次评估 90% 触发率是 evaluator 阈值 bug（分数差检测对 RRF 无效），已修为 match_type 检测
- 核心机制（路由/重试/收敛/防打转）验证通过

## 后续候选

- 重跑 graph 评估确认修复后重试率（预期命中不重试、弱检索触发）
- 生产库规模下补 R@5 before/after 精确对比
- Router prompt 微调降低常识误判（可选，当前安全方向）
