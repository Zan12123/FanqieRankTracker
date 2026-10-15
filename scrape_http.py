#!/usr/bin/env python3
"""番茄榜单爬虫 — 纯 HTTP 请求版，无需浏览器。

原理：直接调用番茄内置 API (/api/rank/category/list)，
用 scrape_ranks.py 同款的字体解码逻辑还原书名/作者/简介。

用法:
    python scrape_http.py --gender female --type new    # 女频新书榜 (每分类 30 本)
    python scrape_http.py --gender female --type read   # 女频阅读榜
    python scrape_http.py --gender male --type new      # 男频新书榜
    python scrape_http.py --gender male --type read     # 男频阅读榜
"""

import os
import json
import sys
import time
import re
from datetime import datetime

# ======================== 字体解码（与 scrape_ranks.py 完全一致） ========================
START_CODE = 58344
CHAR_SEQUENCE = [
    "D", "在", "主", "特", "家", "军", "然", "表", "场", "4", "要", "只", "v", "和", "?", "6", "别", "还", "g", "现", "儿", "岁", "?", "?", "此", "象", "月", "3", "出", "战", "工", "相", "o", "男", "直", "失", "世", "F", "都", "平", "文", "什", "V", "O", "将", "真", "T", "那", "当", "?", "会", "立", "些", "u", "是", "十", "张", "学", "气", "大", "爱", "两", "命", "全", "后", "东", "性", "通", "被", "1", "它", "乐", "接", "而", "感", "车", "山", "公", "了", "常", "以", "何", "可", "话", "先", "p", "i", "叫", "轻", "M", "士", "w", "着", "变", "尔", "快", "l", "个", "说", "少", "色", "里", "安", "花", "远", "7", "难", "师", "放", "t", "报", "认", "面", "道", "S", "?", "克", "地", "度", "I", "好", "机", "U", "民", "写", "把", "万", "同", "水", "新", "没", "书", "电", "吃", "像", "斯", "5", "为", "y", "白", "几", "日", "教", "看", "但", "第", "加", "候", "作", "上", "拉", "住", "有", "法", "r", "事", "应", "位", "利", "你", "声", "身", "国", "问", "马", "女", "他", "Y", "比", "父", "x", "A", "H", "N", "s", "X", "边", "美", "对", "所", "金", "活", "回", "意", "到", "z", "从", "j", "知", "又", "内", "因", "点", "Q", "三", "定", "8", "R", "b", "正", "或", "夫", "向", "德", "听", "更", "?", "得", "告", "并", "本", "q", "过", "记", "L", "让", "打", "f", "人", "就", "者", "去", "原", "满", "体", "做", "经", "K", "走", "如", "孩", "c", "G", "给", "使", "物", "?", "最", "笑", "部", "?", "员", "等", "受", "k", "行", "一", "条", "果", "动", "光", "门", "头", "见", "往", "自", "解", "成", "处", "天", "能", "于", "名", "其", "发", "总", "母", "的", "死", "手", "入", "路", "进", "心", "来", "h", "时", "力", "多", "开", "已", "许", "d", "至", "由", "很", "界", "n", "小", "与", "Z", "想", "代", "么", "分", "生", "口", "再", "妈", "望", "次", "西", "风", "种", "带", "J", "?", "实", "情", "才", "这", "?", "E", "我", "神", "格", "长", "觉", "间", "年", "眼", "无", "不", "亲", "关", "结", "0", "友", "信", "下", "却", "重", "己", "老", "2", "音", "字", "m", "呢", "明", "之", "前", "高", "P", "B", "目", "太", "e", "9", "起", "稜", "她", "也", "W", "用", "方", "子", "英", "每", "理", "便", "四", "数", "期", "中", "C", "外", "样", "a", "海", "们", "任"
]


def decode_text(text: str) -> str:
    if not text:
        return ""
    result = []
    for char in text:
        code = ord(char)
        idx = code - START_CODE
        if 0 <= idx < len(CHAR_SEQUENCE):
            result.append(CHAR_SEQUENCE[idx])
        else:
            result.append(char)
    return "".join(result)


# ======================== 常量 ========================

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

URL_CONFIG = {
    "female": {"new": ("0", "1", "女频新书榜"), "read": ("0", "2", "女频阅读榜")},
    "male":   {"new": ("1", "1", "男频新书榜"), "read": ("1", "2", "男频阅读榜")},
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://fanqienovel.com/",
}


# ======================== HTTP 工具 ========================

def fetch_json(url: str) -> dict:
    """GET 请求返回 JSON。"""
    import urllib.request
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_html(url: str) -> str:
    """请求页面返回 HTML 字符串。"""
    import urllib.request
    hdrs = dict(HEADERS)
    hdrs["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


# ======================== 分类提取（从 SSR __INITIAL_STATE__） ========================

def extract_categories_from_ssr(html: str, gender_code: str) -> list:
    """从页面 SSR 注入的 __INITIAL_STATE__ 中提取分类列表。

    __INITIAL_STATE__.rank.rankCategoryTypeList 包含 gender 分组的分类 ID 和名称。
    分类名称也是加密字体编码的，需要 decode。
    """
    m = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});', html, re.DOTALL)
    if not m:
        raise RuntimeError("未找到 __INITIAL_STATE__ 数据")
    state = json.loads(m.group(1))
    cat_type = state.get("rank", {}).get("rankCategoryTypeList", {})
    gender_key = "female" if gender_code == "0" else "male"
    cat_list = cat_type.get(gender_key, [])
    if not cat_list:
        raise RuntimeError(f"未找到 {gender_key} 的分类列表")
    result = []
    for c in cat_list:
        name = decode_text(c.get("name", ""))
        cat_id = c.get("id", "")
        if name and cat_id:
            result.append({"name": name, "id": cat_id})
    return result


def get_rank_version(html: str) -> str:
    """从 SSR 数据中提取 rank_version（时间戳）。"""
    m = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});', html, re.DOTALL)
    if m:
        state = json.loads(m.group(1))
        ver = state.get("rank", {}).get("rankVersion", "")
        if ver:
            return str(ver)
    return str(int(datetime.now().timestamp()))


# ======================== API 数据提取（每分类 30 本） ========================

API_BASE = "https://fanqienovel.com/api/rank/category/list"

# rank_list_type 固定为 3（综合排序）
# rankMold: 1=新书榜, 2=阅读榜
RANK_MOLD = {"new": "1", "read": "2"}


def fetch_category_books(category_id: str, gender_code: str,
                         rank_type: str, rank_version: str,
                         limit: int = 30) -> list:
    """调用 API 获取指定分类的 Top N 书籍。"""
    params = {
        "app_id": "2503",
        "rank_list_type": "3",
        "offset": "0",
        "limit": str(limit),
        "category_id": category_id,
        "rank_version": rank_version,
        "gender": gender_code,
        "rankMold": RANK_MOLD[rank_type],
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{API_BASE}?{query}"

    data = fetch_json(url)
    if data.get("code") != 0:
        print(f"  ⚠️  API 返回 code={data.get('code')}: {data.get('msg', '')}")
        return []

    book_list = data.get("data", {}).get("book_list", [])
    if not book_list:
        return []

    books = []
    for b in book_list:
        # API 返回的读数为整数（如 45111），需要格式化
        reads_raw = b.get("readCount", 0) or b.get("read_count", 0)
        reads = format_read_count(reads_raw) if reads_raw else "未知"

        books.append({
            "title": decode_text(b.get("bookName", "")),
            "author": decode_text(b.get("author", "")),
            "reads": reads,
            "intro": decode_text(b.get("abstract", "") or ""),
            "cover": format_cover_url(b.get("thumbUri", "")),
            "url": f"https://fanqienovel.com/page/{b.get('bookId', '')}",
            "rank": str(b.get("currentPos", "")),
            "rank_change": format_rank_change(b.get("rankPosDiff")),
        })
    return books


def format_read_count(count) -> str:
    """将整数阅读数格式化为'xx.x万'。"""
    try:
        n = float(count)
        if n >= 10000:
            return f"{n / 10000:.1f}万"
        elif n >= 1000:
            return f"{n / 1000:.1f}千"
        return str(int(n))
    except (ValueError, TypeError):
        return str(count)


def format_rank_change(diff) -> str:
    """格式化排名变化。"""
    if diff is None or diff == 0:
        return "-"
    try:
        d = int(diff)
        if d > 0:
            return f"+{d}"
        return str(d)
    except (ValueError, TypeError):
        return "-"


def format_cover_url(url: str) -> str:
    """修正封面 URL（API 返回的可能是相对或残缺 URL）。"""
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if not url.startswith("http"):
        return "https://" + url
    return url


# ======================== 主逻辑 ========================

def get_file_prefix(gender: str, rank_type: str) -> str:
    return f"fanqie_{gender}_{rank_type}_ranks"


def get_state_prefix(gender: str, rank_type: str) -> str:
    return f"task_state_{gender}_{rank_type}"


def run_scraper(gender: str = "female", rank_type: str = "new",
                limit: int = 30, sleep_sec: int = 3):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    gender_code, rank_code, label = URL_CONFIG[gender][rank_type]
    file_prefix = get_file_prefix(gender, rank_type)
    state_prefix = get_state_prefix(gender, rank_type)

    date_str = datetime.now().strftime("%Y%m%d")
    today = datetime.now().strftime("%Y-%m-%d")
    output_file = os.path.join(OUTPUT_DIR, f"{file_prefix}_{date_str}.json")
    state_file = os.path.join(OUTPUT_DIR, f"{state_prefix}_{date_str}.json")

    # 状态恢复
    completed_cats = set()
    all_categories = []
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
                completed_cats = set(state.get("completed", []))
        except Exception:
            pass
    if os.path.exists(output_file) and completed_cats:
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
                all_categories = existing.get("categories", [])
        except Exception:
            pass

    # 第一步：获取分类列表
    # 用任意一个分类页面加载 SSR 数据
    target_cat = "1141" if gender == "male" else "1139"
    init_url = f"https://fanqienovel.com/rank/{gender_code}_{rank_code}_{target_cat}"
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 初始化 {label}: {init_url}")
    html = fetch_html(init_url)
    categories = extract_categories_from_ssr(html, gender_code)
    rank_version = get_rank_version(html)
    print(f"✅ 成功提取到 {len(categories)} 个分类标签 [{label}]")
    print(f"   rank_version: {rank_version}")

    # 第二步：逐个分类调 API 抓取
    for cat in categories:
        cat_name = cat["name"]
        cat_id = cat["id"]

        if cat_name in completed_cats:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏭️ 跳过已完成: {cat_name}")
            continue

        print(f"[{datetime.now().strftime('%H:%M:%S')}] 抓取分类 -> {cat_name} (id={cat_id})", end="")

        try:
            category_books = fetch_category_books(cat_id, gender_code, rank_type,
                                                   rank_version, limit)
        except Exception as e:
            print(f"  ⚠️ 请求失败 {cat_name}: {str(e)[:80]}，跳过")
            time.sleep(sleep_sec)
            continue

        # 数据完整性检查
        if len(all_categories) > 0 and len(category_books) > 0:
            prev_books = all_categories[-1]["books"]
            prev_urls = set(b["url"] for b in prev_books)
            curr_urls = set(b["url"] for b in category_books)
            if len(prev_urls) > 0 and len(curr_urls) > 0:
                overlap = len(prev_urls & curr_urls)
                overlap_pct = overlap / max(len(prev_urls), len(curr_urls))
                if overlap_pct > 0.8:
                    print(f"\n  ⚠️ 数据重复警告: {cat_name} 与 {all_categories[-1]['name']} 有 {overlap}/{max(len(prev_urls), len(curr_urls))} 本重叠 ({overlap_pct:.0%})，分类切换可能失败！")

        all_categories.append({
            "name": cat_name,
            "books": category_books
        })

        # 每完成一个分类立即写入
        snapshot = {
            "date": today,
            "categories": all_categories
        }
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)

        completed_cats.add(cat_name)
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump({"completed": list(completed_cats)}, f, ensure_ascii=False)

        print(f"  → {len(category_books)} 本，已存档。")
        if len(category_books) > 0:
            print(f"     Top3: {' | '.join(b['title'][:20] for b in category_books[:3])}")

        time.sleep(sleep_sec)

    print(f"\n✅ [{label}] 任务完毕！数据: {output_file}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="番茄小说榜单爬虫 — API 直调版")
    parser.add_argument("--gender", type=str, default="female",
                        choices=["female", "male"], help="频别: female/male")
    parser.add_argument("--type", type=str, default="new",
                        choices=["new", "read"], help="榜单类型: new(新书榜)/read(阅读榜)")
    parser.add_argument("--limit", type=int, default=30, help="每分类抓取数量")
    parser.add_argument("--sleep", type=int, default=3, help="分类间隔秒数")
    args = parser.parse_args()

    label = URL_CONFIG.get(args.gender, {}).get(args.type, ("?", "?", "?"))[2]
    print(f"开始执行番茄 {label} 抓取计划（API 直调模式，每分类 {args.limit} 本）...")
    run_scraper(gender=args.gender, rank_type=args.type,
                limit=args.limit, sleep_sec=args.sleep)
