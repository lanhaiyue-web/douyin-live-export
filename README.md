# 抖音直播复盘分析

按分钟对齐「流量曲线 × 主播话术」，红绿染色，一键导出 Excel 到桌面。

## 🚀 一键安装（Claude Code Plugin Marketplace）

在你的 Claude Code 里贴这三行：

```bash
claude plugin marketplace add lanhaiyue-web/douyin-live-export
claude plugin install douyin-live-export@douyin-live-export
/reload-plugins
```

装好后输入 `/douyin-live-export` 触发，工具会自动：
1. 启动你的默认浏览器
2. 让你扫码登录抖音直播服务平台（仅首次）
3. 列出你近 30 场直播
4. 你告诉它要导哪一场 → Excel 自动出在桌面

---

**如果不用 Claude Code，纯命令行也行**：

```powershell
git clone https://github.com/lanhaiyue-web/douyin-live-export.git
cd douyin-live-export
pip install -r requirements.txt
python douyin_tool.py go                  # 启动浏览器 → 扫码 → 列场次
python douyin_tool.py export --index N    # 导第 N 场
```

LLM 接手请先看 [AGENTS.md](AGENTS.md)。

## 它做什么

输入：抖音直播服务平台 → 直播复盘 → 某一场直播
输出：桌面 Excel，一张表，列固定为

```
分钟 / 时间 / 在线人数 / 净进出 / 进入 / 离开 / 话术
```

- `净进出 > 0` → 整行绿色（这一分钟人在涨）
- `净进出 < 0` → 整行红色（人在跌）
- `净进出 = 0` → 白色
- `话术` 列放同一分钟主播说的所有话（带时间戳）

## 工作原理

- 自动启动你电脑的**默认浏览器**（Windows 上一般是 Edge），带远程调试端口
- 你在弹出的浏览器里**扫码登录抖音直播服务平台**（仅首次）
- 登录态持久保存在 `data/user_data/`，下次直接用
- 工具通过浏览器调试接口拦截 `anchor.douyin.com` 的后台 XHR 响应（不构造请求，所以抖音改签名也不影响）
- 拿到 `minute_trend` 流量曲线 + 复盘页 DOM 上的文字记录 → 按分钟对齐 → 染色 → 写 Excel

## 换设备的 onboarding（首次安装）

```powershell
# 1. clone 项目，进入目录
cd D:\AIProjects\my-first-peoject\抖音直播分析

# 2. 建虚拟环境 + 装依赖
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. 第一次启动托管浏览器（会自动选系统默认浏览器，通常是 Edge）
python douyin_tool.py browser start
# → 浏览器弹出 → 扫码登录抖音直播服务平台 → 登录态永久保存到 data/user_data/
```

不需要 `playwright install`——工具复用本机已有的 Edge / Chrome，不用 Playwright 自带的 chromium。

## 日常使用

### 一条命令（推荐）

```powershell
# 不知道要哪一场 → 跑这条，等扫码 + 自动刷场次 + 列出来让你选
python douyin_tool.py go

# 已经知道要哪一场 → 一条命令到底
python douyin_tool.py go --index 2
python douyin_tool.py go --room-id <你的 room_id>
python douyin_tool.py go --title-contains "聊一聊AI"
python douyin_tool.py go --start-contains "2026-05-15 17:15"
```

`go` 内部按 4 步走，每一步都会打 `[N/4]` 进度：
1. 检查托管浏览器（没起就启）
2. 检测登录态（没登录就轮询等你扫码，最多 10 分钟）
3. 刷新近 30 场缓存，列出场次表
4. 按你指定的 `--index / --room-id / --title-contains / --start-contains` 导出 Excel

### 分步命令（要手动控制时用）

```powershell
python douyin_tool.py browser start                # 只启动浏览器
python douyin_tool.py sessions refresh --limit 30  # 只刷场次缓存
python douyin_tool.py sessions list --cache-only   # 只看缓存
python douyin_tool.py export --index 2             # 只导出
```

Excel 自动保存到桌面，文件名形如：`2026-05-15_聊一聊AI自媒体_流量话术复盘.xlsx`

## 换账号

在托管浏览器里退出当前抖音账号 → 重新扫码登录 → 跑 `python douyin_tool.py sessions refresh`。不需要重装。

## 项目结构

```
抖音直播分析/
├── douyin_tool.py          # 统一 CLI 入口（browser / sessions / export）
├── chrome_daemon.py        # 托管浏览器（自动识别 Windows 默认浏览器，Edge 优先）
├── douyin_sessions.py      # 近 30 场缓存（写入 data/sessions_cache.json）
├── export_review_table.py  # 单场抓取：流量 + 话术 + 染色 Excel
├── excel_export.py         # Excel 导出（染色、桌面路径自动检测）
├── analyzer.py             # 对齐 + 染色 + AI 总结（被 app.py 用）
├── app.py                  # Streamlit 看板（可选 UI 入口）
├── sources/
│   ├── base.py             # 统一数据契约（LiveSession / MinuteData / TranscriptSegment）
│   ├── anchor.py           # anchor.douyin.com 适配器
│   └── manual.py           # 上传 Excel/CSV 兜底
├── requirements.txt
├── README.md / RUNBOOK.md
├── progress.md / tasks.md / memory.md / bugs.md   # 项目四件套
└── data/                   # 运行时数据（gitignored）
    ├── user_data/          # 浏览器持久化登录 profile
    └── sessions_cache.json # 近 30 场缓存
```

## 关键技术点

- **浏览器选择**：`chrome_daemon.find_browser()` 先读 Windows 注册表拿用户当前默认浏览器（`HKCU\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice`），找不到再按 Edge / Chrome / Brave / 360 / QQ 顺序回退
- **反反爬**：`page.reload()`（Playwright CDP 协议）会被抖音识别成自动化指纹，复盘页返回空壳。`export_review_table.py:454` 改用 `page.evaluate("location.reload()")` 在主环境触发 reload，复盘内容正常渲染
- **登录态隔离**：`data/user_data/` 是项目独立的浏览器 profile，跟你日常用的 Edge 不互相干扰
- **接口签名**：不构造请求只拦响应，抖音改 `a_bogus` / `msToken` 等签名算法不影响

## 分发给别人怎么用（跨设备 / 跨账号）

这个项目自带 Claude Code skill（`.claude/skills/douyin-live-export/SKILL.md`），别人拿到项目代码后**直接在项目根开 Claude Code，skill 自动加载**，可以用 `/douyin-live-export` 触发。

### 你（项目所有者）分发流程

1. **打包项目**（去掉登录态）：
   ```powershell
   cd D:\AIProjects\my-first-peoject\抖音直播分析
   python douyin_tool.py browser stop
   Remove-Item -Recurse -Force data\user_data, data\sessions_cache.json, data\chrome_daemon.pid -ErrorAction SilentlyContinue
   Compress-Archive -Path .\* -DestinationPath "$env:USERPROFILE\Desktop\douyin-live-export.zip" -Force
   ```
   生成的 zip 已不含你的抖音账号 cookies / 场次缓存，可以放心发给别人。

2. 把 zip 发给对方（U盘 / 邮件 / 云盘 / 微信都行）。

### 对方（接收者）使用流程

第一次：
```powershell
# 1. 解压 zip 到任意目录，比如：
Expand-Archive .\douyin-live-export.zip -DestinationPath D:\douyin-live-export

# 2. 装依赖
cd D:\douyin-live-export
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. 在项目根开 Claude Code（cd 进项目目录后输入 claude），告诉 AI：
#    /douyin-live-export
# AI 会自动按 SKILL.md 指引走全流程
```

或者**直接命令行**（不靠 LLM，自己跑）：
```powershell
python douyin_tool.py go           # 启浏览器 → 扫码登录 → 列场次
python douyin_tool.py export --index N
```

### 给对方的「一段话指令」（让他贴到 Claude Code / Codex）

```
我在 D:\douyin-live-export（路径自己改）有一个抖音直播复盘提取工具。
请帮我跑 /douyin-live-export，按场次列表让我选一场，导出 Excel 到桌面。
```

或更直接（无需 skill，纯指令）：
```
请进入目录 D:\douyin-live-export，先 pip install -r requirements.txt，
然后跑 python douyin_tool.py go，列出场次后让我选一场，
再跑 python douyin_tool.py export --index <我选的号> 导出。
```

## Streamlit 看板（旁路，没在维护）

`app.py` / `analyzer.py` / `excel_export.py` 是早期 Streamlit UI 路径，**跟 CLI 是完全独立的两套代码**。当前没在用、没在测，留作以后做 UI 的参考。

如果哪天真要做 UI，推荐把 app.py 改造成调用 `douyin_tool` / `export_review_table` 的逻辑，**不要继续维护两套并行实现**。

## 商业化 / 多账号

- 自用：以上即可
- 卖给主播：扩展 `sources/` 加多源（百应 / 抖店罗盘 / 直播伴侣），打包成 exe，独立站售卖
- 多账号：每个账号一份独立 `data/user_data_<name>/`，启动时 `DOUYIN_USER_DATA_DIR` 环境变量切换（待加）

## 故障排查

| 症状 | 原因 | 解决 |
|---|---|---|
| 启动浏览器后 CDP 30 秒没就绪 | 端口 9222 被占 | 关掉占端口的进程，或改环境变量 `DOUYIN_CDP_PORT` |
| 抖音页显示「系统繁忙」 | 抖音识别到自动化 | 换账号、等几小时；持久化 user_data 通常能避免 |
| 拉不到场次 | 登录态过期 | 在托管浏览器里重新扫码 |
| `当前页面没有读到开播时间` | 复盘页被反爬变空壳 | 已修：`export_review_table.py:454` 强制走 `location.reload()`，无需手动处理 |

更多接手说明、决策历史、踩坑记录看 [RUNBOOK.md](RUNBOOK.md) / [progress.md](progress.md) / [bugs.md](bugs.md) / [memory.md](memory.md)。
