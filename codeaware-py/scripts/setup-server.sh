#!/usr/bin/env bash
# =============================================================
# CodeAware 云服务器初始化脚本
# 在云服务器上以 root 运行一次。
# 适用：Ubuntu 22.04/24.04（火山引擎/阿里云/腾讯云）
# =============================================================
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

say() { echo -e "${GREEN}[codeaware-setup]${NC} $1"; }
warn() { echo -e "${YELLOW}[codeaware-setup]${NC} $1"; }

# ---- 检查是否为 root ----
if [ "$(id -u)" -ne 0 ]; then
    echo "请用 root 运行: sudo bash setup-server.sh"
    exit 1
fi

# ---- 创建应用目录 ----
APP_DIR="/opt/codeaware"
APP_USER="codeaware"

say "1/7 安装基础依赖..."
apt update -qq
apt install -y git python3.12 python3.12-venv curl jq

say "2/7 安装 Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
else
    warn "Docker 已安装，跳过"
fi

say "3/7 安装 Docker Compose..."
if ! docker compose version &>/dev/null 2>&1; then
    apt install -y docker-compose-plugin
fi

say "4/7 安装 uv (Python 包管理)..."
if ! command -v uv &>/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # 确保 root 也能用
    export PATH="$HOME/.cargo/bin:$PATH"
    echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> /root/.bashrc
fi

say "5/7 安装 Node.js (前端构建)..."
if ! command -v node &>/dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt install -y nodejs
fi

say "6/7 安装 Caddy (HTTPS 反代)..."
if ! command -v caddy &>/dev/null; then
    apt install -y debian-keyring debian-archive-keyring apt-transport-https
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
    apt update -qq
    apt install -y caddy
fi

say "7/7 创建应用用户和目录..."
# 创建专用用户（无登录 shell）
id -u "$APP_USER" &>/dev/null || useradd -r -s /bin/false -d "$APP_DIR" "$APP_USER"
mkdir -p "$APP_DIR"

# ---- 输出后续步骤 ----
say ""
say "============================================"
say "  服务器初始化完成"
say "============================================"
say ""
say "后续步骤（手动执行）："
say ""
say "1. 拉取代码："
say "   cd /opt/codeaware"
say "   git clone <仓库地址> ."
say ""
say "2. 配置环境变量："
say "   cd /opt/codeaware/codeaware-py"
say "   cp .env.example .env"
say "   vim .env   # 填入 DeepSeek API key"
say ""
say "3. 构建前端 + 启动服务："
say "   cd /opt/codeaware"
say "   bash codeaware-py/scripts/deploy.sh bootstrap"
say ""
say "4. 配置 Caddy（HTTPS）："
say "   cp /opt/codeaware/Caddyfile /etc/caddy/Caddyfile"
say "   vim /etc/caddy/Caddyfile  # 改为你的域名"
say "   systemctl restart caddy"
say ""
