# Golden 集扩充（35→60）+ 评估重跑 + 文档更新（最终封档）

## 背景

项目即将封档。当前 golden 集 35 条样本量小、缺跨文档类别。扩充到 60 条并重跑评估，更新指标数据和文档。

## 1. 扩充 golden 集（35 → 60）

修改 `codeaware-py/tests/eval/golden_retrieval.py`：

### 新增 25 条分布

| 类别 | 现有 | 新增 | 总共 | 新增查询（expected_doc_ids） |
|---|---|---|---|---|
| chinese_exact | 8 | +4 | 12 | 互斥锁[1]、逻辑过期[1]、缓存空值[2]、多级缓存[3] |
| english_natural | 7 | +3 | 10 | how to prevent cache stampede[1]、RRF fusion in hybrid search[4]、HNSW index for vectors[5] |
| rare_identifier | 8 | +4 | 12 | redis_setnx[1]、cache_ttl_jitter[3]、chat.completed[12]、LOCAL_PROJECT_ROOTS[14] |
| semantic_paraphrase | 7 | +8 | 15 | 热点数据失效怎么防数据库被打爆[1]、查询不存在的数据怎么办[2]、一批缓存同时到期[3]、语义和关键词检索如何合并[4]、向量存储格式[5]、全异步怎么实现[6]、表结构怎么组织[7]、怎么固定模型输出格式[8] |
| negative | 5 | +3 | 8 | 推荐一部好看的电影[]、如何做糖醋排骨[]、哪家奶茶店最好喝[] |
| cross_doc（新） | 0 | +3 | 3 | 缓存穿透和缓存击穿的区别[1,2]、向量和关键词检索怎么结合[4,5]、短期记忆和长期记忆区别[10,11] |

### 代码改动

- `GoldenCase` 的 `category` 字段支持新值 `cross_doc`
- `route_expected` 属性逻辑不变（非 negative → retrieve）
- 保持 FIXTURE_DOCS 不变（15 篇，控制变量）

## 2. 重跑评估（live_eval，需重启 Ollama/DeepSeek）

```bash
# 启动基础服务
docker compose up -d postgres redis kafka kafka_consumer celery_worker

# 重跑全部评估（live_eval 标记）
uv run python scripts/run_tests_safe.py tests/eval/ -m live_eval -q
```

评估脚本（自动用新的 60 条 golden）：
- `test_c3_baseline.py` → `artifacts/baseline_c3_pg_trgm.json`
- `test_c4_bm25_baseline.py` → `artifacts/baseline_c4_bm25.json`
- `test_c4_baseline.py` → `artifacts/baseline_c4_jieba.json`
- `test_topk_ablation.py` → `artifacts/topk_ablation.json`
- `test_ragas_generation.py` → `artifacts/ragas_generation.json`
- `test_rag_graph_eval.py` → `artifacts/rag_graph_eval.json`

## 3. 更新指标数据到文档

| 文档 | 更新内容 |
|---|---|
| `docs/optimization/retrieval-evolution.md` | 60 条 golden 基线数据，全部表格刷新 |
| `docs/optimization/README.md` | 评估数据引用 60 条 |
| `docs/optimization/topk-sensitivity.md` | top_k 表格用新数据 |
| `docs/optimization/rag-graph-eval.md` | 路由准确率/重试率用新数据 |
| `docs/optimization/ragas-eval.md` | Faithfulness/Relevancy 用新数据 |
| `README.md` / `README.zh-CN.md` | 检索评估摘要更新为 60 条 |

## 4. 封档清单

- [ ] 全部评估通过，指标数据更新
- [ ] 315+ 测试全通过
- [ ] 文档全部更新
- [ ] README 检索评估摘要为最新
- [ ] 提交 + 推送远程
- [ ] 项目状态标记"已封档"

## 验证

```bash
# 单元测试回归
uv run python scripts/run_tests_safe.py -q

# 前端测试
(cd frontend && npm run test && npm run lint && npm run build)
```