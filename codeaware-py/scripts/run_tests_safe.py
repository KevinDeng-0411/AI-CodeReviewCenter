#!/usr/bin/env python3
"""Fail-closed test runner for disposable PostgreSQL and Redis targets."""

from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
APP_ROOT = SCRIPT_DIR.parent
COMPOSE_FILE = SCRIPT_DIR / "test-stack.compose.yml"
PG_USER = "aicenter"
PG_PASSWORD = "aicenter123"
PG_SEED_DB = "codeaware_seed"
REDIS_GUARD_DB = 15
GUARD_TABLE = "codeaware_test_guard"
GUARD_KEY_PREFIX = "codeaware:test-guard:"


class RunnerInterrupted(RuntimeError):
    """Raised by SIGINT/SIGTERM so the exact stack is cleaned in finally."""


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _compose(
    stack_id: str,
    *args: str,
    env: dict[str, str] | None = None,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess:
    project = f"codeaware-test-{stack_id}"
    command = ["docker", "compose", "-p", project, "-f", str(COMPOSE_FILE), *args]
    return subprocess.run(
        command,
        env=env,
        capture_output=capture,
        text=True,
        check=check,
    )


async def _wait_pg(host: str, port: int, timeout: float = 60.0) -> None:
    import asyncpg

    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            connection = await asyncpg.connect(
                host=host,
                port=port,
                user=PG_USER,
                password=PG_PASSWORD,
                database=PG_SEED_DB,
            )
            await connection.close()
            return
        except Exception as exc:  # noqa: BLE001
            last = exc
            await asyncio.sleep(1)
    raise RuntimeError(f"PG 未在 {timeout}s 内就绪: {type(last).__name__}")


async def _create_dbs(host: str, port: int, names: list[str]) -> None:
    import asyncpg

    connection = await asyncpg.connect(
        host=host,
        port=port,
        user=PG_USER,
        password=PG_PASSWORD,
        database=PG_SEED_DB,
    )
    try:
        for name in names:
            await connection.execute(f'CREATE DATABASE "{name}" OWNER "{PG_USER}"')
    finally:
        await connection.close()


async def _seed_identity(
    host: str,
    pg_port: int,
    redis_port: int,
    databases: list[str],
    stack_id: str,
    auth: str,
) -> None:
    import asyncpg
    import redis.asyncio as aioredis

    auth_hash = hashlib.sha256(auth.encode()).hexdigest()
    for database in databases:
        connection = await asyncpg.connect(
            host=host,
            port=pg_port,
            user=PG_USER,
            password=PG_PASSWORD,
            database=database,
        )
        try:
            await connection.execute(
                f"""
                CREATE TABLE {GUARD_TABLE} (
                    stack_id text PRIMARY KEY,
                    auth_sha256 text NOT NULL
                )
                """
            )
            await connection.execute(
                f"INSERT INTO {GUARD_TABLE} (stack_id, auth_sha256) VALUES ($1, $2)",
                stack_id,
                auth_hash,
            )
        finally:
            await connection.close()

    client = aioredis.Redis(
        host=host,
        port=redis_port,
        db=REDIS_GUARD_DB,
        decode_responses=True,
    )
    try:
        await client.set(f"{GUARD_KEY_PREFIX}{stack_id}", auth_hash)
    finally:
        await client.aclose()


def _wait_redis(host: str, port: int, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), 2):
                return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"Redis 未在 {timeout}s 内就绪")


def _raise_interrupted(signum: int, _frame) -> None:
    raise RunnerInterrupted(f"received signal {signum}")


def _wait_http(url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(0.25)
    raise RuntimeError(
        f"HTTP 服务未在 {timeout}s 内就绪: {type(last).__name__}"
    )


def _stop_process(process: subprocess.Popen | None, label: str) -> bool:
    if process is None or process.poll() is not None:
        return True
    process.terminate()
    try:
        process.wait(timeout=10)
        return True
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=5)
            return True
        except subprocess.TimeoutExpired:
            print(
                f"[safe-runner] !! {label} cleanup failed",
                file=sys.stderr,
            )
            return False


def _run_browser_e2e(test_env: dict[str, str]) -> int:
    """Run real FastAPI + Vite + Playwright against the disposable stack."""
    backend: subprocess.Popen | None = None
    frontend: subprocess.Popen | None = None
    cleanup_ok = True
    frontend_root = APP_ROOT / "frontend"
    with tempfile.TemporaryDirectory(prefix="codeaware-browser-e2e-") as tmp:
        allowed_root = Path(tmp) / "allowed"
        project = allowed_root / "fixture-project"
        project.mkdir(parents=True)
        (project / "README.md").write_text(
            "# Browser Fixture\n\nA safe project used only by C2 browser E2E.\n",
            encoding="utf-8",
        )
        (project / "pyproject.toml").write_text(
            '[project]\nname = "browser-fixture"\nversion = "1.0.0"\n',
            encoding="utf-8",
        )
        (project / "main.py").write_text(
            'print("browser-entrypoint")\n',
            encoding="utf-8",
        )

        browser_env = test_env.copy()
        browser_env.update(
            {
                "CODEAWARE_BROWSER_E2E": "1",
                "CODEAWARE_BROWSER_E2E_PROJECT_ROOT": str(allowed_root),
            }
        )
        migration = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            env=browser_env,
            cwd=str(APP_ROOT),
        )
        if migration.returncode != 0:
            return migration.returncode

        backend_port = _free_port()
        frontend_port = _free_port()
        base_url = f"http://127.0.0.1:{frontend_port}"
        try:
            backend = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(backend_port),
                ],
                env=browser_env,
                cwd=str(APP_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _wait_http(f"http://127.0.0.1:{backend_port}/health/live")

            frontend_env = browser_env.copy()
            frontend_env["CODEAWARE_API_BASE_URL"] = (
                f"http://127.0.0.1:{backend_port}"
            )
            frontend = subprocess.Popen(
                [
                    "npm",
                    "run",
                    "dev",
                    "--",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(frontend_port),
                    "--strictPort",
                ],
                env=frontend_env,
                cwd=str(frontend_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _wait_http(base_url)

            playwright_env = frontend_env.copy()
            playwright_env.update(
                {
                    "CI": "1",
                    "CODEAWARE_BROWSER_BASE_URL": base_url,
                    "CODEAWARE_E2E_PROJECT_PATH": str(project),
                }
            )
            chrome = Path(
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            )
            if chrome.is_file():
                playwright_env["PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"] = str(
                    chrome
                )
            result = subprocess.run(
                ["npm", "run", "test:e2e"],
                env=playwright_env,
                cwd=str(frontend_root),
            )
            return result.returncode
        finally:
            cleanup_ok = _stop_process(frontend, "frontend") and cleanup_ok
            cleanup_ok = _stop_process(backend, "backend") and cleanup_ok
            if not cleanup_ok:
                raise RuntimeError("browser E2E process cleanup failed")


def run(pytest_args: list[str]) -> int:
    stack_id = secrets.token_hex(8)
    auth = secrets.token_hex(16)
    pg_port = _free_port()
    redis_port = _free_port()
    test_db = f"codeaware_test_{stack_id}"
    mig_db = f"codeaware_migtest_{stack_id}"
    project = f"codeaware-test-{stack_id}"

    print(
        f"[safe-runner] stack_id={stack_id} "
        f"pg=127.0.0.1:{pg_port} redis=127.0.0.1:{redis_port}"
    )
    print(
        f"[safe-runner] test_db={test_db} mig_db={mig_db} "
        f"redis_db=1 guard_db={REDIS_GUARD_DB}"
    )

    compose_env = os.environ.copy()
    compose_env["CODEWARE_TEST_PG_PORT"] = str(pg_port)
    compose_env["CODEWARE_TEST_REDIS_PORT"] = str(redis_port)

    previous_handlers: dict[int, object] = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, _raise_interrupted)

    rc = 1
    try:
        _compose(stack_id, "up", "-d", env=compose_env)
        asyncio.run(_wait_pg("127.0.0.1", pg_port))
        asyncio.run(_create_dbs("127.0.0.1", pg_port, [test_db, mig_db]))
        _wait_redis("127.0.0.1", redis_port)
        asyncio.run(
            _seed_identity(
                "127.0.0.1",
                pg_port,
                redis_port,
                [test_db, mig_db],
                stack_id,
                auth,
            )
        )

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
                "CODEWARE_TEST_AUTH": auth,
                "CODEWARE_TEST_PG_PORT": str(pg_port),
                "CODEWARE_TEST_REDIS_PORT": str(redis_port),
                "CODEWARE_TEST_REDIS_GUARD_DB": str(REDIS_GUARD_DB),
                "CODEWARE_TEST_MIG_DB": mig_db,
                "CODEAWARE_TESTING": "1",
            }
        )
        if pytest_args == ["--browser-e2e"]:
            rc = _run_browser_e2e(test_env)
        elif pytest_args == ["--live-eval"]:
            process = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-m",
                    "live_eval",
                    "tests/integration/test_current_release_live.py",
                    "-q",
                    "-s",
                ],
                env=test_env,
                cwd=str(APP_ROOT),
            )
            rc = process.returncode
        else:
            process = subprocess.run(
                [sys.executable, "-m", "pytest", *pytest_args],
                env=test_env,
                cwd=str(APP_ROOT),
            )
            rc = process.returncode
    except RunnerInterrupted as exc:
        print(f"[safe-runner] interrupted: {exc}", file=sys.stderr)
        rc = 130
    except Exception as exc:  # noqa: BLE001
        print(f"[safe-runner] failed: {type(exc).__name__}", file=sys.stderr)
        rc = 1
    finally:
        for signum in previous_handlers:
            signal.signal(signum, signal.SIG_IGN)
        try:
            down = _compose(
                stack_id,
                "down",
                "-v",
                "--remove-orphans",
                env=compose_env,
                capture=True,
                check=False,
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"[safe-runner] !! cleanup failed: {type(exc).__name__}",
                file=sys.stderr,
            )
            rc = 1
        else:
            if down.returncode != 0:
                print(
                    f"[safe-runner] !! cleanup failed rc={down.returncode}",
                    file=sys.stderr,
                )
                rc = 1
            else:
                print(f"[safe-runner] exact cleanup complete project={project}")
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
    return rc


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
