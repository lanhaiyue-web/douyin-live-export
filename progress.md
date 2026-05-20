# 进度

## 当前阶段
**登录态架构已切到 Playwright persistent context（2026-05-20）**：删除 chrome_daemon.py / CDP 端口路径，新增 [auth_browser.py](auth_browser.py)，每个平台一个固定 user-data-dir（`.auth/douyin-creator/`、`.auth/kuaishou/`），浏览器内核统一用 Playwright 自带 Chromium，登录窗口默认 `headless=False`。`douyin_sessions.py` / `export_review_table.py` / `sources/anchor.py` / `douyin_tool.py` 全部改用 `auth_browser.launch_persistent`。

`douyin_tool.py` CLI：`browser` 子命令换成 `auth`（login / status / open / list）。`go` 流程从 4 步缩到 3 步。

**红绿流量 × 话术单表导出已跑通**。当前最可靠入口是 `export_review_table.py`，输出 Claude Code 之前做过的那种单 sheet Excel。

当前已验证场次：
- roomId：`7640044495510866714`
- 标题：`聊一聊AI自媒体`
- 时间：`2026-05-15 17:15:01` 到 `2026-05-15 17:48:02`
- 流量行：35 行
- 文字记录：91 条
- 对齐后有话术行：29 行

## 项目目标
按虾笔刀刀那条抖音视频复刻：自动抓取**自己的**抖音直播复盘数据 → 按分钟把"流量曲线 × 主播话术"对齐 → 涨人段染绿、掉人段染红、平稳段白 → Claude 出复盘建议 → 导出 Excel 到桌面。

最终目标做成 SaaS 卖给主播。

## 文件结构（13 个核心文件 + data/）
```
抖音直播分析/
├── login.py              # Playwright + 真 Chrome 登录抖音直播服务中心，持久化 user_data
├── crawler.py            # 侦察模式：拦截 XHR 写入 xhr_log.jsonl（供分析接口结构）
├── analyzer.py           # 对齐+染色+Claude 总结，用 sources.base 统一契约
├── excel_export.py       # 导出 Excel 到 Windows 桌面（自动检测真实桌面路径）
├── app.py                # Streamlit 看板，整合上面所有模块
├── sources/
│   ├── __init__.py
│   ├── base.py           # LiveSession / MinuteData / TranscriptSegment + DataSource 抽象
│   ├── anchor.py         # AnchorSource：anchor.douyin.com 适配器（拦响应方式，免处理 msToken/a_bogus 签名）
│   └── manual.py         # ManualUploadSource：上传 Excel/CSV 兜底
├── analyze_log.py        # 一次性脚本：按主题分类侦察日志
├── diff_log.py           # 一次性脚本：对比两轮侦察找新接口
├── peek_schema.py        # 一次性脚本：扒接口完整响应体看 schema
├── requirements.txt      # streamlit, playwright, pandas, anthropic, openpyxl
├── progress.md / tasks.md / memory.md / bugs.md   # 项目四件套
└── data/                 # 运行时数据（gitignored）
    ├── user_data/        # Chrome 持久化登录 profile
    ├── xhr_log.jsonl     # 侦察日志
    └── xhr_log_round1.jsonl  # 第一轮侦察备份
```

## 已侦察到的关键接口（anchor.douyin.com 直播服务中心）
| 接口 | 用途 | 状态 |
|---|---|---|
| `webcast/data/.../room/replay/history_list` | 直播场次列表 | ✅ AnchorSource 已实现 |
| `anchor_pc_tinker_proxy/.../room/replay/minute_trend` | 分钟级 4 维曲线（在线/进出/互动/营收等） | ✅ AnchorSource 已实现 |
| `anchor_pc_tinker_proxy/.../room/replay/common_traffic_conversion` | 进出人数 + 变化率 | ✅ 字段已知，可扩展 |
| `anchor_pc_tinker_proxy/.../room/replay/room_base_v2` | 单场基础信息 | ✅ 字段已知 |
| `webcast_api/room/replay_recommend/metric_name` | **抖音自带 AI 复盘推荐**（可白嫖） | ✅ 字段已知，可扩展 |
| 话术 / 文字记录 | 直播复盘 → 内容分析 → 文字记录 tab | ⚠️ 用户账号没数据，前端没发请求，**API 路径未知**——等有数据的账号再侦察 |

## 跟下次接手的人（包括 Codex）说
1. **本项目的核心技术原理**在 `memory.md`，先读它
2. **怎么跑**：见 README.md 的 4 步流程
3. **接手的第一件事**：用户手里有真实复盘数据的账号后，**重跑 crawler.py** 侦察"内容分析→文字记录"页面，把话术接口 URL + 响应 schema 找出来，填入 `sources/anchor.py` 的 `fetch_transcript()` 方法
4. **不要重写**已有结构。统一数据契约（`sources/base.py`）已经设计好，新数据源只是加一个 source 文件继承 `DataSource`

## 现在应该怎么跑

如果浏览器已经打开在目标直播复盘页：

```powershell
cd D:\AIProjects\my-first-peoject\抖音直播分析
python export_review_table.py --current-page --reload
```

这条命令不会新开/关闭浏览器或标签，只连接 `chrome_daemon.py` 的现有 Chrome，并刷新当前复盘页一次捕获流量接口。输出是一张单 sheet Excel：

`分钟 / 时间 / 在线人数 / 净进出 / 进入 / 离开 / 话术`

颜色规则：`净进出 > 0` 绿色，`净进出 < 0` 红色，`净进出 = 0` 白色。

## 还差什么
- ⚠️ 话术抓取：等用户提供有数据的账号侦察后实现
- ⚠️ 端到端实测：等用户用有数据的账号跑通整条链路
- 可选优化：Whisper 录屏转录（作为话术兜底方案）
- 可选打包：PyInstaller 打成独立 exe
- 可选商业化：独立站 + 支付码（虾笔刀刀视频里说他用 Claude Code 写了，所有思路在 memory.md）

## 2026-05-17 更新

已把流程升级为可售卖版本的基础形态：

- `chrome_daemon.py` 改成托管浏览器：自动识别 Chrome / Edge / Brave / Chromium，登录态固定在 `data/user_data`。
- `douyin_sessions.py` 新增近 30 场缓存：当前登录账号刷新后写入 `data/sessions_cache.json`。
- `douyin_tool.py` 新增统一入口：`browser / sessions / export`。
- `export_review_table.py` 去掉固定 room_id，支持 `--index`、`--room-id`、`--title-contains`。
- 文字记录修复长直播漏尾部：React 虚拟列表慢滚 + video 进度检查点分段采集。

当前真实验证：

- 场次：`7640044495510866714`
- 时间：`2026-05-15 17:15:01` 到 `2026-05-15 17:48:02`
- Excel：单 sheet，35 行，7 列
- 有话术分钟：33 行
- 已确认 17:45、17:46、17:47、17:48 的话术都进入表格
- 桌面文件：`E:\桌面\2026-05-15_聊一聊AI自媒体_流量话术复盘_完整版.xlsx`

## 2026-05-18 更新（Edge 连接器路径）

**强约束**：用户桌面的 Edge 是真实交付环境，不要再启 chrome_daemon 替代（详见 memory.md「浏览器优先级」）。

**已修通**：
- `browser_connector` 在 Edge 上跑通流量抓取。Codex 时期的 5 个 bug 全修：
  - 删手拼 minute_trend URL（永远 403，签名走不通）
  - reload 由 `chrome.tabs.reload` 走（`Page.reload` CDP 在 Edge 触发 target_closed → debugger 直接 detach）
  - `chrome.debugger.onDetach` 加自动 re-attach（Edge 在 navigation 时常 target_closed）
  - `Network.setCacheDisabled` + frameNavigated 重 enable 兜底
  - server.py 加 `/diagnose` + `event_counts` + 事件流 dump
- 验证场次：`7640044495510866714`（2026-05-15 17:15 聊一聊AI自媒体）
- 桌面 Excel：`E:\桌面\2026-05-15_聊一聊AI自媒体_流量话术复盘.xlsx`，35 行流量染色全 OK

**未修通**：话术列全空。原因不是接口签名/解析，是 **content.js 主动 fetch transcript 窗口的代码没在 Edge 里加载到**（events.jsonl 看不到 `transcript_done` 事件，说明扩展跑的还是旧版）。

**话术修复怎么续**：
- 已实测：content.js 在 reload 之后第 2 次进入 runExtraction 后，**Edge 会把抖音 tab 后台冻结**，setInterval 死掉（events.jsonl 里 19:35:44 之后 200+ 秒无 heartbeat，但 background.js debugger 仍在收事件）。fetchTranscriptWindows 因此根本没机会运行。
- transcript 接口需要 cookies / referer 校验（无 cookies 直接 fetch 返回 403 `100004 请求域名非法`）

**已交付的兜底方案**：`python browser_connector\server.py fix_transcript --index 2`
- 用户唯一要做：关闭 Edge 所有窗口（msedge.exe 进程也要退）。脚本自动等待 cookies 文件解锁（最多 120 秒）
- 自动流程：读 Edge cookies → DPAPI 解密 master key → AES-GCM 解密每个 cookie → requests 按分钟窗口循环 fetch 33 个 transcript 接口 → 合并到 rooms/xxx.json → 重生成 Excel
- 依赖：`pycryptodome`（已装）
- 实现位置：[browser_connector/server.py](browser_connector/server.py) 的 `_read_edge_cookies_for_douyin` / `_build_edge_cookie_decrypter` / `_fetch_transcript_windows` / `fix_transcript_command`

**长期最优解**（避免每次都要关 Edge）：在 background.js 加 `force_transcript` 命令处理 + 用 `chrome.debugger.sendCommand("Network.getAllCookies")` 拿 cookies → server.py 远程触发 → 完全不依赖 content.js 不依赖关浏览器。要做这个必须扩展重载一次（写好后用户**仅这一次**重载）。

## 2026-05-18 二次更新（真·跑通话术 33 行）

**最终走通路径**：Edge 重启时加 `--remote-debugging-port=9222 --user-data-dir="%LocalAppData%\Microsoft\Edge\User Data"`（复用用户真实 profile，登录态在），跑 `python export_review_table.py --current-page --reload`。

**关键的 bug fix**：[export_review_table.py:454-457](export_review_table.py#L454) — 把 `page.reload()`（CDP 协议）改成 `page.evaluate("() => { location.reload(); }")`（主环境调用）。

**为什么必须改**：抖音 review 复盘页能检测 CDP `page.reload()` 触发的自动化指纹，返回空壳页（只剩顶部导航 + 底部备案，body 只有 163 字符，复盘内容完全不渲染）。改成 location.reload 走主环境后，body 2224 字符完整。

**最终验证**：
- 桌面 Excel：`E:\桌面\2026-05-15_聊一聊AI自媒体_流量话术复盘.xlsx`
- 35 行流量 + 33 行话术 + 染色全 OK
- 17:18 起话术：「这怎么开播没有自然流啊不对呀」「不对呀 嗯嗯嗯嗯」「欢迎新进直播间的」...
- 跟 HANDOFF 文档之前跑通的 33 行话术完全对得上

## 2026-05-18 三次更新（打包整理 + 换设备可跑）

**用户决策变更**：放弃「kill 用户 Edge → 用他真实 profile 加 9222 启动」这条老路径（破坏用户日常浏览器体验）。回到 **chrome_daemon 托管浏览器** + **项目独立 user_data** 路径，但 `find_browser()` 现在**优先选系统默认浏览器**（Windows 一般是 Edge），这是符合用户「自动打开默认浏览器登录」诉求的最稳实现。

**做了的整理**：
- 删了 11 个一次性脚本（analyze_log / diff_log / peek_schema / probe_transcript / debug_anchor / crawler / login / refresh_session / auto_run + 3 个临时 _grab/_probe/_try）
- 删了整个 `browser_connector/` 目录（扩展路径实验失败，路径思路保留在前面历史段落）
- 清了 30+ 个 data/ 调试垃圾（verify_*.xlsx / debug*.txt / xhr_log*.jsonl / *_probe.json / connector/）
- 删了过时文档 AGENTS / HANDOFF / CONNECTOR_RUNBOOK 旧版本
- 新增 [chrome_daemon._detect_windows_default_browser()](chrome_daemon.py)：读 HKCU UserChoice 拿系统默认浏览器
- 重写 [README.md](README.md) / [RUNBOOK.md](RUNBOOK.md) / [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md)（Codex 友好入口）
- 完善 [requirements.txt](requirements.txt) / [.gitignore](.gitignore)

**最终验证（chrome_daemon 路径）**：
```powershell
python douyin_tool.py browser start --minimized   # 自动开 Edge（系统默认），扫码登录到 data/user_data/
python douyin_tool.py sessions refresh --limit 30  # 5 场全列出
python douyin_tool.py export --index 2             # ROWS=35 TEXT_ROWS=33
```

**下次接手第一件事**：看 [AGENTS.md](AGENTS.md)（30 秒读完），跑上面三条命令验证。

## 完整流程（用户随时调取用）

```powershell
cd D:\AIProjects\my-first-peoject\抖音直播分析
python douyin_tool.py browser start            # 第一次会扫码登录
python douyin_tool.py sessions refresh --limit 30
python douyin_tool.py export --index 2
```
