"""C4+ jieba 中文分词 BM25 对比评测（default on content vs default on segmented）。

需要真实 Ollama bge-m3 + BM25 索引。标记 live_eval。
对比同一 35 golden cases 在两种索引下的 BM25 only 指标：
- default_on_content:    生产现状（migration 0006，default tokenizer on chunk_content）
- jieba_on_segmented:    jieba 分词后 default tokenizer on chunk_content_segmented
ParadeDB 每表仅一个 BM25 索引 -> 在同一测试内 drop/create 切换。
"""

import json
import os
import time

import pytest
from sqlalchemy import select, text

from app.ai.config import get_embedding_model
from app.ai.infra.vector_recall import VectorRecallService
from app.ai.rag.chinese_segmenter import segment_chinese
from app.ai.rag.lexical_recall import Bm25LexicalRecall
from app.ai.rag.semantic_chunker import SemanticChunker
from app.db.session import AsyncSessionLocal, engine
from app.models import Document, KnowledgeChunk
from tests.eval.golden_retrieval import FIXTURE_DOCS, GOLDEN_CASES, evaluate_results

pytestmark = pytest.mark.live_eval

OUTPUT_FILE = "tests/eval/artifacts/baseline_c4_jieba.json"

BM25_TPL = (
    "CREATE INDEX {name} ON knowledge_chunks USING bm25 ({col}) "
    "WITH (key_field='id', text_fields='{{\"{col}\": "
    "{{\"tokenizer\": {{\"type\": \"default\"}}}}}}')"
)


async def _eval_bm25(session, bm25, chunk_doc_map, text_column):
    """对 35 golden cases 跑 BM25 only，返回 metrics + (query, hits) 列表。"""
    results = []
    for case in GOLDEN_CASES:
        hits = await bm25.search(
            session, KnowledgeChunk, case.query,
            text_column=text_column, top_k=10,
        )
        results.append((case.query, [chunk_doc_map.get(h[0].id, -1) for h in hits]))
    return evaluate_results(results)


async def test_c4_jieba_baseline(db_session):
    """采集 default-on-content 与 jieba-on-segmented 两路 BM25 指标 + 门禁。"""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_search"))

    # 上传 fixture 文档（提交式；segmented 列用 jieba）
    embedder = get_embedding_model()
    vr = VectorRecallService(embedder)
    chunker = SemanticChunker()
    doc_ids, chunk_doc_map = {}, {}
    async with AsyncSessionLocal() as s:
        for fd in FIXTURE_DOCS:
            doc = Document(title=fd.title, content=fd.content, source_type="MANUAL")
            s.add(doc)
            await s.flush()
            for i, ct in enumerate(chunker.chunk(fd.content, content_type="md")):
                kc = KnowledgeChunk(
                    document_id=doc.id, chunk_index=i,
                    chunk_content=ct, chunk_content_segmented=segment_chinese(ct),
                )
                await vr.store(s, kc, ct)
            doc_ids[fd.doc_id] = doc.id
        await s.commit()
        all_chunks = (await s.execute(select(KnowledgeChunk))).scalars().all()
        for c in all_chunks:
            for fd_id, pk in doc_ids.items():
                if c.document_id == pk:
                    chunk_doc_map[c.id] = fd_id
                    break

    bm25 = Bm25LexicalRecall()

    # ---- Round 1: default tokenizer on chunk_content（生产现状）----
    async with engine.begin() as conn:
        await conn.execute(text("DROP INDEX IF EXISTS ix_kc_chunk_content_segmented_bm25"))
        await conn.execute(text(BM25_TPL.format(name="ix_kc_chunk_content_bm25", col="chunk_content")))
    t0 = time.perf_counter()
    async with AsyncSessionLocal() as s:
        old_metrics = await _eval_bm25(s, bm25, chunk_doc_map, text_column="chunk_content")
    old_time = time.perf_counter() - t0

    # ---- Round 2: default tokenizer on chunk_content_segmented（jieba）----
    async with engine.begin() as conn:
        await conn.execute(text("DROP INDEX IF EXISTS ix_kc_chunk_content_bm25"))
        await conn.execute(text(BM25_TPL.format(name="ix_kc_chunk_content_segmented_bm25", col="chunk_content_segmented")))
    t0 = time.perf_counter()
    async with AsyncSessionLocal() as s:
        new_metrics = await _eval_bm25(s, bm25, chunk_doc_map, text_column="chunk_content_segmented")
    new_time = time.perf_counter() - t0

    # ---- 汇总 ----
    results = {
        "default_on_content": {
            "summary": {
                "recall_at_5_mean": old_metrics["recall@5_mean"],
                "mrr_at_10_mean": old_metrics["mrr@10_mean"],
            },
            "by_category": old_metrics["by_category"],
        },
        "jieba_on_segmented": {
            "summary": {
                "recall_at_5_mean": new_metrics["recall@5_mean"],
                "mrr_at_10_mean": new_metrics["mrr@10_mean"],
            },
            "by_category": new_metrics["by_category"],
        },
        "timing": {"default_on_content": round(old_time, 3), "jieba_on_segmented": round(new_time, 3)},
    }

    # ---- 门禁 ----
    old_chinese = old_metrics["by_category"].get("chinese_exact", {}).get("recall@5_mean", 0)
    new_chinese = new_metrics["by_category"].get("chinese_exact", {}).get("recall@5_mean", 0)
    old_rare = old_metrics["by_category"].get("rare_identifier", {}).get("mrr@10_mean", 0)
    new_rare = new_metrics["by_category"].get("rare_identifier", {}).get("mrr@10_mean", 0)
    gates = {
        "chinese_exact_r5_improved_or_equal": new_chinese >= old_chinese,
        "chinese_exact_r5_gte_0_5": new_chinese >= 0.5,
        "rare_identifier_mrr_not_degraded": new_rare >= old_rare,
        "bm25_r5_not_degraded": new_metrics["recall@5_mean"] >= old_metrics["recall@5_mean"],
    }
    results["quality_gates"] = gates

    os.makedirs("tests/eval/artifacts", exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n[C4-JIEBA] saved to {OUTPUT_FILE}")
    print(f"[C4-JIEBA] default_on_content  R@5={old_metrics['recall@5_mean']:.3f} MRR={old_metrics['mrr@10_mean']:.3f}  chinese_exact R@5={old_chinese:.3f}")
    print(f"[C4-JIEBA] jieba_on_segmented  R@5={new_metrics['recall@5_mean']:.3f} MRR={new_metrics['mrr@10_mean']:.3f}  chinese_exact R@5={new_chinese:.3f}")
    print(f"[C4-JIEBA] gates: {gates}")
    assert gates["chinese_exact_r5_gte_0_5"], "jieba 中文精确 R@5 < 0.5，方案无效"
    assert gates["rare_identifier_mrr_not_degraded"], "jieba 让稀有标识符 MRR 下降，方案不可接受"
