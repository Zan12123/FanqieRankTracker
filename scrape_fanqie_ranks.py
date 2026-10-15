#!/usr/bin/env python3
"""女频新书榜爬虫 — 薄包装，调用统一爬虫。"""

from scrape_ranks import run_scraper

if __name__ == "__main__":
    print("开始执行番茄女频新书榜抓取计划...")
    run_scraper(gender="female", rank_type="new", limit=30, sleep_sec=5)
