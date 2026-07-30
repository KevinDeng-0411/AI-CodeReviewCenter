"""C1-C：multipart Knowledge 文件上传的契约、限制、持久化与演示。"""

import io

import pytest
from fastapi import UploadFile
from pydantic import ValidationError
from sqlalchemy import func, select
from starlette.datastructures import Headers

from app.ai.config import get_chat_model, get_vector_recall_service
from app.ai.services.document_parser import DocumentParserService
from app.api.v1.knowledge import (
    FILE_CONTENT_TOO_LARGE,
    FILE_EMPTY,
    FILE_PARSE_FAILED,
    FILE_TOO_LARGE,
    FILE_TYPE_UNSUPPORTED,
    upload_file,
)
from app.core.config import Settings, settings
from app.core.exceptions import BusinessException
from app.db.session import get_db
from app.main import app
from app.models import Document, KnowledgeChunk


@pytest.fixture
def upload_overrides(db_session, mock_llm, vector_recall):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_chat_model] = lambda: mock_llm
    app.dependency_overrides[get_vector_recall_service] = lambda: vector_recall
    yield
    app.dependency_overrides.clear()


class _TrackedUploadFile(UploadFile):
    close_called = False

    async def close(self) -> None:
        self.close_called = True
        await super().close()


def _tracked_upload(filename: str, content: bytes, content_type: str) -> _TrackedUploadFile:
    return _TrackedUploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


async def test_markdown_upload_persists_project_document_and_chunks(
    client, db_session, upload_overrides
):
    response = await client.post(
        "/api/knowledge/upload-file",
        files={"file": ("README.md", b"# Cache\n\nCache penetration guide", "text/markdown")},
        data={"project_name": "upload-project"},
    )
    assert response.status_code == 200
    document_id = response.json()["data"]["id"]

    document = await db_session.get(Document, document_id)
    assert document is not None
    assert document.title == "README.md"
    assert document.project_name == "upload-project"
    assert document.source_type == "DOC"
    assert "Cache penetration guide" in document.content
    chunk_count = await db_session.scalar(
        select(func.count())
        .select_from(KnowledgeChunk)
        .where(KnowledgeChunk.document_id == document_id)
    )
    assert chunk_count and chunk_count > 0


async def test_text_upload_normalizes_client_path(client, db_session, upload_overrides):
    response = await client.post(
        "/api/knowledge/upload-file",
        files={"file": (r"C:\fakepath\notes.txt", b"plain text body", "text/plain")},
    )
    assert response.status_code == 200
    document = await db_session.get(Document, response.json()["data"]["id"])
    assert document is not None
    assert document.title == "notes.txt"


@pytest.mark.parametrize(
    ("filename", "content", "content_type", "error_code"),
    [
        ("empty.md", b"", "text/markdown", FILE_EMPTY),
        ("malware.exe", b"not executable", "application/octet-stream", FILE_TYPE_UNSUPPORTED),
        ("fake.pdf", b"not a pdf", "image/png", FILE_TYPE_UNSUPPORTED),
    ],
)
async def test_invalid_uploads_return_stable_errors(
    client,
    db_session,
    upload_overrides,
    filename,
    content,
    content_type,
    error_code,
):
    response = await client.post(
        "/api/knowledge/upload-file",
        files={"file": (filename, content, content_type)},
    )
    assert response.status_code == 400
    assert response.json() == {"code": 0, "msg": error_code, "data": None}
    assert await db_session.scalar(select(func.count()).select_from(Document)) == 0


async def test_raw_file_limit_is_enforced_before_parse(
    client, db_session, upload_overrides, monkeypatch
):
    monkeypatch.setattr(settings, "knowledge_upload_max_bytes", 8)
    response = await client.post(
        "/api/knowledge/upload-file",
        files={"file": ("large.txt", b"123456789", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["msg"] == FILE_TOO_LARGE
    assert await db_session.scalar(select(func.count()).select_from(Document)) == 0


async def test_parsed_character_limit_is_enforced(
    client, db_session, upload_overrides, monkeypatch
):
    async def oversized_parse(_self, _content, _filename):
        return "x" * 11

    monkeypatch.setattr(settings, "knowledge_parsed_max_chars", 10)
    monkeypatch.setattr(DocumentParserService, "parse", oversized_parse)
    response = await client.post(
        "/api/knowledge/upload-file",
        files={"file": ("large.md", b"# small", "text/markdown")},
    )
    assert response.status_code == 400
    assert response.json()["msg"] == FILE_CONTENT_TOO_LARGE
    assert await db_session.scalar(select(func.count()).select_from(Document)) == 0


@pytest.mark.parametrize("parser_result", [None, ""])
async def test_empty_or_failed_parse_is_sanitized_and_leaves_no_rows(
    client,
    db_session,
    upload_overrides,
    monkeypatch,
    parser_result,
):
    async def parse_outcome(_self, _content, _filename):
        if parser_result is None:
            raise RuntimeError("/private/tmp/secret-upload parser detail")
        return parser_result

    monkeypatch.setattr(DocumentParserService, "parse", parse_outcome)
    response = await client.post(
        "/api/knowledge/upload-file",
        files={"file": ("broken.md", b"# input", "text/markdown")},
    )
    assert response.status_code == 400
    assert response.json()["msg"] == FILE_PARSE_FAILED
    assert "secret-upload" not in response.text
    assert await db_session.scalar(select(func.count()).select_from(Document)) == 0
    assert await db_session.scalar(select(func.count()).select_from(KnowledgeChunk)) == 0


async def test_upload_file_is_closed_on_success_and_failure(
    db_session, mock_llm, vector_recall
):
    successful = _tracked_upload("ok.txt", b"closed after success", "text/plain")
    result = await upload_file(
        file=successful,
        project_name="close-test",
        db=db_session,
        llm=mock_llm,
        vr=vector_recall,
    )
    assert result.code == 1
    assert successful.close_called is True
    assert successful.file.closed is True

    rejected = _tracked_upload("bad.exe", b"rejected", "application/octet-stream")
    with pytest.raises(BusinessException, match=FILE_TYPE_UNSUPPORTED):
        await upload_file(
            file=rejected,
            project_name=None,
            db=db_session,
            llm=mock_llm,
            vr=vector_recall,
        )
    assert rejected.close_called is True
    assert rejected.file.closed is True


def test_openapi_declares_multipart_file_and_optional_project_name():
    operation = app.openapi()["paths"]["/api/knowledge/upload-file"]["post"]
    assert not any(
        parameter["name"] in {"file", "project_name"}
        for parameter in operation.get("parameters", [])
    )
    media = operation["requestBody"]["content"]["multipart/form-data"]
    schema = media["schema"]
    if "$ref" in schema:
        schema = app.openapi()["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
    assert set(schema["properties"]) == {"file", "project_name"}
    assert schema["properties"]["file"]["type"] == "string"
    assert schema["properties"]["file"]["contentMediaType"] == "application/octet-stream"
    assert schema["required"] == ["file"]


@pytest.mark.parametrize(
    "field",
    ["knowledge_upload_max_bytes", "knowledge_parsed_max_chars"],
)
def test_knowledge_upload_configuration_requires_positive_values(field):
    with pytest.raises(ValidationError):
        Settings(**{field: 0})


async def test_c1c_demo_multipart_success_and_stable_failure(
    client, db_session, upload_overrides
):
    success = await client.post(
        "/api/knowledge/upload-file",
        files={"file": ("demo.md", b"# C1-C\n\nmultipart demo", "text/markdown")},
        data={"project_name": "c1c-demo"},
    )
    assert success.status_code == 200
    document_id = success.json()["data"]["id"]
    document = await db_session.get(Document, document_id)
    chunk_count = await db_session.scalar(
        select(func.count())
        .select_from(KnowledgeChunk)
        .where(KnowledgeChunk.document_id == document_id)
    )

    failure = await client.post(
        "/api/knowledge/upload-file",
        files={"file": ("demo.exe", b"unsupported", "application/octet-stream")},
    )
    assert failure.status_code == 400
    assert failure.json()["msg"] == FILE_TYPE_UNSUPPORTED
    operation = app.openapi()["paths"]["/api/knowledge/upload-file"]["post"]
    assert "multipart/form-data" in operation["requestBody"]["content"]

    print(
        "C1-C demo:",
        "multipart_status=200",
        f"document_id={document_id}",
        f"project_name={document.project_name}",
        f"content_chars={len(document.content)}",
        f"chunk_count={chunk_count}",
        "openapi=multipart/form-data",
        f"failure_code={FILE_TYPE_UNSUPPORTED}",
    )
