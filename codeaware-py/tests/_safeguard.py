"""Fail-closed destructive-test target guard.

Static checks reject obviously unsafe targets. The async identity check additionally
requires a runner-created sentinel in both the selected PostgreSQL database and an
isolated Redis guard DB, so inherited or hand-written environment variables are not
enough to authorize drop_all, flushdb, or Alembic downgrade.
"""

from __future__ import annotations

import hashlib
import os
import re

import asyncpg
import redis.asyncio as aioredis

from app.core.config import settings

DENY_PG_DBS = {
    "ai_center",
    "ai_center_py",
    "ai_center_test",
    "ai_center_migtest",
    "postgres",
    "codeaware_seed",
}
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
STACK_ID_RE = re.compile(r"^[0-9a-f]{16}$")
GUARD_TABLE = "codeaware_test_guard"
GUARD_KEY_PREFIX = "codeaware:test-guard:"


class UnsafeTargetError(RuntimeError):
    """The requested destructive test target is not runner-owned."""


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise UnsafeTargetError(
            "缺少 runner 授权或目标标识；禁止裸跑 destructive 测试，"
            "请经 scripts/run_tests_safe.py 执行。"
        )
    return value


def assert_safe_targets() -> str:
    """Perform non-I/O target validation and return the stack identity."""
    stack_id = _required_env("CODEWARE_TEST_STACK_ID")
    _required_env("CODEWARE_TEST_AUTH")
    expected_pg_port = _required_env("CODEWARE_TEST_PG_PORT")
    expected_redis_port = _required_env("CODEWARE_TEST_REDIS_PORT")
    guard_db_raw = _required_env("CODEWARE_TEST_REDIS_GUARD_DB")

    if not STACK_ID_RE.fullmatch(stack_id):
        raise UnsafeTargetError("stack_id 格式无效，拒绝。")

    allowed_dbs = {
        f"codeaware_test_{stack_id}",
        f"codeaware_migtest_{stack_id}",
    }
    if settings.pg_db in DENY_PG_DBS:
        raise UnsafeTargetError(f"PG_DB={settings.pg_db!r} 在黑名单（开发/固定库），拒绝。")
    if settings.pg_db not in allowed_dbs:
        raise UnsafeTargetError(f"PG_DB={settings.pg_db!r} 不属于本次 stack_id，拒绝。")
    if settings.pg_host not in LOOPBACK_HOSTS:
        raise UnsafeTargetError(f"PG_HOST={settings.pg_host!r} 非 loopback，拒绝。")
    if str(settings.pg_port) != expected_pg_port:
        raise UnsafeTargetError("PG_PORT 与 runner 临时实例不匹配，拒绝。")

    try:
        guard_db = int(guard_db_raw)
    except ValueError as exc:
        raise UnsafeTargetError("Redis guard DB 格式无效，拒绝。") from exc
    if settings.redis_db == 0 or guard_db == 0 or settings.redis_db == guard_db:
        raise UnsafeTargetError("Redis 测试 DB/guard DB 必须隔离且均非 0，拒绝。")
    if settings.redis_host not in LOOPBACK_HOSTS:
        raise UnsafeTargetError(f"REDIS_HOST={settings.redis_host!r} 非 loopback，拒绝。")
    if str(settings.redis_port) != expected_redis_port:
        raise UnsafeTargetError("REDIS_PORT 与 runner 临时实例不匹配，拒绝。")

    return stack_id


async def assert_safe_target_identity() -> str:
    """Verify the runner capability against PG and Redis sentinels."""
    stack_id = assert_safe_targets()
    auth_hash = hashlib.sha256(_required_env("CODEWARE_TEST_AUTH").encode()).hexdigest()

    try:
        connection = await asyncpg.connect(
            host=settings.pg_host,
            port=settings.pg_port,
            user=settings.pg_user,
            password=settings.pg_password,
            database=settings.pg_db,
            timeout=3,
        )
        try:
            pg_hash = await connection.fetchval(
                f"SELECT auth_sha256 FROM {GUARD_TABLE} WHERE stack_id = $1",
                stack_id,
            )
        finally:
            await connection.close()
    except Exception as exc:  # noqa: BLE001
        raise UnsafeTargetError("PG runner sentinel 缺失或不可验证，拒绝。") from exc
    if pg_hash != auth_hash:
        raise UnsafeTargetError("PG runner sentinel 不匹配，拒绝。")

    guard_db = int(_required_env("CODEWARE_TEST_REDIS_GUARD_DB"))
    client = aioredis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=guard_db,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )
    try:
        redis_hash = await client.get(f"{GUARD_KEY_PREFIX}{stack_id}")
    except Exception as exc:  # noqa: BLE001
        raise UnsafeTargetError("Redis runner sentinel 缺失或不可验证，拒绝。") from exc
    finally:
        await client.aclose()
    if redis_hash != auth_hash:
        raise UnsafeTargetError("Redis runner sentinel 不匹配，拒绝。")

    return stack_id
