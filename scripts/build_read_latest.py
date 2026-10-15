#!/usr/bin/env python3
"""女频阅读榜趋势构建 — 兼容脚本，直接调用统一构建。"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_latest

if __name__ == "__main__":
    # 解析原有参数，透传 --force / --date
    extra = [a for a in sys.argv[1:] if a in ("--force",)]
    date_arg = []
    for i, a in enumerate(sys.argv[1:]):
        if a == "--date" and i + 1 < len(sys.argv[1:]):
            date_arg = ["--date", sys.argv[i + 2]]
    # 设置 args 为 --gender female --type read + 额外参数
    sys.argv = [sys.argv[0], "--gender", "female", "--type", "read"] + extra + date_arg
    build_latest.main()
