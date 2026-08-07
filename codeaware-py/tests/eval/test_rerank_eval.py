"""Reranker 对比评估 — 纯 RRF vs RRF + cross-encoder 精排。

60 条 golden，同一 fixture，对比两种路径的 R@5 / MRR@10（按类别）。
需要真实 Ollama bge-m3（embedding）+ ONNX reranker（本地模型）。live_eval。
"""

import json
import os

import pytest
from sqlalchemy import text

from app.ai.config import get_embedding_model
from app.ai.infra.vector_recall import VectorRecallService
from app.ai.rag.hybrid_retriever import HybridRetriever
from app.ai.rag.lexical_recall import Bm25LexicalRecall
from app.ai.rag.reranker import CrossEncoderReranker
from app.ai.rag.semantic_chunker import SemanticChunker
from app.ai.rag.chinese_segmenter import segment_chinese
from app.ai.services.rag import RagService
from app.db.session import AsyncSessionLocal, engine
from app.models import Document, KnowledgeChunk
from tests.eval.golden_retrieval import FIXTURE_DOCS, GOLDEN_CASES, evaluate_results

pytestmark = pytest.mark.live_eval

OUTPUT_FILE = "tests/eval/artifacts/rerank_comparison.json"


class _NoopRewriter:
    """只测检索，不改写（隔离 rerank 变量）。"""

    async def rewrite(self, q):
        return [q]


async def test_rerank_vs_rrf(setup_db):
    # 1. 建索引 + fixture（同 topk_ablation）
    async with engine.begin() as conn:
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

    embedder = get_embedding_model()
    vr = VectorRecallService(embedder)
    chunker = SemanticChunker()

    # 2. 建 chunk -> 逻辑 fixture doc_id 映射（对齐 golden expected_doc_ids）
    doc_ids: dict[int, int] = {}  # fixture_doc_id -> actual db doc.id
    async with AsyncSessionLocal() as s:
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
            doc_ids[fd.doc_id] = d.id
        await s.commit()
        all_chunks = (await s.execute(
            text("SELECT id, document_id FROM knowledge_chunks WHERE chunk_content != '_init'")
        )).all()
    chunk_doc_map: dict[int, int] = {}
    for cid, pid in all_chunks:
        for fd_id, pk in doc_ids.items():
            if pid == pk:
                chunk_doc_map[cid] = fd_id
                break

    def _map_docs(docs) -> list[int]:
        """chunk -> 逻辑 fixture doc_id（保留顺序去重）。"""
        seen: set[int] = set()
        result: list[int] = []
        for r in docs:
            fd_id = chunk_doc_map.get(r.chunk.id, -1)
            if fd_id not in seen:
                seen.add(fd_id)
                result.append(fd_id)
        return result

    # 3. 两条路径对比（同一 fixture，同一 noop rewriter）
    reranker = CrossEncoderReranker()
    print(f"reranker ready: {reranker.ready}")
    rrf_results: list[tuple[str, list[int]]] = []
    rerank_results: list[tuple[str, list[int]]] = []
    golden_nonneg = [c for c in GOLDEN_CASES if c.category != "negative"]

    for case in golden_nonneg:
        async with AsyncSessionLocal() as s:
            hybrid = HybridRetriever(s, vr, Bm25LexicalRecall())
            rag_rrf = RagService(s, chunker, vr, _NoopRewriter(), hybrid, reranker=None)
            rag_rr = RagService(s, chunker, vr, _NoopRewriter(), hybrid, reranker=reranker)

            prep = await rag_rrf.prepare_search(case.query)
            docs_rrf = await rag_rrf.search_prepared(prep, top_k=5)
            rrf_results.append((case.query, _map_docs(docs_rrf)))

            prep2 = await rag_rr.prepare_search(case.query)
            docs_rr = await rag_rr.search_prepared(prep2, top_k=5, rerank_query=case.query)
            rerank_results.append((case.query, _map_docs(docs_rr)))

    # 3. 评估
    rrf_metrics = evaluate_results(rrf_results, golden_nonneg)
    rerank_metrics = evaluate_results(rerank_results, golden_nonneg)

    result = {
        "n": rrf_metrics["n"],
        "rrf_only": rrf_metrics,
        "rrf_rerank": rerank_metrics,
        "delta": {
            "recall_delta": round(rerank_metrics["recall@5_mean"] - rrf_metrics["recall@5_mean"], 4),
            "mrr_delta": round(rerank_metrics["mrr@10_mean"] - rrf_metrics["mrr@10_mean"], 4),
        },
    }
    os.makedirs("tests/eval/artifacts", exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n[RERANK-EVAL] saved to {OUTPUT_FILE}")
    print(f"[RERANK-EVAL] RRF only:  R@5={rrf_metrics['recall@5_mean']:.3f} MRR={rrf_metrics['mrr@10_mean']:.3f}")
    print(f"[RERANK-EVAL] RRF+rerank: R@5={rerank_metrics['recall@5_mean']:.3f} MRR={rerank_metrics['mrr@10_mean']:.3f}")
    print(f"[RERANK-EVAL] ΔMRR = {result['delta']['mrr_delta']:+.4f}")
