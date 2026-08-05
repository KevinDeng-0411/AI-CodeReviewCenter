"""C2-E：Chat 核心域与 AIReadMe 安全快照的 route-level 回归闭环。"""

import hashlib
from conftest import clear_overrides_keep_auth  # noqa: E402
import json

import pytest
from sqlalchemy import delete, func, select

from app.ai.config import get_chat_model, get_vector_recall_service
from app.ai.infra.vector_recall import VectorRecallService
from app.ai.prompt.template_manager import PromptTemplateManager
from app.ai.services.project_snapshot import (
    PROJECT_OUTSIDE_ROOTS,
    ProjectSnapshotService,
)
from app.api.v1.ai_readme import get_project_snapshot_service
from app.core.enums import PromptType
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models import (
    AiReadmeDocument,
    Conversation,
    Document,
    LongTermMemory,
    Message,
    PromptTemplate,
)
from app.schemas.ai_readme import AiReadmeResult
from app.schemas.memory import ExtractedFacts


class _DeterministicEmbedder:
    async def aembed_query(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        return [digest[index % len(digest)] / 255.0 + 0.01 for index in range(1024)]


class _C2EModel:
    def __init__(self) -> None:
        self.chat_prompts: list[str] = []
        self.readme_prompts: list[str] = []
        self.extraction_prompts: list[str] = []

    async def astream(self, prompt, **_kwargs):
        self.chat_prompts.append(prompt)
        for content in ("C2-E ", "reply\n"):
            class _Chunk:
                def __init__(self, value: str) -> None:
                    self.content = value

            yield _Chunk(content)

    async def ainvoke(self, prompt, **_kwargs):
        class _Response:
            content = ""

        response = _Response()
        if "查询优化专家" in prompt:
            response.content = '["C2-E RAG marker","RAG marker"]'
        else:
            response.content = "C2-E persisted summary"
        return response

    def with_structured_output(self, schema, **_kwargs):
        owner = self

        class _Structured:
            async def ainvoke(self, prompt, **_kwargs):
                if schema is ExtractedFacts:
                    owner.extraction_prompts.append(prompt)
                    return ExtractedFacts(facts=["C2-E 自动事实来自当前会话"])
                if schema is AiReadmeResult:
                    owner.readme_prompts.append(prompt)
                    return AiReadmeResult(
                        content="# C2-E Generated\n\nSafe snapshot content."
                    )
                raise AssertionError(f"unexpected structured schema: {schema}")

        return _Structured()


@pytest.fixture
async def c2e_context(setup_db, redis_client, tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    project = allowed / "fixture-project"
    project.mkdir()
    (project / "README.md").write_text(
        "# C2-E Fixture\n\nThis repository demonstrates a safe snapshot.\n",
        encoding="utf-8",
    )
    (project / "pyproject.toml").write_text(
        '[project]\nname = "c2e-fixture"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    (project / "main.py").write_text(
        'print("c2e-entrypoint")\n',
        encoding="utf-8",
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "README.md").write_text("# outside\n", encoding="utf-8")

    model = _C2EModel()
    recall = VectorRecallService(_DeterministicEmbedder())
    snapshot_service = ProjectSnapshotService(
        enabled=True,
        allowed_roots=[allowed],
        max_files=20,
        max_file_bytes=20_000,
        max_total_bytes=100_000,
        max_prompt_chars=30_000,
        timeout_seconds=2,
    )
    async with AsyncSessionLocal() as session:
        manager = PromptTemplateManager(session)
        await manager.save_and_activate(
            PromptType.CHAT,
            name="C2-E Chat",
            role_setting="C2-E CHAT ROLE",
            template_body=(
                "MEMORY:\n{{long_term_memory}}\n\n"
                "RAG:\n{{rag_context}}\n\n"
                "HISTORY:\n{{conversation_history}}\n\n"
                "USER:\n{{user_message}}"
            ),
        )
        await manager.save_and_activate(
            PromptType.AI_README,
            name="C2-E AIReadMe",
            role_setting="C2-E README ROLE",
            template_body="为 {{project_name}}（{{project_path}}）生成项目文档。",
        )
        await session.commit()

    app.dependency_overrides[get_chat_model] = lambda: model
    app.dependency_overrides[get_vector_recall_service] = lambda: recall
    app.dependency_overrides[get_project_snapshot_service] = lambda: snapshot_service
    try:
        yield {
            "model": model,
            "project": project,
            "outside": outside,
        }
    finally:
        clear_overrides_keep_auth()
        async with AsyncSessionLocal() as session:
            conversation_ids = list(
                (
                    await session.scalars(
                        select(Conversation.conversation_id).where(
                            Conversation.title.like("C2-E%")
                        )
                    )
                ).all()
            )
            if conversation_ids:
                await session.execute(
                    delete(Message).where(Message.conversation_id.in_(conversation_ids))
                )
                await session.execute(
                    delete(LongTermMemory).where(
                        LongTermMemory.conversation_id.in_(conversation_ids)
                    )
                )
                await session.execute(
                    delete(Conversation).where(
                        Conversation.conversation_id.in_(conversation_ids)
                    )
                )
            await session.execute(
                delete(LongTermMemory).where(LongTermMemory.content.like("C2-E %"))
            )
            await session.execute(
                delete(Document).where(Document.project_name.like("c2e-%"))
            )
            await session.execute(
                delete(AiReadmeDocument).where(
                    AiReadmeDocument.project_name.like("c2e-%")
                )
            )
            await session.execute(
                delete(PromptTemplate).where(PromptTemplate.name.like("C2-E%"))
            )
            await session.commit()


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        event_name = ""
        payload = None
        event_id = None
        for line in block.splitlines():
            if line.startswith("id:"):
                event_id = int(line.removeprefix("id:").strip())
            elif line.startswith("event:"):
                event_name = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                payload = json.loads(line.removeprefix("data:").strip())
        assert payload is not None
        assert event_id == payload["sequence"]
        events.append((event_name, payload))
    return events


async def test_chat_context_summary_fact_and_delete_closure(
    client,
    redis_client,
    c2e_context,
):
    document = await client.post(
        "/api/knowledge/upload",
        json={
            "title": "C2-E Chat knowledge",
            "content": "# C2-E RAG marker\n\n知识上下文来自文档分块。",
            "source_type": "MANUAL",
            "project_name": "c2e-chat",
        },
    )
    manual_memory = await client.post(
        "/api/memory/long-term",
        json={
            "content": "C2-E 手动偏好使用 FastAPI",
            "memory_type": "REFERENCE",
        },
    )
    assert document.status_code == manual_memory.status_code == 200

    streamed = await client.post(
        "/api/chat/send/stream",
        json={"message": "C2-E first question"},
    )
    assert streamed.status_code == 200
    events = _parse_sse(streamed.text)
    assert [name for name, _ in events] == [
        "chat.started",
        "context.references",
        "token.delta",
        "token.delta",
        "chat.completed",
    ]
    assert [payload["sequence"] for _, payload in events] == [1, 2, 3, 4, 5]
    assert all(payload["protocol_version"] == 1 for _, payload in events)
    cid = events[0][1]["conversation_id"]
    assert "".join(
        payload["delta"] for name, payload in events if name == "token.delta"
    ) == "C2-E reply\n"

    first_prompt = c2e_context["model"].chat_prompts[-1]
    assert "C2-E 手动偏好使用 FastAPI" in first_prompt
    assert "知识上下文来自文档分块" in first_prompt
    assert first_prompt.count("C2-E first question") == 1

    for turn in range(2, 6):
        response = await client.post(
            "/api/chat/send",
            json={
                "conversation_id": cid,
                "message": f"C2-E question {turn}",
            },
        )
        assert response.status_code == 200
        assert response.json()["data"]["conversation_id"] == cid
        assert response.json()["data"]["reply"] == "C2-E reply\n"

    async with AsyncSessionLocal() as session:
        conversation = await session.scalar(
            select(Conversation).where(Conversation.conversation_id == cid)
        )
        assert conversation is not None
        assert conversation.summary == "C2-E persisted summary"
        assert conversation.summary_message_count == 10
        assert (
            await session.scalar(
                select(func.count())
                .select_from(LongTermMemory)
                .where(
                    LongTermMemory.conversation_id == cid,
                    LongTermMemory.memory_type == "FACT",
                    LongTermMemory.content == "C2-E 自动事实来自当前会话",
                )
            )
            == 1
        )
    assert await redis_client.get(f"summary:{cid}") == "C2-E persisted summary"

    continuation = await client.post(
        "/api/chat/send",
        json={
            "conversation_id": cid,
            "message": "C2-E after summary",
        },
    )
    assert continuation.status_code == 200
    continued_prompt = c2e_context["model"].chat_prompts[-1]
    assert "C2-E persisted summary" in continued_prompt
    assert "C2-E first question" in continued_prompt
    assert continued_prompt.count("C2-E after summary") == 1

    history = await client.get(f"/api/chat/conversations/{cid}")
    conversations = await client.get("/api/chat/conversations")
    assert len(history.json()["data"]) == 12
    listed = next(
        item
        for item in conversations.json()["data"]
        if item["conversation_id"] == cid
    )
    assert listed["summary"] == "C2-E persisted summary"

    deleted = await client.delete(f"/api/chat/conversations/{cid}")
    assert deleted.status_code == 200
    async with AsyncSessionLocal() as session:
        assert await session.scalar(
            select(Conversation.id).where(Conversation.conversation_id == cid)
        ) is None
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.conversation_id == cid)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(LongTermMemory)
                .where(LongTermMemory.conversation_id == cid)
            )
            == 0
        )
        assert await session.get(
            LongTermMemory,
            manual_memory.json()["data"]["id"],
        ) is not None
    assert await redis_client.exists(f"msgs:{cid}", f"summary:{cid}") == 0

    missing = await client.post(
        "/api/chat/send",
        json={"conversation_id": cid, "message": "must fail"},
    )
    assert missing.status_code == 404
    assert missing.json()["msg"] == "CHAT_CONVERSATION_NOT_FOUND"


async def test_ai_readme_snapshot_version_latest_and_rejection_closure(
    client,
    c2e_context,
):
    capability = await client.get("/api/ai-readme/capabilities")
    assert capability.status_code == 200
    assert capability.json()["data"] == {"enabled": True, "reason": "available"}

    payload = {
        "project_name": "c2e-fixture",
        "project_path": str(c2e_context["project"]),
    }
    first = await client.post("/api/ai-readme/generate", json=payload)
    second = await client.post("/api/ai-readme/generate", json=payload)
    latest = await client.get("/api/ai-readme/c2e-fixture")
    assert first.status_code == second.status_code == latest.status_code == 200
    first_data = first.json()["data"]
    second_data = second.json()["data"]
    latest_data = latest.json()["data"]
    assert [first_data["version"], second_data["version"]] == [1, 2]
    assert first_data["snapshot_hash"] == second_data["snapshot_hash"]
    assert latest_data["version"] == 2
    assert latest_data["id"] == second_data["id"]
    assert latest_data["snapshot_file_count"] == 3

    prompts = c2e_context["model"].readme_prompts
    assert len(prompts) == 2
    assert all("# C2-E Fixture" in prompt for prompt in prompts)
    assert all("c2e-fixture" in prompt for prompt in prompts)
    assert all("c2e-entrypoint" in prompt for prompt in prompts)
    assert all("不可信资料" in prompt for prompt in prompts)
    assert all(str(c2e_context["project"]) not in prompt for prompt in prompts)

    rejected = await client.post(
        "/api/ai-readme/generate",
        json={
            "project_name": "c2e-rejected",
            "project_path": str(c2e_context["outside"]),
        },
    )
    assert rejected.status_code == 400
    assert rejected.json()["msg"] == PROJECT_OUTSIDE_ROOTS
    assert str(c2e_context["outside"]) not in rejected.text
    async with AsyncSessionLocal() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AiReadmeDocument)
                .where(AiReadmeDocument.project_name == "c2e-rejected")
            )
            == 0
        )


async def test_c2e_demo_chat_and_ai_readme_closure(
    client,
    c2e_context,
):
    chat_response = await client.post(
        "/api/chat/send",
        json={"message": "C2-E demo chat"},
    )
    readme_response = await client.post(
        "/api/ai-readme/generate",
        json={
            "project_name": "c2e-demo",
            "project_path": str(c2e_context["project"]),
        },
    )
    assert chat_response.status_code == readme_response.status_code == 200
    print(
        "C2-E demo:",
        {
            "conversation_id": chat_response.json()["data"]["conversation_id"],
            "chat_reply_preserved": chat_response.json()["data"]["reply"]
            == "C2-E reply\n",
            "snapshot_version": readme_response.json()["data"]["version"],
            "snapshot_files": readme_response.json()["data"][
                "snapshot_file_count"
            ],
            "absolute_path_hidden": str(c2e_context["project"])
            not in c2e_context["model"].readme_prompts[-1],
        },
    )
