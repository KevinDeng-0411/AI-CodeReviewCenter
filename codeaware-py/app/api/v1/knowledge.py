"""Knowledge API - /api/knowledge（RAG 上传+检索+删除）。"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.infra.vector_recall import VectorRecallService
from app.ai.rag.hybrid_retriever import HybridRetriever
from app.ai.rag.query_rewriter import QueryRewriter
from app.ai.rag.semantic_chunker import SemanticChunker
from app.ai.services.rag import RagService
from app.api.v1.deps import get_chat_model, get_db, get_vector_recall_service
from app.core.response import Result

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge"])


class KnowledgeUploadRequest(BaseModel):
    title: str
    content: str
    source_type: str = "MANUAL"
    project_name: str | None = None


class KnowledgeSearchRequest(BaseModel):
    query: str
    top_k: int = 5


def _rag_service(db, llm, vr):
    return RagService(db, SemanticChunker(), vr, QueryRewriter(llm), HybridRetriever(db, vr))


@router.post("/upload")
async def upload(
    req: KnowledgeUploadRequest,
    db: AsyncSession = Depends(get_db),
    llm=Depends(get_chat_model),
    vr: VectorRecallService = Depends(get_vector_recall_service),
):
    rag = _rag_service(db, llm, vr)
    doc = await rag.upload_document(req.title, req.content, req.source_type, req.project_name)
    return Result.ok({"id": doc.id, "title": doc.title})


@router.post("/search")
async def search(
    req: KnowledgeSearchRequest,
    db: AsyncSession = Depends(get_db),
    llm=Depends(get_chat_model),
    vr: VectorRecallService = Depends(get_vector_recall_service),
):
    rag = _rag_service(db, llm, vr)
    results = await rag.search(req.query, top_k=req.top_k)
    return Result.ok(
        [
            {
                "score": r.score,
                "matchType": r.match_type,
                "document_id": r.chunk.document_id,
                "chunk_content": r.chunk.chunk_content,
            }
            for r in results
        ]
    )


@router.delete("/{doc_id}")
async def delete(doc_id: int, db: AsyncSession = Depends(get_db)):
    from app.models import Document
    doc = await db.get(Document, doc_id)
    if doc:
        await db.delete(doc)
        await db.commit()
    return Result.ok()
