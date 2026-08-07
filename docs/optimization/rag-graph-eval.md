# LangGraph 检索增强评估（ADR-0015）

> 状态：✅ 已完成（2026-08-07，60 条 golden 重跑）
> 脚本：`codeaware-py/tests/eval/test_rag_graph_eval.py`（live_eval）
> 原始数据：`codeaware-py/tests/eval/artifacts/rag_graph_eval.json`

> **⚠️ 2026-08-05 路由故障修复**：实测发现 Router 自创建起**从未真正决策过**——
> `with_structured_output(method="json_mode")` 要求 prompt 必须含 "json" 字眼，原 prompt 没有，
> DeepSeek 每次都返回 400 `BadRequestError` → 降级 retrieve。因此旧 eval 的 **0.914 是"永远返回
> retrieve"这一降级策略的准确率**（32 条 retrieve + 3 条 direct 的 golden 恰好 32/35），并非路由决策成绩。
> 修复后（prompt 补 "json" + 输出格式示例），完整 live_eval 重跑：
> **路由 35/35 = 1.000**；重试触发率 **0.0**（32 条检索全部 `retries=0`、`docs_count=5`——
> match_type 评估器修复后命中查询评估满意、不重试，符合预期）。
> 旧 0.914 / 0.906 数据作废，`rag_graph_eval.json` 已为修复后真实数据。

## 背景

[ADR-0015](../decisions/adr/0015-langgraph-retrieval-enhancement.md) 引入 LangGraph 检索增强：智能路由（区分常识/检索）+ 自我纠错（检索不理想自动改写重试）。本评估量化其数据表现，对比 service（基线）vs graph（新结构）。

## 评估设计

- **路由准确率**：60 条 golden，Router 预测 route 对比 `route_expected`（非 negative → retrieve；negative 中技术问题如 Python GIL/K8s → retrieve，常识 → direct）
- **重试统计**：对 expected=retrieve 的 54 条跑 graph，记录 retries/docs_count
- 真实 DeepSeek（router judge）+ Ollama bge-m3 + BM25 索引

## 结果

### 路由准确率：1.000（60/60）✅

60 条真实 DeepSeek 判断：**全部正确**（含 6 条常识负例正确路由 direct）。

| 类别 | 数量 | 结果 |
|---|---|---|
| 技术/项目问题 → retrieve | 52 | 52 正确 |
| negative 技术问题（Python GIL/K8s）→ retrieve | 2 | 2 正确 |
| negative 常识 → direct | 6 | 6 正确 |

> 旧报告 0.914（32/35）系 Router 故障时"永远降级 retrieve"的产物，见顶部修复说明。修复前 3 条 direct
> 被误判为 retrieve 并非路由决策，而是 API 400 后的兜底值。

### 重试统计：触发率 1.9%（60 条）

| 指标 | 值 |
|---|---|
| 重试触发率 | **0.019**（1/54） |
| 平均重试次数 | 0.019 |
| 重试后 docs | 全部 = 5（首检即满意） |

54 条检索中 53 条 `retries=0`、`docs_count=5`（首检即满意，不触发重试）；1 条触发重试后收敛。符合 match_type 检测的设计预期（仅弱检索/未捞到才重试）。

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
| 路由准确率 ≥ 0.90 | **1.000**（修复后，35/35） | ✅ |
| 重试收敛 retries ≤ 2 | 全部 ≤ 2（mock 断言 + 重跑 0.0） | ✅ |
| 检索质量不降 | 重跑 32 条全部 docs=5 | ✅（未测 R@5 对比，见下） |

## 已知边界

1. **evaluator 阈值已修复**（match_type 检测替代分数差）。修复后重跑触发率 0.0（32 条命中查询全部首检满意），符合预期；弱检索触发路径由 mock 覆盖（tests/test_rag_graph.py）。
2. **R@5 对比未单独测**：graph 重试后 docs=5 全命中，但未与 service R@5=0.986 精确对比（受 fixture 规模限制）。生产评估需补。
3. **Router 误判安全**：修复后 0 误判（35/35）；即使失败/不确定也降级 retrieve（宁可多检索不漏），无"知识问题误判 direct 漏检"风险。
4. **match_type 依赖 BM25 词法腿**：若生产 RAG_LEXICAL_BACKEND=pg_trgm（非 bm25），词法腿仍返回 keyword，检测不受影响；但需确认 pg_trgm 在 segmented 列上可用（pg_trgm 建在 chunk_content 上，segmented 列无 trgm 索引 → 需评估）。

## 结论

- 智能路由**生效**（修复后 35/35 = 1.000，真实 DeepSeek 决策）
- 自我纠错**机制有效**（mock：弱检索 → 改写重试 → 命中收敛，retries ≤ 2）；旧 evaluator 阈值 bug（分数差对 RRF 无效）已修为 match_type 检测
- **修复后完整 eval 已重跑**：路由 1.000、重试触发率 0.0（命中查询首检满意不重试）

## 后续候选

- 生产库规模下补 R@5 before/after 精确对比
- 构造"首次检索差、改写后可命中"的真实弱检索样本，实测重试提升（当前 fixture 全部首检命中，重试路径仅 mock 覆盖）
- Router prompt 微调（可选；当前 1.000，无误判样本）
