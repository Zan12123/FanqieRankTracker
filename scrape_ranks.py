#!/usr/bin/env python3
"""统一榜单爬虫：支持女频/男频，新书榜/阅读榜。

用法:
    python scrape_ranks.py --gender female --type new    # 女频新书榜
    python scrape_ranks.py --gender female --type read   # 女频阅读榜
    python scrape_ranks.py --gender male --type new      # 男频新书榜
    python scrape_ranks.py --gender male --type read     # 男频阅读榜
"""

import os
import json
import sys
import time
import random
import argparse
from datetime import datetime
from playwright.sync_api import sync_playwright

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


OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# URL 模式: gender_code: 0=女频, 1=男频; rank_code: 1=新书榜, 2=阅读榜
URL_CONFIG = {
    "female": {"new": ("0_1", "女频新书榜"), "read": ("0_2", "女频阅读榜")},
    "male":   {"new": ("1_1", "男频新书榜"), "read": ("1_2", "男频阅读榜")},
}


def get_file_prefix(gender: str, rank_type: str) -> str:
    """返回文件名前缀，如 fanqie_female_new_ranks"""
    return f"fanqie_{gender}_{rank_type}_ranks"


def get_state_prefix(gender: str, rank_type: str) -> str:
    """返回状态文件名前缀，如 task_state_female_new"""
    return f"task_state_{gender}_{rank_type}"


def run_scraper(gender: str = "female", rank_type: str = "new",
                limit: int = 30, sleep_sec: int = 5):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    url_code, label = URL_CONFIG[gender][rank_type]
    file_prefix = get_file_prefix(gender, rank_type)
    state_prefix = get_state_prefix(gender, rank_type)

    date_str = datetime.now().strftime("%Y%m%d")
    output_file = os.path.join(OUTPUT_DIR, f"{file_prefix}_{date_str}.json")
    state_file = os.path.join(OUTPUT_DIR, f"{state_prefix}_{date_str}.json")

    # 入口 URL: 抓取任意一个分类页面以获取侧边栏分类列表
    # 女频用 1139 (古风世情)，男频用 1141 (西方奇幻)
    # 侧边栏全量分类列表存在于任意分类页面，不需要精确匹配
    target_cat = "1141" if gender == "male" else "1139"
    max_init_retries = 3

    # ------------- 状态恢复逻辑 -------------
    completed_cats = []
    all_categories = []
    if os.path.exists(state_file):
        with open(state_file, "r", encoding="utf-8") as f:
            try:
                state = json.load(f)
                completed_cats = state.get("completed", [])
            except Exception:
                pass
    if os.path.exists(output_file) and len(completed_cats) > 0:
        with open(output_file, "r", encoding="utf-8") as f:
            try:
                existing = json.load(f)
                all_categories = existing.get("categories", [])
            except Exception:
                pass
    # ----------------------------------------

    with sync_playwright() as p:
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-web-security",
            "--no-sandbox",
            "--disable-setuid-sandbox",
        ]
        browser = p.chromium.launch(headless=True, args=launch_args)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        page = context.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        # 先用一个分类页面提取侧边栏列表（通过 JS 解析所有带 rank 前缀的链接）
        # 由于 Fanqie 服务器有时会返回残缺 HTML（无 SSR 内容），使用重试机制
        init_url = f"https://fanqienovel.com/rank/{url_code}_{target_cat}"
        rank_prefix = f"/rank/{url_code}_"
        categories_js = f"""
        () => {{
            return Array.from(document.querySelectorAll('a'))
                .filter(a => a.href.includes('{rank_prefix}'))
                .map(a => ({{
                    name: a.textContent.trim(),
                    href: a.getAttribute('href')
                }}));
        }}
        """
        # 首次访问前加入随机延迟，降低被限流概率
        time.sleep(random.uniform(1.0, 3.0))
        categories = None
        for attempt in range(1, max_init_retries + 1):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 初始化 {label} (尝试 {attempt}/{max_init_retries}): {init_url}")
            try:
                if attempt > 1:
                    # 重试时加随机延迟 + 随机 query param 防缓存/限流
                    time.sleep(random.uniform(2.0, 5.0))
                    retry_url = f"{init_url}?_={random.randint(10000, 99999)}"
                    page.goto(retry_url, wait_until="commit", timeout=60000)
                else:
                    page.goto(init_url, wait_until="commit", timeout=60000)
            except Exception as e:
                print(f"  ⚠️ 导航失败: {e}")

            # 等待页面加载 — 先检查 SSR 内容
            page.wait_for_timeout(10000)
            try:
                page.wait_for_function(
                    "() => document.body && document.body.innerText.length > 50",
                    timeout=20000)
            except Exception:
                body_len = page.evaluate("() => document.body?.innerText.length || 0")
                print(f"  ⚠️ body 内容不足 (len={body_len})，可能 SSR 渲染失败")

            # 额外等待：给 SPA 水合留时间
            page.wait_for_timeout(5000)

            categories = page.evaluate(categories_js)
            if categories and len(categories) > 0:
                print(f"✅ 成功提取到 {len(categories)} 个分类标签 [{label}]")
                break
            else:
                links_total = page.evaluate("() => document.querySelectorAll('a').length")
                body_len = page.evaluate("() => document.body?.innerText.length || 0")
                print(f"  ❌ 未提取到分类 (页面 <a>={links_total}, body={body_len}b)")
                if attempt < max_init_retries:
                    print(f"  🔄 等待后重试...")
                else:
                    print(f"❌ 初始化失败 [{label}]，已达最大重试次数")
                    try:
                        page.screenshot(path=os.path.join(OUTPUT_DIR, f"error_{label}_{date_str}.png"))
                    except Exception:
                        pass
                    browser.close()
                    return

        for idx, cat in enumerate(categories):
            cat_name = decode_text(cat["name"])
            cat_href = cat["href"]

            if cat_name in completed_cats:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏭️ 跳过已完成: {cat_name}")
                continue

            print(f"[{datetime.now().strftime('%H:%M:%S')}] 抓取分类 -> {cat_name}")

            # 直接 URL 导航 — 最可靠的方式
            # 等待时间长一些确保 SPA 水合 + 懒加载机制就绪
            cat_url = f"https://fanqienovel.com{cat_href}"
            nav_ok = False
            try:
                page.goto(cat_url, wait_until="commit", timeout=60000)
                page.wait_for_timeout(8000)  # 等 SPA 水合 + 懒加载 ready
                page.wait_for_selector('a[href^="/page/"]', timeout=15000)
                nav_ok = True
            except Exception as e:
                print(f"  ⚠️ 导航失败 {cat_name}: {str(e)[:80]}，跳过")
                continue

            # 动态滚动加载：持续滚动直到够数或无新条目
            max_scrolls = 15
            target_links = limit * 3
            for i in range(max_scrolls):
                prev_count = page.evaluate("""() => {
                    return document.querySelectorAll('a[href^="/page/"]').length;
                }""")
                # 滚到页面底部触发懒加载
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2.0)
                new_count = page.evaluate("""() => {
                    return document.querySelectorAll('a[href^="/page/"]').length;
                }""")
                if new_count >= target_links:
                    print(f"  滚动 {i+1} 次后已加载 {new_count} 个条目")
                    break
                if new_count == prev_count and new_count > 0:
                    print(f"  滚动 {i+1} 次后无新增（已加载 {new_count} 条），回顶再触底...")
                    page.evaluate("window.scrollTo(0, 0)")
                    time.sleep(1)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(2)
                    retry_count = page.evaluate("""() => {
                        return document.querySelectorAll('a[href^="/page/"]').length;
                    }""")
                    if retry_count == new_count:
                        print(f"  确认已加载全部 {retry_count} 条，停止滚动")
                        break
                    else:
                        print(f"  回顶触底新增 {retry_count - new_count} 条（共 {retry_count} 条）")

            extract_js = """
            () => {
                const bookMap = new Map();
                const links = document.querySelectorAll('a[href^="/page/"]');
                links.forEach(link => {
                    let container = link.parentElement;
                    let depth = 0;
                    while (container && depth < 6) {
                        if (container.querySelector('img') && container.innerText.includes('在读')) {
                            const href = link.getAttribute('href');
                            if (!bookMap.has(href)) {
                                bookMap.set(href, container);
                            }
                            break;
                        }
                        container = container.parentElement;
                        depth++;
                    }
                });

                const cards = Array.from(bookMap.values());
                const results = [];
                for (const item of cards) {
                    let imgNode = item.querySelector('img');
                    let cover = imgNode ? imgNode.getAttribute('src') : "";

                    let title = "";
                    if (imgNode && imgNode.getAttribute('alt')) {
                        title = imgNode.getAttribute('alt').trim();
                    }
                    if (!title) {
                        let textTitleNode = item.querySelector('h4, .title, h1') || item.querySelector('a[href^="/page/"]');
                        if (textTitleNode) {
                            let text = textTitleNode.innerText.trim();
                            if (text && !/^\\d+$/.test(text)) {
                                title = text;
                            }
                        }
                    }
                    if (!title) title = "未知";
                    if (title.includes("榜单说明")) continue;

                    let authorNode = item.querySelector('.author, .author-name') || item.querySelector('a[href^="/author-page/"]');
                    let author = authorNode ? authorNode.innerText.trim() : "未知";

                    let reads = "未知";
                    const lines = item.innerText.split('\\n');
                    for (let line of lines) {
                        if (line.includes('在读')) {
                            reads = line;
                            break;
                        }
                    }

                    let introNode = item.querySelector('.intro, .abstract, .desc');
                    let intro = introNode ? introNode.innerText.trim() : "暂无简介";

                    results.push({
                        title: title,
                        author: author,
                        reads: reads,
                        intro: intro,
                        cover: cover,
                        url: item.querySelector('a[href^="/page/"]')?.getAttribute('href') || ''
                    });
                }
                return results;
            }
            """

            try:
                books_data = page.evaluate(extract_js)
            except Exception as e:
                print(f"JS抽取失败 {cat_name}: {e}")
                books_data = []

            category_books = []
            for b in books_data[:limit]:
                t = decode_text(b.get("title", ""))
                a = decode_text(b.get("author", ""))
                r_raw = decode_text(b.get("reads", ""))
                i = decode_text(b.get("intro", "")).replace("\\n", " ")
                c = b.get("cover", "")

                if "在读" in r_raw:
                    parts = r_raw.split("在读")
                    cleaned_r = parts[1].replace(":", "").replace("：", "").strip() if len(parts) > 1 else r_raw
                else:
                    cleaned_r = r_raw

                category_books.append({
                    "title": t,
                    "author": a,
                    "reads": cleaned_r,
                    "intro": i,
                    "cover": c,
                    "url": "https://fanqienovel.com" + b.get("url", "")
                })

            # 数据完整性检查：对比上一个分类，检测分类切换是否失败
            if len(all_categories) > 0 and len(category_books) > 0:
                prev_books = all_categories[-1]["books"]
                prev_urls = set(b["url"] for b in prev_books)
                curr_urls = set(b["url"] for b in category_books)
                if len(prev_urls) > 0 and len(curr_urls) > 0:
                    overlap = len(prev_urls & curr_urls)
                    overlap_pct = overlap / max(len(prev_urls), len(curr_urls))
                    if overlap_pct > 0.8:
                        print(f"  ⚠️ 数据重复警告: {cat_name} 与 {all_categories[-1]['name']} 有 {overlap}/{max(len(prev_urls), len(curr_urls))} 本重叠 ({overlap_pct:.0%})，分类切换可能失败！")

            all_categories.append({
                "name": cat_name,
                "books": category_books
            })

            # 每完成一个分类立即写入
            snapshot = {
                "date": datetime.now().strftime('%Y-%m-%d'),
                "categories": all_categories
            }
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)

            completed_cats.append(cat_name)
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump({"completed": completed_cats}, f, ensure_ascii=False)

            print(f"✅ {cat_name} 抓取 {len(category_books)} 本，已存档。等待 {sleep_sec}s...")
            time.sleep(sleep_sec)

        browser.close()

    print(f"\n✅ [{label}] 任务完毕！数据: {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="番茄小说榜单爬虫")
    parser.add_argument("--gender", type=str, default="female",
                        choices=["female", "male"], help="频别: female/male")
    parser.add_argument("--type", type=str, default="new",
                        choices=["new", "read"], help="榜单类型: new(新书榜)/read(阅读榜)")
    parser.add_argument("--limit", type=int, default=30, help="每分类抓取数量")
    parser.add_argument("--sleep", type=int, default=5, help="分类间隔秒数")
    args = parser.parse_args()

    label = URL_CONFIG.get(args.gender, {}).get(args.type, ("?", "?"))[1]
    print(f"开始执行番茄 {label} 抓取计划...")
    run_scraper(gender=args.gender, rank_type=args.type,
                limit=args.limit, sleep_sec=args.sleep)
