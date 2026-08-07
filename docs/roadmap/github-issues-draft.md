# GitHub Issues 草稿（封档后开放项）

基于项目真实边界和路线图，以下 issue 体现仓库的开放性和后续规划。

---

## Issue 1: [enhancement] 流式端点答案缓存

**Labels**: enhancement, chat

**Body**:
当前答案缓存（TTL 5min，精确匹配）只作用于同步端点 `/api/chat/send`，命中时从 ~31s 降到 ~0.02s。流式端点 `/api/chat/send/stream` 未实现缓存，原因是：
- 引用来源（context.references）和思考过程（reasoning.delta）无法从纯文本缓存回放
- SSE 合成流回放的一致性维护成本高

**候选方案**：缓存 `reply + knowledge_refs + memory_refs` 三元组，命中时合成 SSE 流回放（保留引用卡片，放弃 reasoning）。需真实流量数据评估收益后再实施。

参考：docs/optimization/sync-vs-stream-endpoints.md

---

## Issue 2: [enhancement] 多 worker 支持（PG advisory lock 替代进程内 set）

**Labels**: enhancement, architecture

**Body**:
当前 turn guard 是进程内 `set[str]`（TurnCoordinator._active），仅适用于单 worker。多 worker 部署时同会话并发保护失效。

**方案**：PG advisory lock 替代进程内集合，支持 `uvicorn --workers N` 横向扩展。

**依赖**：
- 需评估锁粒度（conversation_id 级别）
- 锁超时/释放策略

---

## Issue 3: [enhancement] 无关查询降级策略（negative 类 Faithfulness 提升）

**Labels**: enhancement, rag

**Body**:
RAGAS 评估显示 negative 类（无关查询）Faithfulness 最低（60 条采样下约 0.6-0.7）——检索不到 context 时模型硬答导致主张无支撑。

**现状**：前端已有"未检索知识库"标注（LangGraph direct 路由），但 direct 判定后的生成仍可能编造。

**候选方案**：
- direct 路径注入"库中无相关信息"约束到 prompt
- 或返回结构化"未找到"响应而非自由发挥

---

## Issue 4: [enhancement] Golden 集扩充到 100+ 条

**Labels**: enhancement, eval

**Body**:
当前 60 条 golden cases（15 篇 fixture 文档，6 类：chinese_exact/english_natural/rare_identifier/semantic_paraphrase/negative/cross_doc）。

**目标**：扩充到 100+ 条，覆盖：
- 更多跨文档组合查询
- 真实用户口语化查询
- 复合/多跳问题
- 边界 case（超长查询、模糊表述）

**收益**：R@5/MRR 统计显著性更强，能区分 top_k=3 vs 5 的细微差异。

---

## Issue 5: [enhancement] 高频查询缓存（Redis LRU）

**Labels**: enhancement, performance

**Body**:
当前答案缓存是精确匹配（MD5(message)），语义相近但表述不同的查询无法命中。且流式端点无缓存。

**候选方案**：
- 检索结果缓存：相同/相似查询复用 RRF+rerank 结果（需处理 KB 时效性）
- embedding 缓存：相同文本跳过 embedding（Metal GPU 128ms 下 ROI 已低，暂缓）

---

## Issue 6: [enhancement] 可观测性增强：Grafana/Loki 日志可视化

**Labels**: enhancement, observability

**Body**:
已有：
- JSON 结构化日志（app/core/logging.py）
- Kafka 事件流（audit.document / metrics.retrieval / ops.error）
- Flower 任务监控

**候选方案**：
- Loki 收集 JSON 日志 + Grafana 面板
- Kafka Consumer 写 PG 审计表（替代文件归档）
- Prometheus /metrics 端点（请求数/延迟/错误率）

---

## Issue 7: [enhancement] 知识库按用户/团队权限隔离

**Labels**: enhancement, team

**Body**:
当前知识库/记忆全员共享（实验室场景）。多团队部署需要：
- 文档级 ACL（团队/用户可见性）
- 记忆按团队隔离（recall 增加 filter）

**依赖**：X-Project-ID 项目隔离机制（当前未实现）。

---

## Issue 8: [enhancement] API 限流中间件

**Labels**: enhancement, security

**Body**:
当前无请求限流。`/api/chat/send` 的 LLM 调用成本较高，恶意/异常请求可打满 API 配额。

**方案**：按用户/IP 限流（如 30 次/分钟 /api/chat），返回 429。

---

## Issue 9: [enhancement] 部署增强：CI/CD 流水线

**Labels**: enhancement, devops

**Body**:
当前为本地开发优先，无 CI/CD。候选：
- GitHub Actions：测试 → 构建 → 镜像
- docker-compose 一键生产部署（start.sh 完善）
- 备份/恢复演练文档

---

## Issue 10: [enhancement] TurnCoordinator 进一步拆分（StreamManager 提取）

**Labels**: enhancement, refactor

**Body**:
已拆出 ContextBuilder + PostTurnProcessor（870 行 → 534 行），`run()` SSE 事件生成器仍在 TurnCoordinator。

**候选方案**：提取 StreamManager（事件流编排），TurnCoordinator 降为纯事务/guard 编排。
