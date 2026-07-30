"""P1：Alembic 迁移 up/down 往返（在 runner 注入的 stack_id mig 库上）。

同步测试 + alembic command API（内部 asyncio.run，sync 测试无运行 loop 不冲突），
避免子进程 `uv run alembic` 的多次启动开销。destructive 前经 _safeguard 校验 mig 库属本次 stack。
"""

import asyncio
import os

import asyncpg
import app.core.config as cfg
from _safeguard import assert_safe_targets
from alembic import command
from alembic.config import Config

ALEMBIC_INI = "alembic.ini"


async def _assert_summary_watermark_default() -> None:
    connection = await asyncpg.connect(
        host=cfg.settings.pg_host,
        port=cfg.settings.pg_port,
        user=cfg.settings.pg_user,
        password=cfg.settings.pg_password,
        database=cfg.settings.pg_db,
    )
    try:
        await connection.execute(
            "INSERT INTO conversations (conversation_id, title) "
            "VALUES ('migration-watermark-default', 'migration')"
        )
        value = await connection.fetchval(
            "SELECT summary_message_count FROM conversations "
            "WHERE conversation_id = 'migration-watermark-default'"
        )
        assert value == 0
    finally:
        await connection.close()


def test_migration_roundtrip():
    orig_db = cfg.settings.pg_db
    cfg.settings.pg_db = os.environ["CODEWARE_TEST_MIG_DB"]  # runner 注入：codeaware_migtest_<stack_id>
    assert_safe_targets()  # 校验 mig 库含 stack_id、非开发库
    ac = Config(ALEMBIC_INI)
    try:
        command.downgrade(ac, "base")  # 清空（fresh 库为 no-op）
        command.upgrade(ac, "0002")
        command.upgrade(ac, "0003")    # C1-B：新增水位线
        asyncio.run(_assert_summary_watermark_default())
        command.downgrade(ac, "0002")  # C1-B：删除水位线
        command.upgrade(ac, "0003")    # C1-B：再次新增，验证可往返
        command.downgrade(ac, "base")  # 拆：验证 downgrade SQL
        command.upgrade(ac, "head")    # 重建：可重复
    finally:
        cfg.settings.pg_db = orig_db
