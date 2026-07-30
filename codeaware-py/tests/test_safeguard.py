"""C1-D fail-closed target guard tests."""

import hashlib

import pytest

from app.core.config import settings
from _safeguard import (
    UnsafeTargetError,
    assert_safe_target_identity,
    assert_safe_targets,
)

SID = "abc12345abc12345"
AUTH = "runner-secret"


@pytest.fixture
def valid_static_target(monkeypatch):
    monkeypatch.setenv("CODEWARE_TEST_STACK_ID", SID)
    monkeypatch.setenv("CODEWARE_TEST_AUTH", AUTH)
    monkeypatch.setenv("CODEWARE_TEST_PG_PORT", "35432")
    monkeypatch.setenv("CODEWARE_TEST_REDIS_PORT", "36379")
    monkeypatch.setenv("CODEWARE_TEST_REDIS_GUARD_DB", "15")
    monkeypatch.setattr(settings, "pg_db", f"codeaware_test_{SID}")
    monkeypatch.setattr(settings, "pg_host", "127.0.0.1")
    monkeypatch.setattr(settings, "pg_port", 35432)
    monkeypatch.setattr(settings, "redis_db", 1)
    monkeypatch.setattr(settings, "redis_host", "127.0.0.1")
    monkeypatch.setattr(settings, "redis_port", 36379)


def test_refuses_without_runner_auth(monkeypatch):
    monkeypatch.delenv("CODEWARE_TEST_STACK_ID", raising=False)
    monkeypatch.delenv("CODEWARE_TEST_AUTH", raising=False)
    with pytest.raises(UnsafeTargetError, match="授权"):
        assert_safe_targets()


def test_refuses_dev_db_in_denylist(valid_static_target, monkeypatch):
    monkeypatch.setattr(settings, "pg_db", "ai_center_py")
    with pytest.raises(UnsafeTargetError, match="黑名单"):
        assert_safe_targets()


def test_refuses_db_not_owned_by_stack(valid_static_target, monkeypatch):
    monkeypatch.setattr(settings, "pg_db", "codeaware_test_zzz99999")
    with pytest.raises(UnsafeTargetError, match="stack_id"):
        assert_safe_targets()


def test_refuses_redis_db_zero(valid_static_target, monkeypatch):
    monkeypatch.setattr(settings, "redis_db", 0)
    with pytest.raises(UnsafeTargetError, match="Redis"):
        assert_safe_targets()


def test_refuses_wrong_dynamic_port(valid_static_target, monkeypatch):
    monkeypatch.setattr(settings, "redis_port", 6380)
    with pytest.raises(UnsafeTargetError, match="REDIS_PORT"):
        assert_safe_targets()


def test_refuses_non_loopback_host(valid_static_target, monkeypatch):
    monkeypatch.setattr(settings, "pg_host", "10.0.0.5")
    with pytest.raises(UnsafeTargetError, match="loopback"):
        assert_safe_targets()


def test_accepts_valid_static_disposable_target(valid_static_target):
    assert assert_safe_targets() == SID


async def test_identity_accepts_runner_owned_target():
    assert await assert_safe_target_identity() == __import__("os").environ[
        "CODEWARE_TEST_STACK_ID"
    ]


async def test_identity_rejects_missing_pg_sentinel(valid_static_target, monkeypatch):
    async def connect(**_kwargs):
        raise OSError("not the runner database")

    monkeypatch.setattr("asyncpg.connect", connect)
    with pytest.raises(UnsafeTargetError, match="PG runner sentinel"):
        await assert_safe_target_identity()


async def test_identity_rejects_mismatched_pg_sentinel(valid_static_target, monkeypatch):
    class Connection:
        async def fetchval(self, *_args):
            return hashlib.sha256(b"different-auth").hexdigest()

        async def close(self):
            return None

    async def connect(**_kwargs):
        return Connection()

    monkeypatch.setattr("asyncpg.connect", connect)
    with pytest.raises(UnsafeTargetError, match="PG runner sentinel 不匹配"):
        await assert_safe_target_identity()


async def test_identity_rejects_mismatched_redis_sentinel(valid_static_target, monkeypatch):
    expected_hash = hashlib.sha256(AUTH.encode()).hexdigest()

    class Connection:
        async def fetchval(self, *_args):
            return expected_hash

        async def close(self):
            return None

    class Redis:
        def __init__(self, **_kwargs):
            pass

        async def get(self, _key):
            return "wrong"

        async def aclose(self):
            return None

    async def connect(**_kwargs):
        return Connection()

    monkeypatch.setattr("asyncpg.connect", connect)
    monkeypatch.setattr("redis.asyncio.Redis", Redis)
    with pytest.raises(UnsafeTargetError, match="Redis runner sentinel 不匹配"):
        await assert_safe_target_identity()
