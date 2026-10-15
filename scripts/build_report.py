#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
番茄扫榜 · 报告生成器（日报 / 月报）

用法：
  venv/bin/python scripts/build_report.py --mode daily                      # 日报：最新一期
  venv/bin/python scripts/build_report.py --mode daily --date 20260922
  venv/bin/python scripts/build_report.py --mode monthly --period 2026-09 --list female-new
  venv/bin/python scripts/build_report.py --mode monthly --period 2026-09 --list all

输出（写入 Obsidian 库）：
  日报 -> 03-选题与市场/扫榜与趋势/日报/YYYY-MM-DD.md
  月报 -> 03-选题与市场/扫榜与趋势/月报/YYYY-MM-<榜单名>.md

设计原则：
  - 能算全算（品类热度、梗计数、爆发书、结构指标均为确定性计算）
  - 判断类给「规则初稿」（阈值规则），AI 配置后可升级精读版
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_PATH = os.path.join(BASE_DIR, "config", "report_keywords.json")
def _find_vault_root(start):
    """向上找含 .obsidian 的目录 = Obsidian 库根。
    从 start 的上级开始找，跳过项目自身可能自带的 .obsidian（否则会认成库根）。"""
    p = os.path.dirname(os.path.abspath(start))
    for _ in range(8):
        if os.path.isdir(os.path.join(p, ".obsidian")):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return None


_VAULT_ROOT = _find_vault_root(BASE_DIR) or os.path.abspath(os.path.join(BASE_DIR, "..", "..", ".."))
VAULT_DIR = os.path.join(_VAULT_ROOT, "03-选题与市场", "03.扫榜与趋势")

# 题材温度口径：新书榜 → 对应阅读榜（阅读榜换血率低，趋势更稳）
SIBLING = {"female-new": "female-read", "male-new": "male-read"}

# 日报按频道分册
CHANNELS = {"女频": ["female-new", "female-read"], "男频": ["male-new", "male-read"]}

LISTS = {
    "female-new":  {"label": "女频新书榜", "trends": "trends",           "market": "market_summary.json",
                    "prefix": "fanqie_female_new_ranks_",  "channel": "女频", "rank": "新书榜"},
    "female-read": {"label": "女频阅读榜", "trends": "trends-read",      "market": "market_read_summary.json",
                    "prefix": "fanqie_female_read_ranks_", "channel": "女频", "rank": "阅读榜"},
    "male-new":    {"label": "男频新书榜", "trends": "trends-male",      "market": "market_male_summary.json",
                    "prefix": "fanqie_male_new_ranks_",    "channel": "男频", "rank": "新书榜"},
    "male-read":   {"label": "男频阅读榜", "trends": "trends-male-read", "market": "market_male_read_summary.json",
                    "prefix": "fanqie_male_read_ranks_",   "channel": "男频", "rank": "阅读榜"},
}


# ---------------- 基础工具 ----------------

def parse_reads(s):
    """'6.2万' -> 62000, '1543' -> 1543, '1.2亿' -> 120000000"""
    if s is None:
        return 0
    s = str(s).strip()
    try:
        if "亿" in s:
            return int(float(re.sub(r"[^\d.]", "", s)) * 100000000)
        if "万" in s:
            return int(float(re.sub(r"[^\d.]", "", s)) * 10000)
        m = re.match(r"([\d.]+)", s)
        return int(float(m.group(1))) if m else 0
    except (ValueError, TypeError):
        return 0


def fmt_reads(n):
    """62000 -> '6.2万'"""
    if n >= 100000000:
        return f"{n / 100000000:.1f}亿"
    if n >= 10000:
        return f"{n / 10000:.1f}万"
    return f"{n}"


def load_json(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def snapshots_of(prefix):
    return sorted(
        f[len(prefix):-5] for f in os.listdir(DATA_DIR)
        if f.startswith(prefix) and f.endswith(".json")
    )


def load_snapshot(prefix, date):
    """快照 -> {品类: [书 dict]}"""
    d = load_json(os.path.join(DATA_DIR, f"{prefix}{date}.json"))
    if not d:
        return None
    return {c["name"]: c["books"] for c in d["categories"]}


def months_of(prefix):
    """可用月份列表（按已有快照）"""
    return sorted({d[:6] for d in snapshots_of(prefix)})


def month_snapshots(prefix, month):
    return [d for d in snapshots_of(prefix) if d.startswith(month)]


def trend_arrow(delta_pct, flat=10):
    if delta_pct > flat:
        return "↑"
    if delta_pct < -flat:
        return "↓"
    return "→"


def load_keywords():
    cfg = load_json(CONFIG_PATH) or {}
    return cfg.get("flat", [])


def count_keywords(intro_text, keywords):
    return {k: intro_text.count(k) for k in keywords}


# ---------------- 日报 ----------------

def build_daily(date=None, channel=None):
    """按频道生成日报：女频一份、男频一份（各自含本频道的新书榜 + 阅读榜）"""
    all_keys = [k for ks in CHANNELS.values() for k in ks]
    if not date:
        date = max(d for k in all_keys for d in snapshots_of(LISTS[k]["prefix"]))
    d_iso = f"{date[:4]}-{date[4:6]}-{date[6:]}"

    outs = []
    for ch, keys in CHANNELS.items():
        if channel and ch != channel:
            continue
        parts = [f"# {d_iso} {ch}日报", ""]
        prev_dates = {}

        for key in keys:
            m = LISTS[key]
            trends = load_json(os.path.join(DATA_DIR, m["trends"], f"{d_iso}.json"))
            if not trends:
                parts.append(f"## {m['label']}\n\n> 本期无数据（趋势文件缺失）\n")
                continue

            prev_date = trends.get("prev_date", "")
            prev_dates[key] = prev_date
            t = trends["trends"]
            total_new = sum(v["new_count"] for v in t.values())
            total_dropped = sum(v["dropped_count"] for v in t.values())

            # 品类异动排序
            cat_moves = sorted(t.items(), key=lambda kv: -kv[1]["new_count"])
            # 跨品类涨幅聚合
            growth = {}
            for cat, v in t.items():
                for g in v.get("reads_growth", []):
                    title = g.get("title", "")
                    val = parse_reads(str(g.get("growth", "")).lstrip("+"))
                    if title and val:
                        growth[title] = max(growth.get(title, 0), val)
            top_growth = sorted(growth.items(), key=lambda kv: -kv[1])[:5]
            # 新上榜头部（回查在读）
            snap = load_snapshot(m["prefix"], date) or {}
            reads_by_title = {b["title"]: parse_reads(b["reads"]) for books in snap.values() for b in books}
            new_titles = []
            for cat, v in t.items():
                for title in v.get("new_books", []):
                    if title not in new_titles:
                        new_titles.append(title)
            top_new = sorted(new_titles, key=lambda x: -reads_by_title.get(x, 0))[:5]

            # 进榜门槛（末位在读）+ 上期对比
            reads_all = [r for r in reads_by_title.values() if r]
            entry = min(reads_all) if reads_all else 0
            prev_snap = load_snapshot(m["prefix"], prev_date.replace("-", "")) if prev_date else None
            prev_entry = 0
            if prev_snap:
                pr = [parse_reads(b["reads"]) for books in prev_snap.values() for b in books]
                prev_entry = min([x for x in pr if x]) if pr else 0

            # 排名跌幅 & 掉榜
            fallers = []
            for cat, v in t.items():
                for f in v.get("top_fallers", []):
                    try:
                        fallers.append((f.get("title", ""), int(str(f.get("change", "0")).replace("+", ""))))
                    except ValueError:
                        pass
            fallers.sort(key=lambda x: x[1])
            drops = []
            for cat, v in t.items():
                for b in v.get("dropped_books", []):
                    title = b.get("title") if isinstance(b, dict) else b
                    if title and title not in drops:
                        drops.append(title)

            parts.append(f"## {m['label']}")
            parts.append("")
            parts.append(f"- **换血**：新进榜 {total_new} 本 / 掉出 {total_dropped} 本")
            moves = "、".join(f"{c} +{v['new_count']}/-{v['dropped_count']}" for c, v in cat_moves[:5])
            parts.append(f"- **品类异动**（新增/掉出）：{moves}")
            if top_growth:
                gtxt = "、".join(f"《{n}》{fmt_reads(v)}" for n, v in top_growth)
                parts.append(f"- **在读涨幅 Top5**：{gtxt}")
            if top_new:
                ntxt = "、".join(f"《{n}》{fmt_reads(reads_by_title.get(n, 0))}" for n in top_new)
                parts.append(f"- **新上榜头部**：{ntxt}")
            if entry:
                arrow = "↑" if entry > prev_entry else ("↓" if entry < prev_entry else "→")
                parts.append(f"- **进榜门槛**：末位 {fmt_reads(entry)}（上期 {fmt_reads(prev_entry)} {arrow}）")
            if fallers:
                ftxt = "、".join(f"《{n}》{c}位" for n, c in fallers[:5])
                parts.append(f"- **排名跌幅 Top5**：{ftxt}")
            if drops:
                parts.append(f"- **掉榜**：{'、'.join('《' + d + '》' for d in drops[:5])} 等 {total_dropped} 本")
            parts.append("")
            parts.append(f"> 对比基期：{prev_date}（上一个可用快照）")
            parts.append("")

        # 新书晋级（上期新书榜 ∩ 本期阅读榜）——同日交集结构上恒为 0，必须跨期比
        if len(keys) == 2:
            pd = prev_dates.get(keys[0], "").replace("-", "")
            s_prev_new = load_snapshot(LISTS[keys[0]]["prefix"], pd) if pd else None
            s_read = load_snapshot(LISTS[keys[1]]["prefix"], date) or {}
            if s_prev_new:
                pn = {b["title"]: parse_reads(b["reads"]) for books in s_prev_new.values() for b in books}
                cr = {b["title"]: parse_reads(b["reads"]) for books in s_read.values() for b in books}
                prom = sorted([(t_, pn[t_], cr[t_]) for t_ in pn if t_ in cr], key=lambda x: -x[2])
                if prom:
                    parts.append("## 新书晋级（上期新书榜 → 本期阅读榜）")
                    parts.append("")
                    parts.append(f"> 从新书榜升进阅读榜 = 真的爆了，不是榜单曝光（{pd[:4]}-{pd[4:6]}-{pd[6:]} → {d_iso}）")
                    parts.append("")
                    for t_, nv, rv in prom[:8]:
                        parts.append(f"- 《{t_}》：新书榜 {fmt_reads(nv)} → 阅读榜 {fmt_reads(rv)}")
                    parts.append("")

        # 市场热点（本频道近 7 日）
        market = load_json(os.path.join(DATA_DIR, LISTS[keys[0]]["market"]))
        if market and "periods" in market:
            p7 = market["periods"].get("7") or market["periods"].get(7)
            if p7 and p7.get("summary"):
                parts.append("## 市场热点（近 7 日）")
                parts.append("")
                parts.append(p7["summary"])
                parts.append("")

        out = os.path.join(VAULT_DIR, "日报", f"{d_iso}-{ch}.md")
        write_text(out, "\n".join(parts).rstrip() + "\n")
        outs.append(out)
    return outs


# ---------------- 月报 ----------------

def monthly_stats(prefix, date, keywords):
    """单快照统计：品类热度、份额、结构、梗计数"""
    snap = load_snapshot(prefix, date)
    if not snap:
        return None
    cat_stat = {}
    grand = 0
    for cat, books in snap.items():
        tot = sum(parse_reads(b["reads"]) for b in books)
        avg = tot / len(books) if books else 0
        cat_stat[cat] = {"total": tot, "avg": avg, "n": len(books)}
        grand += tot
    for cat in cat_stat:
        cat_stat[cat]["share"] = cat_stat[cat]["total"] / grand if grand else 0

    titles = {b["title"]: parse_reads(b["reads"]) for books in snap.values() for b in books}
    all_reads = sorted(titles.values(), reverse=True)
    top10 = sum(all_reads[:10]) / sum(all_reads) if all_reads else 0
    intro_text = " ".join(b["intro"] for books in snap.values() for b in books)

    return {
        "date": date, "snap": snap, "cat": cat_stat, "grand": grand,
        "titles": titles, "top10_share": top10,
        "keywords": count_keywords(intro_text, keywords),
        "over10w": sum(1 for r in all_reads if r >= 100000),
    }


def build_monthly(period, key):
    m = LISTS[key]
    period_ym = period.replace("-", "")
    months = months_of(m["prefix"])
    if period_ym not in months:
        avail = ", ".join(f"{x[:4]}-{x[4:]}" for x in months)
        raise SystemExit(f"❌ {m['label']} 没有 {period} 的快照，可用月份：{avail}")

    cur_dates = month_snapshots(m["prefix"], period_ym)
    cur_last = cur_dates[-1]
    cur_first = cur_dates[0]
    # 上月基期
    idx = months.index(period_ym)
    prev_month = months[idx - 1] if idx > 0 else None
    prev_last = month_snapshots(m["prefix"], prev_month)[-1] if prev_month else None

    keywords = load_keywords()
    cur = monthly_stats(m["prefix"], cur_last, keywords)
    prev = monthly_stats(m["prefix"], prev_last, keywords) if prev_last else None
    # 上上月末（判断"连续两月涨"用）
    prev2_last = None
    if prev_month:
        idx2 = months.index(prev_month)
        if idx2 > 0:
            prev2_last = month_snapshots(m["prefix"], months[idx2 - 1])[-1]
    prev2 = monthly_stats(m["prefix"], prev2_last, keywords) if prev2_last else None

    # ---- frontmatter ----
    heat = []
    for cat, s in sorted(cur["cat"].items(), key=lambda kv: -kv[1]["avg"]):
        d = 0
        if prev and cat in prev["cat"] and prev["cat"][cat]["avg"]:
            d = (s["avg"] - prev["cat"][cat]["avg"]) / prev["cat"][cat]["avg"] * 100
        dp = 0
        if prev and prev2 and cat in prev["cat"] and cat in prev2["cat"] and prev2["cat"][cat]["avg"]:
            dp = (prev["cat"][cat]["avg"] - prev2["cat"][cat]["avg"]) / prev2["cat"][cat]["avg"] * 100
        ds = 0
        if prev and cat in prev["cat"]:
            ds = (s["share"] - prev["cat"][cat]["share"]) * 100   # 份额变化（百分点）
        heat.append({"name": cat, "avg_reads": int(s["avg"]),
                     "trend": {"↑": "up", "↓": "down"}.get(trend_arrow(d), "flat"),
                     "share": round(s["share"], 3), "delta": round(d), "delta_prev": round(dp),
                     "d_share": round(ds, 2)})

    # 梗计数对比
    hot_tags, rising, falling = [], [], []
    if prev:
        diffs = []
        for k in keywords:
            c, p = cur["keywords"].get(k, 0), prev["keywords"].get(k, 0)
            if c >= 3 or p >= 3:
                diffs.append((k, c, p, (c / p if p else float("inf"))))
        rising = [(k, c, p) for k, c, p, r in diffs if (p and r >= 1.5 and c >= 5) or (p == 0 and c >= 4)]
        falling = [(k, c, p) for k, c, p, r in diffs if p >= 8 and c / p <= 0.6]
        hot_tags = [k for k, c, p, r in sorted(diffs, key=lambda x: -x[1])[:8]]
    else:
        hot_tags = [k for k, c in sorted(cur["keywords"].items(), key=lambda x: -x[1])[:8] if c >= 3]

    # 爆发书（相对上月末的新进榜）
    prev_titles = set(prev["titles"]) if prev else set()
    breakouts = sorted(
        ((t, r) for t, r in cur["titles"].items() if t not in prev_titles),
        key=lambda x: -x[1],
    )[:5]

    # 结构
    turnover = (len([t for t in cur["titles"] if t not in prev_titles]) / len(cur["titles"])) if prev else 0

    # A: 题材温度交叉参考——新书榜 → 对应阅读榜（阅读榜换血率低，趋势更稳）
    sib_block = None
    sib_key = SIBLING.get(key)
    if sib_key:
        sm = LISTS[sib_key]
        smonths = months_of(sm["prefix"])
        if period_ym in smonths:
            si = smonths.index(period_ym)
            s_cur = monthly_stats(sm["prefix"], month_snapshots(sm["prefix"], period_ym)[-1], keywords)
            s_prev = (monthly_stats(sm["prefix"], month_snapshots(sm["prefix"], smonths[si - 1])[-1], keywords)
                      if si > 0 else None)
            sib_block = []
            for cat, s in s_cur["cat"].items():
                sd = 0
                if s_prev and cat in s_prev["cat"] and s_prev["cat"][cat]["avg"]:
                    sd = (s["avg"] - s_prev["cat"][cat]["avg"]) / s_prev["cat"][cat]["avg"] * 100
                sdp = 0
                if s_prev and cat in s_prev["cat"]:
                    sdp = (s["share"] - s_prev["cat"][cat]["share"]) * 100
                sib_block.append({"name": cat, "avg_reads": int(s["avg"]), "share": round(s["share"], 3),
                                  "delta": round(sd), "d_share": round(sdp, 2)})
            sib_block.sort(key=lambda r: -r["d_share"])   # 按份额变化排序（相对强弱）

    fm = [
        "---",
        f'period: "{period}"',
        f"channel: {m['channel']}",
        f"rank: {m['rank']}",
        f'latest_snapshot: "{cur_last[:4]}-{cur_last[4:6]}-{cur_last[6:]}"',
    ]
    if prev_last:
        fm.append(f'base_snapshot: "{prev_last[:4]}-{prev_last[4:6]}-{prev_last[6:]}"')
    fm.append(f"turnover_rate: {round(turnover, 2)}")
    fm.append(f"top10_share: {round(cur['top10_share'], 2)}")
    fm.append("category_heat:")
    for h in heat:
        fm.append(f"  - {{name: {h['name']}, avg_reads: {h['avg_reads']}, trend: {h['trend']}, share: {h['share']}}}")
    fm.append(f"hot_tags: [{', '.join(hot_tags)}]")
    fm.append("---")

    # ---- 正文 ----
    L = []
    L.append("")
    L.append(f"# {period} {m['label']}结论")
    L.append("")
    if prev:
        biggest = max(heat, key=lambda h: h["delta"])
        worst = min(heat, key=lambda h: h["delta"])
        L.append(f"> **一句话判断**（规则初稿）：{biggest['name']}（{biggest['delta']:+d}%）领涨、{worst['name']}（{worst['delta']:+d}%）领跌；本期样本 {len(cur['titles'])} 本，换血率 {round(turnover * 100)}%。")
    else:
        L.append("> **一句话判断**：首期报告，暂无环比基期。")
    L.append("")
    L.append("## 0. 数据口径")
    L.append("")
    L.append(f"- 本期：{cur_last[:4]}-{cur_last[4:6]}-{cur_last[6:]} 快照（本月 {len(cur_dates)} 个采集日，{len(cur['titles'])} 本去重书）")
    if prev_last:
        L.append(f"- 基期：{prev_last[:4]}-{prev_last[4:6]}-{prev_last[6:]} 快照（上月末）")
    L.append("- 指标：在读（番茄页面显示值，\"万\"级精度）")
    L.append("- 生成方式：规则版（脚本自动计算）")
    L.append("")

    # 1 品类热度
    L.append("## 1. 品类热度环比")
    L.append("")
    L.append("| 分类 | 平均在读 | 环比 | 趋势 | 份额 |")
    L.append("|---|---|---|---|---|")
    for h in heat:
        d = f"{h['delta']:+d}%" if prev_last else "—"
        L.append(f"| {h['name']} | {h['avg_reads']:,} | {d} | {trend_arrow(h['delta'])} | {h['share'] * 100:.1f}% |")
    L.append("")
    ups = [h["name"] for h in heat if h["delta"] > 10]
    downs = [h["name"] for h in heat if h["delta"] < -10]
    L.append(f"- **在涨**：{'、'.join(ups) if ups else '无'}")
    L.append(f"- **在跌**：{'、'.join(downs) if downs else '无'}")
    L.append("")
    if key.endswith("-read"):
        L.append(f"- 📌 阅读榜换血率低（本期 {round(turnover * 100)}%），是**题材温度**的权威口径；新书榜只负责「新书爆发」。")
        L.append("")
    if sib_block:
        L.append(f"> ⚠️ 本期新书榜换血率 {round(turnover * 100)}%——每月大半本书被替换，上表很大程度上反映的是「当月恰好在榜的是哪几本书」，噪声大。**题材趋势以下方阅读榜口径为准。**")
        L.append("")
        L.append("### 题材温度（阅读榜口径，按份额变化排序）")
        L.append("")
        L.append("> **份额变化**是相对强弱口径：份额涨＝抢到了地盘，不受大盘整体涨跌干扰（均读环比会被大盘带偏）。")
        L.append("")
        n_sib = len(sib_block)
        show = sib_block[:6] + sib_block[-6:] if n_sib > 12 else sib_block
        L.append("| 分类 | 阅读榜平均在读 | 均读环比 | 份额 | 份额变化 |")
        L.append("|---|---|---|---|---|")
        for r in show:
            L.append(f"| {r['name']} | {r['avg_reads']:,} | {r['delta']:+d}% | {r['share'] * 100:.1f}% | {r['d_share']:+.2f}pp |")
        L.append("")

    # 2 梗风向
    L.append("## 2. 梗与标签风向")
    L.append("")
    L.append(f"> 口径：简介全文关键词计数（{len(cur['titles'])} 本 vs 基期），词表见 config/report_keywords.json")
    L.append("")
    if rising:
        L.append("| 新升 | 本期 | 基期 |")
        L.append("|---|---|---|")
        for k, c, p in rising[:8]:
            L.append(f"| {k} | {c} | {p} |")
        L.append("")
    if falling:
        L.append("| 退潮 | 本期 | 基期 |")
        L.append("|---|---|---|")
        for k, c, p in falling[:8]:
            L.append(f"| {k} | {c} | {p} |")
        L.append("")
    if not rising and not falling:
        L.append("（本期无显著异动）\n")
    # 新书梗风向：只统计本月新进榜的书（供给端信号）
    if prev_titles:
        intro_of = {b["title"]: b["intro"] for books in cur["snap"].values() for b in books}
        new_all = [t for t in cur["titles"] if t not in prev_titles]
        nk = count_keywords(" ".join(intro_of.get(t, "") for t in new_all), keywords)
        top_nk = sorted([(k, c) for k, c in nk.items() if c >= 2], key=lambda x: -x[1])[:8]
        if top_nk:
            L.append(f"**新进榜书的梗分布**（{len(new_all)} 本样本）——供给端在往哪挤：")
            L.append("")
            L.append("　" + "、".join(f"{k} ×{c}" for k, c in top_nk))
            L.append("")

    # 3 爆发书
    L.append("## 3. 爆发书 Top5")
    L.append("")
    L.append("> 判定：本期快照中相对基期新进榜、按在读排序")
    L.append("")
    L.append("| # | 书名 | 分类 | 在读 |")
    L.append("|---|---|---|---|")
    cat_of = {b["title"]: cat for cat, books in cur["snap"].items() for b in books}
    for i, (t, r) in enumerate(breakouts, 1):
        L.append(f"| {i} | {t} | {cat_of.get(t, '')} | {fmt_reads(r)} |")
    L.append("")
    L.append("> 拆解位（核心梗 / 可抄作业）留给 AI 精读或人工补写。")
    L.append("")

    # 4 结构信号
    L.append("## 4. 榜单结构信号")
    L.append("")
    if prev_last:
        L.append(f"- **换血率**：{round(turnover * 100)}%（{len(cur['titles'])} 本中 {len([t for t in cur['titles'] if t not in prev_titles])} 本为新进）")
    if prev and prev["grand"]:
        lvl = (cur["grand"] - prev["grand"]) / prev["grand"] * 100
        L.append(f"- **大盘水位**：总在读 {cur['grand'] / 100000000:.2f}亿（环比 {lvl:+.0f}%）")
    L.append(f"- **头部集中度**：Top10 在读占比 {cur['top10_share'] * 100:.0f}%")
    L.append(f"- **10 万+ 在读**：{cur['over10w']} 本（占 {cur['over10w'] / len(cur['titles']) * 100:.0f}%）")
    L.append("")

    # 5 异动观察（只陈列，不冒充结论）
    L.append("## 5. 异动观察")
    L.append("")
    L.append("> 回测显示**单月涨幅不预测下月走势**（样本内命中率极低），本节只做异动陈列；是否为真机会，需结合供给、季节与自身写作方向判断。")
    L.append("")
    has_prev2 = prev2 is not None
    up_moves = [h for h in heat if h["delta"] > 15 and h["share"] >= 0.03]
    down_moves = [h for h in heat if h["delta"] < -25 and h["share"] >= 0.03]
    L.append("**涨幅异动**（环比 > +15% 且 份额 ≥ 3%）：")
    L.append("")
    if up_moves:
        for h in sorted(up_moves, key=lambda x: -x["delta"]):
            cont = f"　↗ 连续两月涨（上月 {h['delta_prev']:+d}%）" if (has_prev2 and h["delta_prev"] > 0) else ""
            L.append(f"- {h['name']}：{h['delta']:+d}%，份额 {h['share'] * 100:.1f}%（{h['d_share']:+.2f}pp），均读 {fmt_reads(h['avg_reads'])}{cont}")
    else:
        L.append("- 无")
    L.append("")
    L.append("**跌幅异动**（环比 < −25% 且 份额 ≥ 3%，已排除小盘噪音）：")
    L.append("")
    if down_moves:
        for h in down_moves:
            L.append(f"- {h['name']}：{h['delta']:+d}%，份额 {h['share'] * 100:.1f}%（{h['d_share']:+.2f}pp）")
    else:
        L.append("- 无")
    L.append("")
    # 份额异动：相对强弱口径（优先用阅读榜）
    src = sib_block if sib_block else heat
    src_name = "阅读榜口径" if sib_block else "本榜口径"
    gain = sorted([r for r in src if r.get("d_share", 0) >= 1.0], key=lambda x: -x["d_share"])
    lose = sorted([r for r in src if r.get("d_share", 0) <= -1.0], key=lambda x: x["d_share"])
    L.append(f"**份额异动**（{src_name}，|份额变化| ≥ 1.0pp）——相对强弱，不受大盘涨跌干扰：")
    L.append("")
    if gain or lose:
        for r in gain:
            L.append(f"- ↗ {r['name']}：份额 {r['share'] * 100:.1f}%（{r['d_share']:+.2f}pp）")
        for r in lose:
            L.append(f"- ↘ {r['name']}：份额 {r['share'] * 100:.1f}%（{r['d_share']:+.2f}pp）")
    else:
        L.append("- 无")
    if falling:
        L.append(f"- 过气梗：{'、'.join(k for k, _, _ in falling[:5])}")
    L.append("")

    # 6 watchlist
    L.append("## 6. 下期 Watchlist")
    L.append("")
    L.append("| 书名 | 盯什么 |")
    L.append("|---|---|")
    for t, r in breakouts[:3]:
        L.append(f"| {t} | 在读能否站稳 {fmt_reads(int(r * 1.2))} |")
    if rising:
        L.append(f"| —（梗） | {'、'.join(k for k, _, _ in rising[:3])} 是否出现头部书（梗热→爆款验证） |")
    L.append("")

    out = os.path.join(VAULT_DIR, "月报", f"{period}-{m['label']}.md")
    write_text(out, "\n".join(fm + L).rstrip() + "\n")
    return out


# ---------------- CLI ----------------

def main():
    ap = argparse.ArgumentParser(description="番茄扫榜报告生成器")
    ap.add_argument("--mode", choices=["daily", "monthly"], required=True)
    ap.add_argument("--date", help="日报日期 YYYYMMDD（默认最新）")
    ap.add_argument("--channel", choices=["女频", "男频"], help="只出该频道的日报（默认两个都出）")
    ap.add_argument("--period", help="月报周期 YYYY-MM")
    ap.add_argument("--list", dest="list_key", default="female-new",
                    help="榜单：female-new / female-read / male-new / male-read / all（月报生效）")
    args = ap.parse_args()

    if args.mode == "daily":
        for p in build_daily(args.date, args.channel):
            print(f"✅ 日报已生成: {p}")
    else:
        if not args.period:
            raise SystemExit("❌ 月报需要 --period YYYY-MM")
        keys = list(LISTS.keys()) if args.list_key == "all" else [args.list_key]
        for k in keys:
            try:
                path = build_monthly(args.period, k)
                print(f"✅ 月报已生成: {path}")
            except SystemExit as e:
                print(f"⚠️  跳过 {k}: {e}")


if __name__ == "__main__":
    main()
