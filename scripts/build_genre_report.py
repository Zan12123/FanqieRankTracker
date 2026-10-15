#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
番茄扫榜 · 题材榜单生成器（单一分类：阅读榜 + 新书榜）

用法：
  venv/bin/python scripts/build_genre_report.py                          # 最新一期 · 女频「年代」
  venv/bin/python scripts/build_genre_report.py --date 20261010          # 指定日期
  venv/bin/python scripts/build_genre_report.py --category 种田           # 换分类
  venv/bin/python scripts/build_genre_report.py --gender male --category 都市高武

输出（写入 Obsidian 库）：
  03-选题与市场/03.扫榜与趋势/{分类}题材榜单-YYYY-MM-DD.md
  含：frontmatter + 速览（对比上一期可用快照）+ 阅读榜 30 本 + 新书榜 30 本（排名表 + 逐本简介）

设计原则：
  - 全部指标确定性计算（换血/涨跌/区间），不掺编辑判断
  - 对比基期 = 往前找最近一个「含该分类」的快照（跳过断档日）
  - daily.sh 每日扫榜后自动调用（默认女频·年代）
"""
import argparse
import datetime as dt
import glob
import json
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")


def _find_vault_root(start):
    """向上找含 .obsidian 的目录 = Obsidian 库根（跳过项目自身，同 build_report.py）。"""
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

GENDERS = {
    "female": {"label": "女频", "read": "fanqie_female_read_ranks_", "new": "fanqie_female_new_ranks_"},
    "male":   {"label": "男频", "read": "fanqie_male_read_ranks_",   "new": "fanqie_male_new_ranks_"},
}

MAX_BACK_DAYS = 15  # 往前找基期的最大天数


# ---------------- 数据加载 ----------------

def data_path(prefix, ymd):
    return os.path.join(DATA_DIR, f"{prefix}{ymd}.json")


def load_day(prefix, ymd):
    path = data_path(prefix, ymd)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def get_category(data, name):
    for c in data.get("categories", []):
        if c.get("name") == name:
            return c.get("books", [])
    return None


def load_category_day(prefix, ymd, category):
    """返回 (books, data) 或 (None, None)。books 为空列表也算有效（分类存在但无书）。"""
    data = load_day(prefix, ymd)
    if data is None:
        return None, None
    books = get_category(data, category)
    if books is None:
        return None, None
    return books, data


def prev_available(ymd, category, genders):
    """往前找最近一个两榜任一含该分类的快照日期。"""
    d = dt.datetime.strptime(ymd, "%Y%m%d").date()
    for i in range(1, MAX_BACK_DAYS + 1):
        p = (d - dt.timedelta(days=i)).strftime("%Y%m%d")
        for prefix in (genders["read"], genders["new"]):
            books, _ = load_category_day(prefix, p, category)
            if books is not None:
                return p
    return None


# ---------------- 指标计算 ----------------

def titles(books):
    return [b["title"] for b in books]


def rank_map(books):
    return {b["title"]: i + 1 for i, b in enumerate(books)}


def movement(cur, prev, cap_up=6, cap_down=3):
    """同书两期都在的排名变化：(升 [(名,a,b)], 降 [(名,a,b)])，按幅度降序。"""
    pm, cm = rank_map(prev), rank_map(cur)
    shared = [(t, pm[t], cm[t]) for t in cm if t in pm]
    ups = sorted([x for x in shared if x[1] > x[2]], key=lambda x: x[1] - x[2], reverse=True)
    downs = sorted([x for x in shared if x[1] < x[2]], key=lambda x: x[2] - x[1], reverse=True)
    return ups[:cap_up], downs[:cap_down]


def churn_desc(n_in, n_out, total):
    avg = (n_in + n_out) / 2 / max(total, 1)
    if avg <= 0.10:
        return "，头部盘面稳定"
    if avg >= 0.30:
        return "，换血剧烈"
    return ""


def fmt_moves(moves):
    out = []
    for t, a, b in moves:
        tag = "（登顶）" if b == 1 and a > 1 else ""
        out.append(f"《{t}》{a}→{b}{tag}")
    return "、".join(out)


# ---------------- 报告生成 ----------------

def build_report(ymd, category, gender_key):
    g = GENDERS[gender_key]
    r_cur, _ = load_category_day(g["read"], ymd, category)
    n_cur, _ = load_category_day(g["new"], ymd, category)
    if r_cur is None and n_cur is None:
        return None, f"当日（{ymd}）快照不存在或无「{category}」分类，请先运行 /番茄扫榜 采集"

    # 单榜缺失时仍可出报告（用空列表占位）
    r_cur = r_cur or []
    n_cur = n_cur or []
    iso = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"

    prev_ymd = prev_available(ymd, category, g)
    r_prev, n_prev = [], []
    if prev_ymd:
        r_prev, _ = load_category_day(g["read"], prev_ymd, category)
        n_prev, _ = load_category_day(g["new"], prev_ymd, category)
        r_prev = r_prev or []
        n_prev = n_prev or []
    prev_iso = f"{prev_ymd[:4]}-{prev_ymd[4:6]}-{prev_ymd[6:]}" if prev_ymd else None

    L = []
    A = L.append
    A("---")
    A(f"date: {iso}")
    A(f"source: 番茄{g['label']} · {category}分类（阅读榜 + 新书榜）")
    A(f"category: {category}")
    A(f"阅读榜数量: {len(r_cur)}")
    A(f"新书榜数量: {len(n_cur)}")
    A("tags:")
    A("  - 扫榜数据")
    A(f"  - {category}文")
    A(f"  - 番茄{g['label']}")
    A("---")
    A("")
    A(f"# {g['label']}{category}题材榜单（{iso}）")
    A("")
    A(f"> 数据来源：番茄小说{g['label']}「{category}」分类快照，共 **{len(r_cur) + len(n_cur)} 本**（阅读榜 {len(r_cur)} 本 + 新书榜 {len(n_cur)} 本）。")
    A(f"> 原始 JSON：`09-原料库/02.AI工具/skill/番茄扫榜skill/data/{g['read']}{ymd}.json`、`{g['new']}{ymd}.json`。")
    A("")
    A("## 速览")
    A("")
    A("| 口径 | 头部（在读） | 进榜门槛（末位在读） |")
    A("|---|:---:|:---:|")
    if r_cur:
        A(f"| 阅读榜（存量·读者现在要什么） | {r_cur[0]['title']} · {r_cur[0]['reads']} | {r_cur[-1]['title']} · {r_cur[-1]['reads']} |")
    else:
        A("| 阅读榜（存量·读者现在要什么） | — | — |")
    if n_cur:
        A(f"| 新书榜（增量·市场正在涌向哪） | {n_cur[0]['title']} · {n_cur[0]['reads']} | {n_cur[-1]['title']} · {n_cur[-1]['reads']} |")
    else:
        A("| 新书榜（增量·市场正在涌向哪） | — | — |")
    A("")

    r_range = f"阅读榜在读区间：{r_cur[-1]['reads']} – {r_cur[0]['reads']}" if r_cur else "阅读榜：当日无数据"
    n_range = f"新书榜区间：{n_cur[-1]['reads']} – {n_cur[0]['reads']}" if n_cur else "新书榜：当日无数据"
    A(f"- {r_range}；{n_range}。")

    dup = set(titles(r_cur)) & set(titles(n_cur))
    A(f"- 两榜当日重复：{len(dup)} 本（新书上榜后一般先在阅读榜爬升，同日交集低属正常）。")

    if not prev_ymd:
        A(f"- 近 {MAX_BACK_DAYS} 日内无上期可用快照，跳过对比。")
    else:
        r_in = [t for t in titles(r_cur) if t not in set(titles(r_prev))]
        r_out = [t for t in titles(r_prev) if t not in set(titles(r_cur))]
        n_in = [t for t in titles(n_cur) if t not in set(titles(n_prev))]
        n_out = [t for t in titles(n_prev) if t not in set(titles(n_cur))]
        A(f"- **对比 {prev_iso}**：阅读榜换血 {len(r_in)} 进 / {len(r_out)} 出"
          f"{churn_desc(len(r_in), len(r_out), len(r_cur))}；"
          f"新书榜换血 {len(n_in)} 进 / {len(n_out)} 出{churn_desc(len(n_in), len(n_out), len(n_cur))}。")

        if r_in or r_out:
            ins = "、".join(f"《{b['title']}》{b['reads']}" for b in r_cur if b["title"] in set(r_in)) or "无"
            outs = "、".join(f"《{t}》" for t in r_out) or "无"
            A(f"- 阅读榜新进榜：{ins}。掉榜：{outs}。")
        if n_in or n_out:
            ins = "、".join(f"《{b['title']}》{b['reads']}" for b in n_cur if b["title"] in set(n_in)) or "无"
            outs = "、".join(f"《{t}》" for t in n_out) or "无"
            A(f"- 新书榜新进榜：{ins}。掉榜：{outs}。")

        r_ups, r_downs = movement(r_cur, r_prev)
        if r_ups or r_downs:
            parts = []
            if r_ups:
                parts.append(f"涨幅明显：{fmt_moves(r_ups)}")
            if r_downs:
                parts.append(f"跌幅：{fmt_moves(r_downs)}")
            A(f"- 阅读榜{'；'.join(parts)}。")
        n_ups, _ = movement(n_cur, n_prev, cap_up=5)
        if n_ups:
            A(f"- 新书榜爬升明显：{fmt_moves(n_ups)}。")
    A("")

    def emit_section(title, books, note):
        A("---")
        A("")
        A(f"## {title}")
        A("")
        A(f"> {note}")
        A("")
        A("| 排名 | 书名 | 作者 | 在读 |")
        A("|:---:|---|---|:---:|")
        for i, b in enumerate(books, 1):
            A(f"| {i} | 《{b['title']}》 | {b['author']} | {b['reads']} |")
        A("")
        A("### 逐本简介")
        A("")
        for i, b in enumerate(books, 1):
            intro = re.sub(r"\s+", " ", b.get("intro", "")).strip()
            url = b.get("url", "")
            link = f"—— [番茄页面]({url})" if url else ""
            A(f"**{i}. 《{b['title']}》**（{b['author']} · 在读 {b['reads']}）{link}")
            A("")
            A(f"> {intro}")
            A("")

    if r_cur:
        emit_section(f"一、阅读榜 · {category}（{len(r_cur)} 本）", r_cur,
                     "阅读榜 = 存量需求，反映读者**现在**在读什么，判断题材真实热度以此为准。")
    if n_cur:
        idx = "二" if r_cur else "一"
        emit_section(f"{idx}、新书榜 · {category}（{len(n_cur)} 本）", n_cur,
                     "新书榜 = 增量供给，反映市场（作者/平台）**正在涌向**哪些梗，噪声较大、换血快。")

    out_path = os.path.join(VAULT_DIR, f"{category}题材榜单-{iso}.md")
    os.makedirs(VAULT_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return out_path, None


def main():
    ap = argparse.ArgumentParser(description="生成单一题材的阅读榜+新书榜榜单报告")
    ap.add_argument("--date", default=dt.date.today().strftime("%Y%m%d"), help="YYYYMMDD，默认今天")
    ap.add_argument("--category", default="年代", help="平台分类名，默认「年代」")
    ap.add_argument("--gender", default="female", choices=list(GENDERS), help="频道，默认女频")
    args = ap.parse_args()

    ymd = re.sub(r"[^0-9]", "", args.date)
    path, err = build_report(ymd, args.category, args.gender)
    if err:
        print(f"⚠️  {err}")
        raise SystemExit(1)
    print(f"✅ {args.category}题材榜单已写入: {path}")


if __name__ == "__main__":
    main()
