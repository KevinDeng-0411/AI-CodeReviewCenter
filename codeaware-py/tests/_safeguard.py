"""fail-closed 目标守卫 - 在任何 destructive 操作（drop_all / flushdb / alembic downgrade）前校验。

由 scripts/run_tests_safe.py 注入 CODEWARE_TEST_STACK_ID + CODEWARE_TEST_AUTH + 连接信息；
fixture 侧调用 assert_safe_targets() 确认目标属于本次一次性 stack，而非开发/共享库。

即便调用者手工导出 auth 变量，也无法绕过：开发库名（ai_center/ai_center_py 等）在黑名单且
不含本次 stack_id 后缀，校验失败即抛错、不执行 destructive 操作。
"""

import os

from app.core.config import settings

# 开发/固定库名黑名单——任何情况下都禁止对其 drop_all / downgrade
DENY_PG_DBS = {
    "ai_center",
    "ai_center_py",
    "ai_center_test",
    "ai_center_migtest",
    "postgres",
    "codeaware_seed",
}
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


class UnsafeTargetError(RuntimeError):
    """目标不安全，拒绝执行 destructive 测试操作。"""


def assert_safe_targets() -> str:
    """校验 PG/Redis 目标属于本次 runner 一次性 stack。返回 stack_id。"""
    stack_id = os.environ.get("CODEWARE_TEST_STACK_ID")
    auth = os.environ.get("CODEWARE_TEST_AUTH")
    if not stack_id or not auth:
        raise UnsafeTargetError(
            "缺少 runner 授权（CODEWARE_TEST_STACK_ID / CODEWARE_TEST_AUTH）。"
            "禁止裸跑 destructive 测试；请经 scripts/run_tests_safe.py 执行。"
        )

    pg_db = settings.pg_db
    if pg_db in DENY_PG_DBS:
        raise UnsafeTargetError(f"PG_DB={pg_db!r} 在黑名单（开发/固定库），拒绝。")
    if stack_id not in pg_db:
        raise UnsafeTargetError(f"PG_DB={pg_db!r} 不含本次 stack_id={stack_id!r}，拒绝。")
    if settings.pg_host not in LOOPBACK_HOSTS:
        raise UnsafeTargetError(f"PG_HOST={settings.pg_host!r} 非 loopback，拒绝。")

    if settings.redis_db == 0:
        raise UnsafeTargetError("REDIS_DB=0 拒绝（开发库）。")
    if settings.redis_host not in LOOPBACK_HOSTS:
        raise UnsafeTargetError(f"REDIS_HOST={settings.redis_host!r} 非 loopback，拒绝。")

    return stack_id
