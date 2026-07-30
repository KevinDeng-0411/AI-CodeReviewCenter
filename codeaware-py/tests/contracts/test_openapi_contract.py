"""C2 canonical HTTP/OpenAPI contract checks."""

import json
from pathlib import Path

from app.main import app
from scripts.export_openapi import encoded, normalized_openapi

APP_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = APP_ROOT / "openapi" / "current-release.json"


def _query_names(schema: dict, path: str, method: str) -> set[str]:
    return {
        parameter["name"]
        for parameter in schema["paths"][path][method]["parameters"]
        if parameter["in"] == "query"
    }


def test_openapi_snapshot_matches_app():
    assert SNAPSHOT.is_file()
    assert SNAPSHOT.read_text(encoding="utf-8") == encoded(normalized_openapi())


def test_current_release_routes_and_canonical_query_names():
    schema = app.openapi()
    required_methods = {
        "/api/code-review/review": "post",
        "/api/unit-test/generate": "post",
        "/api/ai-readme/generate": "post",
        "/api/chat/send": "post",
        "/api/chat/send/stream": "post",
        "/api/knowledge/upload": "post",
        "/api/knowledge/upload-file": "post",
        "/api/knowledge/search": "post",
        "/api/memory/long-term": "post",
        "/api/memory/long-term/search": "get",
        "/api/prompts": "post",
    }
    for path, method in required_methods.items():
        assert method in schema["paths"][path]

    assert _query_names(
        schema,
        "/api/memory/long-term/search",
        "get",
    ) == {"query", "threshold", "top_k"}
    assert _query_names(
        schema,
        "/api/prompts/{template_id}/preview",
        "get",
    ) == {"sample_code"}
    assert "project_name" in _query_names(
        schema,
        "/api/code-review/records",
        "get",
    )

    serialized = json.dumps(schema, ensure_ascii=False)
    assert '"topK"' not in serialized
    assert '"sampleCode"' not in serialized
