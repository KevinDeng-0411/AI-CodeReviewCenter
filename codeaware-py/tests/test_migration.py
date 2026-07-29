"""P1：Alembic 迁移 up/down 往返（在独立 ai_center_migtest 库上）。

同步测试 + alembic command API（内部 asyncio.run，sync 测试无运行 loop 不冲突），
避免子进程 `uv run alembic` 的多次启动开销。
"""

import app.core.config as cfg
from alembic import command
from alembic.config import Config

ALEMBIC_INI = "alembic.ini"


def test_migration_roundtrip():
    orig_db = cfg.settings.pg_db
    cfg.settings.pg_db = "ai_center_migtest"  # 独立库，env.py 经 settings 连接
    ac = Config(ALEMBIC_INI)
    try:
        command.downgrade(ac, "base")  # 清空（fresh 库为 no-op）
        command.upgrade(ac, "head")    # 建：验证 upgrade SQL
        command.downgrade(ac, "base")  # 拆：验证 downgrade SQL
        command.upgrade(ac, "head")    # 重建：可重复
    finally:
        cfg.settings.pg_db = orig_db
