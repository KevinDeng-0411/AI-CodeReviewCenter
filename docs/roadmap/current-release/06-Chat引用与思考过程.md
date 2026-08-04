# C6：Chat 引用与思考过程增强

> 本阶段在 C5 之后。目标：让 Chat 回答可溯源（下发参考来源）+ 思考过程可见（流式展示
> reasoning_content）。新增两个 typed SSE 事件，扩展现有 6 事件协议到 8 事件。
>
> **当前状态：已完成。** Chat 回答可溯源（`context.references` 下发知识+记忆参考来源，
> 前端来源卡片）+ 思考过程可见（`reasoning.delta` 流式展示，折叠窗）。切 `ChatDeepSeek`
> 提取 reasoning_content（ChatOpenAI 官方不提取）。后端 285 passed + 前端 36 passed，
> 真实 DeepSeek 流含 references + reasoning。沿用 C5 降密度：无 evidence manifest，
> 完成标志 = 测试通过 + demo。

## 1. 为什么单独设为 C6

当前 RAG 把检索到的知识 chunk + 记忆塞进 prompt 生成回答，用户只看到回答：
- **不可溯源**：不知道依据哪条知识/记忆，RAG 黑盒
- **思考不可见**：v4-flash 的 reasoning_content 被 `chunk.content` 读取逻辑丢弃

C6 不改检索/分块/向量，只在 Chat 层暴露已有数据（检索结果）+ 捕获被丢弃的 reasoning。

## 2. 开工门槛

- `evidence/C1~C4/manifest.json` 存在并通过 validator；C5 完成。
- 工作区干净；测试继续走 `run_tests_safe.py`（ disposable PG/Redis）。
- 用户明确要求实施 C6。
- **思考过程前置 spike**：确认 ChatDeepSeek 提取 reasoning_content（见 §4 C6-B）。

## 3. 技术选择门禁

| 项 | C6 决策 |
|---|---|
| 引用展示 | 摘要形式来源卡片（标题 + chunk 片段 + match_type 徽标）+ inline 展开；v1 不跳转原文 |
| 引用措辞 | "参考来源"（被检索并注入 prompt），不依赖 LLM 显式 cite |
| 思考展示 | 折叠窗（流式展开 -> 答案开始自动折叠 -> 用户可切换）；不持久化 |
| reasoning 捕获 | 切 ChatDeepSeek（ChatOpenAI 不提取 reasoning_content，见 ADR-0010） |
| SSE 扩展 | 新增 `context.references` + `reasoning.delta` 两个事件 |
| 不做 | 跳转原文、reasoning 持久化、LLM 显式 cite（脆弱）、ReAct 伪造思考 |

## 4. 最小拆分

```text
C6-A 文档先行：ADR-0010 + 本卡 + INDEX（用户 review 点）
C6-B 后端实现：
   1. spike：装 langchain-deepseek，验证 ChatDeepSeek.astream chunk 含 reasoning_content
   2. config：get_chat_model ChatOpenAI -> ChatDeepSeek
   3. SSE schema：chat_events.py 加 context.references + reasoning.delta
   4. TurnCoordinator：捕获 reasoning_content 分流 reasoning.delta；检索后发 context.references
C6-C 前端 + 测试：
   1. 前端：SSE parser 处理新事件；SourceCards 组件；ThinkingPanel 折叠组件；消息布局
   2. 后端测试：SSE 事件序列（refs -> reasoning -> tokens）、reasoning 捕获、refs payload
   3. 前端测试：来源卡片渲染、思考折叠展开
```

**引用与思考可独立交付**：引用不依赖 langchain-deepseek，C6-B 可先只做引用；思考依赖
spike 结果，spike 失败则思考降级（不做或改原始客户端）。

## 5. 实现细节

### 5.1 SSE 新事件 schema（chat_events.py）

```python
# context.references：检索后、LLM 前下发
class KnowledgeRef: document_id, title, snippet, match_type, score
class MemoryRef: content, memory_type, similarity
class ContextReferences: knowledge_refs: list[KnowledgeRef], memory_refs: list[MemoryRef]

# reasoning.delta：reasoning_content 流式
class ReasoningDelta: delta: str   # 同 TokenDelta 结构，独立事件
```

### 5.2 TurnCoordinator 改动

- **检索后发 refs**：`prepare_search` + memory recall 完成后（line 534 附近），构建
  ContextReferences payload（知识 ScoredChunk -> KnowledgeRef，需 join Document.title；
  memory recalled -> MemoryRef），emit `context.references`。
- **捕获 reasoning**：line 268 `delta = chunk.content` 改为同时读 reasoning_content
  （ChatDeepSeek chunk 字段位置 spike 确认），reasoning 分流 `reasoning.delta`，
  content 分流 `token.delta`。

### 5.3 前端

- SSE parser：新增 `context.references` / `reasoning.delta` 处理
- SourceCards：来源卡片列表（知识 ref 标题+片段+match_type 徽标，可展开；记忆 ref 内容+类型）
- ThinkingPanel：折叠窗，reasoning.delta 流式追加，token.delta 开始自动折叠，可手动切换
- 消息布局：[ThinkingPanel] + [答案正文] + [SourceCards]

## 6. 完成标志

- 定向 + 安全全量测试通过（`run_tests_safe.py`）。
- 前端 test/lint/build 通过。
- demo：上传知识 + 存记忆 -> 提问 -> 看到思考折叠窗 + 答案 + 来源卡片（知识/记忆可展开）。
- **思考功能依赖 spike**：若 ChatDeepSeek 不提取 reasoning_content，思考降级（文档记录），
  引用功能独立完成。

## 7. 完成边界

- 不改检索/分块/向量算法（C4/C5 成果不动）。
- 不跳转原文（v1）、不持久化 reasoning、不让 LLM 显式 cite。
- 不做 ReAct/CoT 伪造思考（思考只来自模型原生 reasoning_content）。
- 不开始 Agent 路线。
