"""Knowledge API - /api/knowledge（RAG 上传+检索+删除）。"""

import logging

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.infra.vector_recall import VectorRecallService
from app.ai.rag.hybrid_retriever import HybridRetriever
from app.ai.rag.query_rewriter import QueryRewriter
from app.ai.rag.semantic_chunker import SemanticChunker
from app.ai.services.rag import RagService
from app.api.v1.deps import get_chat_model, get_db, get_lexical_recall, get_vector_recall_service, get_current_user
from app.core.config import settings
from app.core.exceptions import BusinessException
from app.core.response import Result
from app.schemas.knowledge import (
    DocumentListVO,
    DocumentVO,
    KnowledgeDocumentVO,
    KnowledgeSearchHit,
    KnowledgeSearchRequest,
    KnowledgeUploadRequest,
)

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge"], dependencies=[Depends(get_current_user)])
logger = logging.getLogger(__name__)

FILE_EMPTY = "KNOWLEDGE_FILE_EMPTY"
FILE_TYPE_UNSUPPORTED = "KNOWLEDGE_FILE_TYPE_UNSUPPORTED"
FILE_TOO_LARGE = "KNOWLEDGE_FILE_TOO_LARGE"
FILE_PARSE_FAILED = "KNOWLEDGE_FILE_PARSE_FAILED"
FILE_CONTENT_TOO_LARGE = "KNOWLEDGE_FILE_CONTENT_TOO_LARGE"
PDF_NO_TEXT_LAYER = "KNOWLEDGE_PDF_NO_TEXT_LAYER"


def _rag_service(db, llm, vr, lr):
    return RagService(db, SemanticChunker(), vr, QueryRewriter(llm), HybridRetriever(db, vr, lr))


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


@router.post("/upload", response_model=Result[KnowledgeDocumentVO])
async def upload(
    req: KnowledgeUploadRequest,
    db: AsyncSession = Depends(get_db),
    llm=Depends(get_chat_model),
    vr: VectorRecallService = Depends(get_vector_recall_service),
    lr=Depends(get_lexical_recall),
):
    rag = _rag_service(db, llm, vr, lr)
    try:
        doc = await rag.upload_document(
            req.title,
            req.content,
            req.source_type,
            req.project_name,
        )
    except BusinessException:
        raise
    except Exception as exc:
        raise BusinessException("KNOWLEDGE_EMBEDDING_FAILED", status_code=502) from exc
    return Result.ok(KnowledgeDocumentVO(id=doc.id, title=doc.title))


@router.post("/search", response_model=Result[list[KnowledgeSearchHit]])
async def search(
    req: KnowledgeSearchRequest,
    db: AsyncSession = Depends(get_db),
    llm=Depends(get_chat_model),
    vr: VectorRecallService = Depends(get_vector_recall_service),
    lr=Depends(get_lexical_recall),
):
    rag = _rag_service(db, llm, vr, lr)
    try:
        results = await rag.search(req.query, top_k=req.top_k)
    except BusinessException:
        raise
    except Exception as exc:
        raise BusinessException("KNOWLEDGE_SEARCH_FAILED", status_code=502) from exc
    return Result.ok(
        [
            KnowledgeSearchHit(
                score=r.score,
                match_type=r.match_type,
                document_id=r.chunk.document_id,
                chunk_content=r.chunk.chunk_content,
            )
            for r in results
        ]
    )


@router.get("/documents", response_model=Result[DocumentListVO])
async def list_documents(
    status: str = Query("ACTIVE", pattern="^(ACTIVE|DELETED|ALL)$"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """文档列表（ADR-0013）：status 过滤 + 分页 + chunk_count。"""
    from app.models import Document, KnowledgeChunk

    chunk_count_subq = (
        select(func.count(KnowledgeChunk.id))
        .where(KnowledgeChunk.document_id == Document.id)
        .correlate(Document)
        .scalar_subquery()
    )
    base = select(
        Document.id, Document.title, Document.source_type, Document.project_name,
        Document.status, chunk_count_subq.label("chunk_count"),
        Document.created_at, Document.deleted_at,
    )
    count_stmt = select(func.count()).select_from(Document)
    if status != "ALL":
        base = base.where(Document.status == status)
        count_stmt = count_stmt.where(Document.status == status)
    total = await db.scalar(count_stmt)
    rows = (
        await db.execute(
            base.order_by(Document.id.desc()).offset((page - 1) * size).limit(size)
        )
    ).all()
    records = [
        DocumentVO(
            id=r.id, title=r.title, source_type=r.source_type,
            project_name=r.project_name, status=r.status, chunk_count=r.chunk_count,
            created_at=r.created_at.isoformat() if r.created_at else "",
            deleted_at=r.deleted_at.isoformat() if r.deleted_at else None,
        )
        for r in rows
    ]
    return Result.ok(
        DocumentListVO(total=total or 0, page=page, size=size, records=records)
    )


@router.delete("/{doc_id}", response_model=Result[None])
async def delete(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    llm=Depends(get_chat_model),
    vr: VectorRecallService = Depends(get_vector_recall_service),
    lr=Depends(get_lexical_recall),
):
    """软删文档（ADR-0013）：标 DELETED + 物理删 chunks。

    commit 由 get_db 统一处理（override 到测试 db_session 时不提交，保证隔离）。
    """
    rag = _rag_service(db, llm, vr, lr)
    await rag.delete_document(doc_id)
    return Result.ok()


@router.post(
    "/upload-file",
    response_model=Result[KnowledgeDocumentVO],
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
    lr=Depends(get_lexical_recall),
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
            raise BusinessException(
                PDF_NO_TEXT_LAYER if extension == ".pdf" else FILE_PARSE_FAILED
            )
        if len(text) > settings.knowledge_parsed_max_chars:
            raise BusinessException(FILE_CONTENT_TOO_LARGE)

        rag = _rag_service(db, llm, vr, lr)
        try:
            doc = await rag.upload_document(
                filename,
                text,
                source_type="DOC",
                project_name=project_name,
            )
        except Exception as exc:
            raise BusinessException(
                "KNOWLEDGE_EMBEDDING_FAILED",
                status_code=502,
            ) from exc
        return Result.ok(KnowledgeDocumentVO(id=doc.id, title=doc.title))
    finally:
        await file.close()


@router.post(
    "/{doc_id}/replace",
    response_model=Result[KnowledgeDocumentVO],
    responses={
        404: {"description": "doc_id 不存在", "model": Result[None]},
        400: {"description": "文件为空/格式不支持/超限/解析失败", "model": Result[None]},
    },
)
async def replace(
    doc_id: int,
    file: UploadFile = File(
        ...,
        description="PDF/DOCX/HTML/Markdown/TXT，原始文件最大 5 MiB",
    ),
    project_name: str | None = Form(default=None, max_length=100),
    db: AsyncSession = Depends(get_db),
    llm=Depends(get_chat_model),
    vr: VectorRecallService = Depends(get_vector_recall_service),
    lr=Depends(get_lexical_recall),
):
    """更新文档（ADR-0013）：解析新文件 -> 软删旧文档 -> 上传新文档。"""
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
                "knowledge replace parse failed code=%s extension=%s",
                FILE_PARSE_FAILED,
                extension,
            )
            raise BusinessException(FILE_PARSE_FAILED) from exc
        if not text:
            raise BusinessException(
                PDF_NO_TEXT_LAYER if extension == ".pdf" else FILE_PARSE_FAILED
            )
        if len(text) > settings.knowledge_parsed_max_chars:
            raise BusinessException(FILE_CONTENT_TOO_LARGE)

        rag = _rag_service(db, llm, vr, lr)
        try:
            new_doc = await rag.replace_document(
                doc_id,
                filename,
                text,
                source_type="DOC",
                project_name=project_name,
            )
        except BusinessException:
            raise
        except Exception as exc:
            raise BusinessException(
                "KNOWLEDGE_EMBEDDING_FAILED",
                status_code=502,
            ) from exc
        # commit 由 get_db 统一处理（测试 override 时不提交，保证隔离）
        return Result.ok(KnowledgeDocumentVO(id=new_doc.id, title=new_doc.title))
    finally:
        await file.close()
