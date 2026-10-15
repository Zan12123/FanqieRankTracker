#!/usr/bin/env python3
"""番茄榜单爬虫 — Kimi WebBridge 适配版。

用法:
    python scrape_webbridge.py --gender female --type new    # 女频新书榜
    python scrape_webbridge.py --gender female --type read   # 女频阅读榜
    python scrape_webbridge.py --gender male --type new      # 男频新书榜
    python scrape_webbridge.py --gender male --type read     # 男频阅读榜

原理:
    1. 通过 WebBridge HTTP API (127.0.0.1:10086) 控制用户的真实浏览器
    2. 导航到番茄榜单页面，用 evaluate 执行 JS 提取 DOM 数据
    3. 复用 scrape_ranks.py 的字体解码逻辑
    4. 输出与原有格式完全兼容的 JSON 快照

前置条件:
    - Kimi WebBridge 扩展已安装且连接（浏览器扩展图标显示绿色）
    - 浏览器已登录番茄小说账号（推荐，减少风控）
"""

import os
import json
import sys
import time
import random
import argparse
import urllib.request
import urllib.error
from datetime import datetime
from typing import List, Dict, Any, Optional

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


# ======================== WebBridge HTTP Client ========================
WEBBRIDGE_URL = "http://127.0.0.1:10086/command"


class WebBridgeClient:
    """封装 Kimi WebBridge HTTP API。"""

    def __init__(self, session: str):
        self.session = session

    def _post(self, action: str, args: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "action": action,
            "args": args,
            "session": self.session,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            WEBBRIDGE_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if not data.get("ok", False):
                    err = data.get("error", {})
                    raise RuntimeError(f"WebBridge {action} failed: {err}")
                return data.get("result", {})
        except urllib.error.URLError as e:
            raise RuntimeError(f"WebBridge connection failed: {e}")

    def navigate(self, url: str, new_tab: bool = True,
                 group_title: str = "番茄扫榜") -> Dict[str, Any]:
        return self._post("navigate", {
            "url": url,
            "newTab": new_tab,
            "group_title": group_title,
        })

    def snapshot(self) -> Dict[str, Any]:
        """获取页面可访问性树（文本）。对字体反爬可能有奇效！"""
        return self._post("snapshot", {})

    def evaluate(self, code: str) -> Any:
        """在页面执行 JS 代码。"""
        result = self._post("evaluate", {"code": code})
        return result.get("value")

    def screenshot(self, path: Optional[str] = None,
                   selector: Optional[str] = None) -> str:
        """截图并返回文件路径。"""
        args = {}
        if path:
            args["path"] = path
        if selector:
            args["selector"] = selector
        result = self._post("screenshot", args)
        return result.get("path", "")

    def scroll_to_bottom(self):
        """滚动到页面底部。"""
        self.evaluate("window.scrollTo(0, document.body.scrollHeight)")

    def scroll_to_top(self):
        self.evaluate("window.scrollTo(0, 0)")

    def wait(self, ms: int = 2000):
        time.sleep(ms / 1000)

    def close_tab(self):
        self._post("close_tab", {})

    def close_session(self):
        self._post("close_session", {})


# ======================== 爬虫逻辑 ========================
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

URL_CONFIG = {
    "female": {"new": ("0_1", "女频新书榜"), "read": ("0_2", "女频阅读榜")},
    "male":   {"new": ("1_1", "男频新书榜"), "read": ("1_2", "男频阅读榜")},
}


def get_file_prefix(gender: str, rank_type: str) -> str:
    return f"fanqie_{gender}_{rank_type}_ranks"


def get_state_prefix(gender: str, rank_type: str) -> str:
    return f"task_state_{gender}_{rank_type}"


def _fetch_categories_js(rank_prefix: str) -> str:
    """提取侧边栏分类列表的 JS 代码。"""
    return f"""
    (() => {{
        return Array.from(document.querySelectorAll('a'))
            .filter(a => a.href.includes('{rank_prefix}'))
            .map(a => ({{
                name: a.textContent.trim(),
                href: a.getAttribute('href')
            }}));
    }})()
    """


def _extract_books_js() -> str:
    """提取书籍卡片的 JS 代码。"""
    return """
    (() => {
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
    })()
    """


def run_webbridge_scraper(gender: str = "female", rank_type: str = "new",
                          limit: int = 30, sleep_sec: int = 5):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    url_code, label = URL_CONFIG[gender][rank_type]
    file_prefix = get_file_prefix(gender, rank_type)
    state_prefix = get_state_prefix(gender, rank_type)

    date_str = datetime.now().strftime("%Y%m%d")
    output_file = os.path.join(OUTPUT_DIR, f"{file_prefix}_{date_str}.json")
    state_file = os.path.join(OUTPUT_DIR, f"{state_prefix}_{date_str}.json")

    target_cat = "1141" if gender == "male" else "1139"
    max_init_retries = 3

    # 状态恢复
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

    session_name = f"fanqie-{gender}-{rank_type}-{date_str}"
    client = WebBridgeClient(session_name)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔌 连接 WebBridge ...")
    try:
        # 测试连接
        result = client.navigate("about:blank", new_tab=False)
        print(f"  ✅ WebBridge 连接成功，tabId={result.get('tabId', 'unknown')}")
    except Exception as e:
        print(f"  ❌ WebBridge 连接失败: {e}")
        print(f"  💡 请确认：1) 浏览器已安装 Kimi WebBridge 扩展；2) 扩展图标为绿色/已连接状态")
        print(f"  📖 安装指南：https://www.kimi.com/zh-cn/features/webbridge")
        return

    rank_prefix = f"/rank/{url_code}_"
    init_url = f"https://fanqienovel.com/rank/{url_code}_{target_cat}"

    # 第一步：获取分类列表
    categories = None
    for attempt in range(1, max_init_retries + 1):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 初始化 {label} (尝试 {attempt}/{max_init_retries})")
        try:
            if attempt > 1:
                time.sleep(random.uniform(2.0, 5.0))
                retry_url = f"{init_url}?_={random.randint(10000, 99999)}"
                client.navigate(retry_url, new_tab=False)
            else:
                client.navigate(init_url, new_tab=False)
        except Exception as e:
            print(f"  ⚠️ 导航失败: {e}")
            continue

        client.wait(10000)  # 等页面渲染

        try:
            categories = client.evaluate(_fetch_categories_js(rank_prefix))
        except Exception as e:
            print(f"  ⚠️ 分类提取失败: {e}")
            categories = []

        if categories and len(categories) > 0:
            print(f"✅ 成功提取到 {len(categories)} 个分类标签 [{label}]")
            break
        else:
            print(f"  ❌ 未提取到分类，尝试重试...")
            if attempt >= max_init_retries:
                print(f"❌ 初始化失败 [{label}]")
                try:
                    err_path = os.path.join(OUTPUT_DIR, f"error_{label}_{date_str}.png")
                    client.screenshot(path=err_path)
                    print(f"  📸 已截图保存到: {err_path}")
                except Exception:
                    pass
                client.close_session()
                return

    # 第二步：逐个分类抓取
    for idx, cat in enumerate(categories):
        cat_name = decode_text(cat["name"])
        cat_href = cat["href"]

        if cat_name in completed_cats:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏭️ 跳过已完成: {cat_name}")
            continue

        print(f"[{datetime.now().strftime('%H:%M:%S')}] 抓取分类 -> {cat_name}")

        cat_url = f"https://fanqienovel.com{cat_href}"
        try:
            client.navigate(cat_url, new_tab=False)
            client.wait(8000)
        except Exception as e:
            print(f"  ⚠️ 导航失败 {cat_name}: {str(e)[:80]}，跳过")
            continue

        # 动态滚动加载
        max_scrolls = 15
        target_links = limit * 3
        for i in range(max_scrolls):
            prev_count = client.evaluate(
                "document.querySelectorAll('a[href^=\"/page/\"]').length"
            )
            client.scroll_to_bottom()
            client.wait(2000)
            new_count = client.evaluate(
                "document.querySelectorAll('a[href^=\"/page/\"]').length"
            )
            if new_count >= target_links:
                print(f"  滚动 {i+1} 次后已加载 {new_count} 个条目")
                break
            if new_count == prev_count and new_count > 0:
                client.scroll_to_top()
                client.wait(1000)
                client.scroll_to_bottom()
                client.wait(2000)
                retry_count = client.evaluate(
                    "document.querySelectorAll('a[href^=\"/page/\"]').length"
                )
                if retry_count == new_count:
                    print(f"  确认已加载全部 {retry_count} 条，停止滚动")
                    break
                else:
                    print(f"  回顶触底新增 {retry_count - new_count} 条（共 {retry_count} 条）")

        # 提取数据
        try:
            books_data = client.evaluate(_extract_books_js())
        except Exception as e:
            print(f"JS 抽取失败 {cat_name}: {e}")
            books_data = []

        category_books = []
        for b in books_data[:limit]:
            t = decode_text(b.get("title", ""))
            a = decode_text(b.get("author", ""))
            r_raw = decode_text(b.get("reads", ""))
            i = decode_text(b.get("intro", "")).replace("\n", " ")
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

        # 数据完整性检查
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

    client.close_session()
    print(f"\n✅ [{label}] 任务完毕！数据: {output_file}")


# ======================== 主入口 ========================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="番茄小说榜单爬虫 — Kimi WebBridge 版")
    parser.add_argument("--gender", type=str, default="female",
                        choices=["female", "male"], help="频别: female/male")
    parser.add_argument("--type", type=str, default="new",
                        choices=["new", "read"], help="榜单类型: new(新书榜)/read(阅读榜)")
    parser.add_argument("--limit", type=int, default=30, help="每分类抓取数量")
    parser.add_argument("--sleep", type=int, default=5, help="分类间隔秒数")
    args = parser.parse_args()

    label = URL_CONFIG.get(args.gender, {}).get(args.type, ("?", "?"))[1]
    print(f"开始执行番茄 {label} 抓取计划（WebBridge 模式）...")
    run_webbridge_scraper(gender=args.gender, rank_type=args.type,
                          limit=args.limit, sleep_sec=args.sleep)
