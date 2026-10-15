#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
番茄扫榜 · 月度数据图谱生成器（题材变化图 + 梗趋势图）

每月两张图，文件名带月份，跨月不覆盖（同月重跑刷新当月）：
  图1 题材变化-<榜单>-YYYY-MM.canvas   7 大赛道分组，组内是各分类（本月 vs 上月）
  图2 梗趋势-<榜单>-YYYY-MM.canvas     梗节点带迷你走势线（截至当月）

用法：
  venv/bin/python scripts/build_canvas.py --list female-new --period 2026-09
  venv/bin/python scripts/build_canvas.py --list female-new          # 默认最新月

输出：<vault>/03-选题与市场/03.扫榜与趋势/图谱/
"""
import argparse
import json
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_report import (LISTS, VAULT_DIR, fmt_reads, load_keywords,
                          month_snapshots, months_of, monthly_stats)
from build_latest import FEMALE_GENRE_GROUPS, MALE_GENRE_GROUPS

# Obsidian canvas 预设色：1红 2橙 3黄 4绿 5青 6紫
COLOR_UP, COLOR_DOWN, COLOR_FLAT = "1", "4", "6"   # 红涨 绿跌 紫平
SPARK = "▁▂▃▄▅▆▇█"
GROUP_BY_CHANNEL = {"女频": FEMALE_GENRE_GROUPS, "男频": MALE_GENRE_GROUPS}


def color_of(delta):
    if delta is None:
        return COLOR_FLAT
    if delta > 10:
        return COLOR_UP
    if delta < -10:
        return COLOR_DOWN
    return COLOR_FLAT


def delta_pct(cur, prev, key="avg"):
    if not prev or not prev.get(key):
        return None
    return (cur[key] - prev[key]) / prev[key] * 100


def agg_genre(stats_obj, cats):
    """把一个赛道下的分类聚合成赛道级数据"""
    total = n = share = 0.0
    for c in cats:
        s = (stats_obj or {}).get("cat", {}).get(c)
        if s:
            total += s["total"]
            n += s["n"]
            share += s["share"]
    return {"total": total, "n": n, "share": share, "avg": (total / n if n else 0)}


def sparkline(values):
    if not values:
        return ""
    mx = max(values) or 1
    return "".join(SPARK[min(7, int(v / mx * 7.99))] for v in values)


# ---------------- 图1：题材变化 ----------------

def build_genre_canvas(m, stats, months, period_ym, out_dir):
    groups = GROUP_BY_CHANNEL.get(m["channel"], [])
    prev_ym = months[months.index(period_ym) - 1] if months.index(period_ym) > 0 else None
    cur, prev = stats[period_ym], (stats[prev_ym] if prev_ym else None)

    nodes = [{
        "id": "title", "type": "text", "x": 100, "y": 0, "width": 1100, "height": 130,
        "text": (f"# {m['label']} · 题材变化（{period_ym[:4]}-{period_ym[4:]}）\n"
                 f"对比基期：{prev_ym[:4]}-{prev_ym[4:]}（上月）\n"
                 f"**颜色：🔴涨 / 🟢跌 / 🟣平**　节点：均读 · 份额 · 环比　粗框=赛道汇总"),
    }]
    y0, pitch = 190, 175
    for i, g in enumerate(groups):
        cats = g["categories"]
        cur_agg = agg_genre(cur, cats)
        prev_agg = agg_genre(prev, cats) if prev else None
        d = delta_pct(cur_agg, prev_agg)
        dy = y0 + i * pitch
        gw = 380 + len(cats) * 300
        nodes.append({"id": f"g{i}", "type": "group", "x": 90, "y": dy,
                      "width": gw, "height": 145,
                      "label": f"{g['name']}" + (f"　{d:+.0f}%" if d is not None else "")})
        dtxt = f"环比 {d:+.0f}%" if d is not None else "环比 —"
        nodes.append({"id": f"gs{i}", "type": "text", "x": 115, "y": dy + 30,
                      "width": 320, "height": 95, "color": color_of(d),
                      "text": f"**{g['name']}**\n均读 {fmt_reads(int(cur_agg['avg']))} · 份额 {cur_agg['share'] * 100:.1f}%\n{dtxt}"})
        for j, cat in enumerate(cats):
            s = cur["cat"].get(cat)
            ps = (prev or {}).get("cat", {}).get(cat)
            cd = delta_pct(s, ps) if s else None
            if s:
                txt = f"**{cat}**\n均读 {fmt_reads(int(s['avg']))} · 份额 {s['share'] * 100:.1f}%\n" + \
                      (f"环比 {cd:+.0f}%" if cd is not None else "环比 —")
            else:
                txt = f"**{cat}**\n（本月未在榜）"
            nodes.append({"id": f"c{i}_{j}", "type": "text", "x": 455 + j * 300, "y": dy + 30,
                          "width": 280, "height": 95, "color": color_of(cd), "text": txt})

    out = os.path.join(out_dir, f"题材变化-{m['label']}-{period_ym[:4]}-{period_ym[4:]}.canvas")
    _write(out, nodes, [])
    return out


# ---------------- 图2：梗趋势 ----------------

def build_tag_canvas(m, stats, months, period_ym, keywords, out_dir, cap=30):
    upto = [mo for mo in months if mo <= period_ym]
    prev_ym = months[months.index(period_ym) - 1] if months.index(period_ym) > 0 else None

    rows = []
    for k in keywords:
        series = [stats[mo]["keywords"].get(k, 0) for mo in upto]
        cur_n = series[-1] if series else 0
        prev_n = stats[prev_ym]["keywords"].get(k, 0) if prev_ym else 0
        mx = max(series) if series else 0
        if cur_n < 3 and mx < 10:
            continue
        d = ((cur_n - prev_n) / prev_n * 100) if prev_n else (None if cur_n == 0 else 999)
        rows.append({"k": k, "series": series, "cur": cur_n, "prev": prev_n, "max": mx, "d": d})

    rows.sort(key=lambda r: -r["cur"])
    rows = rows[:cap]

    def bucket(r):
        if r["prev"] == 0:
            return "up" if r["cur"] >= 3 else "flat"
        if r["d"] is not None and r["d"] >= 25:
            return "up"
        if r["d"] is not None and r["d"] <= -20:
            return "down"
        return "flat"

    buckets = {"up": [], "flat": [], "down": []}
    for r in rows:
        buckets[bucket(r)].append(r)

    nodes = [{
        "id": "title", "type": "text", "x": 100, "y": 0, "width": 1160, "height": 150,
        "text": (f"# {m['label']} · 梗趋势（截至 {period_ym[:4]}-{period_ym[4:]}）\n"
                 f"迷你线 = {upto[0][:4]}-{upto[0][4:]} → {upto[-1][:4]}-{upto[-1][4:]} 的每月出现次数走势\n"
                 f"**颜色按近期涨跌：🔴升 / 🟢退 / 🟣平**　数字 = 本月出现次数（简介全文计数）"),
    }]

    titles = {"up": "🔼 新升 / 走强", "flat": "➡️ 平稳", "down": "🔽 退潮"}
    cols = [("up", 100), ("flat", 540), ("down", 980)]
    y0, pitch = 210, 105
    for key, x in cols:
        items = buckets[key]
        if not items:
            continue
        gh = len(items) * pitch + 60
        nodes.append({"id": f"g_{key}", "type": "group", "x": x - 15, "y": y0 - 15,
                      "width": 420, "height": gh, "label": titles[key]})
        for n, r in enumerate(items):
            if r["d"] is None:
                dtxt = "环比 —"
            elif r["d"] == 999:
                dtxt = "本月新出现"
            else:
                dtxt = f"环比 {r['d']:+.0f}%"
            nodes.append({
                "id": f"t_{key}_{n}", "type": "text", "x": x, "y": y0 + n * pitch,
                "width": 390, "height": 90, "color": color_of(r["d"] if r["d"] != 999 else 50),
                "text": f"**{r['k']}**　{sparkline(r['series'])}　**{r['cur']}**\n{dtxt}",
            })

    out = os.path.join(out_dir, f"梗趋势-{m['label']}-{period_ym[:4]}-{period_ym[4:]}.canvas")
    _write(out, nodes, [])
    return out


# ---------------- 柱状图版（横向柱：标签列 + 柱节点） ----------------

def center_pad(text, width_px, unit_px=7.2):
    """用不换行空格(NBSP)把文字在 width_px 宽的节点里近似居中（Canvas 无对齐字段）"""
    def units(s):
        return sum(2.0 if unicodedata.east_asian_width(ch) in ("W", "F", "A") else 1.0 for ch in s)
    plain = text.replace("**", "")
    pad = max(0, int(round((width_px / unit_px - units(plain)) / 2)))
    return "\u00a0" * pad + text


def sign_color(d):
    """上涨标红 / 下降标绿 / 无数据紫"""
    if d is None:
        return COLOR_FLAT
    if d > 0:
        return COLOR_UP
    if d < 0:
        return COLOR_DOWN
    return COLOR_FLAT


def build_bar_canvas(m, stats, months, period_ym, out_dir, level="cat"):
    """横向柱状图：一张图同时表达「体量」（柱长）与「环比」（红/绿）"""
    groups = GROUP_BY_CHANNEL.get(m["channel"], [])
    idx = months.index(period_ym)
    prev_ym = months[idx - 1] if idx > 0 else None
    cur, prev = stats[period_ym], (stats[prev_ym] if prev_ym else None)

    def cat_delta(name):
        ca = cur["cat"].get(name)
        pa = (prev or {}).get("cat", {}).get(name)
        return delta_pct(ca, pa) if ca else None

    rows = []
    if level == "genre":
        for g in groups:
            ca = agg_genre(cur, g["categories"])
            pa = agg_genre(prev, g["categories"]) if prev else None
            rows.append({"name": g["name"], "avg": ca["avg"], "share": ca["share"], "d": delta_pct(ca, pa)})
    else:
        for cat, s in cur["cat"].items():
            rows.append({"name": cat, "avg": s["avg"], "share": s["share"], "d": cat_delta(cat)})

    rows = sorted(rows, key=lambda r: -r["avg"])      # 倒金字塔：体量从大到小
    pv = f"{prev_ym[:4]}-{prev_ym[4:]}" if prev_ym else "—"

    # ---- 五列网格：题材 | 均在读 | 环比 | 份额 | 体量柱（份额·体量共用一个表头）----
    LBL_X, LBL_W = 100, 120
    AVG_X, AVG_W = 220, 100
    DLT_X, DLT_W = 320, 100
    SHR_X, SHR_W = 420, 100
    BAR_X, BAR_MAX = 520, 640
    TOP, PITCH, BAR_H = 180, 68, 46
    maxa = max([r["avg"] for r in rows] or [1])
    scale = BAR_MAX / maxa

    nodes = [{
        "id": "caption", "type": "text", "x": LBL_X, "y": 40, "width": 1082, "height": 72,
        "text": (f"{m['label']} · 题材体量与环比（{period_ym[:4]}-{period_ym[4:]}）\n"
                 f"均在读（倒金字塔） 环比：🔴涨 ▲ / 🟢跌 ▼ 基期 {pv}"),
    }]
    # 表头
    for hid, hx, hw, htxt in [("h1", LBL_X, LBL_W, "**题材**"),
                              ("h2", AVG_X, AVG_W, "**均在读**"),
                              ("h3", DLT_X, DLT_W, "**环比**"),
                              ("h4", SHR_X, 760, "**份额 · 体量占比**")]:
        nodes.append({"id": hid, "type": "text", "x": hx, "y": 120, "width": hw, "height": 34,
                      "text": htxt})

    for i, r in enumerate(rows):
        y = TOP + i * PITCH
        d = r["d"]
        col = sign_color(d)
        nodes.append({"id": f"l{i}", "type": "text", "x": LBL_X, "y": y, "width": LBL_W, "height": BAR_H,
                      "text": f"**{r['name']}**"})
        nodes.append({"id": f"a{i}", "type": "text", "x": AVG_X, "y": y, "width": AVG_W, "height": BAR_H,
                      "text": f"**{fmt_reads(int(r['avg']))}**"})
        nodes.append({"id": f"d{i}", "type": "text", "x": DLT_X, "y": y, "width": DLT_W,
                      "height": BAR_H, "color": col,
                      "text": "—" if d is None else f"{'▲' if d > 0 else '▼'} {d:+.0f}%"})
        nodes.append({"id": f"s{i}", "type": "text", "x": SHR_X, "y": y, "width": SHR_W, "height": BAR_H,
                      "text": f"{r['share'] * 100:.1f}%"})
        w = max(r["avg"] * scale, 8)
        nodes.append({"id": f"b{i}", "type": "text", "x": BAR_X, "y": y,
                      "width": int(w), "height": BAR_H, "color": col, "text": ""})

    out = os.path.join(out_dir, f"题材-{m['label']}-{period_ym[:4]}-{period_ym[4:]}.canvas")
    _write(out, nodes, [])
    return [out]


def _write(path, nodes, edges):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"nodes": nodes, "edges": edges}, f, ensure_ascii=False, indent="\t")
    return path


def build(list_key="female-new", period=None, style="bar", level="cat"):
    m = LISTS[list_key]
    months = months_of(m["prefix"])
    period_ym = (period or months[-1]).replace("-", "")
    if period_ym not in months:
        avail = ", ".join(f"{x[:4]}-{x[4:]}" for x in months)
        raise SystemExit(f"❌ {m['label']} 没有 {period_ym} 的数据，可用月份：{avail}")

    kw = load_keywords()
    stats = {mo: monthly_stats(m["prefix"], month_snapshots(m["prefix"], mo)[-1], kw) for mo in months}
    out_dir = os.path.join(VAULT_DIR, "图谱")

    if style == "bar":
        outs = build_bar_canvas(m, stats, months, period_ym, out_dir, level)
    else:
        outs = [build_genre_canvas(m, stats, months, period_ym, out_dir)]
    outs.append(build_tag_canvas(m, stats, months, period_ym, kw, out_dir))
    return outs


def main():
    ap = argparse.ArgumentParser(description="扫榜月度图谱生成器（题材变化 + 梗趋势）")
    ap.add_argument("--list", dest="list_key", default="female-new",
                    help="榜单：female-new / female-read / male-new / male-read")
    ap.add_argument("--period", help="周期 YYYY-MM（默认最新月）")
    ap.add_argument("--style", choices=["grouped", "bar"], default="bar",
                    help="题材图样式：bar=横向柱状图（默认）；grouped=分组节点")
    ap.add_argument("--level", choices=["genre", "cat"], default="cat",
                    help="bar 样式粒度：cat=18 品类（默认）/ genre=7 大赛道")
    args = ap.parse_args()
    for p in build(args.list_key, args.period, args.style, args.level):
        print(f"✅ {p}")


if __name__ == "__main__":
    main()
