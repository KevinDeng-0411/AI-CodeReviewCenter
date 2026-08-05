#!/usr/bin/env python3
"""快速 jieba vs default BM25 中文对比评测（需要 dev PG + Ollama 运行）。"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("CODEAWARE_TESTING", "1")
os.environ.setdefault("JWT_SECRET_KEY", "test")

from sqlalchemy import text
from app.db.session import engine, AsyncSessionLocal
from app.models import Document, KnowledgeChunk
from app.ai.rag.semantic_chunker import SemanticChunker
from app.ai.rag.chinese_segmenter import segment_chinese
from app.ai.rag.lexical_recall import Bm25LexicalRecall

async def main():
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_search"))
        await conn.execute(text("DROP INDEX IF EXISTS ix_kc_chunk_content_bm25"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_kc_chunk_content_bm25 "
            "ON knowledge_chunks USING bm25 (chunk_content) "
            "WITH (key_field='id', text_fields='{\"chunk_content\": "
            "{\"tokenizer\": {\"type\": \"default\"}}}')"
        ))

    tests = [
        ("缓存", "## 缓存击穿\n热点Key失效方案：互斥锁、逻辑过期。", "缓存击穿如何解决"),
        ("雪崩", "缓存雪崩：大量key同时失效方案", "缓存雪崩"),
        ("穿透", "## 缓存穿透\n大量请求查询不存在的数据", "缓存穿透"),
        ("config", "summary_message_count watermark triggers incremental summary", "summary_message_count"),
    ]
    chunker = SemanticChunker()
    async with AsyncSessionLocal() as s:
        for title, content, _ in tests:
            doc = Document(title=title, content=content, source_type="MANUAL")
            s.add(doc); await s.flush()
            for ct in chunker.chunk(content, content_type="md"):
                s.add(KnowledgeChunk(document_id=doc.id, chunk_index=0,
                    chunk_content=ct, chunk_content_segmented=segment_chinese(ct)))
            await s.flush()
        await s.commit()

    bm25 = Bm25LexicalRecall()
    print("查询                              | default(col) | jieba(seg) |")
    print("-" * 75)
    for _, _, query in tests:
        r_old = await bm25.search(s, KnowledgeChunk, query, text_column="chunk_content", top_k=5)
        r_new = await bm25.search(s, KnowledgeChunk, query, text_column="chunk_content_segmented", top_k=5)
        print(f"{query:35} | {len(r_old):>12} | {len(r_new):>10} |")

asyncio.run(main())
