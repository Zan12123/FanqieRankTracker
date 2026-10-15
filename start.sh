#!/bin/bash
# 番茄扫榜快速启动（最简版）
# 双击运行或在终端执行

cd "$(dirname "$0")"

echo "🍅 番茄扫榜启动中..."
echo ""

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "🔧 首次运行，正在配置环境..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    playwright install chromium
    echo "✅ 环境配置完成"
fi

# 执行自动化脚本
venv/bin/python auto_run.py

echo ""
echo "🚀 数据更新完成！正在启动看板..."
echo ""

# 启动服务器并打开浏览器
PORT=8080
if ! lsof -i :$PORT -sTCP:LISTEN >/dev/null 2>&1; then
    python3 -m http.server $PORT &
    sleep 1
fi

open "http://localhost:$PORT/index.html"

echo "✅ 看板已打开: http://localhost:$PORT/index.html"
echo "   按 Ctrl+C 停止服务器"
echo ""

# 保持运行，等待用户按 Ctrl+C
wait
