#!/usr/bin/env bash
# =============================================================
# CodeAware 快速启动脚本
# 从仓库根目录执行：bash codeaware-py/scripts/start.sh
# 首次运行会引导创建 admin 账号。
# =============================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/codeaware-py"
FRONTEND_DIR="$BACKEND_DIR/frontend"

GREEN='\033[0;32m'
NC='\033[0m'
say() { echo -e "${GREEN}[start]${NC} $1"; }

cd "$REPO_ROOT"

# 1. 启动 docker 基础服务
say "启动基础服务（PG + Redis + Ollama）..."
docker compose up -d
# 等待健康检查
for _ in $(seq 1 20); do
    ready=$(docker compose ps 2>/dev/null | grep -c "healthy" || true)
    if [ "$ready" -ge 3 ]; then
        break
    fi
    sleep 1
done
say "基础服务已就绪"

# 2. 运行数据库迁移
cd "$BACKEND_DIR"
say "运行数据库迁移..."
uv run alembic upgrade head

# 3. 首次引导：检查是否需要创建 admin
cd "$BACKEND_DIR"
if ! uv run python -c "
from app.db.session import AsyncSessionLocal
from sqlalchemy import select
from app.models import User
import asyncio
async def check():
    async with AsyncSessionLocal() as s:
        r = await s.scalar(select(User.id).limit(1))
        return r is not None
print('ok' if asyncio.run(check()) else 'no-admin')
" 2>/dev/null | grep -q "ok"; then
    echo ""
    echo -e "${GREEN}[start]${NC} 首次启动：创建管理员账号"
    uv run python -m scripts.create_admin
fi

# 4. 启动后端（后台运行，日志写入 /tmp）
say "启动后端 127.0.0.1:8000..."
pkill -f "uvicorn app.main:app" 2>/dev/null || true
nohup uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 > /tmp/codeaware-backend.log 2>&1 &
echo $! > /tmp/codeaware-backend.pid
sleep 2
if curl -sf http://127.0.0.1:8000/api/ai/health > /dev/null; then
    say "后端已启动"
else
    echo "后端启动失败，查看 /tmp/codeaware-backend.log"
    exit 1
fi

# 5. 启动前端（后台运行）
say "启动前端 127.0.0.1:5173..."
cd "$FRONTEND_DIR"
pkill -f "vite" 2>/dev/null || true
nohup npx vite --host 127.0.0.1 --port 5173 > /tmp/codeaware-frontend.log 2>&1 &
echo $! > /tmp/codeaware-frontend.pid
sleep 3
if curl -sf http://127.0.0.1:5173/ > /dev/null; then
    say "前端已启动"
else
    echo "前端启动失败，查看 /tmp/codeaware-frontend.log"
    exit 1
fi

echo ""
say "============================================"
say "  全部就绪！"
say "  前端: http://localhost:5173/"
say "  后端: http://localhost:8000/api/ai/health"
say ""
say "  停止: bash codeaware-py/scripts/stop.sh"
say "============================================"
