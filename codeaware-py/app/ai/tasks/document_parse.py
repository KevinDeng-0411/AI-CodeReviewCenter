"""文档解析+分块+embedding 异步任务。"""
import asyncio
from app.ai.celery_app import celery_app
from app.ai.infra.vector_recall import VectorRecallService
from app.ai.rag.chinese_segmenter import segment_chinese
from app.ai.rag.semantic_chunker import SemanticChunker
from app.ai.tasks.base import CodeAwareTask
from app.db.session import AsyncSessionLocal
from app.models import Document, KnowledgeChunk


@celery_app.task(bind=True, base=CodeAwareTask, name="document.parse")
def parse_document_task(self, doc_id: int, title: str, content: str,
                        source_type: str = "MANUAL", project_name: str | None = None) -> dict:
    async def _run():
        chunker = SemanticChunker()
        chunks = chunker.chunk(content, content_type="md")
        from app.ai.config import get_embedding_model
        vector_recall = VectorRecallService(get_embedding_model())
        prepared = []
        for chunk_text in chunks:
            embedding = await vector_recall.embed(chunk_text)
            prepared.append((chunk_text, embedding))
        async with AsyncSessionLocal() as session:
            doc = await session.get(Document, doc_id)
            if doc is None:
                raise ValueError(f"Document {doc_id} not found")
            for i, (chunk_text, embedding) in enumerate(prepared):
                kc = KnowledgeChunk(
                    document_id=doc_id, chunk_index=i,
                    chunk_content=chunk_text,
                    chunk_content_segmented=segment_chinese(chunk_text),
                )
                await vector_recall.store_preembedded(session, kc, embedding)
            await session.commit()
        return {"doc_id": doc_id, "chunk_count": len(prepared)}
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_run())
    finally:
        loop.close()
