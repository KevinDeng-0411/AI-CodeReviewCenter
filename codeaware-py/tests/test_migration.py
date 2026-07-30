"""P1：Alembic 迁移 up/down 往返（在 runner 注入的 stack_id mig 库上）。

同步测试 + alembic command API（内部 asyncio.run，sync 测试无运行 loop 不冲突），
避免子进程 `uv run alembic` 的多次启动开销。destructive 前经 _safeguard 校验 mig 库属本次 stack。
"""

import os

import app.core.config as cfg
from _safeguard import assert_safe_targets
from alembic import command
from alembic.config import Config

ALEMBIC_INI = "alembic.ini"


def test_migration_roundtrip():
    orig_db = cfg.settings.pg_db
    cfg.settings.pg_db = os.environ["CODEWARE_TEST_MIG_DB"]  # runner 注入：codeaware_migtest_<stack_id>
    assert_safe_targets()  # 校验 mig 库含 stack_id、非开发库
    ac = Config(ALEMBIC_INI)
    try:
        command.downgrade(ac, "base")  # 清空（fresh 库为 no-op）
        command.upgrade(ac, "head")    # 建：验证 upgrade SQL
        command.downgrade(ac, "base")  # 拆：验证 downgrade SQL
        command.upgrade(ac, "head")    # 重建：可重复
    finally:
        cfg.settings.pg_db = orig_db
