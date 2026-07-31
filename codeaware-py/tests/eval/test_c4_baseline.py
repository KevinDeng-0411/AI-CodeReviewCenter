"""C4-D: BM25 检索基线指标采集 - BM25 only / BM25+vector fused 两路对照。

C4-A 已有 C3 pg_trgm 基线(baseline_c3_pg_trgm.json)。本文件采集 C4 基线，
供三路对照门禁(C3 pg_trgm / C4 BM25 only / C4 BM25+vector fused)。
需要真实 Ollama bge-m3 + BM25 镜像。标记 live_eval。
"""

import json
import os
import time

import re

import pytest
from sqlalchemy import select, text

from app.ai.config import get_embedding_model
from app.ai.infra.vector_recall import VectorRecallService
from app.ai.rag.hybrid_retriever import HybridRetriever
from app.ai.rag.lexical_recall import Bm25LexicalRecall
from app.db.session import AsyncSessionLocal
from app.models import Document, KnowledgeChunk
from tests.eval.golden_retrieval import FIXTURE_DOCS, GOLDEN_CASES, evaluate_results

pytestmark = pytest.mark.live_eval
OUTPUT_FILE = "tests/eval/artifacts/baseline_c4_bm25.json"


@pytest.fixture
def real_vr():
    return VectorRecallService(get_embedding_model())


@pytest.fixture
async def bm25_index(setup_db):
    """创建 BM25 索引（default tokenizer，英文标识符更强）。"""
    async with AsyncSessionLocal() as s:
        for ext in ("vector", "pg_search", "pg_trgm"):
            await s.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
        await s.execute(text("DROP INDEX IF EXISTS ix_kc_chunk_content_bm25"))
        await s.execute(text(
            "CREATE INDEX ix_kc_chunk_content_bm25 ON knowledge_chunks"
            " USING bm25 (chunk_content)"
            " WITH (key_field='id', text_fields='{\"chunk_content\": {\"tokenizer\": {\"type\": \"default\"}}}')"
        ))
        await s.commit()


@pytest.fixture
async def upload_fixture(db_session, real_vr):
    """上传 FIXTURE_DOCS（真实 bge-m3 embedding）。"""
    doc_ids = {}
    for fd in FIXTURE_DOCS:
        doc = Document(title=fd.title, content=fd.content, source_type="MANUAL")
        db_session.add(doc)
        await db_session.flush()
        chunks = [c.strip() for c in re.split(r'\n\n+', fd.content) if c.strip()]
        if not chunks:
            chunks = [fd.content.strip()]
        for i, chunk_text in enumerate(chunks):
            kc = KnowledgeChunk(document_id=doc.id, chunk_index=i, chunk_content=chunk_text)
            await real_vr.store(db_session, kc, chunk_text)
        doc_ids[fd.doc_id] = doc.id
        await db_session.flush()
    return doc_ids


async def _bm25_search(db_session, query: str, top_k: int = 10) -> list[KnowledgeChunk]:
    """BM25 only 召回。@@@ 右边必须 text literal。"""
    from sqlalchemy import text as sqla_text

    q = query.replace("'", "''")
    rows = (
        await db_session.execute(
            select(KnowledgeChunk)
            .where(sqla_text(f"knowledge_chunks.chunk_content @@@ '{q}'"))
            .limit(top_k * 3)
        )
    ).scalars().all()
    return list(rows)


async def _fused_search(real_vr, db_session, query: str, top_k: int = 10) -> list[KnowledgeChunk]:
    """BM25 + vector + RRF 融合。"""
    hr = HybridRetriever(db_session, real_vr, Bm25LexicalRecall())
    results = await hr.search(query, top_k=top_k)
    return [r.chunk for r in results]


async def test_c4_baseline_metrics(db_session, real_vr, bm25_index, upload_fixture):
    """采集 C4 BM25-only 与 BM25+vector fused 指标。"""
    doc_ids = upload_fixture
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

    results = {"bm25": [], "fused": [], "timing": {}}
    methods = [("bm25", _bm25_search), ("fused", _fused_search)]
    for method, searcher in methods:
        t0 = time.perf_counter()
        query_results = []
        for case in GOLDEN_CASES:
            if method == "bm25":
                chunks = await searcher(db_session, case.query)
            else:
                chunks = await searcher(real_vr, db_session, case.query)
            result_doc_ids = [chunk_doc_map.get(c.id, -1) for c in chunks]
            query_results.append((case.query, result_doc_ids))
        elapsed = time.perf_counter() - t0
        results["timing"][method] = round(elapsed, 3)
        metrics = evaluate_results(query_results)
        results[method] = {
            "summary": {
                "recall_at_5_mean": metrics["recall@5_mean"],
                "mrr_at_10_mean": metrics["mrr@10_mean"],
            },
            "by_category": metrics["by_category"],
        }

    os.makedirs("tests/eval/artifacts", exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"[C4-BASELINE] saved to {OUTPUT_FILE}")
    print(f"[C4-BASELINE] BM25 only R@5={results['bm25']['summary']['recall_at_5_mean']:.3f} MRR@10={results['bm25']['summary']['mrr_at_10_mean']:.3f}")
    print(f"[C4-BASELINE] fused      R@5={results['fused']['summary']['recall_at_5_mean']:.3f} MRR@10={results['fused']['summary']['mrr_at_10_mean']:.3f}")
    assert results["bm25"]["summary"]["recall_at_5_mean"] > 0
