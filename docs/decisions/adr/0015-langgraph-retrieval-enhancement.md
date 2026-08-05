# ADR-0015: LangGraph 检索增强——智能路由 + 自我纠错

**状态**: 已实施
**日期**: 2026-08-05
**决策者**: Kevin

## 背景

用户明确要求引入 LangGraph，两个场景：
1. **智能路由**：区分"常识问题"和"需要检索的问题"，避免无谓检索开销
2. **自我纠错**：检索结果不理想时自动改写查询重试

定位约束：Chat，最多贴近 Agent——模型参与**检索决策**（不执行工具/写代码）是合理形态。[ADR-0014](0014-langchain-thin-adapter-no-langgraph.md) 记录"不引入 LangGraph"，本 ADR 是其**决策变更**：原"不引入"针对完整 Agent 能力，本次引入用于**检索层的模型决策**。

## 图设计（LangGraph StateGraph）

```text
用户消息
  → router_node: LLM 判断 route ∈ {retrieve, direct}
     ├─ direct → 跳过 RAG，直接回答（带"未检索知识库"标注）
     └─ retrieve → rag_node
  → rag_node: prepare_search + search_prepared（BM25+vector RRF）
  → evaluate_node: 极差 + 数量检测
     ├─ 满意 → 结束
     └─ 不满意 + retries<MAX_RETRY(2) + 新 query → rewrite_node → rag_node
     └─ 达上限 或 query 重复 → 结束（"库中没有相关信息"）
```

## 关键设计

| 项 | 决策 | 理由 |
|---|---|---|
| 路由判断 | LLM 单次调用（json_mode），失败降级 retrieve | 语义判断比规则准；宁可多检索不漏 |
| **重试评估** | **极差检测**：`max - 2nd < 0.01` 或召回 < 3 → 不满意 | RRF 分数是相对值，绝对值阈值会误判 |
| **防打转** | rewrite prompt 铁律：与上轮相似度 < 0.8 + 补缺失关键词 | 避免三次检索一样 |
| **兜底缓存** | `seen_queries` 集合，query 重复立即跳出 | 库里没有时跳过无谓重试 |
| 运行时 | `RAG_RUNTIME=service\|graph` 双运行时，默认 graph | 出问题一键回退 |

## 与 S3 卡的关系

S3（确定性 Graph 双运行时）是固定边、为完整 Agent 铺路的平台化设计。本规划是**动态边**（模型决策路由 + 条件重试），独立实施，**不并入 S3**。两者都未涉及工具循环/checkpoint。

## 评估结果（详见 rag-graph-eval.md）

- **路由准确率 0.914**（32/35，门禁 ≥0.90 通过）；误判全是常识→retrieve（安全方向）
- **重试触发率 0.906 异常高**：evaluator 极差阈值 0.01 对 RRF 分数太严（fixture 文档少时 top2 分数差天然小）。重试后全部命中（docs=5，改写有效），但"自我纠错"过度——记录为已知边界，**触发条件**：生产真实库重试率仍 >50% 时调阈值
- 门禁：路由 ≥0.90 ✅、重试收敛 ✅

## 改动范围

| 文件 | 内容 |
|---|---|
| `app/ai/rag/router.py` | RouteRouter（LLM 判断 retrieve/direct） |
| `app/ai/rag/evaluator.py` | RetrievalEvaluator（极差 + 数量检测） |
| `app/ai/rag/rag_graph.py` | RagGraph（StateGraph + 节点 + 条件边 + seen 兜底） |
| `app/ai/rag/query_rewriter.py` | +failure_hint 参数（重试针对性改写，向后兼容） |
| `app/core/config.py` | +rag_runtime（graph/service） |
| `turn_coordinator.py` | _build_context 按 rag_runtime 分流 |
| `tests/test_rag_graph.py` | 7 测试（evaluator/router/graph 收敛） |

## 不做

- 不做工具循环/checkpoint（超定位）
- 不做 LLM 评估检索质量（分数阈值足够）
- 不并入 S3 卡
- 不改前端/OpenAPI
