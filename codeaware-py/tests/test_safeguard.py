"""C1-SAFE-HARNESS: fail-closed 目标守卫的拒绝/接受逻辑。

验证 _safeguard.assert_safe_targets 在以下情形的判定：
- 无 runner 授权 -> 拒（禁止裸跑 destructive）
- 开发库（黑名单）-> 拒
- 库名不含本次 stack_id -> 拒
- REDIS_DB=0 -> 拒
- 非 loopback -> 拒
- 合法一次性 stack -> 通过
"""

import pytest

from app.core.config import settings
from _safeguard import UnsafeTargetError, assert_safe_targets

SID = "abc12345"


def test_refuses_without_runner_auth(monkeypatch):
    monkeypatch.delenv("CODEWARE_TEST_STACK_ID", raising=False)
    monkeypatch.delenv("CODEWARE_TEST_AUTH", raising=False)
    with pytest.raises(UnsafeTargetError, match="授权"):
        assert_safe_targets()


def test_refuses_dev_db_in_denylist(monkeypatch):
    monkeypatch.setenv("CODEWARE_TEST_STACK_ID", SID)
    monkeypatch.setenv("CODEWARE_TEST_AUTH", "secret")
    monkeypatch.setattr(settings, "pg_db", "ai_center_py")
    with pytest.raises(UnsafeTargetError, match="黑名单"):
        assert_safe_targets()


def test_refuses_db_without_stack_id_suffix(monkeypatch):
    monkeypatch.setenv("CODEWARE_TEST_STACK_ID", SID)
    monkeypatch.setenv("CODEWARE_TEST_AUTH", "secret")
    # 名字像测试库但不含本次 stack_id -> 拒（防止冒充）
    monkeypatch.setattr(settings, "pg_db", "codeaware_test_zzz99999")
    with pytest.raises(UnsafeTargetError, match="stack_id"):
        assert_safe_targets()


def test_refuses_redis_db_zero(monkeypatch):
    monkeypatch.setenv("CODEWARE_TEST_STACK_ID", SID)
    monkeypatch.setenv("CODEWARE_TEST_AUTH", "secret")
    monkeypatch.setattr(settings, "pg_db", f"codeaware_test_{SID}")
    monkeypatch.setattr(settings, "pg_host", "127.0.0.1")
    monkeypatch.setattr(settings, "redis_db", 0)
    with pytest.raises(UnsafeTargetError, match="REDIS_DB"):
        assert_safe_targets()


def test_refuses_non_loopback_host(monkeypatch):
    monkeypatch.setenv("CODEWARE_TEST_STACK_ID", SID)
    monkeypatch.setenv("CODEWARE_TEST_AUTH", "secret")
    monkeypatch.setattr(settings, "pg_db", f"codeaware_test_{SID}")
    monkeypatch.setattr(settings, "pg_host", "10.0.0.5")
    with pytest.raises(UnsafeTargetError, match="loopback"):
        assert_safe_targets()


def test_accepts_valid_disposable_stack(monkeypatch):
    monkeypatch.setenv("CODEWARE_TEST_STACK_ID", SID)
    monkeypatch.setenv("CODEWARE_TEST_AUTH", "secret")
    monkeypatch.setattr(settings, "pg_db", f"codeaware_test_{SID}")
    monkeypatch.setattr(settings, "pg_host", "127.0.0.1")
    monkeypatch.setattr(settings, "redis_db", 1)
    monkeypatch.setattr(settings, "redis_host", "localhost")
    assert assert_safe_targets() == SID
