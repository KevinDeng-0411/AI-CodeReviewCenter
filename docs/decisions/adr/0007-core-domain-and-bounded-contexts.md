# ADR-0007: 核心领域与限界上下文

- **状态**: Accepted
- **日期**: 2026-07-28
- **关联术语**: 核心领域
- **上游**: 收口开篇 Q1("一个领域还是多个共享基建的特性集合")

## 背景

"AI 研发效能中台"是**营销标签,不是领域**。需明确核心域与上下文边界。难度/IP 分布:CR/unittest/readme 均薄(加载 prompt -> 调 LLM -> 记日志,ADR-0006);厚 IP 在 PromptTemplate(ADR-0005)/Memory(ADR-0001/3/4)/VectorRecallService(ADR-0001);Chat 是唯一把 memory+RAG+prompt 全栈拧在一起的上下文。

## 决策(采纳 Chat 为核心域的澄清)

1. **核心域 = Chat(智能问答)**:多轮对话 + 两级记忆(ADR-0001/3/4)+ RAG(ADR-0001/2)+ prompt 编排(ADR-0005)在此收敛。这是业务价值集中的旗舰能力。
2. **支撑子域 = AI 编排基础设施**:PromptTemplate / Memory(短/长)/ VectorRecallService。它是为服务 Chat(并被工具复用)而存在的硬技术 IP,但本身不是核心业务能力。Embedding(内联 pgvector `Vector(1024)`)与 Hybrid Retrieval(pg_trgm+pgvector)均为 VectorRecallService 的**基础设施实现细节**,不立独立 ADR。
3. **次要/通用上下文 = Code Review / Unit Test / AIReadMe**:复用基建的薄工具上下文(load prompt + LLM + log operation)。刻意保持薄,不过度设计。
4. **本次迁移范围**:交付 Chat 功能基线(短期记忆+长期记忆+RAG 混合检索+SSE,迁移文档 P3-2/3-3/3-4)+ 薄工具(CR/UT/AIReadMe)。**LangGraph 状态图编排等工程深度加深为预留项,本次迁移不实现**。

> **2026-08-05 更新**:上述"预留项"已部分落地——LangGraph 通过 [ADR-0015](0015-langgraph-retrieval-enhancement.md) 引入用于**检索层增强**(智能路由 + 自我纠错),属"贴近 Agent"的模型决策形态;完整 Agent 工具循环结论不变(见 [ADR-0014](0014-langchain-thin-adapter-no-langgraph.md) 决策变更)。

## 上下文图

```
        ┌──────────── 核心域 ────────────┐
        │           Chat(智能问答)        │
        └──────────────┬─────────────────┘
                       │ 编排/消费
        ┌──────────────▼─────────────────┐
        │   支撑子域:AI 编排基础设施        │
        │  PromptTemplate / Memory /      │
        │  VectorRecallService            │
        └──────┬──────────────┬───────────┘
               │              │ 复用
   ┌───────────▼──┐ ┌────────▼────────┐
   │ CR / UT / AIReadMe (次要上下文)    │
   └───────────────────────────────────┘
```

## 结果

- 面试表述:"核心域是智能问答 Chat--两级记忆+RAG+prompt 编排在此收敛;共享 AI 基建是支撑子域;CR/单测/AIReadMe 是复用基建的次要工具上下文。" 不再说含糊的"研发效能中台"。
- 建模精力优先给 Chat(核心);基建为服务 Chat 而设计;3 个工具刻意薄。
- **价值类型区分**:Chat=架构纵深(记忆/RAG/SSE/上下文编排);CR=提示词工程展示(七层结构化 Prompt);UT/AIReadMe=薄壳复用。面试分层叙事:主线 Chat 架构,辅线 CR 提示词,UT/AIReadMe 广度;勿把薄工具包装成深度工程。
- 闭合 Q1:这是**共享基建平台 + 核心域 Chat + 次要工具上下文**,不是一个均质领域,也不是松散特性堆砌。

## 遗留(跨 ADR)

- ~~ADR-0003 子决策:LLM 摘要持久化~~ **已解决**(见 ADR-0003 决策点 4:PG `conversations.summary` 真相 + Redis 缓存,miss 读 PG 不重算,写入异步双写)。
- ADR-0005:`review_dimensions`/`severity_levels` 仅 CODE_REVIEW 有意义,余 type 为空(可接受)。
