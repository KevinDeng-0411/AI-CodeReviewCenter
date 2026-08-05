"""会话隔离测试（团队化升级阶段 B）。

走真实认证链路：建两个真实用户 + 真实 token，验证会话按用户隔离、知识库共享。
不使用 default_user override（pop 掉走真实 get_current_user）。
不依赖 TurnCoordinator（避免 LLM/prompt 依赖），直接 seed 会话测路由层归属过滤。
"""

import httpx
import pytest
import uuid
from httpx import ASGITransport
from sqlalchemy import delete, select

from app.api.v1.deps import get_current_user, get_db
from app.core.security import create_access_token, hash_password
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models import Conversation, User

pytestmark = pytest.mark.usefixtures("setup_db")


@pytest.fixture
async def two_users(db_session, vector_recall, mock_llm):
    """建两个真实用户 alice/bob，各自 seed 一个会话。返回 token + cid。"""
    from app.ai.config import get_chat_model, get_vector_recall_service
    from app.api.v1.deps import get_lexical_recall

    saved_override = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_vector_recall_service] = lambda: vector_recall
    app.dependency_overrides[get_chat_model] = lambda: mock_llm

    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        alice = User(username=f"alice-{suffix}", password_hash=hash_password("pw123456"), role="member")
        bob = User(username=f"bob-{suffix}", password_hash=hash_password("pw123456"), role="member")
        session.add_all([alice, bob])
        await session.flush()
        alice_cid = f"alice-conv-{suffix}"
        bob_cid = f"bob-conv-{suffix}"
        session.add_all([
            Conversation(conversation_id=alice_cid, title="alice 的会话", user_id=alice.id),
            Conversation(conversation_id=bob_cid, title="bob 的会话", user_id=bob.id),
        ])
        await session.commit()

    yield (
        create_access_token(user_id=alice.id, role="member"),
        create_access_token(user_id=bob.id, role="member"),
        alice_cid,
        bob_cid,
    )

    # 清理：删除本测试创建的会话和用户
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(Conversation).where(
                Conversation.conversation_id.in_([alice_cid, bob_cid])
            )
        )
        await session.execute(delete(User).where(User.id.in_([alice.id, bob.id])))
        await session.commit()

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_vector_recall_service, None)
    app.dependency_overrides.pop(get_chat_model, None)
    if saved_override is not None:
        app.dependency_overrides[get_current_user] = saved_override


def _client():
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_list_conversations_only_returns_own(two_users):
    alice_token, bob_token, alice_cid, bob_cid = two_users
    async with _client() as c:
        alice_list = await c.get(
            "/api/chat/conversations", headers={"Authorization": f"Bearer {alice_token}"}
        )
        assert alice_list.status_code == 200
        alice_cids = [x["conversation_id"] for x in alice_list.json()["data"]]
        assert alice_cid in alice_cids
        assert bob_cid not in alice_cids  # bob 的会话 alice 看不到

        bob_list = await c.get(
            "/api/chat/conversations", headers={"Authorization": f"Bearer {bob_token}"}
        )
        bob_cids = [x["conversation_id"] for x in bob_list.json()["data"]]
        assert bob_cid in bob_cids
        assert alice_cid not in bob_cids


async def test_accessing_others_conversation_returns_404(two_users):
    alice_token, bob_token, alice_cid, _ = two_users
    async with _client() as c:
        # bob 用 alice 的 cid 访问历史 -> 404（不泄露存在性）
        bob_access = await c.get(
            f"/api/chat/conversations/{alice_cid}",
            headers={"Authorization": f"Bearer {bob_token}"},
        )
        assert bob_access.status_code == 404

        # alice 自己能访问
        alice_access = await c.get(
            f"/api/chat/conversations/{alice_cid}",
            headers={"Authorization": f"Bearer {alice_token}"},
        )
        assert alice_access.status_code == 200


async def test_delete_others_conversation_returns_404(two_users):
    alice_token, bob_token, alice_cid, _ = two_users
    async with _client() as c:
        bob_delete = await c.delete(
            f"/api/chat/conversations/{alice_cid}",
            headers={"Authorization": f"Bearer {bob_token}"},
        )
        assert bob_delete.status_code == 404


async def test_unauthenticated_returns_401():
    # 临时移除 default_user override，确保走真实认证（无 token -> 401）
    saved = app.dependency_overrides.pop(get_current_user, None)
    try:
        async with _client() as c:
            r = await c.get("/api/chat/conversations")
            assert r.status_code == 401
            assert r.json()["msg"] == "AUTH_TOKEN_REQUIRED"
    finally:
        if saved is not None:
            app.dependency_overrides[get_current_user] = saved


async def test_knowledge_is_shared_across_users(two_users):
    """知识库全员共享：alice 上传，bob 能搜到。"""
    alice_token, bob_token, _, _ = two_users
    async with _client() as c:
        upload = await c.post(
            "/api/knowledge/upload",
            json={
                "title": "团队编码规范",
                "content": "# 团队编码规范\n所有变量用驼峰命名",
                "source_type": "MANUAL",
            },
            headers={"Authorization": f"Bearer {alice_token}"},
        )
        assert upload.status_code == 200

        search = await c.post(
            "/api/knowledge/search",
            json={"query": "编码规范", "top_k": 5},
            headers={"Authorization": f"Bearer {bob_token}"},
        )
        assert search.status_code == 200
        assert len(search.json()["data"]) > 0
