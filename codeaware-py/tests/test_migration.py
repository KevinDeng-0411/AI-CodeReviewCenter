"""P1：Alembic 迁移 up/down 往返（在 runner 注入的 stack_id mig 库上）。

同步测试 + alembic command API（内部 asyncio.run，sync 测试无运行 loop 不冲突），
避免子进程 `uv run alembic` 的多次启动开销。destructive 前经 _safeguard 校验 mig 库属本次 stack。
"""

import asyncio
import os

import asyncpg
import app.core.config as cfg
from _safeguard import assert_safe_target_identity
from alembic import command
from alembic.config import Config
from asyncpg import UniqueViolationError

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


async def _seed_duplicate_ai_readme_versions() -> None:
    connection = await _migration_connection()
    try:
        await connection.executemany(
            "INSERT INTO ai_readme_documents "
            "(project_name, section, content, version) VALUES ($1, $2, $3, $4)",
            [
                ("project-a", "README", "first", 1),
                ("project-a", "README", "second", 1),
                ("project-b", "README", "only", 1),
            ],
        )
    finally:
        await connection.close()


async def _assert_ai_readme_0004(*, metadata_present: bool) -> None:
    connection = await _migration_connection()
    try:
        columns = {
            row["column_name"]
            for row in await connection.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'ai_readme_documents'"
            )
        }
        snapshot_columns = {
            "snapshot_hash",
            "snapshot_file_count",
            "snapshot_generated_at",
            "snapshot_truncated",
        }
        assert snapshot_columns.issubset(columns) is metadata_present

        rows = await connection.fetch(
            "SELECT project_name, content, version "
            "FROM ai_readme_documents ORDER BY project_name, id"
        )
        assert [
            (row["project_name"], row["content"], row["version"]) for row in rows
        ] == [
            ("project-a", "first", 1),
            ("project-a", "second", 2),
            ("project-b", "only", 1),
        ]

        index_exists = await connection.fetchval(
            "SELECT EXISTS ("
            "SELECT 1 FROM pg_indexes "
            "WHERE schemaname = 'public' "
            "AND tablename = 'ai_readme_documents' "
            "AND indexname = 'uq_ard_project_name_version'"
            ")"
        )
        assert index_exists is metadata_present

        if metadata_present:
            try:
                await connection.execute(
                    "INSERT INTO ai_readme_documents "
                    "(project_name, section, content, version) "
                    "VALUES ('project-a', 'README', 'duplicate', 2)"
                )
            except UniqueViolationError:
                pass
            else:
                raise AssertionError("同项目重复 version 应被唯一索引拒绝")
    finally:
        await connection.close()


async def _migration_connection():
    return await asyncpg.connect(
        host=cfg.settings.pg_host,
        port=cfg.settings.pg_port,
        user=cfg.settings.pg_user,
        password=cfg.settings.pg_password,
        database=cfg.settings.pg_db,
    )


def _safe_downgrade(config: Config, revision: str) -> None:
    asyncio.run(assert_safe_target_identity())
    command.downgrade(config, revision)


def test_migration_roundtrip():
    orig_db = cfg.settings.pg_db
    cfg.settings.pg_db = os.environ["CODEWARE_TEST_MIG_DB"]  # runner 注入：codeaware_migtest_<stack_id>
    ac = Config(ALEMBIC_INI)
    try:
        _safe_downgrade(ac, "base")  # 清空（fresh 库为 no-op）
        command.upgrade(ac, "0002")
        command.upgrade(ac, "0003")    # C1-B：新增水位线
        asyncio.run(_assert_summary_watermark_default())
        asyncio.run(_seed_duplicate_ai_readme_versions())
        command.upgrade(ac, "0004")    # C1-E：元数据、版本回填、唯一索引
        asyncio.run(_assert_ai_readme_0004(metadata_present=True))
        _safe_downgrade(ac, "0003")   # C1-E：删除元数据/索引，保留已回填 version
        asyncio.run(_assert_ai_readme_0004(metadata_present=False))
        command.upgrade(ac, "0004")    # C1-E：再次新增，验证可往返
        asyncio.run(_assert_ai_readme_0004(metadata_present=True))
        _safe_downgrade(ac, "0002")   # C1-B：删除水位线
        command.upgrade(ac, "0004")    # C1-B/C1-E：再次新增到 head，验证迁移链
        _safe_downgrade(ac, "base")  # 拆：验证 downgrade SQL
        command.upgrade(ac, "head")    # 重建：可重复
    finally:
        cfg.settings.pg_db = orig_db
