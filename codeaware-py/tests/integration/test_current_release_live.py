"""C2-G release smoke against real DeepSeek and Ollama on disposable storage."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime
from typing import Literal

import pytest
from pydantic import BaseModel
from sqlalchemy import func, select

from app.ai.config import (
    get_chat_model,
    get_embedding_model,
    get_vector_recall_service,
)
from app.ai.prompt.template_manager import PromptTemplateManager
from app.ai.rag.hybrid_retriever import HybridRetriever
from app.ai.rag.semantic_chunker import SemanticChunker
from app.ai.services.ai_readme import AiReadmeService
from app.ai.services.project_snapshot import ProjectSnapshotService
from app.ai.services.rag import RagService
from app.core.config import settings
from app.core.enums import PromptType
from app.models import AiReadmeDocument, Document, KnowledgeChunk


class _LiveStructuredCheck(BaseModel):
    status: Literal["ok"]


class _UnusedRewriter:
    async def rewrite(self, query: str) -> list[str]:
        return [query]


def _elapsed_ms(started: float) -> int:
    return round((time.monotonic() - started) * 1_000)


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _token_usage(response) -> dict[str, int]:
    raw = getattr(response, "usage_metadata", None) or {}
    allowed = ("input_tokens", "output_tokens", "total_tokens")
    return {
        key: int(raw[key])
        for key in allowed
        if isinstance(raw.get(key), int) and raw[key] >= 0
    }


@pytest.mark.live_eval
async def test_c2_live_deepseek_ollama_knowledge_and_readme(
    db_session,
    tmp_path,
):
    """Minimal paid/local smoke; output contains only model names, metrics and hashes."""
    if (
        not settings.llm_api_key
        or settings.llm_api_key.startswith("sk-your-")
        or len(settings.llm_api_key) < 12
    ):
        pytest.fail("C2_LIVE_LLM_KEY_MISSING")

    get_chat_model.cache_clear()
    get_embedding_model.cache_clear()
    get_vector_recall_service.cache_clear()
    llm = get_chat_model()
    embedder = get_embedding_model()
    vector_recall = get_vector_recall_service()
    metrics: dict[str, object] = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "llm_model": settings.llm_model,
        "embedding_model": settings.ollama_embedding_model,
    }

    started = time.monotonic()
    chat_response = await asyncio.wait_for(
        llm.ainvoke(
            "C2 release connectivity check. Reply with a short acknowledgement only."
        ),
        timeout=120,
    )
    chat_content = str(getattr(chat_response, "content", "")).strip()
    assert chat_content
    metrics["chat"] = {
        "elapsed_ms": _elapsed_ms(started),
        "output_chars": len(chat_content),
        "output_sha256_prefix": _content_hash(chat_content),
        "token_usage": _token_usage(chat_response),
    }

    started = time.monotonic()
    structured = llm.with_structured_output(
        _LiveStructuredCheck,
        method="json_mode",
    )
    structured_result = await asyncio.wait_for(
        structured.ainvoke(
            'Return JSON only and set status to "ok". This is a schema connectivity check.'
        ),
        timeout=120,
    )
    assert structured_result.status == "ok"
    metrics["structured_output"] = {
        "elapsed_ms": _elapsed_ms(started),
        "schema": "_LiveStructuredCheck",
        "valid": True,
    }

    started = time.monotonic()
    embedding = await asyncio.wait_for(
        embedder.aembed_query("C2 bge-m3 dimension check"),
        timeout=60,
    )
    assert len(embedding) == 1024
    assert all(isinstance(value, (int, float)) for value in embedding)
    metrics["embedding"] = {
        "elapsed_ms": _elapsed_ms(started),
        "dimension": len(embedding),
    }

    rag = RagService(
        db_session,
        SemanticChunker(),
        vector_recall,
        _UnusedRewriter(),
        HybridRetriever(db_session, vector_recall),
    )
    started = time.monotonic()
    document = await rag.upload_document(
        "C2 live knowledge",
        "# Live RAG\n\nC2 live retrieval marker uses pgvector and pg_trgm.",
        source_type="MANUAL",
        project_name="c2-live",
    )
    results = await HybridRetriever(db_session, vector_recall).search(
        "C2 live retrieval marker",
        top_k=3,
    )
    assert any(result.chunk.document_id == document.id for result in results)
    chunk_count = await db_session.scalar(
        select(func.count())
        .select_from(KnowledgeChunk)
        .where(KnowledgeChunk.document_id == document.id)
    )
    assert chunk_count and chunk_count > 0
    metrics["knowledge"] = {
        "elapsed_ms": _elapsed_ms(started),
        "document_persisted": await db_session.get(Document, document.id)
        is not None,
        "chunk_count": chunk_count,
        "hit_count": len(results),
        "match_types": sorted({result.match_type for result in results}),
    }

    project = tmp_path / "live-fixture"
    project.mkdir()
    (project / "README.md").write_text(
        "# C2 Live Fixture\n\nA minimal non-sensitive snapshot.\n",
        encoding="utf-8",
    )
    (project / "pyproject.toml").write_text(
        '[project]\nname = "c2-live-fixture"\n',
        encoding="utf-8",
    )
    manager = PromptTemplateManager(db_session)
    await manager.save_and_activate(
        PromptType.AI_README,
        name="C2 live AIReadMe",
        role_setting=(
            "Generate a concise Markdown README. Return a JSON object with a "
            "single non-empty content field."
        ),
        template_body="Project {{project_name}} from {{project_path}}.",
    )
    snapshot_service = ProjectSnapshotService(
        enabled=True,
        allowed_roots=[tmp_path],
        max_files=10,
        max_file_bytes=20_000,
        max_total_bytes=50_000,
        max_prompt_chars=20_000,
        timeout_seconds=3,
    )
    started = time.monotonic()
    readme = await asyncio.wait_for(
        AiReadmeService(
            db_session,
            llm,
            manager,
            snapshot_service,
        ).generate("c2-live-fixture", str(project)),
        timeout=120,
    )
    assert readme.version == 1
    assert readme.snapshot_hash
    assert readme.snapshot_file_count == 2
    assert await db_session.scalar(
        select(func.count())
        .select_from(AiReadmeDocument)
        .where(AiReadmeDocument.project_name == "c2-live-fixture")
    ) == 1
    metrics["ai_readme"] = {
        "elapsed_ms": _elapsed_ms(started),
        "version": readme.version,
        "snapshot_files": readme.snapshot_file_count,
        "snapshot_hash_prefix": readme.snapshot_hash[:16],
        "content_chars": len(readme.content),
        "content_sha256_prefix": _content_hash(readme.content),
    }

    usage = metrics["chat"]["token_usage"]  # type: ignore[index]
    metrics["cost"] = {
        "currency": "USD",
        "amount": None,
        "basis": (
            "provider response exposes token usage but not billed amount; "
            "no unverified price table is hard-coded"
        ),
        "metered_tokens": usage.get("total_tokens") if isinstance(usage, dict) else None,
        "real_llm_calls": 3,
    }
    print("[C2 LIVE] " + json.dumps(metrics, ensure_ascii=False, sort_keys=True))
