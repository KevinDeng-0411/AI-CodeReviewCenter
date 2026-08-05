"""生成层评估基线（自实现 RAGAS 指标）——Faithfulness + Answer Relevancy。

衡量"答案质量"，补齐检索层（R@5/MRR）覆盖不到的生成层。

指标（自实现，对齐 RAGAS 语义）：
- Faithfulness：回答的主张是否被检索 context 支撑（0-1）
- Answer Relevancy：回答切题程度 = 反向生成问题与原问题的 embedding 相似度（0-1）

需要真实 DeepSeek（生成+judge）+ Ollama bge-m3（embedding）。live_eval。
"""

import json
import os

import pytest

from app.ai.config import get_chat_model, get_embedding_model
from app.ai.infra.vector_recall import VectorRecallService
from app.ai.rag.chinese_segmenter import segment_chinese
from app.ai.rag.hybrid_retriever import HybridRetriever
from app.ai.rag.lexical_recall import Bm25LexicalRecall
from app.ai.rag.semantic_chunker import SemanticChunker
from app.db.session import AsyncSessionLocal, engine
from app.models import Document, KnowledgeChunk
from tests.eval.golden_retrieval import FIXTURE_DOCS, GOLDEN_CASES

pytestmark = pytest.mark.live_eval

OUTPUT_FILE = "tests/eval/artifacts/ragas_generation.json"
SAMPLE_LIMIT = 35  # 全部 35 条；可改小控制成本


# ---------- Judge 提示词 ----------

FAITHFULNESS_PROMPT = """你是 RAG 系统评估器。判断"回答"的主张是否都被"参考上下文"支撑。
只输出 JSON: {{"supported": 主张数中被上下文支撑的数量, "total": 回答中的总主张数}}

参考上下文:
{context}

回答:
{answer}
"""

ANSWER_RELEVANCY_PROMPT = """你是 RAG 系统评估器。根据"回答"生成 1 个最相关的问题（只输出问题本身，不要其他文字）。
回答:
{answer}
"""


def _build_context(chunks: list[str], max_chars: int = 1500) -> str:
    """拼接检索到的 chunk 为 context（截断到 max_chars）。"""
    parts = []
    total = 0
    for c in chunks:
        if total >= max_chars:
            break
        parts.append(c[:max_chars])
        total += len(c)
    return "\n\n".join(parts) or "（无检索上下文）"


async def test_ragas_generation_baseline(setup_db):
    # 1. 上传 fixture docs（真实 embedding）+ 建检索器
    embedder = get_embedding_model()
    vr = VectorRecallService(embedder)
    bm25 = Bm25LexicalRecall()
    llm = get_chat_model()
    chunker = SemanticChunker()

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

    # 2. 对每条 golden 跑评估
    rows = []
    for i, case in enumerate(GOLDEN_CASES[:SAMPLE_LIMIT]):
        query = case.query
        async with AsyncSessionLocal() as s:
            retriever = HybridRetriever(s, vr, bm25)
            hits = await retriever.search(query, top_k=3)
            chunks = [h.chunk.chunk_content for h in hits]
        context = _build_context(chunks)
        if not context or "（无检索上下文）" in context:
            rows.append({"query": query, "faithfulness": None, "answer_relevancy": None,
                         "skipped": "no_context"})
            continue

        # 3. 生成回答（基于 context）
        try:
            resp = await llm.ainvoke(
                f"基于以下知识回答问题。如果知识不足，直接说明不知道。\n\n知识:\n{context}\n\n问题: {query}"
            )
            answer = resp.content if hasattr(resp, "content") else str(resp)
        except Exception as exc:  # noqa: BLE001
            rows.append({"query": query, "faithfulness": None, "answer_relevancy": None,
                         "skipped": f"gen_failed: {type(exc).__name__}"})
            continue

        # 4. Faithfulness：judge 判断主张支撑比例
        try:
            fj = await llm.ainvoke(
                FAITHFULNESS_PROMPT.format(context=context[:4000], answer=answer[:2000])
            )
            fj_text = fj.content if hasattr(fj, "content") else str(fj)
            import re

            m = re.search(r"\{.*\}", fj_text, re.DOTALL)
            fj_json = json.loads(m.group(0)) if m else {}
            total = int(fj_json.get("total", 0))
            supported = int(fj_json.get("supported", 0))
            faithfulness = round(supported / total, 3) if total > 0 else None
        except Exception as exc:  # noqa: BLE001
            faithfulness = None

        # 5. Answer Relevancy：反向生成问题 + embedding 相似度
        try:
            ar = await llm.ainvoke(ANSWER_RELEVANCY_PROMPT.format(answer=answer[:2000]))
            gen_q = ar.content if hasattr(ar, "content") else str(ar)
            gen_q = gen_q.strip().strip('"').strip()
            q_vec = await embedder.aembed_query(query)
            g_vec = await embedder.aembed_query(gen_q)
            # cosine similarity
            dot = sum(a * b for a, b in zip(q_vec, g_vec))
            norm_q = sum(a * a for a in q_vec) ** 0.5
            norm_g = sum(b * b for b in g_vec) ** 0.5
            relevancy = round(dot / (norm_q * norm_g + 1e-9), 3)
        except Exception as exc:  # noqa: BLE001
            relevancy = None

        rows.append({"query": query, "faithfulness": faithfulness, "answer_relevancy": relevancy})
        print(f"[RAGAS] {i+1}/{SAMPLE_LIMIT} q={query[:16]}.. "
              f"faith={faithfulness} relev={relevancy}")

    # 6. 汇总
    faith_vals = [r["faithfulness"] for r in rows if r.get("faithfulness") is not None]
    relev_vals = [r["answer_relevancy"] for r in rows if r.get("answer_relevancy") is not None]
    result = {
        "n": len(rows),
        "faithfulness": {"mean": round(sum(faith_vals) / len(faith_vals), 3) if faith_vals else None,
                         "n": len(faith_vals)},
        "answer_relevancy": {"mean": round(sum(relev_vals) / len(relev_vals), 3) if relev_vals else None,
                             "n": len(relev_vals)},
        "rows": rows,
    }
    os.makedirs("tests/eval/artifacts", exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n[RAGAS] saved to {OUTPUT_FILE}")
    print(f"[RAGAS] Faithfulness mean={result['faithfulness']['mean']} (n={result['faithfulness']['n']})")
    print(f"[RAGAS] Answer Relevancy mean={result['answer_relevancy']['mean']} (n={result['answer_relevancy']['n']})")
