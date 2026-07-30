"""C4-A: C3 检索基线指标采集 - pg_trgm / vector / fused 三路对照。

需要真实 Ollama bge-m3 embedding（经 safe runner 一次性 PG,dev Ollama）。
标记 live_eval,不跑普通 CI。
"""

import json
import time

import pytest
from sqlalchemy import func, select

from app.ai.config import get_embedding_model
from app.ai.infra.vector_recall import VectorRecallService
from app.ai.rag.hybrid_retriever import HybridRetriever
from app.ai.rag.semantic_chunker import SemanticChunker
from app.ai.services.rag import RagService
from app.core.config import settings
from app.models import KnowledgeChunk
from tests.eval.golden_retrieval import FIXTURE_DOCS, GOLDEN_CASES, evaluate_results

pytestmark = pytest.mark.live_eval

OUTPUT_FILE = "tests/eval/artifacts/baseline_c3_pg_trgm.json"


@pytest.fixture
def real_embedder():
    return get_embedding_model()


@pytest.fixture
def real_vr(real_embedder):
    return VectorRecallService(real_embedder)


@pytest.fixture
async def upload_fixture(db_session, real_vr):
    """上传 FIXTURE_DOCS 到一次性 PG（真实 bge-m3 embedding）。"""
    chunker = SemanticChunker()
    from app.ai.rag.query_rewriter import QueryRewriter
    from app.models import Document

    # 不需要真实 LLM 做 query rewrite；C4 基线只测 keyword/vector 腿
    class _NoopRewriter:
        async def rewrite(self, q):
            return [q]

    doc_ids = {}
    for fd in FIXTURE_DOCS:
        doc = Document(title=fd.title, content=fd.content, source_type="MANUAL")
        db_session.add(doc)
        await db_session.flush()
        chunks = chunker.chunk(fd.content, content_type="md")
        for i, chunk_text in enumerate(chunks):
            kc = KnowledgeChunk(document_id=doc.id, chunk_index=i, chunk_content=chunk_text)
            await real_vr.store(db_session, kc, chunk_text)
        doc_ids[fd.doc_id] = doc.id
        await db_session.flush()
    return doc_ids


async def _pg_trgm_search(db_session, query: str, top_k: int = 10) -> list[KnowledgeChunk]:
    """pg_trgm similarity 关键词腿（纯 SQL，不经过 HybridRetriever）。"""
    rows = (
        await db_session.execute(
            select(KnowledgeChunk, func.similarity(KnowledgeChunk.chunk_content, query).label("score"))
            .where(func.similarity(KnowledgeChunk.chunk_content, query) > 0.1)
            .order_by(func.similarity(KnowledgeChunk.chunk_content, query).desc())
            .limit(top_k)
        )
    ).all()
    return [r[0] for r in rows]


async def _vector_search(real_vr, db_session, query: str, top_k: int = 10) -> list[KnowledgeChunk]:
    """纯向量召回（hybrid=False）。"""
    rows = await real_vr.recall(
        db_session, KnowledgeChunk, query, top_k=top_k, hybrid=False, text_column="chunk_content"
    )
    return [r[0] for r in rows]


async def _fused_search(real_vr, db_session, query: str, top_k: int = 10) -> list[KnowledgeChunk]:
    """混合召回（pg_trgm + vector + RRF）。"""
    rows = await real_vr.recall(
        db_session, KnowledgeChunk, query, top_k=top_k, hybrid=True, text_column="chunk_content"
    )
    return [r[0] for r in rows]


async def test_c3_baseline_metrics(db_session, real_vr, upload_fixture):
    """采集 C3 pg_trgm / vector / fused 三路基线指标。"""
    doc_ids = upload_fixture
    # 建立 chunk_id -> doc_id 映射
    chunk_doc_map = {}
    for fd in FIXTURE_DOCS:
        doc_pk = doc_ids[fd.doc_id]
        chunks = (
            await db_session.execute(
                select(KnowledgeChunk.id).where(KnowledgeChunk.document_id == doc_pk)
            )
        ).scalars().all()
        for cid in chunks:
            chunk_doc_map[cid] = fd.doc_id

    results = {"pg_trgm": [], "vector": [], "fused": [], "timing": {}}

    # 预热
    for query in [c.query for c in GOLDEN_CASES[:3]]:
        await _pg_trgm_search(db_session, query, top_k=1)
        await _vector_search(real_vr, db_session, query, top_k=1)
        await _fused_search(real_vr, db_session, query, top_k=1)

    # 三路评测
    for method, searcher in [
        ("pg_trgm", _pg_trgm_search),
        ("vector", _vector_search),
        ("fused", _fused_search),
    ]:
        t0 = time.perf_counter()
        query_results = []
        for case in GOLDEN_CASES:
            if method == "pg_trgm":
                chunks = await searcher(db_session, case.query)
            elif method == "vector":
                chunks = await searcher(real_vr, db_session, case.query)
            else:
                chunks = await searcher(real_vr, db_session, case.query)
            result_doc_ids = [chunk_doc_map.get(c.id, -1) for c in chunks]
            query_results.append((case.query, result_doc_ids))
        elapsed = time.perf_counter() - t0
        results["timing"][method] = round(elapsed, 3)
        metrics = evaluate_results(query_results)
        # 展平指标
        results[method] = {
            "summary": {
                "recall_at_5_mean": metrics["recall@5_mean"],
                "mrr_at_10_mean": metrics["mrr@10_mean"],
            },
            "by_category": metrics["by_category"],
        }

    # 保存基线
    import os

    os.makedirs("tests/eval/artifacts", exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n[C3-BASELINE] saved to {OUTPUT_FILE}")
    print(f"[C3-BASELINE] pg_trgm R@5={results['pg_trgm']['summary']['recall_at_5_mean']:.3f} MRR@10={results['pg_trgm']['summary']['mrr_at_10_mean']:.3f}")
    print(f"[C3-BASELINE] vector  R@5={results['vector']['summary']['recall_at_5_mean']:.3f} MRR@10={results['vector']['summary']['mrr_at_10_mean']:.3f}")
    print(f"[C3-BASELINE] fused   R@5={results['fused']['summary']['recall_at_5_mean']:.3f} MRR@10={results['fused']['summary']['mrr_at_10_mean']:.3f}")

    # 基本合理性断言
    assert results["pg_trgm"]["summary"]["recall_at_5_mean"] > 0
    assert results["vector"]["summary"]["recall_at_5_mean"] > 0
    assert results["fused"]["summary"]["recall_at_5_mean"] > 0