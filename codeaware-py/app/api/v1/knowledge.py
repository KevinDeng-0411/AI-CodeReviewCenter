"""Knowledge API - /api/knowledge（RAG 上传+检索+删除）。"""

import logging

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.infra.vector_recall import VectorRecallService
from app.ai.rag.hybrid_retriever import HybridRetriever
from app.ai.rag.query_rewriter import QueryRewriter
from app.ai.rag.semantic_chunker import SemanticChunker
from app.ai.services.rag import RagService
from app.api.v1.deps import get_chat_model, get_db, get_vector_recall_service
from app.core.config import settings
from app.core.exceptions import BusinessException
from app.core.response import Result

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge"])
logger = logging.getLogger(__name__)

FILE_EMPTY = "KNOWLEDGE_FILE_EMPTY"
FILE_TYPE_UNSUPPORTED = "KNOWLEDGE_FILE_TYPE_UNSUPPORTED"
FILE_TOO_LARGE = "KNOWLEDGE_FILE_TOO_LARGE"
FILE_PARSE_FAILED = "KNOWLEDGE_FILE_PARSE_FAILED"
FILE_CONTENT_TOO_LARGE = "KNOWLEDGE_FILE_CONTENT_TOO_LARGE"


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


async def _read_limited_upload(file: UploadFile) -> bytes:
    """分块读取，避免在判定超限前一次性加载整个上传文件。"""
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(64 * 1024):
        total += len(chunk)
        if total > settings.knowledge_upload_max_bytes:
            raise BusinessException(FILE_TOO_LARGE)
        chunks.append(chunk)
    return b"".join(chunks)


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


@router.post(
    "/upload-file",
    responses={
        400: {
            "description": "文件为空、格式不支持、超限或解析失败",
            "content": {
                "application/json": {
                    "example": {
                        "code": 0,
                        "msg": FILE_PARSE_FAILED,
                        "data": None,
                    }
                }
            },
        }
    },
)
async def upload_file(
    file: UploadFile = File(
        ...,
        description="PDF/DOCX/HTML/Markdown/TXT，原始文件最大 5 MiB",
    ),
    project_name: str | None = Form(default=None, max_length=100),
    db: AsyncSession = Depends(get_db),
    llm=Depends(get_chat_model),
    vr: VectorRecallService = Depends(get_vector_recall_service),
):
    from app.ai.services.document_parser import DocumentParserService

    parser = DocumentParserService()
    filename = parser.safe_filename(file.filename)
    extension = parser.extension(filename) or "none"
    try:
        if not filename or not parser.supports_upload(filename, file.content_type):
            raise BusinessException(FILE_TYPE_UNSUPPORTED)

        content = await _read_limited_upload(file)
        if not content or not content.strip():
            raise BusinessException(FILE_EMPTY)

        try:
            text = (await parser.parse(content, filename)).strip()
        except Exception as exc:
            logger.warning(
                "knowledge upload parse failed code=%s extension=%s",
                FILE_PARSE_FAILED,
                extension,
            )
            raise BusinessException(FILE_PARSE_FAILED) from exc
        if not text:
            raise BusinessException(FILE_PARSE_FAILED)
        if len(text) > settings.knowledge_parsed_max_chars:
            raise BusinessException(FILE_CONTENT_TOO_LARGE)

        rag = _rag_service(db, llm, vr)
        doc = await rag.upload_document(
            filename,
            text,
            source_type="DOC",
            project_name=project_name,
        )
        return Result.ok({"id": doc.id, "title": doc.title})
    finally:
        await file.close()
