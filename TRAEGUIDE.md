# 番茄扫榜 × TRAE 自动化使用指南

本文档说明如何将番茄扫榜项目与 TRAE 自动化功能结合，实现每天开机自动运行数据抓取。

---

## 🎯 核心方案

**去掉 GitHub 依赖，完全本地运行 + iCloud 同步**

- ✅ 无需 GitHub Actions
- ✅ 无需 git commit/push
- ✅ 数据通过 iCloud 在多设备间同步
- ✅ TRAE 每天自动执行爬虫任务

---

## 📁 文件说明

| 文件 | 用途 |
|------|------|
| `auto_run.py` | 自动化执行主脚本（带日志、断点续跑） |
| `daily.sh` | 一键启动脚本（抓取 + 启动看板服务器） |
| `scrape_ranks.py` | 统一爬虫脚本（支持男女频、新书榜/阅读榜） |
| `scripts/build_latest.py` | 数据构建 + AI 趋势分析 |

---

## 🚀 快速开始

### 第一步：配置 Python 虚拟环境

```bash
cd /Users/zxian/Library/Mobile\ Documents/com~apple~CloudDocs/FanqieRankTracker

# 创建虚拟环境（如果不存在）
python3 -m venv venv

# 激活虚拟环境并安装依赖
source venv/bin/activate
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
```

### 第二步：配置 AI 分析（可选）

如需启用 AI 趋势分析，在 TRAE 自动化任务中设置环境变量：

```bash
export API_BASE_URL="https://your-api-endpoint/v1"
export API_KEY="your-api-key"
export API_MODEL="gpt-4o-mini"
```

---

## ⚙️ TRAE 自动化配置

### 方式一：通过 Schedule 功能（推荐）

在 TRAE 中创建定时任务，每天上午自动执行：

1. 打开 TRAE
2. 输入 `/schedule` 或使用 Schedule 功能
3. 创建新任务，配置如下：

| 配置项 | 值 |
|--------|-----|
| **任务名称** | `番茄扫榜每日更新` |
| **Cron 表达式** | `0 8 * * *` (每天早上 8 点) |
| **时区** | `Asia/Shanghai` (北京时间) |
| **执行命令** | `cd /Users/zxian/Library/Mobile\ Documents/com~apple~CloudDocs/FanqieRankTracker && venv/bin/python auto_run.py` |

### 详细的 Schedule 任务消息内容

```
番茄扫榜每日自动更新任务

工作目录: /Users/zxian/Library/Mobile\ Documents/com~apple~CloudDocs/FanqieRankTracker

执行步骤:
1. 检查今日数据是否已存在（避免重复抓取）
2. 抓取番茄小说女频新书榜 + 阅读榜
3. 抓取番茄小说男频新书榜 + 阅读榜
4. 构建趋势数据和 AI 分析
5. 所有数据保存在本地 data/ 目录，通过 iCloud 同步

日志文件: auto_run.log

AI 分析配置（如需要请添加环境变量）:
- API_BASE_URL: OpenAI 兼容 API 地址
- API_KEY: API 密钥
- API_MODEL: 模型名称（如 gpt-4o-mini）

执行命令: venv/bin/python auto_run.py
```

### 方式二：直接在 TRAE 中运行

随时可以在 TRAE 中手动触发一次完整抓取：

```bash
cd /Users/zxian/Library/Mobile\ Documents/com~apple~CloudDocs/FanqieRankTracker
venv/bin/python auto_run.py
```

---

## 🖥️ 查看看板数据

### 方法一：使用 daily.sh 一键启动

```bash
cd /Users/zxian/Library/Mobile\ Documents/com~apple~CloudDocs/FanqieRankTracker
./daily.sh
```

这会自动：
1. 检查并抓取今日数据（如果缺失）
2. 启动本地 HTTP 服务器 (端口 8080)
3. 在浏览器中自动打开看板

### 方法二：手动启动服务器

```bash
cd /Users/zxian/Library/Mobile\ Documents/com~apple~CloudDocs/FanqieRankTracker
python3 -m http.server 8080
```

然后在浏览器访问：
- 女频新书榜: http://localhost:8080/index.html
- 女频阅读榜: http://localhost:8080/read.html
- 男频新书榜: http://localhost:8080/male.html
- 男频阅读榜: http://localhost:8080/male_read.html
- 趋势分析(女): http://localhost:8080/trend.html
- 趋势分析(男): http://localhost:8080/male_trend.html

---

## 📊 数据存储与 iCloud 同步

所有数据都保存在项目目录下，自动通过 iCloud 同步：

```
FanqieRankTracker/
├── data/                           # 原始数据
│   ├── fanqie_female_new_ranks_YYYYMMDD.json   # 女频新书榜
│   ├── fanqie_female_read_ranks_YYYYMMDD.json  # 女频阅读榜
│   ├── fanqie_male_new_ranks_YYYYMMDD.json     # 男频新书榜
│   ├── fanqie_male_read_ranks_YYYYMMDD.json    # 男频阅读榜
│   ├── latest_ranks.json           # 最新聚合数据
│   ├── latest_read_ranks.json      # 女频阅读榜聚合
│   ├── latest_male_ranks.json      # 男频新书榜聚合
│   ├── latest_male_read_ranks.json # 男频阅读榜聚合
│   ├── trends/                     # 女频趋势历史
│   ├── trends-read/                # 女频阅读趋势
│   ├── trends-male/                # 男频趋势历史
│   └── trends-male-read/           # 男频阅读趋势
├── api/                            # 静态 API 数据
│   ├── lastest/                    # 女频新书榜 API
│   ├── read-lastest/               # 女频阅读榜 API
│   ├── male-lastest/               # 男频新书榜 API
│   └── male-read-lastest/          # 男频阅读榜 API
└── auto_run.log                    # 自动化运行日志
```

---

## 🔍 查看运行日志

```bash
cd /Users/zxian/Library/Mobile\ Documents/com~apple~CloudDocs/FanqieRankTracker

# 查看最近的日志
tail -50 auto_run.log

# 实时监控日志（运行时）
tail -f auto_run.log
```

---

## 🎛️ 高级用法

### 单独抓取某个榜单

```bash
# 女频新书榜
venv/bin/python scrape_ranks.py --gender female --type new

# 男频阅读榜
venv/bin/python scrape_ranks.py --gender male --type read
```

### 强制重新生成 AI 分析

```bash
venv/bin/python scripts/build_latest.py --gender female --type new --force
```

### 指定日期重新构建

```bash
venv/bin/python scripts/build_latest.py --gender female --type new --date 2026-07-30
```

---

## 🐛 常见问题

### Q: TRAE 任务执行失败怎么办？

1. 查看日志文件：`cat auto_run.log`
2. 检查虚拟环境是否正常：`ls venv/bin/python`
3. 手动执行一次看报错：`venv/bin/python auto_run.py`

### Q: 爬虫抓取失败？

可能原因：
- 网络连接问题
- 番茄小说页面结构变更
- Playwright 浏览器未安装

解决：
```bash
source venv/bin/activate
playwright install chromium
```

### Q: 数据没有同步到其他设备？

1. 检查 iCloud Drive 是否开启
2. 确认该目录在 iCloud 同步范围内
3. 等待 iCloud 同步完成（可能需要几分钟）

### Q: 如何停止自动任务？

```bash
# 在 TRAE 中使用 Schedule 管理
/schedule list                  # 查看所有任务
/schedule delete <task-id>      # 删除指定任务
/schedule pause <task-id>       # 暂停指定任务
```

---

## 🔄 与原 GitHub 方案对比

| 特性 | 原 GitHub 方案 | 新 TRAE 本地方案 |
|------|---------------|------------------|
| 定时执行 | GitHub Actions | TRAE Schedule |
| 数据存储 | GitHub 仓库 | 本地 + iCloud |
| 访问方式 | GitHub Pages | 本地 HTTP 服务器 |
| 依赖 | Git + GitHub | 仅 Python 环境 |
| 网络要求 | 需要外网 | 只需访问番茄小说 |
| 同步方式 | Git 提交 | iCloud 自动同步 |

---

## 📝 更新日志

### 2026-07-30
- ✅ 移除所有 GitHub 相关依赖（git pull、commit 等）
- ✅ 创建 `auto_run.py` 自动化脚本，带日志和断点续跑
- ✅ 更新 `daily.sh`，纯本地运行
- ✅ 完善 `requirements.txt`，添加 openai 依赖
- ✅ 创建本使用指南文档

---

## 💡 小提示

1. **第一次运行**建议手动执行，确保虚拟环境和依赖都正常
2. **每天的数据**都会独立保存，不用担心覆盖问题
3. **AI 分析**是可选的，不配置也能正常运行（会自动使用规则摘要）
4. **查看历史数据**直接在浏览器中打开对应 HTML 文件即可
5. **多设备使用**只要都连接同一个 iCloud 账号，数据自动同步

---

有问题随时在 TRAE 中提问！😊
