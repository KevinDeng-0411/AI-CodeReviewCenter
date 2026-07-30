#!/usr/bin/env python3
"""fail-closed 测试执行器 - C1-SAFE-HARNESS。

每次运行创建一次性 PG/Redis stack（随机 stack_id、动态端口、ephemeral volume），
注入连接信息与授权变量后跑 pytest，结束精确清理本次 project。

- 调用：`(cd codeaware-py && uv run python scripts/run_tests_safe.py [-q|--cov=app ...])`
- 拒绝复用开发库：测试库由本脚本以 stack_id 后缀创建；fixture 侧 _safeguard 二次校验。
- 任何清理失败返回非零，不打印 PASS。

不在本脚本内做业务代码修改；仅编排一次性环境与 pytest。
"""

from __future__ import annotations

import asyncio
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
APP_ROOT = SCRIPT_DIR.parent  # codeaware-py/
COMPOSE_FILE = SCRIPT_DIR / "test-stack.compose.yml"
PG_USER = "aicenter"
PG_PASSWORD = "aicenter123"
PG_SEED_DB = "codeaware_seed"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _compose(stack_id: str, *args: str, capture: bool = False, check: bool = True) -> subprocess.CompletedProcess:
    project = f"codeaware-test-{stack_id}"
    cmd = ["docker", "compose", "-p", project, "-f", str(COMPOSE_FILE), *args]
    return subprocess.run(cmd, capture_output=capture, text=True, check=check)


async def _wait_pg(host: str, port: int, timeout: float = 60.0) -> None:
    import asyncpg

    deadline = time.time() + timeout
    last: Exception | None = None
    while time.time() < deadline:
        try:
            conn = await asyncpg.connect(
                host=host, port=port, user=PG_USER, password=PG_PASSWORD, database=PG_SEED_DB
            )
            await conn.close()
            return
        except Exception as e:  # noqa: BLE001
            last = e
            await asyncio.sleep(1)
    raise RuntimeError(f"PG 未在 {timeout}s 内就绪: {last}")


async def _create_dbs(host: str, port: int, names: list[str]) -> None:
    import asyncpg

    conn = await asyncpg.connect(
        host=host, port=port, user=PG_USER, password=PG_PASSWORD, database=PG_SEED_DB
    )
    try:
        for name in names:
            # CREATE DATABASE 不允许在事务内；asyncpg execute 走 simple query，不强制事务
            await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


def _wait_redis(host: str, port: int, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), 2):
                return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"Redis 未在 {timeout}s 内就绪")


def main() -> int:
    pytest_args = sys.argv[1:]
    stack_id = secrets.token_hex(4)
    pg_port = _free_port()
    redis_port = _free_port()
    test_db = f"codeaware_test_{stack_id}"
    mig_db = f"codeaware_migtest_{stack_id}"

    print(f"[safe-runner] stack_id={stack_id} pg=127.0.0.1:{pg_port} redis=127.0.0.1:{redis_port}")
    print(f"[safe-runner] test_db={test_db} mig_db={mig_db}")

    up_env = os.environ.copy()
    up_env["CODEWARE_TEST_PG_PORT"] = str(pg_port)
    up_env["CODEWARE_TEST_REDIS_PORT"] = str(redis_port)
    project = f"codeaware-test-{stack_id}"
    subprocess.run(
        ["docker", "compose", "-p", project, "-f", str(COMPOSE_FILE), "up", "-d"],
        env=up_env,
        check=True,
    )

    rc = 1
    try:
        asyncio.run(_wait_pg("127.0.0.1", pg_port))
        asyncio.run(_create_dbs("127.0.0.1", pg_port, [test_db, mig_db]))
        _wait_redis("127.0.0.1", redis_port)

        test_env = os.environ.copy()
        test_env.update(
            {
                "PG_HOST": "127.0.0.1",
                "PG_PORT": str(pg_port),
                "PG_USER": PG_USER,
                "PG_PASSWORD": PG_PASSWORD,
                "PG_DB": test_db,
                "REDIS_HOST": "127.0.0.1",
                "REDIS_PORT": str(redis_port),
                "REDIS_DB": "1",
                "CODEWARE_TEST_STACK_ID": stack_id,
                "CODEWARE_TEST_AUTH": secrets.token_hex(8),
                "CODEWARE_TEST_MIG_DB": mig_db,
                "CODEAWARE_TESTING": "1",
            }
        )
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", *pytest_args],
            env=test_env,
            cwd=str(APP_ROOT),
        )
        rc = proc.returncode
    finally:
        down = _compose(stack_id, "down", "-v", "--remove-orphans", capture=True, check=False)
        if down.returncode != 0:
            print(f"[safe-runner] !! 清理失败 (rc={down.returncode}): {down.stderr.strip()}", file=sys.stderr)
            rc = 1
        else:
            print(f"[safe-runner] 已精确清理 project {project}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
