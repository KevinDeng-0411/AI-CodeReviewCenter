"""P5 端到端全链路冒烟（迁移文档 §8.2）。

链路：上传知识库 -> RAG 检索 -> 存长期记忆 -> 多轮对话(同步 + SSE) -> 会话管理 -> Code Review。

CI 友好：dependency_overrides 注入 FakeLLM(含 astream + with_structured_output)与 FakeEmbedder，
不打真实 DeepSeek/Ollama；走 ASGI 客户端验证核心域 Chat 全链路打通。
此测试同时覆盖 chat.py 的 SSE 流式(49-62)、长期记忆召回命中(81-83)、list_conversations(120-121)。
"""

import hashlib

import pytest

import app.ai.config as ai_config
from app.ai.infra.vector_recall import VectorRecallService
from app.ai.prompt.template_manager import PromptTemplateManager
from app.core.enums import PromptType
from app.db.session import get_db
from app.main import app
from app.schemas.code_review import CodeReviewResult, ReviewIssue


class _FakeEmbedder:
    """确定性 1024 维：同文本同向量，不同文本 cosine ∈ (0,1]，threshold=0.0 必召回。"""

    async def aembed_query(self, text):
        h = hashlib.sha256(text.encode()).digest()
        return [h[i % 32] / 255.0 + 0.01 for i in range(1024)]


class _E2EChatModel:
    """多态假 LLM：Chat 走 ainvoke/astream，CodeReview 走 with_structured_output。"""

    def __init__(self, cr_result: CodeReviewResult) -> None:
        self._cr = cr_result

    async def ainvoke(self, prompt, **kw):
        class _R:
            content = "pong"

        return _R()

    async def astream(self, prompt, **kw):
        for tok in ("hel", "lo", " world"):
            class _C:
                content = tok

            yield _C()

    def with_structured_output(self, schema, **kw):
        result = self._cr

        class _Structured:
            async def ainvoke(self, prompt, **kw):
                return result

        return _Structured()


_CR_RESULT = CodeReviewResult(
    summary="存在 SQL 注入风险",
    score=30,
    issues=[
        ReviewIssue(
            dimension="安全性",
            severity="Critical",
            line_range="1-3",
            title="SQL注入",
            description="字符串拼接构造 SQL，可被注入",
            suggestion="使用参数化查询",
            fix_code="PreparedStatement ps = conn.prepareStatement(sql);",
        ),
    ],
    highlights=[],
)


@pytest.fixture
async def e2e_overrides(db_session):
    """注入 mock 依赖 + 预置 CODE_REVIEW/CHAT 模板（贴近 alembic seed 生产态）。"""
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[ai_config.get_chat_model] = lambda: _E2EChatModel(_CR_RESULT)
    app.dependency_overrides[ai_config.get_vector_recall_service] = lambda: VectorRecallService(
        _FakeEmbedder()
    )
    pm = PromptTemplateManager(db_session)
    await pm.save_and_activate(
        PromptType.CODE_REVIEW,
        name="v1",
        role_setting="你是评审专家",
        template_body="评审: {{source_code}}",
        review_dimensions="代码质量,安全性",
        severity_levels="Critical,Warning,Info",
    )
    await pm.save_and_activate(
        PromptType.CHAT,
        name="v1",
        role_setting="你是技术助手",
        template_body=(
            "## 长期记忆\n{{long_term_memory}}\n\n"
            "{{rag_context}}\n\n"
            "## 对话历史\n{{conversation_history}}\n\n"
            "## 用户问题\n{{user_message}}"
        ),
    )
    yield
    app.dependency_overrides.clear()


async def test_full_chain_knowledge_rag_chat_review(client, e2e_overrides):
    """全链路冒烟：知识库 -> RAG -> 长期记忆 -> 多轮对话(同步+SSE) -> 会话管理 -> CR。"""
    # 1. 上传知识库
    r = await client.post(
        "/api/knowledge/upload",
        json={
            "title": "缓存最佳实践",
            "content": "# 缓存\n## 缓存击穿\n热点Key失效瞬间大量请求打DB。方案：互斥锁、逻辑过期。",
            "source_type": "MANUAL",
            "project_name": "e2e",
        },
    )
    assert r.status_code == 200
    doc_id = r.json()["data"]["id"]
    assert doc_id is not None

    # 2. RAG 混合检索（验证知识库可被检索，命中 matchType）
    r = await client.post("/api/knowledge/search", json={"query": "缓存击穿方案", "top_k": 3})
    assert r.status_code == 200
    results = r.json()["data"]
    assert len(results) >= 1
    assert "matchType" in results[0]

    # 3. 存长期记忆（让后续对话的长期记忆召回分支命中）
    r = await client.post(
        "/api/memory/long-term",
        json={"content": "团队使用 SQLAlchemy 2.0 作为 ORM 框架", "memory_type": "KNOWLEDGE"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["id"] is not None

    # 4. 多轮对话 - 第一轮（新建会话；三级上下文：长期记忆 + RAG + 短期记忆）
    r = await client.post("/api/chat/send", json={"message": "缓存击穿方案"})
    assert r.status_code == 200
    data = r.json()["data"]
    cid = data["conversation_id"]
    assert cid  # 自动创建 conversation_id（ADR-0004）
    assert data["reply"] == "pong"

    # 5. 多轮对话 - 第二轮（复用 conversation_id，短期记忆续接）
    r = await client.post(
        "/api/chat/send", json={"conversation_id": cid, "message": "再详细说说"}
    )
    assert r.status_code == 200
    assert r.json()["data"]["conversation_id"] == cid

    # 6. SSE 流式（逐 token + [DONE]）
    r = await client.post(
        "/api/chat/send/stream", json={"conversation_id": cid, "message": "流式回答"}
    )
    assert r.status_code == 200
    body = r.text
    assert "data:" in body and "[DONE]" in body
    assert "hello world" in body.replace("\n\n", "").replace("data: ", "")

    # 7. 会话列表 + 历史 + 删除
    r = await client.get("/api/chat/conversations")
    assert r.status_code == 200
    assert any(c["conversation_id"] == cid for c in r.json()["data"])

    r = await client.get(f"/api/chat/conversations/{cid}")
    assert r.status_code == 200
    assert len(r.json()["data"]) >= 4  # 至少 2 轮 × 2 条

    r = await client.delete(f"/api/chat/conversations/{cid}")
    assert r.status_code == 200

    # 8. Code Review（薄工具，经 API 验证结构化输出 + 持久化）
    r = await client.post(
        "/api/code-review/review",
        json={
            "project_name": "e2e",
            "file_path": "src/Svc.java",
            "source_code": 'public void save(String n){String s="DELETE FROM t WHERE n="+n;jdbc.execute(s);}',
        },
    )
    assert r.status_code == 200
    cr = r.json()["data"]
    assert cr["critical_count"] == 1
    assert cr["issues_count"] == 1
    assert cr["id"] is not None  # 持久化到 ai_operation_records（ADR-0006）

    # 9. CR 记录可查（合并表 ai_operation_records，type 鉴别）
    r = await client.get("/api/code-review/records?page=1&size=10")
    assert r.status_code == 200
    assert r.json()["data"]["total"] >= 1
