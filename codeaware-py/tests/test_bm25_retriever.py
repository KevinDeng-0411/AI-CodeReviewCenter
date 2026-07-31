"""C4-B: BM25 词法召回测试 - ParadeDB pg_search + chinese_compatible tokenizer。

需要 BM25 镜像（codeaware/pgvector-pgsearch:pg16-v0.12.0）。
BM25 索引由 bm25_ready fixture 创建（create_all 不含 ParadeDB 索引）。
"""

import pytest
from sqlalchemy import text

from app.ai.rag.lexical_recall import Bm25LexicalRecall, PgTrgmLexicalRecall
from app.ai.rag.hybrid_retriever import HybridRetriever
from app.db.session import engine
from app.models import Document, KnowledgeChunk


@pytest.fixture
async def bm25_ready(setup_db):
    """函数级：创建 pg_search 扩展 + BM25 索引 + dummy 行初始化 Tantivy。
    teardown 删除索引 + dummy，确保非 BM25 测试不受影响（Tantivy 不支持事务回滚）。"""
    from app.db.session import AsyncSessionLocal

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_search"))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_kc_chunk_content_bm25 "
            "ON knowledge_chunks USING bm25 (chunk_content) "
            "WITH (key_field='id', text_fields='{\"chunk_content\": {\"tokenizer\": {\"type\": \"chinese_compatible\"}}}')"
        ))
    # ParadeDB v0.12.0:空表上建 BM25 索引不初始化 Tantivy 文件 -> 首次 INSERT 报错
    async with AsyncSessionLocal() as s:
        doc = Document(title="_bm25_init", content="_init", source_type="MANUAL")
        s.add(doc)
        await s.flush()
        s.add(KnowledgeChunk(document_id=doc.id, chunk_index=0, chunk_content="_bm25_init"))
        await s.commit()
    yield
    # 清理：删除索引 + dummy（Tantivy 不支持 rollback，必须显式清理）
    async with engine.begin() as conn:
        await conn.execute(text("DROP INDEX IF EXISTS ix_kc_chunk_content_bm25"))
    async with AsyncSessionLocal() as s:
        await s.execute(text("DELETE FROM knowledge_chunks WHERE chunk_content = '_bm25_init'"))
        await s.execute(text("DELETE FROM documents WHERE title = '_bm25_init'"))
        await s.commit()


async def _upload_doc(db_session, title, content, vr):
    """上传一篇文档（含 embedding），返回 doc_id。"""
    from app.ai.rag.semantic_chunker import SemanticChunker
    chunker = SemanticChunker()
    doc = Document(title=title, content=content, source_type="MANUAL")
    db_session.add(doc)
    await db_session.flush()
    chunks = chunker.chunk(content, content_type="md")
    for i, c in enumerate(chunks):
        kc = KnowledgeChunk(document_id=doc.id, chunk_index=i, chunk_content=c)
        await vr.store(db_session, kc, c)
    await db_session.flush()
    return doc.id


async def test_bm25_chinese_query(bm25_ready, db_session, vector_recall):
    """BM25 中文查询：chinese_compatible tokenizer 命中中文内容。"""
    await _upload_doc(db_session, "缓存", "## 缓存击穿\n热点Key失效方案：互斥锁、逻辑过期。", vector_recall)
    await _upload_doc(db_session, "RAG", "## RAG 检索\n查询改写 + 混合检索 + RRF 融合。", vector_recall)

    bm25 = Bm25LexicalRecall()
    results = await bm25.search(db_session, KnowledgeChunk, "缓存击穿", text_column="chunk_content", top_k=5)
    assert len(results) > 0
    assert "缓存" in results[0][0].chunk_content


async def test_bm25_english_query(bm25_ready, db_session, vector_recall):
    """BM25 英文查询：命中英文标识符。"""
    await _upload_doc(db_session, "FastAPI", "## FastAPI async\nTurnCoordinator manages session lifecycle.", vector_recall)

    bm25 = Bm25LexicalRecall()
    results = await bm25.search(db_session, KnowledgeChunk, "TurnCoordinator", text_column="chunk_content", top_k=5)
    assert len(results) > 0
    assert "TurnCoordinator" in results[0][0].chunk_content


async def test_bm25_rare_identifier(bm25_ready, db_session, vector_recall):
    """BM25 稀有标识符：精确匹配 snake_case/类名。"""
    await _upload_doc(db_session, "config", "summary_message_count watermark triggers summary.", vector_recall)
    await _upload_doc(db_session, "other", "完全无关的内容 about weather and food.", vector_recall)

    bm25 = Bm25LexicalRecall()
    results = await bm25.search(db_session, KnowledgeChunk, "summary_message_count", text_column="chunk_content", top_k=5)
    assert len(results) > 0
    assert "summary_message_count" in results[0][0].chunk_content


async def test_bm25_no_results_for_unrelated(bm25_ready, db_session, vector_recall):
    """BM25 不相关查询返回空。"""
    await _upload_doc(db_session, "cache", "缓存击穿方案", vector_recall)

    bm25 = Bm25LexicalRecall()
    results = await bm25.search(db_session, KnowledgeChunk, "股票投资", text_column="chunk_content", top_k=5)
    assert len(results) == 0


async def test_bm25_fallback_returns_empty_on_error(db_session):
    """BM25 扩展/索引不可用时返回空列表（降级纯向量）。"""
    bm25 = Bm25LexicalRecall()
    # 不创建 BM25 索引 -> @@@ 操作符无索引可用 -> 异常 -> 空列表
    results = await bm25.search(db_session, KnowledgeChunk, "test", text_column="chunk_content", top_k=5)
    assert results == []


async def test_hybrid_with_bm25_returns_match_type(bm25_ready, db_session, vector_recall):
    """HybridRetriever + Bm25LexicalRecall：混合检索返回结果。"""
    await _upload_doc(db_session, "hybrid", "缓存击穿热点Key失效方案互斥锁", vector_recall)

    bm25 = Bm25LexicalRecall()
    retriever = HybridRetriever(db_session, vector_recall, bm25)
    results = await retriever.search("缓存击穿", top_k=5)
    assert len(results) > 0
    # 直接 BM25 搜索验证索引可用
    direct = await bm25.search(db_session, KnowledgeChunk, "缓存击穿", text_column="chunk_content", top_k=5)
    assert len(direct) > 0
    # 若 BM25 经 hybrid 路径也命中，应有 keyword/both；至少 vector 命中
    match_types = {r.match_type for r in results}
    assert "vector" in match_types


async def test_hybrid_with_pg_trgm_still_works(bm25_ready, db_session, vector_recall):
    """HybridRetriever + PgTrgmLexicalRecall：pg_trgm 回退后端仍正常。"""
    await _upload_doc(db_session, "trgm", "TurnCoordinator session lifecycle management", vector_recall)

    pg_trgm = PgTrgmLexicalRecall()
    retriever = HybridRetriever(db_session, vector_recall, pg_trgm)
    results = await retriever.search("TurnCoordinator", top_k=5)
    assert len(results) > 0


async def test_bm25_upsert_index_consistency(bm25_ready, db_session, vector_recall):
    """上传 -> 查到 -> 删除文档 -> 查不到（索引一致性）。"""
    doc_id = await _upload_doc(db_session, "upsert", "缓存雪崩大量key同时失效方案", vector_recall)

    bm25 = Bm25LexicalRecall()
    results_before = await bm25.search(db_session, KnowledgeChunk, "缓存雪崩", text_column="chunk_content", top_k=5)
    assert len(results_before) > 0

    # 删除文档 -> chunks CASCADE -> BM25 索引应自动更新
    doc = await db_session.get(Document, doc_id)
    if doc:
        await db_session.delete(doc)
        await db_session.flush()

    results_after = await bm25.search(db_session, KnowledgeChunk, "缓存雪崩", text_column="chunk_content", top_k=5)
    assert len(results_after) == 0
