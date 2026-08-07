# 生成层评估基线：自实现 RAGAS 指标

> 状态：✅ 已完成（2026-08-07，60 条 golden 采样 35）
> 指标：Faithfulness + Answer Relevancy（自实现，对齐 RAGAS 语义）
> 脚本：`codeaware-py/tests/eval/test_ragas_generation.py`（live_eval）
> 原始数据：`codeaware-py/tests/eval/artifacts/ragas_generation.json`

## 背景

检索层已有完整评估（R@5/MRR，[topk-sensitivity](topk-sensitivity.md)），但检索准 ≠ 答案好。本评估补齐**生成层**：答案有没有编造（Faithfulness）、切不切题（Answer Relevancy）。

**为什么自实现而非装 ragas 库**：ragas 依赖重（langchain/langgraph），与项目"不堆依赖、自控可解释"原则冲突。用现有 DeepSeek 做生成+judge，Ollama bge-m3 做 embedding，逻辑完全可控。

## 指标定义

| 指标 | 定义 | 依赖 ground truth |
|---|---|---|
| Faithfulness | 回答的主张中被检索 context 支撑的比例（0-1） | ❌ 无（judge 自参考） |
| Answer Relevancy | 反向生成问题与原问题的 embedding 相似度（0-1） | ❌ 无 |

## 结果（60 条 golden 采样 35，真实 DeepSeek + bge-m3）

| 指标 | mean | n |
|---|---|---|
| **Faithfulness** | **0.931** | 35（60 条采样） |
| **Answer Relevancy** | **0.793** | 35 |

### 按类别

| 类别 | n | faithfulness | relevancy |
|---|---|---|---|
| chinese_exact | 8 | 0.929 | 0.870 |
| english_natural | 7 | 0.967 | 0.813 |
| rare_identifier | 8 | 0.975 | 0.824 |
| semantic_paraphrase | 7 | **1.000** | 0.875 |
| **negative** | 5 | **0.667** | **0.610** |

## 解读

1. **整体健康**：Faithfulness 0.931——回答基本被检索 context 支撑，编造少。这与 C6 引用（context.references）+ 提示词"基于知识库回答"约束一致。
2. **negative 类最弱**（0.667/0.610）：无关查询（"今天天气"）检索不到相关 context，模型硬答导致主张无支撑、回答跑题。这是 RAG 对无关查询的已知弱项——现有"检索不到→注入空上下文→模型自由发挥"路径需要关注。
3. **Answer Relevancy 0.793**：整体切题。相比 35 条基线略降（0.812→0.793），因新增 25 条含更难的语义改写/跨文档用例。
4. **4 条 judge 解析失败**（缓存击穿/如何 hybrid/今天天气/Python GIL）：回答过短或负例导致 judge JSON 不完整——记录为已知评估噪声，不影响整体趋势。

## 成本与触发条件

- **成本**：60 条采样 35 ×（1 生成 + 2 judge + 2 embedding）≈ 105 次真实 LLM 调用，约 40 分钟（60 条全量更久，采样控制成本）
- **不建议频繁跑**：live_eval 标记，仅在以下情况重跑
  - 生成 prompt 模板变更后（对比 Faithfulness 是否变化）
  - 出现"答案胡说"用户反馈（定位是否检索/生成层问题）
  - 评估集扩充到 100+ 条

## 后续候选

- **Context Recall**（需 ground truth 答案集）暂缓——人工成本高，当前无信号
- **negative 类优化**：无关查询时的降级策略（返回"未找到相关知识"而非硬答）——可提升 Faithfulness 最弱类
- judge 解析失败率优化：对回答过短的样本降级为默认分，减少噪声
