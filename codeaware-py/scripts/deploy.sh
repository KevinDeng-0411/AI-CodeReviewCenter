#!/usr/bin/env bash
# =============================================================
# CodeAware 部署脚本
# 在服务器上 /opt/codeaware 目录下执行。
# 用法：
#   bash codeaware-py/scripts/deploy.sh bootstrap  ← 首次部署
#   bash codeaware-py/scripts/deploy.sh update     ← 日常更新
#   bash codeaware-py/scripts/deploy.sh restart    ← 仅重启
#   bash codeaware-py/scripts/deploy.sh status     ← 查看状态
#   bash codeaware-py/scripts/deploy.sh backup     ← 备份数据库
# =============================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/codeaware-py"
FRONTEND_DIR="$BACKEND_DIR/frontend"
APP_USER="codeaware"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

say()  { echo -e "${GREEN}[deploy]${NC} $1"; }
warn() { echo -e "${YELLOW}[deploy]${NC} $1"; }
err()  { echo -e "${RED}[deploy]${NC} $1"; }

# ---- 1. 启动基础服务（PG + Redis + Ollama）----
start_services() {
    say "启动基础服务（PG + Redis + Ollama）..."
    cd "$REPO_ROOT"
    docker compose up -d

    # 等待健康检查通过
    say "等待服务就绪..."
    for _ in $(seq 1 30); do
        if docker compose ps | grep -q "healthy"; then
            HEALTHY=$(docker compose ps | grep -c "healthy" || true)
            if [ "$HEALTHY" -ge 3 ]; then
                say "全部基础服务 healthy"
                break
            fi
        fi
        sleep 2
    done

    # 确保 bge-m3 已拉取
    if ! docker exec ai-center-ollama ollama list 2>/dev/null | grep -q "bge-m3"; then
        say "首次拉取 bge-m3 嵌入模型（约 2GB，仅一次）..."
        docker exec ai-center-ollama ollama pull bge-m3
    fi
}

# ---- 2. 同步 Python 依赖 ----
sync_deps() {
    say "同步 Python 依赖..."
    cd "$BACKEND_DIR"
    uv sync --frozen
}

# ---- 3. 构建前端 ----
build_frontend() {
    say "构建前端..."
    cd "$FRONTEND_DIR"
    npm ci --silent
    npm run build
    say "前端构建完成 → $FRONTEND_DIR/dist/"
}

# ---- 4. 运行数据库迁移 ----
run_migrations() {
    say "运行数据库迁移..."
    cd "$BACKEND_DIR"
    if ! uv run alembic upgrade head; then
        err "迁移失败"
        exit 1
    fi
}

# ---- 5. 安装/重启 systemd 服务 ----
setup_systemd() {
    say "配置 systemd 服务..."

    sudo tee /etc/systemd/system/codeaware.service << EOF
[Unit]
Description=CodeAware Backend
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${BACKEND_DIR}
Environment="PATH=${BACKEND_DIR}/.venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=${BACKEND_DIR}/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    sudo chown -R "$APP_USER:$APP_USER" "$REPO_ROOT"
    sudo systemctl daemon-reload
    sudo systemctl enable codeaware
    sudo systemctl restart codeaware

    sleep 2
    if sudo systemctl is-active --quiet codeaware; then
        say "systemd 服务已启动"
    else
        err "systemd 启动失败"
        sudo journalctl -u codeaware --no-pager -n 20
        exit 1
    fi
}

# ---- 健康检查 ----
health_check() {
    say "健康检查..."
    sleep 1
    if curl -sf http://127.0.0.1:8000/api/ai/health > /dev/null; then
        say "后端健康检查通过 ✓"
        echo ""
        curl -s http://127.0.0.1:8000/api/ai/health | python3 -m json.tool 2>/dev/null || true
    else
        err "健康检查失败"
        exit 1
    fi
}

# ---- 备份数据库 ----
do_backup() {
    BACKUP_FILE="$REPO_ROOT/backups/backup_$(date +%Y%m%d_%H%M%S).sql"
    mkdir -p "$REPO_ROOT/backups"
    say "备份数据库到 $BACKUP_FILE..."
    docker exec ai-center-postgres pg_dump -U aicenter ai_center_py > "$BACKUP_FILE"
    say "备份完成 ($(du -h "$BACKUP_FILE" | cut -f1))"
}

# ---- status ----
do_status() {
    echo "=== systemd ==="
    sudo systemctl status codeaware --no-pager -l 2>/dev/null || echo "codeaware 服务未安装"
    echo ""
    echo "=== docker ==="
    cd "$REPO_ROOT"
    docker compose ps 2>/dev/null || echo "docker compose 未运行"
    echo ""
    echo "=== health ==="
    curl -s http://127.0.0.1:8000/api/ai/health 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "后端未响应"
}

# ---- 主入口 ----
case "${1:-}" in
    bootstrap)
        say "============================================"
        say "  CodeAware 首次部署"
        say "============================================"
        start_services
        sync_deps
        build_frontend
        run_migrations
        setup_systemd
        health_check
        say ""
        say "============================================"
        say "  部署完成！"
        say ""
        say "  后端:  http://127.0.0.1:8000/api/ai/health"
        say "  前端:  http://<你的域名或IP>/"
        say ""
        say "  接下来配置 Caddy："
        say "    sudo cp $REPO_ROOT/Caddyfile /etc/caddy/Caddyfile"
        say "    sudo vim /etc/caddy/Caddyfile  # 改域名"
        say "    sudo systemctl restart caddy"
        say "============================================"
        ;;
    update)
        say "更新部署..."
        sync_deps
        build_frontend
        run_migrations
        sudo systemctl restart codeaware
        health_check
        say "更新完成"
        ;;
    restart)
        sudo systemctl restart codeaware
        health_check
        say "重启完成"
        ;;
    backup)
        do_backup
        ;;
    status)
        do_status
        ;;
    *)
        echo "用法: bash codeaware-py/scripts/deploy.sh {bootstrap|update|restart|backup|status}"
        exit 1
        ;;
esac
