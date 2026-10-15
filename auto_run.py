#!/usr/bin/env python3
"""
番茄扫榜本地自动化执行脚本（无 GitHub 依赖）
每天开机后自动执行，数据存储在本地 iCloud 目录
"""

import os
import shlex
import sys
import subprocess
import time
from datetime import datetime

# 项目根目录（iCloud 中的位置）
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(PROJECT_DIR, "venv", "bin", "python")

# 日志文件
LOG_FILE = os.path.join(PROJECT_DIR, "auto_run.log")


def load_env():
    """从 .env 文件加载环境变量"""
    env_path = os.path.join(PROJECT_DIR, ".env")
    if not os.path.exists(env_path):
        return
    
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key and value:
                    os.environ[key] = value
                    print(f"✅ 已加载环境变量: {key}")


def log(message: str):
    """写入日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_command(cmd_parts: list, description: str) -> bool:
    """执行命令并记录日志"""
    # 构建 shell 安全的命令字符串，处理路径中的空格
    cmd_str = " ".join(shlex.quote(p) for p in cmd_parts)
    log(f"▶ 开始: {description}")
    log(f"  命令: {cmd_str}")
    
    try:
        result = subprocess.run(
            cmd_str,
            shell=True,
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=3600  # 1小时超时
        )
        
        if result.stdout:
            log(f"  输出:\n{result.stdout}")
        if result.stderr:
            log(f"  错误:\n{result.stderr}")
        
        if result.returncode == 0:
            log(f"✅ 完成: {description}")
            return True
        else:
            log(f"❌ 失败: {description} (返回码: {result.returncode})")
            return False
            
    except subprocess.TimeoutExpired:
        log(f"⏰ 超时: {description}")
        return False
    except Exception as e:
        log(f"❌ 异常: {description} - {str(e)}")
        return False


def check_today_data_exists() -> bool:
    """检查今天的数据是否已经抓取过"""
    today = datetime.now().strftime("%Y%m%d")
    data_files = [
        f"data/fanqie_female_new_ranks_{today}.json",
        f"data/fanqie_male_new_ranks_{today}.json",
    ]
    exists = all(os.path.exists(os.path.join(PROJECT_DIR, f)) for f in data_files)
    if exists:
        log(f"📦 今日({today})数据已存在，跳过抓取")
    return exists


def main():
    # 加载环境变量
    load_env()
    
    log("=" * 60)
    log("🚀 番茄扫榜自动化任务启动")
    
    # 检查 AI 配置
    if os.environ.get("API_BASE_URL") and os.environ.get("API_KEY"):
        log(f"🤖 AI 分析已启用: {os.environ.get('API_MODEL', 'default')}")
    else:
        log("ℹ️  AI 分析未配置，将使用规则摘要")
    
    # 检查虚拟环境
    if not os.path.exists(VENV_PYTHON):
        log(f"❌ 虚拟环境不存在: {VENV_PYTHON}")
        log("   请先执行: python -m venv venv && source venv/bin/activate && pip install -r requirements.txt")
        return 1
    
    # 检查今日数据
    if check_today_data_exists():
        log("📊 今日数据已存在，只执行构建和更新")
        # 只执行构建
        tasks = [
            ("女频新书榜数据构建", [VENV_PYTHON, "scripts/build_latest.py", "--gender", "female", "--type", "new"]),
            ("女频阅读榜数据构建", [VENV_PYTHON, "scripts/build_latest.py", "--gender", "female", "--type", "read"]),
            ("男频新书榜数据构建", [VENV_PYTHON, "scripts/build_latest.py", "--gender", "male", "--type", "new"]),
            ("男频阅读榜数据构建", [VENV_PYTHON, "scripts/build_latest.py", "--gender", "male", "--type", "read"]),
        ]
    else:
        # 完整执行：抓取 + 构建
        tasks = [
            ("女频新书榜抓取", [VENV_PYTHON, "scrape_ranks.py", "--gender", "female", "--type", "new"]),
            ("女频阅读榜抓取", [VENV_PYTHON, "scrape_ranks.py", "--gender", "female", "--type", "read"]),
            ("男频新书榜抓取", [VENV_PYTHON, "scrape_ranks.py", "--gender", "male", "--type", "new"]),
            ("男频阅读榜抓取", [VENV_PYTHON, "scrape_ranks.py", "--gender", "male", "--type", "read"]),
            ("女频新书榜数据构建", [VENV_PYTHON, "scripts/build_latest.py", "--gender", "female", "--type", "new"]),
            ("女频阅读榜数据构建", [VENV_PYTHON, "scripts/build_latest.py", "--gender", "female", "--type", "read"]),
            ("男频新书榜数据构建", [VENV_PYTHON, "scripts/build_latest.py", "--gender", "male", "--type", "new"]),
            ("男频阅读榜数据构建", [VENV_PYTHON, "scripts/build_latest.py", "--gender", "male", "--type", "read"]),
        ]
    
    # 执行所有任务
    success_count = 0
    for desc, cmd in tasks:
        if run_command(cmd, desc):
            success_count += 1
        time.sleep(2)  # 任务间间隔
    
    log("-" * 60)
    log(f"📊 任务完成: {success_count}/{len(tasks)} 成功")
    
    if success_count == len(tasks):
        log("🎉 所有任务执行成功！")
        log(f"   看板地址: file://{PROJECT_DIR}/index.html")
    else:
        log(f"⚠️  有 {len(tasks) - success_count} 个任务失败，请检查日志")
    
    log("=" * 60)
    return 0 if success_count == len(tasks) else 1


if __name__ == "__main__":
    sys.exit(main())
