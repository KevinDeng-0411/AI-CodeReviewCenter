"""认证测试（团队化升级阶段 A）。

走真实认证链路：override get_db -> db_session（让 seed 的用户对 router 可见），
但不 override get_current_user（测真实 token 解析 + 用户查询）。
"""

import pytest
from sqlalchemy import select

from app.api.v1.deps import get_db
from app.core.security import create_access_token, hash_password
from app.models import User

pytestmark = pytest.mark.usefixtures("setup_db")


@pytest.fixture
def api_overrides(db_session):
    """让 router 用测试 session（seed 的用户可见）。

    auth 测试走真实认证链路：临时移除 default_user 设置的 get_current_user override，
    测完恢复。
    """
    from app.api.v1.deps import get_current_user
    from app.main import app

    saved_override = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides.pop(get_current_user, None)  # 走真实认证
    app.dependency_overrides[get_db] = lambda: db_session
    yield
    app.dependency_overrides.pop(get_db, None)
    if saved_override is not None:
        app.dependency_overrides[get_current_user] = saved_override


async def _seed_user(db_session, *, username="alice", password="password123", role="admin"):
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        display_name=username.title(),
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def test_login_success_returns_token(client, db_session, api_overrides):
    await _seed_user(db_session, username="alice", password="password123")
    await db_session.flush()

    r = await client.post(
        "/api/auth/login", json={"username": "alice", "password": "password123"}
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["user"]["username"] == "alice"
    assert data["user"]["role"] == "admin"


async def test_login_wrong_password_returns_401(client, db_session, api_overrides):
    await _seed_user(db_session, username="alice", password="password123")
    await db_session.flush()

    r = await client.post(
        "/api/auth/login", json={"username": "alice", "password": "wrong"}
    )
    assert r.status_code == 401
    assert r.json()["msg"] == "AUTH_INVALID_CREDENTIALS"


async def test_login_unknown_user_returns_401(client, db_session, api_overrides):
    r = await client.post(
        "/api/auth/login", json={"username": "ghost", "password": "whatever"}
    )
    assert r.status_code == 401
    assert r.json()["msg"] == "AUTH_INVALID_CREDENTIALS"


async def test_me_without_token_returns_401(client, api_overrides):
    r = await client.get("/api/auth/me")
    assert r.status_code == 401
    assert r.json()["msg"] == "AUTH_TOKEN_REQUIRED"


async def test_me_with_valid_token_returns_user(client, db_session, api_overrides):
    user = await _seed_user(db_session, username="alice", password="password123", role="member")
    await db_session.flush()
    token = create_access_token(user_id=user.id, role=user.role)

    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["data"]["username"] == "alice"
    assert r.json()["data"]["role"] == "member"


async def test_me_with_garbage_token_returns_401(client, api_overrides):
    r = await client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401
    assert r.json()["msg"] == "AUTH_INVALID_TOKEN"


async def test_register_requires_admin(client, db_session, api_overrides):
    # member 尝试建账号 -> 403
    member = await _seed_user(db_session, username="bob", password="password123", role="member")
    await db_session.flush()
    token = create_access_token(user_id=member.id, role=member.role)

    r = await client.post(
        "/api/auth/register",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "newbie", "password": "password123"},
    )
    assert r.status_code == 403
    assert r.json()["msg"] == "AUTH_FORBIDDEN"


async def test_register_without_token_returns_401(client, api_overrides):
    r = await client.post(
        "/api/auth/register",
        json={"username": "newbie", "password": "password123"},
    )
    assert r.status_code == 401


async def test_admin_can_register_new_member(client, db_session, api_overrides):
    admin = await _seed_user(db_session, username="admin", password="password123", role="admin")
    await db_session.flush()
    token = create_access_token(user_id=admin.id, role=admin.role)

    r = await client.post(
        "/api/auth/register",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "newbie", "password": "password123", "role": "member"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["username"] == "newbie"
    assert r.json()["data"]["role"] == "member"


async def test_register_duplicate_username_returns_409(client, db_session, api_overrides):
    admin = await _seed_user(db_session, username="admin", password="password123", role="admin")
    await _seed_user(db_session, username="taken", password="password123")
    await db_session.flush()
    token = create_access_token(user_id=admin.id, role=admin.role)

    r = await client.post(
        "/api/auth/register",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "taken", "password": "password123"},
    )
    assert r.status_code == 409
    assert r.json()["msg"] == "AUTH_USERNAME_TAKEN"
