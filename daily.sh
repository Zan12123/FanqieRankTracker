#!/bin/bash
# 番茄扫榜一键启动（本地版，无 GitHub 依赖）
# 数据自动存储在 iCloud 同步的项目目录中

set -e

cd "$(dirname "$0")"
PORT=8080
TODAY=$(date +%Y%m%d)

echo "=== 番茄扫榜（女频+男频）本地版 ==="
echo ""

# 1. 检查虚拟环境
if [ ! -f "venv/bin/python" ]; then
    echo "⚠️  虚拟环境不存在，正在创建..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    echo "✅ 虚拟环境创建完成"
fi

# 2. 检查今日采集数据，缺失则运行采集
FEMALE_NEW="data/fanqie_female_new_ranks_${TODAY}.json"
FEMALE_READ="data/fanqie_female_read_ranks_${TODAY}.json"
MALE_NEW="data/fanqie_male_new_ranks_${TODAY}.json"
MALE_READ="data/fanqie_male_read_ranks_${TODAY}.json"

# 女频新书榜
if [ -f "$FEMALE_NEW" ]; then
    echo "✅ 女频新书榜今日数据已存在"
else
    echo "🕷️  女频新书榜数据缺失，开始采集..."
    venv/bin/python scrape_ranks.py --gender female --type new
fi

# 女频阅读榜
if [ -f "$FEMALE_READ" ]; then
    echo "✅ 女频阅读榜今日数据已存在"
else
    echo "🕷️  女频阅读榜数据缺失，开始采集..."
    venv/bin/python scrape_ranks.py --gender female --type read
fi

# 男频新书榜
if [ -f "$MALE_NEW" ]; then
    echo "✅ 男频新书榜今日数据已存在"
else
    echo "🕷️  男频新书榜数据缺失，开始采集..."
    venv/bin/python scrape_ranks.py --gender male --type new
fi

# 男频阅读榜
if [ -f "$MALE_READ" ]; then
    echo "✅ 男频阅读榜今日数据已存在"
else
    echo "🕷️  男频阅读榜数据缺失，开始采集..."
    venv/bin/python scrape_ranks.py --gender male --type read
fi

# 3. 检查 API 文件是否比数据文件旧，如果是则重新构建
NEED_BUILD=false

check_and_build() {
    local data_file=$1
    local build_cmd=$2
    local api_file=$3

    if [ ! -f "$data_file" ]; then
        return
    fi

    local data_mtime=$(stat -f %m "$data_file" 2>/dev/null || echo 0)
    local api_mtime=0
    if [ -f "$api_file" ]; then
        api_mtime=$(stat -f %m "$api_file" 2>/dev/null || echo 0)
    fi

    if [ "$api_mtime" -lt "$data_mtime" ]; then
        echo "🔧 $api_file 过期，重新构建..."
        eval "$build_cmd"
        NEED_BUILD=true
    else
        echo "✅ $api_file 已是最新"
    fi
}

check_and_build "$FEMALE_NEW" \
    "venv/bin/python scripts/build_latest.py --gender female --type new" \
    "api/lastest/index.json"

check_and_build "$FEMALE_READ" \
    "venv/bin/python scripts/build_latest.py --gender female --type read" \
    "api/read-lastest/index.json"

check_and_build "$MALE_NEW" \
    "venv/bin/python scripts/build_latest.py --gender male --type new" \
    "api/male-lastest/index.json"

check_and_build "$MALE_READ" \
    "venv/bin/python scripts/build_latest.py --gender male --type read" \
    "api/male-read-lastest/index.json"

# 4. 生成扫榜日报（写入 Obsidian 库：03-选题与市场/扫榜与趋势/日报/）
echo ""
echo "📝 生成当日扫榜日报..."
if venv/bin/python scripts/build_report.py --mode daily; then
    echo "✅ 日报已写入 Obsidian 库"
else
    echo "⚠️  日报生成失败（不影响看板）"
fi

# 4.5 生成题材榜单（女频·年代：阅读榜+新书榜 逐本落盘）
echo ""
echo "📖 生成年代题材榜单..."
if venv/bin/python scripts/build_genre_report.py; then
    echo "✅ 年代题材榜单已写入 Obsidian 库"
else
    echo "⚠️  年代题材榜单生成失败（不影响看板）"
fi

# 5. 启动本地服务器（如果端口未被占用）
if lsof -i :$PORT -sTCP:LISTEN >/dev/null 2>&1; then
    echo "✅ 服务器已在运行: http://localhost:$PORT"
else
    python3 -m http.server $PORT &
    sleep 1
    echo "✅ 服务器已启动: http://localhost:$PORT"
fi

echo ""
echo "📊 女频新书榜:   http://localhost:$PORT/index.html"
echo "📊 女频阅读榜:   http://localhost:$PORT/read.html"
echo "📊 男频新书榜:   http://localhost:$PORT/male.html"
echo "📊 男频阅读榜:   http://localhost:$PORT/male_read.html"
echo "📊 趋势分析(女): http://localhost:$PORT/trend.html"
echo "📊 趋势分析(男): http://localhost:$PORT/male_trend.html"

# 6. 自动打开浏览器（默认打开女频新书榜）
open "http://localhost:$PORT/index.html"
