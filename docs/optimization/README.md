# CodeAware 检索与系统优化

> 本文件夹记录**基本开发完成之后**的性能/质量优化评估与实施，与
> [基本开发路线](../roadmap/current-release/README.md)（C1-C6 功能交付）分开。
> 架构决策记录仍按 ADR 编号序列存放于 [docs/decisions/adr/](../decisions/adr/)，
> 本文件夹负责"优化计划、敏感性分析、评估结论"。

## 优化项总览

| 优化项 | 状态 | 决策记录 | 说明 |
|---|---|---|---|
| **检索质量演进总览** | ✅ 持续更新 | [retrieval-evolution.md](retrieval-evolution.md) | 全阶段 R@5/MRR/延迟/决策对比 |
| LangGraph 检索增强（路由+纠错） | ✅ 已实施 | [ADR-0015](../decisions/adr/0015-langgraph-retrieval-enhancement.md) / [eval](rag-graph-eval.md) | 路由准确率 1.000（修复 json_mode 400 后） |
| LangChain 薄 adapter / 完整 Agent 不引 LangGraph | ✅ 已评估 | [ADR-0014](../decisions/adr/0014-langchain-thin-adapter-no-langgraph.md) | 耦合度极低；完整 Agent 仍不做 |
| 生成层评估（RAGAS） | ✅ 已完成 | [ragas-eval.md](ragas-eval.md) | Faithfulness 0.939 / Relevancy 0.812 |
| 分块策略（chunk_by_title） | ✅ 已实施 | [chunking-strategy.md](chunking-strategy.md) / [ADR-0008](../decisions/adr/0008-document-parsing-element-aware-serialization.md) | 标题切分 + 段落边界 + 500字兜底 |
| BM25 词法检索 (C4) | ✅ 已实施 | [04 卡](../roadmap/current-release/04-BM25检索增强.md) | pg_trgm → ParadeDB BM25 |
| 元素感知分块 (C5) | ✅ 已实施 | [ADR-0008](../decisions/adr/0008-document-parsing-element-aware-serialization.md) | DOCX/HTML/PDF 标题穿到分块层 |
| Chat 引用+思考 (C6) | ✅ 已实施 | [ADR-0010](../decisions/adr/0010-chat-references-and-reasoning.md) | 8 事件 typed SSE |
| jieba 中文分词 | ✅ 已实施 | [ADR-0011](../decisions/adr/0011-jieba-chinese-bm25-segmentation.md) | 中文 BM25 R@5 0.25→1.000 |
| **top_k 敏感性分析** | ✅ 已完成 | [topk-sensitivity.md](topk-sensitivity.md) / [ADR-0012](../decisions/adr/0012-topk-sensitivity-keep-5.md) | 保持 k=5，数据驱动 |
| 文档管理（软删+列表+更新） | ✅ 已实施 | [ADR-0013](../decisions/adr/0013-document-management-soft-delete.md) | 软删行+物理删分块 |
| Reranker 二阶段精排 | ⏸ 评估后暂缓 | [ADR-0009](../decisions/adr/0009-reranker-deferred.md) | 门禁 MRR+0.01，torch 依赖 |
| 意图识别 | ❌ 评估后不做 | 面试指南 §6.15 | 90% 知识问题，加分类引入漏检 |

## 决策优先级原则

优化看**实测收益**，不看"看起来更高级"。优先级排序（ADR-0011/面试指南决策8）：

```text
jieba 中文 BM25（R@5 +0.34） > top_k 敏感性（待测） > reranker（门禁仅 +0.01） > 意图识别（负收益）
```

- **jieba 让中文 BM25 从残废变可用**（BM25-only R@5 0.25→1.000）——投入小、收益大
- **reranker 门禁 MRR+0.01**（torch 依赖 + 0.5s 延迟）——收益未实测，暂缓
- **意图识别**把知识问题误判成闲聊的风险 > 闲聊省下的延迟——不做

## 面试交叉引用

- 面试指南：[§6.12 reranker 暂缓](../interview/面试准备指南.md)、[§6.14 jieba](../interview/面试准备指南.md)、[§6.15 意图识别](../interview/面试准备指南.md)、[§6.16 top_k](../interview/面试准备指南.md)、[§6.17 文档管理](../interview/面试准备指南.md)、决策 7/8
- 面试速通版：Q3 检索追问（reranker + 意图识别一句带过）

## 评测数据

- 检索基线：`codeaware-py/tests/eval/artifacts/baseline_c{3,4}_*.json`
- 敏感分析：`codeaware-py/tests/eval/artifacts/topk_ablation.json`
- 60 条 golden cases（15 篇 fixture 文档），真实 bge-m3 embedding
