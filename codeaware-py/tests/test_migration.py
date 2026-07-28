"""P1：Alembic 迁移 up/down 往返（在独立 ai_center_migtest 库上，子进程执行）。

子进程方式避免与异步测试事件循环的 asyncio.run 冲突。
"""

import os
import subprocess
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent


def _alembic(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PG_DB": "ai_center_migtest"}
    return subprocess.run(
        ["uv", "run", "alembic", *args],
        cwd=PROJ,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_migration_roundtrip():
    # 1) upgrade head（fresh migtest 建全部表 + 扩展 + seed）
    r1 = _alembic("upgrade", "head")
    assert r1.returncode == 0, r1.stderr
    assert "0001" in _alembic("current").stdout

    # 2) downgrade base（drop 全部表）
    r2 = _alembic("downgrade", "base")
    assert r2.returncode == 0, r2.stderr

    # 3) upgrade head 再次（验证可重复）
    r3 = _alembic("upgrade", "head")
    assert r3.returncode == 0, r3.stderr
    assert "0001" in _alembic("current").stdout
