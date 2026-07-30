"""Deterministic model adapters for C2 browser E2E.

This module is installed only when ``main.py`` verifies both CODEAWARE_TESTING and
CODEAWARE_BROWSER_E2E inside a disposable safe-runner stack.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from fastapi import FastAPI

from app.ai.config import get_chat_model, get_vector_recall_service
from app.ai.infra.vector_recall import VectorRecallService
from app.ai.services.project_snapshot import ProjectSnapshotService
from app.api.v1.ai_readme import get_project_snapshot_service
from app.schemas.ai_readme import AiReadmeResult
from app.schemas.code_review import CodeReviewResult, ReviewIssue
from app.schemas.memory import ExtractedFacts
from app.schemas.unit_test import UnitTestResult


class _BrowserEmbedder:
    async def aembed_query(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        return [digest[index % len(digest)] / 255.0 + 0.01 for index in range(1024)]


class _BrowserModel:
    async def astream(self, _prompt, **_kwargs):
        for content in ("Browser reply", "\nline"):
            class _Chunk:
                def __init__(self, value: str) -> None:
                    self.content = value

            yield _Chunk(content)

    async def ainvoke(self, prompt, **_kwargs):
        class _Response:
            content = ""

        response = _Response()
        if "BROWSER_INVALID_OUTPUT" in prompt:
            response.content = "not-json"
        elif "查询优化专家" in prompt:
            response.content = '["browser caching","browser knowledge"]'
        else:
            response.content = "Browser summary"
        return response

    def with_structured_output(self, schema, **_kwargs):
        class _Structured:
            async def ainvoke(self, prompt, **_kwargs):
                if "BROWSER_INVALID_OUTPUT" in prompt:
                    raise RuntimeError("forced deterministic browser failure")
                if schema is CodeReviewResult:
                    return CodeReviewResult(
                        summary="浏览器评审完成",
                        score=58,
                        issues=[
                            ReviewIssue(
                                dimension="安全性",
                                severity="Critical",
                                line_range="2",
                                title="字符串拼接 SQL",
                                description="输入未经参数化处理",
                                suggestion="使用参数化查询",
                                fix_code="jdbc.query(sql, name);",
                            )
                        ],
                        highlights=["结构清晰"],
                    )
                if schema is UnitTestResult:
                    return UnitTestResult(
                        test_code=(
                            "class CalcTest {\n"
                            "  @Test void addsNumbers() { assertEquals(3, new Calc().add(1, 2)); }\n"
                            "}"
                        ),
                        test_framework="JUnit5",
                    )
                if schema is AiReadmeResult:
                    return AiReadmeResult(
                        content="# Browser Fixture\n\nGenerated from the safe snapshot."
                    )
                if schema is ExtractedFacts:
                    return ExtractedFacts(facts=["Browser Chat 使用 FastAPI"])
                raise AssertionError(f"unexpected schema: {schema}")

        return _Structured()


def install_browser_e2e_overrides(app: FastAPI) -> None:
    """Install deterministic dependencies after main has fail-closed the environment."""
    allowed_root = Path(os.environ["CODEAWARE_BROWSER_E2E_PROJECT_ROOT"]).resolve()
    model = _BrowserModel()
    vector_recall = VectorRecallService(_BrowserEmbedder())
    snapshot_service = ProjectSnapshotService(
        enabled=True,
        allowed_roots=[allowed_root],
        max_files=50,
        max_file_bytes=64_000,
        max_total_bytes=500_000,
        max_prompt_chars=40_000,
        timeout_seconds=3,
    )
    app.dependency_overrides[get_chat_model] = lambda: model
    app.dependency_overrides[get_vector_recall_service] = lambda: vector_recall
    app.dependency_overrides[get_project_snapshot_service] = lambda: snapshot_service
