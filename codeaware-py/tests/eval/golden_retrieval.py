"""C4-A: 检索 golden set - 固定 fixture 文档 + 查询用例 + 评测指标。

expected_doc_ids 在实现前固定（不看完结果改答案），覆盖：
- 中文精确术语
- 英文自然语言
- snake_case/类名/配置键/错误码稀有标识符
- 语义改写同义词（只能靠向量召回）
- 负例（应无结果）
"""

from dataclasses import dataclass


@dataclass
class FixtureDoc:
    doc_id: int  # 上传后 document.id（1-based）
    title: str
    content: str


@dataclass
class GoldenCase:
    query: str
    expected_doc_ids: list[int]  # 相关文档 id（ Recall@5/MRR 判定用）
    category: str  # chinese_exact / english_natural / rare_identifier / semantic_paraphrase / negative
    expected_route: str | None = None  # 显式标注 retrieve/direct；None 由 category 推断

    @property
    def route_expected(self) -> str:
        """LangGraph 智能路由（ADR-0015）的预期 route。

        - 非 negative：应检索（retrieve）
        - negative：常识/无关 -> direct；技术问题（Python GIL/K8s）即使库中没有也应检索
        """
        if self.expected_route:
            return self.expected_route
        if self.category == "negative":
            return "retrieve" if self.query in ("Python GIL 问题", "Kubernetes pod 调度") else "direct"
        return "retrieve"


# ---------- Fixture 文档（15 篇，覆盖技术领域 + 代码标识符）----------

FIXTURE_DOCS: list[FixtureDoc] = [
    FixtureDoc(1, "缓存击穿方案",
        "## 缓存击穿\n热点Key失效瞬间大量请求打DB。方案：互斥锁、逻辑过期。\n"
        "使用 redis_setnx 实现互斥锁，避免缓存重建期间数据库过载。"),
    FixtureDoc(2, "缓存穿透方案",
        "## 缓存穿透\n查询不存在的数据。方案：布隆过滤器、缓存空值。\n"
        "bloom_filter 拦截非法查询，减少数据库无效访问。"),
    FixtureDoc(3, "缓存雪崩方案",
        "## 缓存雪崩\n大量Key同时失效。方案：过期时间加随机值、多级缓存。\n"
        "cache_ttl_jitter 防止批量过期导致的雪崩效应。"),
    FixtureDoc(4, "RAG 混合检索",
        "## RAG 检索增强生成\n查询重写 -> BM25 关键词 + pgvector 向量 -> RRF 融合。\n"
        "HybridRetriever 作用在 knowledge_chunks 表，返回 match_type=vector|keyword|both。"),
    FixtureDoc(5, "pgvector 内联向量",
        "## pgvector Vector(1024)\n向量内联同表存储，消除 UUID 反查。\n"
        "embedding 列用 Vector(1024)，HNSW 索引加速 cosine_distance 查询。"),
    FixtureDoc(6, "FastAPI 异步架构",
        "## FastAPI + asyncpg\n全异步：async 路由 + async SQLAlchemy + async redis。\n"
        "SSE 用 ChatOpenAI.astream() + StreamingResponse，TurnCoordinator 自管 session 事务。"),
    FixtureDoc(7, "SQLAlchemy 2.0 模型",
        "## SQLAlchemy 2.0 async\n8 张表：prompt_templates, ai_operation_records, conversations, messages,\n"
        "long_term_memories, documents, knowledge_chunks, ai_readme_documents。\n"
        "conversation_id 命名（ADR-0004），不用 session_id。"),
    FixtureDoc(8, "DeepSeek 集成",
        "## DeepSeek thinking mode\nthinking 模型用 json_mode 结构化输出（不支持 json_schema/function_calling）。\n"
        "非思考模式 thinking:disabled 解除 tool_choice 限制，function_calling 可用。"),
    FixtureDoc(9, "Prompt 版本化",
        "## PromptTemplate 版本化\n编辑=新建版本并激活，每 type 恰一 is_active（部分唯一索引）。\n"
        "save_and_activate 事务内 deactivate 同 type 其他 + activate 新版本。"),
    FixtureDoc(10, "短期记忆摘要",
        "## ShortTermMemoryManager\nPG messages 真相源 + Redis 滑窗缓存 + miss 回查 PG。\n"
        "summary_message_count 水位线触发摘要，LLM 不持 DB 事务。"),
    FixtureDoc(11, "长期记忆抽取",
        "## LongTermMemoryManager\nChat 达 2 轮后自动抽取原子事实（FACT 类型，conversation_id 关联）。\n"
        "extract_facts_text 纯 LLM 调用，save_facts 写 long_term_memories。"),
    FixtureDoc(12, "typed SSE 协议",
        "## ChatEventBase\nprotocol_version/conversation_id/turn_id/sequence。\n"
        "事件：chat.started/token.delta/chat.completed/chat.failed/context.warning/post_turn.warning。\n"
        "SSE id 等于十进制 sequence，delta 原样保留不 trim。"),
    FixtureDoc(13, "fail-closed 测试安全",
        "## run_tests_safe.py\n随机 stack_id 一次性 PG/Redis，拒绝 ai_center/ai_center_py/Redis DB0。\n"
        "_safeguard.assert_safe_targets 校验 stack_id 后缀 + 黑名单 + loopback。"),
    FixtureDoc(14, "AIReadMe 项目快照",
        "## ProjectSnapshot\n读取 LOCAL_PROJECT_ROOTS allowlist 下的真实文件。\n"
        "symlink 逃逸/二进制/大文件拦截，snapshot_hash 追踪版本递增。"),
    FixtureDoc(15, "知识库父子表",
        "## documents + knowledge_chunks\n父表存全文一次，子表 N 个 chunk 各存 chunk_content + embedding。\n"
        "删除走文档级 CASCADE，unstructured chunk_by_title 分块。"),
]


# ---------- Golden 查询用例（35 条）----------

GOLDEN_CASES: list[GoldenCase] = [
    # --- 中文精确术语 (8) ---
    GoldenCase("缓存击穿如何解决", [1], "chinese_exact"),
    GoldenCase("缓存穿透方案", [2], "chinese_exact"),
    GoldenCase("缓存雪崩", [3], "chinese_exact"),
    GoldenCase("查询重写", [4], "chinese_exact"),
    GoldenCase("向量内联存储", [5], "chinese_exact"),
    GoldenCase("摘要生成", [10], "chinese_exact"),
    GoldenCase("记忆抽取", [11], "chinese_exact"),
    GoldenCase("版本化模板", [9], "chinese_exact"),

    # --- 英文自然语言 (7) ---
    GoldenCase("how to do hybrid retrieval", [4], "english_natural"),
    GoldenCase("FastAPI async architecture", [6], "english_natural"),
    GoldenCase("SQLAlchemy models", [7], "english_natural"),
    GoldenCase("DeepSeek thinking mode", [8], "english_natural"),
    GoldenCase("typed SSE protocol", [12], "english_natural"),
    GoldenCase("safe test runner", [13], "english_natural"),
    GoldenCase("project snapshot for AIReadMe", [14], "english_natural"),

    # --- 稀有标识符 (8) ---
    GoldenCase("HybridRetriever", [4], "rare_identifier"),
    GoldenCase("summary_message_count", [10], "rare_identifier"),
    GoldenCase("conversation_id", [7, 12], "rare_identifier"),
    GoldenCase("chat.started", [12], "rare_identifier"),
    GoldenCase("assert_safe_targets", [13], "rare_identifier"),
    GoldenCase("save_and_activate", [9], "rare_identifier"),
    GoldenCase("extract_facts_text", [11], "rare_identifier"),
    GoldenCase("knowledge_chunks", [4, 15], "rare_identifier"),

    # --- 语义改写同义词 (7, 主要靠向量) ---
    GoldenCase("热点Key失效怎么办", [1], "semantic_paraphrase"),
    GoldenCase("布隆过滤器拦截", [2], "semantic_paraphrase"),
    GoldenCase("过期时间随机化", [3], "semantic_paraphrase"),
    GoldenCase("两级记忆整合", [10, 11], "semantic_paraphrase"),
    GoldenCase("流式逐token推送", [12], "semantic_paraphrase"),
    GoldenCase("一次性测试环境隔离", [13], "semantic_paraphrase"),
    GoldenCase("文档分块检索", [4, 15], "semantic_paraphrase"),

    # --- 负例 (5, 应无结果或低相关) ---
    GoldenCase("今天天气怎么样", [], "negative"),
    GoldenCase("如何做红烧肉", [], "negative"),
    GoldenCase("Python GIL 问题", [], "negative"),
    GoldenCase("Kubernetes pod 调度", [], "negative"),
    GoldenCase("股票投资策略", [], "negative"),
]


# ---------- 评测指标 ----------

def recall_at_k(result_doc_ids: list[int], expected_doc_ids: list[int], k: int = 5) -> float:
    """Recall@k：前 k 个结果中包含多少期望文档。"""
    if not expected_doc_ids:
        return 1.0  # 负例无期望，默认 1.0（不扣分）
    top_k = result_doc_ids[:k]
    hits = sum(1 for d in expected_doc_ids if d in top_k)
    return hits / len(expected_doc_ids)


def reciprocal_rank(result_doc_ids: list[int], expected_doc_ids: list[int], k: int = 10) -> float:
    """MRR：第一个命中期望文档的倒数排名（1/rank），前 k 内无命中则 0。"""
    if not expected_doc_ids:
        return 1.0  # 负例
    for i, doc_id in enumerate(result_doc_ids[:k]):
        if doc_id in expected_doc_ids:
            return 1.0 / (i + 1)
    return 0.0


def evaluate_results(
    results: list[tuple[str, list[int]]],  # (query, result_doc_ids)
    cases: list[GoldenCase] | None = None,
) -> dict:
    """对一批查询结果计算 Recall@5 / MRR@10 / 分类别指标。"""
    cases = cases or GOLDEN_CASES
    case_map = {c.query: c for c in cases}
    metrics = {"recall@5": [], "mrr@10": [], "by_category": {}}

    for query, result_doc_ids in results:
        case = case_map.get(query)
        if not case:
            continue
        r5 = recall_at_k(result_doc_ids, case.expected_doc_ids, k=5)
        rr = reciprocal_rank(result_doc_ids, case.expected_doc_ids, k=10)
        metrics["recall@5"].append(r5)
        metrics["mrr@10"].append(rr)
        cat = case.category
        if cat not in metrics["by_category"]:
            metrics["by_category"][cat] = {"recall@5": [], "mrr@10": []}
        metrics["by_category"][cat]["recall@5"].append(r5)
        metrics["by_category"][cat]["mrr@10"].append(rr)

    # 汇总
    n = len(metrics["recall@5"])
    summary = {
        "n": n,
        "recall@5_mean": sum(metrics["recall@5"]) / n if n else 0,
        "mrr@10_mean": sum(metrics["mrr@10"]) / n if n else 0,
        "by_category": {},
    }
    for cat, vals in metrics["by_category"].items():
        cn = len(vals["recall@5"])
        summary["by_category"][cat] = {
            "n": cn,
            "recall@5_mean": sum(vals["recall@5"]) / cn if cn else 0,
            "mrr@10_mean": sum(vals["mrr@10"]) / cn if cn else 0,
        }
    return summary
