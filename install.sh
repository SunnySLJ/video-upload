#!/bin/bash
# OpenClaw 银龄工作流 - 一键安装与更新脚本
# 本仓库需直接克隆至 ~/.openclaw/workspace 目录下使用

set -e

echo "========================================="
echo "   OpenClaw 银龄工作流 - 自动部署程序"
echo "========================================="

OPENCLAW_ROOT="$HOME/.openclaw"
WORKSPACE_DIR="$OPENCLAW_ROOT/workspace"

# 1. 检查执行目录
if [ "$(pwd)" != "$WORKSPACE_DIR" ]; then
    echo "[警告] 当前脚本不在 $WORKSPACE_DIR 目录下执行！"
    echo "如果是首次安装，请先执行: git clone https://github.com/SunnySLJ/video-upload.git $WORKSPACE_DIR"
    read -p "是否强制继续？(y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 2. 生成配置和凭证目录
echo ">>> [1/3] 正在检查基础配置文件..."
mkdir -p "$OPENCLAW_ROOT/credentials"

if [ ! -f "$OPENCLAW_ROOT/openclaw.json" ]; then
    echo "    - 检测到缺失主配置，正在生成 openclaw.json 模板..."
    cp openclaw_config_template.json "$OPENCLAW_ROOT/openclaw.json"
fi

if [ ! -f "TOOLS.md" ]; then
    echo "    - 正在生成 TOOLS.md 模板..."
    cp TOOLS.example.md TOOLS.md
fi

# 3. 配置 Python 虚拟环境
echo ">>> [2/3] 正在配置底层 Python 运行环境..."
cd "$WORKSPACE_DIR/openclaw_upload"

# 检查 Python 3.11
if ! command -v python3.11 &> /dev/null; then
    echo "[错误] 未找到 python3.11。请先安装 Python 3.11。"
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "    - 创建全新的虚拟环境..."
    python3.11 -m venv .venv
fi

echo ">>> [3/3] 正在安装/更新底层库..."
source .venv/bin/activate
pip install -r requirements.txt --upgrade > /dev/null

echo "========================================="
echo "✅ 部署/更新成功！"
echo "👉 请参考《部署说明.md》补全缺失的 API Key 和微信配置。"
echo "========================================="
