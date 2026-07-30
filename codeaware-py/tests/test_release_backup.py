"""C3-C logical backup/restore drill on the safe runner's disposable database."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import asyncpg

from _safeguard import assert_safe_target_identity
from app.core.config import settings


COMPOSE_FILE = Path(__file__).resolve().parents[1] / "scripts/test-stack.compose.yml"
PROBE_TABLE = "c3_backup_restore_probe"


def _compose_exec(*argv: str, input_bytes: bytes | None = None):
    stack_id = os.environ["CODEWARE_TEST_STACK_ID"]
    return subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            f"codeaware-test-{stack_id}",
            "-f",
            str(COMPOSE_FILE),
            "exec",
            "-T",
            "pg",
            *argv,
        ],
        check=True,
        capture_output=True,
        input=input_bytes,
    )


async def test_disposable_database_logical_backup_restore(setup_db):
    await assert_safe_target_identity()
    connection = await asyncpg.connect(
        host=settings.pg_host,
        port=settings.pg_port,
        user=settings.pg_user,
        password=settings.pg_password,
        database=settings.pg_db,
    )
    try:
        await connection.execute(
            f"CREATE TABLE {PROBE_TABLE} "
            "(id integer PRIMARY KEY, payload text NOT NULL)"
        )
        await connection.execute(
            f"INSERT INTO {PROBE_TABLE} (id, payload) "
            "VALUES (1, 'c3-backup-restore-ok')"
        )

        dump = _compose_exec(
            "pg_dump",
            "--username",
            settings.pg_user,
            "--dbname",
            settings.pg_db,
            "--format=plain",
            "--data-only",
            "--column-inserts",
            "--no-owner",
            "--no-privileges",
            "--table",
            f"public.{PROBE_TABLE}",
        )
        assert f"INSERT INTO public.{PROBE_TABLE}".encode() in dump.stdout

        await assert_safe_target_identity()
        await connection.execute(f"TRUNCATE TABLE {PROBE_TABLE}")
        assert await connection.fetchval(f"SELECT count(*) FROM {PROBE_TABLE}") == 0

        _compose_exec(
            "psql",
            "--username",
            settings.pg_user,
            "--dbname",
            settings.pg_db,
            "--set",
            "ON_ERROR_STOP=1",
            input_bytes=dump.stdout,
        )
        restored = await connection.fetchrow(
            f"SELECT id, payload FROM {PROBE_TABLE}"
        )
        assert dict(restored) == {
            "id": 1,
            "payload": "c3-backup-restore-ok",
        }
        print(
            "[C3 BACKUP] PASS format=plain-data-only rows=1 "
            "disposable_database=true credentials_logged=false"
        )
    finally:
        await assert_safe_target_identity()
        await connection.execute(f"DROP TABLE IF EXISTS {PROBE_TABLE}")
        await connection.close()
