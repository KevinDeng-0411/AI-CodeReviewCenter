#!/usr/bin/env bash
# =============================================================
# CodeAware 快速停止脚本
# 从仓库根目录执行：bash codeaware-py/scripts/stop.sh
# 停止后端 + 前端；docker 服务不关（数据保留）。
# =============================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
say() { echo -e "${GREEN}[stop]${NC} $1"; }
warn() { echo -e "${YELLOW}[stop]${NC} $1"; }

# 停止后端
if [ -f /tmp/codeaware-backend.pid ]; then
    pid=$(cat /tmp/codeaware-backend.pid)
    if kill "$pid" 2>/dev/null; then
        say "后端已停止 (pid=$pid)"
    else
        warn "后端进程不存在"
    fi
    rm -f /tmp/codeaware-backend.pid
else
    # fallback: 按进程名杀
    pkill -f "uvicorn app.main:app" 2>/dev/null && say "后端已停止" || warn "后端未运行"
fi

# 停止前端
if [ -f /tmp/codeaware-frontend.pid ]; then
    pid=$(cat /tmp/codeaware-frontend.pid)
    if kill "$pid" 2>/dev/null; then
        say "前端已停止 (pid=$pid)"
    else
        warn "前端进程不存在"
    fi
    rm -f /tmp/codeaware-frontend.pid
else
    pkill -f "vite.*5173" 2>/dev/null && say "前端已停止" || warn "前端未运行"
fi

say "完成。docker 服务（PG/Redis/Ollama）未关闭，下次启动更快。"
echo "  全停（含 docker）：cd $(dirname "$0")/.. && docker compose down"
