"""top_k 敏感性分析 - 用数据决定检索层 K 值。

扫描 top_k ∈ {3, 5, 8, 10, 15}，对 35 条 golden cases 跑生产路径
（HybridRetriever.search_by_vector, BM25+vector RRF, segmented 列）,
记录 fused R@5 / MRR@10 / 去重后实际条数 / 估算 prompt token。

需要真实 Ollama bge-m3 + BM25 索引。标记 live_eval。
"""

import json
import os

import pytest
from sqlalchemy import text

from app.ai.config import get_embedding_model
from app.ai.infra.vector_recall import VectorRecallService
from app.ai.rag.hybrid_retriever import HybridRetriever
from app.ai.rag.lexical_recall import Bm25LexicalRecall
from app.ai.rag.semantic_chunker import SemanticChunker
from app.ai.rag.chinese_segmenter import segment_chinese
from app.db.session import AsyncSessionLocal, engine
from app.models import Document, KnowledgeChunk
from tests.eval.golden_retrieval import FIXTURE_DOCS, GOLDEN_CASES, evaluate_results

pytestmark = pytest.mark.live_eval

OUTPUT_FILE = "tests/eval/artifacts/topk_ablation.json"
TOP_K_GRID = [3, 5, 8, 10, 15]
# 500 字 chunk ≈ 300 token（估算用）
TOKENS_PER_CHUNK = 300


async def test_topk_sensitivity(setup_db):
    # 1. 建 segmented BM25 索引 + dummy 行初始化 Tantivy
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

    # 2. 上传 FIXTURE_DOCS（真实 embedding + segmented 列）
    embedder = get_embedding_model()
    vr = VectorRecallService(embedder)
    chunker = SemanticChunker()
    doc_ids = {}
    chunk_doc_map = {}
    async with AsyncSessionLocal() as s:
        for fd in FIXTURE_DOCS:
            doc = Document(title=fd.title, content=fd.content, source_type="MANUAL")
            s.add(doc)
            await s.flush()
            chunks = chunker.chunk(fd.content, content_type="md")
            for i, ct in enumerate(chunks):
                emb = await vr.embed(ct)
                kc = KnowledgeChunk(
                    document_id=doc.id, chunk_index=i,
                    chunk_content=ct, chunk_content_segmented=segment_chinese(ct),
                    embedding=emb,
                )
                s.add(kc)
            doc_ids[fd.doc_id] = doc.id
        await s.commit()
        all_chunks = (await s.execute(
            text("SELECT id, document_id FROM knowledge_chunks WHERE chunk_content != '_init'")
        )).all()
        for cid, pid in all_chunks:
            for fd_id, pk in doc_ids.items():
                if pid == pk:
                    chunk_doc_map[cid] = fd_id
                    break

    # 3. 预热 + 每档评测
    bm25 = Bm25LexicalRecall()
    rows = []
    for k in TOP_K_GRID:
        retriever = HybridRetriever(await _session(), vr, bm25)
        results = []
        actual_counts = []
        for case in GOLDEN_CASES:
            async with AsyncSessionLocal() as s:
                qv = await vr.embed(case.query)
                retriever.session = s
                hits = await retriever.search_by_vector(case.query, qv, top_k=k)
            results.append(
                (case.query, [chunk_doc_map.get(h.chunk.id, -1) for h in hits])
            )
            actual_counts.append(len(hits))
        metrics = evaluate_results(results)

        avg_actual = sum(actual_counts) / len(actual_counts)
        est_tokens = int(avg_actual * TOKENS_PER_CHUNK)
        rows.append({
            "top_k": k,
            "fused_recall_at_5": metrics["recall@5_mean"],
            "fused_mrr_at_10": metrics["mrr@10_mean"],
            "avg_actual_after_dedup": round(avg_actual, 2),
            "est_prompt_tokens": est_tokens,
            "by_category": metrics["by_category"],
        })
        print(f"[TOPK] k={k:>2}  R@5={metrics['recall@5_mean']:.3f}  "
              f"MRR@10={metrics['mrr@10_mean']:.3f}  "
              f"avg_actual={avg_actual:.1f}  est_tokens={est_tokens}")

    # 4. 汇总 JSON
    os.makedirs("tests/eval/artifacts", exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump({"grid": TOP_K_GRID, "rows": rows}, f, indent=2, ensure_ascii=False)
    print(f"\n[TOPK] saved to {OUTPUT_FILE}")


async def _session():
    """返回一个 AsyncSession（供 HybridRetriever 构造占位，实际查询前替换）。"""
    from app.db.session import AsyncSessionLocal as _ASL
    return _ASL()
