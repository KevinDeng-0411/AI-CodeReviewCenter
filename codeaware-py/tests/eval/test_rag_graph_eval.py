"""LangGraph 检索增强评估（ADR-0015）——路由准确率 + 重试统计。

需要真实 DeepSeek（router judge）+ Ollama bge-m3（embedding）+ BM25 索引。live_eval。
"""

import json
import os

import pytest

from app.ai.config import get_chat_model, get_embedding_model
from app.ai.infra.vector_recall import VectorRecallService
from app.ai.rag.lexical_recall import Bm25LexicalRecall
from app.ai.rag.rag_graph import RagGraph
from app.ai.rag.router import RouteRouter
from app.ai.rag.semantic_chunker import SemanticChunker
from app.db.session import AsyncSessionLocal, engine
from app.models import Document, KnowledgeChunk
from tests.eval.golden_retrieval import FIXTURE_DOCS, GOLDEN_CASES

pytestmark = pytest.mark.live_eval

OUTPUT_FILE = "tests/eval/artifacts/rag_graph_eval.json"


async def test_rag_graph_route_accuracy_and_retry_stats(setup_db):
    # 1. 建索引 + 上传 fixture docs（真实 embedding + segmented）
    embedder = get_embedding_model()
    vr = VectorRecallService(embedder)
    chunker = SemanticChunker()
    from app.ai.rag.chinese_segmenter import segment_chinese

    async with engine.begin() as conn:
        from sqlalchemy import text

        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_search"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_kc_chunk_content_segmented_bm25 "
            "ON knowledge_chunks USING bm25 (chunk_content_segmented) "
            "WITH (key_field='id', "
            "text_fields='{\"chunk_content_segmented\": "
            "{\"tokenizer\": {\"type\": \"default\"}}}')"
        ))
    async with AsyncSessionLocal() as s:
        doc = Document(title="_init", content="_init", source_type="MANUAL")
        s.add(doc)
        await s.flush()
        s.add(KnowledgeChunk(
            document_id=doc.id, chunk_index=0,
            chunk_content="_init", chunk_content_segmented="_init",
        ))
        await s.commit()
        for fd in FIXTURE_DOCS:
            d = Document(title=fd.title, content=fd.content, source_type="MANUAL")
            s.add(d)
            await s.flush()
            for ct in chunker.chunk(fd.content, content_type="md"):
                s.add(KnowledgeChunk(
                    document_id=d.id, chunk_index=0,
                    chunk_content=ct, chunk_content_segmented=segment_chinese(ct),
                    embedding=await embedder.aembed_query(ct),
                ))
        await s.commit()

    # 2. 路由准确率
    llm = get_chat_model()
    router = RouteRouter(llm)
    route_rows = []
    for case in GOLDEN_CASES:
        predicted = await router.decide(case.query)
        route_rows.append({
            "query": case.query, "category": case.category,
            "expected": case.route_expected, "predicted": predicted,
            "correct": predicted == case.route_expected,
        })
    correct = sum(1 for r in route_rows if r["correct"])
    route_accuracy = correct / len(route_rows)

    # 3. 重试统计（对 predicted=retrieve 的跑 graph）
    graph = RagGraph(
        chat_model=llm,
        vector_recall=vr,
        lexical_recall=Bm25LexicalRecall(),
        query_rewriter=__import__("app.ai.rag.query_rewriter", fromlist=["QueryRewriter"]).QueryRewriter(llm),
        chunker=chunker,
        session_factory=AsyncSessionLocal,
    )
    retry_stats = []
    for case in GOLDEN_CASES:
        if case.route_expected != "retrieve":
            continue
        result = await graph.run(case.query)
        retry_stats.append({
            "query": case.query,
            "retries": result.retries,
            "direct": result.direct,
            "docs_count": len(result.docs),
            "route": result.route,
        })

    n_retry = sum(1 for r in retry_stats if r["retries"] > 0)
    avg_retry = sum(r["retries"] for r in retry_stats) / len(retry_stats) if retry_stats else 0
    n_direct = sum(1 for r in retry_stats if r["direct"])

    result = {
        "route_accuracy": {
            "mean": round(route_accuracy, 3),
            "correct": correct,
            "total": len(route_rows),
        },
        "retry_stats": {
            "n": len(retry_stats),
            "retry_triggered": n_retry,
            "retry_rate": round(n_retry / len(retry_stats), 3) if retry_stats else 0,
            "avg_retries": round(avg_retry, 3),
            "direct_predictions": n_direct,
        },
        "route_rows": route_rows,
        "retry_rows": retry_stats,
    }
    os.makedirs("tests/eval/artifacts", exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n[RAG-GRAPH] saved to {OUTPUT_FILE}")
    print(f"[RAG-GRAPH] route accuracy = {route_accuracy:.3f} ({correct}/{len(route_rows)})")
    print(f"[RAG-GRAPH] retry rate = {result['retry_stats']['retry_rate']:.3f} "
          f"({n_retry}/{len(retry_stats)}), avg retries = {avg_retry:.2f}")

    # 门禁：路由准确率 >= 0.90（误判 <= 2 条）
    assert route_accuracy >= 0.90, f"route accuracy {route_accuracy:.3f} < 0.90"
    # 门禁：重试收敛（retries <= MAX_RETRY=2）
    assert all(r["retries"] <= 2 for r in retry_stats), "retry exceeds MAX_RETRY"
