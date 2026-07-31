"""C4-D: BM25 基线评测 - BM25 only / BM25+vector fused 两路指标。

需要真实 Ollama bge-m3 + BM25 索引。标记 live_eval。
对照 C3 基线（baseline_c3_pg_trgm.json）验证质量门禁。
使用提交式 session（Tantovy 不支持事务回滚）。
"""

import json
import os
import time

import pytest
from sqlalchemy import select, text

from app.ai.config import get_embedding_model
from app.ai.infra.vector_recall import VectorRecallService
from app.ai.rag.hybrid_retriever import HybridRetriever
from app.ai.rag.lexical_recall import Bm25LexicalRecall
from app.ai.rag.semantic_chunker import SemanticChunker
from app.db.session import AsyncSessionLocal, engine
from app.models import Document, KnowledgeChunk
from tests.eval.golden_retrieval import FIXTURE_DOCS, GOLDEN_CASES, evaluate_results

pytestmark = pytest.mark.live_eval

OUTPUT_FILE = "tests/eval/artifacts/baseline_c4_bm25.json"
C3_BASELINE_FILE = "tests/eval/artifacts/baseline_c3_pg_trgm.json"


async def test_c4_bm25_baseline_and_quality_gates(db_session):
    """采集 C4 BM25 基线 + 对照 C3 质量门禁。使用提交式 session。"""
    # 1. 建 BM25 索引 + dummy 初始化
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_search"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_kc_chunk_content_bm25 "
            "ON knowledge_chunks USING bm25 (chunk_content) "
            "WITH (key_field='id', text_fields='{\"chunk_content\": {\"tokenizer\": {\"type\": \"chinese_compatible\"}}}')"
        ))
    async with AsyncSessionLocal() as s:
        doc = Document(title="_init", content="_init", source_type="MANUAL")
        s.add(doc)
        await s.flush()
        s.add(KnowledgeChunk(document_id=doc.id, chunk_index=0, chunk_content="_init"))
        await s.commit()

    # 2. 上传 fixture 文档（提交式，Tantovy 可靠）
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
                kc = KnowledgeChunk(document_id=doc.id, chunk_index=i, chunk_content=ct)
                await vr.store(s, kc, ct)
            doc_ids[fd.doc_id] = doc.id
        await s.commit()
        # 建立 chunk_id -> doc_id 映射
        all_chunks = (await s.execute(select(KnowledgeChunk))).scalars().all()
        for c in all_chunks:
            for fd_id, pk in doc_ids.items():
                if c.document_id == pk:
                    chunk_doc_map[c.id] = fd_id
                    break

    bm25 = Bm25LexicalRecall()

    # 3. 预热
    for q in [c.query for c in GOLDEN_CASES[:3]]:
        async with AsyncSessionLocal() as s:
            await bm25.search(s, KnowledgeChunk, q, text_column="chunk_content", top_k=1)

    # 4. BM25 only 评测
    t0 = time.perf_counter()
    bm25_results = []
    for case in GOLDEN_CASES:
        async with AsyncSessionLocal() as s:
            hits = await bm25.search(s, KnowledgeChunk, case.query, text_column="chunk_content", top_k=10)
            bm25_results.append((case.query, [chunk_doc_map.get(h[0].id, -1) for h in hits]))
    bm25_time = time.perf_counter() - t0
    bm25_metrics = evaluate_results(bm25_results)

    # 5. BM25 + vector fused 评测
    t0 = time.perf_counter()
    fused_results = []
    for case in GOLDEN_CASES:
        async with AsyncSessionLocal() as s:
            retriever = HybridRetriever(s, vr, bm25)
            hits = await retriever.search(case.query, top_k=10)
            fused_results.append((case.query, [chunk_doc_map.get(h.chunk.id, -1) for h in hits]))
    fused_time = time.perf_counter() - t0
    fused_metrics = evaluate_results(fused_results)

    # 6. 汇总
    results = {
        "bm25_only": {
            "summary": {"recall_at_5_mean": bm25_metrics["recall@5_mean"], "mrr_at_10_mean": bm25_metrics["mrr@10_mean"]},
            "by_category": bm25_metrics["by_category"],
        },
        "bm25_fused": {
            "summary": {"recall_at_5_mean": fused_metrics["recall@5_mean"], "mrr_at_10_mean": fused_metrics["mrr@10_mean"]},
            "by_category": fused_metrics["by_category"],
        },
        "timing": {"bm25_only": round(bm25_time, 3), "bm25_fused": round(fused_time, 3)},
    }

    # 7. 加载 C3 基线对照 + 质量门禁
    c3 = {}
    if os.path.exists(C3_BASELINE_FILE):
        with open(C3_BASELINE_FILE) as f:
            c3 = json.load(f)

    c3_fused_r5 = c3.get("fused", {}).get("summary", {}).get("recall_at_5_mean", 0)
    c3_pg_trgm_rare_mrr = c3.get("pg_trgm", {}).get("by_category", {}).get("rare_identifier", {}).get("mrr@10_mean", 0)
    c3_vector_semantic_r5 = c3.get("vector", {}).get("by_category", {}).get("semantic_paraphrase", {}).get("recall@5_mean", 0)
    c4_fused_r5 = results["bm25_fused"]["summary"]["recall_at_5_mean"]
    c4_bm25_rare_mrr = results["bm25_only"]["by_category"].get("rare_identifier", {}).get("mrr@10_mean", 0)
    c4_fused_semantic_r5 = results["bm25_fused"]["by_category"].get("semantic_paraphrase", {}).get("recall@5_mean", 0)

    gates = {
        "fused_recall_at_5_gte_c3": c4_fused_r5 >= c3_fused_r5,
        "rare_identifier_mrr_gt_pg_trgm": c4_bm25_rare_mrr > c3_pg_trgm_rare_mrr,
        "semantic_recall_at_5_gte_vector_only": c4_fused_semantic_r5 >= c3_vector_semantic_r5,
    }
    results["quality_gates"] = gates
    results["c3_comparison"] = {
        "c3_fused_r5": c3_fused_r5, "c4_fused_r5": c4_fused_r5,
        "c3_pg_trgm_rare_mrr": c3_pg_trgm_rare_mrr, "c4_bm25_rare_mrr": c4_bm25_rare_mrr,
        "c3_vector_semantic_r5": c3_vector_semantic_r5, "c4_fused_semantic_r5": c4_fused_semantic_r5,
    }

    os.makedirs("tests/eval/artifacts", exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n[C4-BASELINE] saved to {OUTPUT_FILE}")
    print(f"[C4-BASELINE] BM25 only  R@5={results['bm25_only']['summary']['recall_at_5_mean']:.3f} MRR@10={results['bm25_only']['summary']['mrr_at_10_mean']:.3f}")
    print(f"[C4-BASELINE] BM25 fused R@5={results['bm25_fused']['summary']['recall_at_5_mean']:.3f} MRR@10={results['bm25_fused']['summary']['mrr_at_10_mean']:.3f}")
    print(f"[C4-GATES] fused_r5_gte_c3={gates['fused_recall_at_5_gte_c3']} ({c4_fused_r5:.3f} vs {c3_fused_r5:.3f})")
    print(f"[C4-GATES] rare_mrr_gt_pg_trgm={gates['rare_identifier_mrr_gt_pg_trgm']} ({c4_bm25_rare_mrr:.3f} vs {c3_pg_trgm_rare_mrr:.3f})")
    print(f"[C4-GATES] semantic_r5_gte_vector={gates['semantic_recall_at_5_gte_vector_only']} ({c4_fused_semantic_r5:.3f} vs {c3_vector_semantic_r5:.3f})")

    assert results["bm25_only"]["summary"]["recall_at_5_mean"] > 0
    assert results["bm25_fused"]["summary"]["recall_at_5_mean"] > 0
