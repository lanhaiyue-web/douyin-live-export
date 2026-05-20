# 给接手 Agent 看（Codex / Claude / 任何 LLM 都看这一份）

## 30 秒看懂这个项目

抖音直播复盘提取工具。输入：抖音直播服务平台的某场直播。输出：桌面单 sheet Excel，列固定为 `分钟 / 时间 / 在线人数 / 净进出 / 进入 / 离开 / 话术`，按净进出红绿白染色。

## 接手第一件事：跑通验证

```powershell
cd D:\AIProjects\my-first-peoject\抖音直播分析
python douyin_tool.py go --index 2     # 一条命令：检测登录 + 必要时扫码 + 刷场次 + 导出
```

`go` 会自己处理：没登录就弹窗等扫码，登录后自动 refresh + export。

如果输出 `ROWS=35 TEXT_ROWS=33 EXCEL=E:\桌面\...xlsx`，说明你跑通了。

分步命令（调试用）：
```powershell
python auth_browser.py status douyin-creator       # 看登录态
python douyin_tool.py sessions list --cache-only   # 看场次缓存
python douyin_tool.py export --index 2             # 直接导出（要求已登录 + 有缓存）
```

## 不要做的事（之前的人踩过的坑）

1. **不要把单 sheet Excel 改回多 sheet**。用户明确只要一张表。
2. **不要把 `page.evaluate("() => { location.reload(); }")` 改回 `page.reload()`**。抖音对 Playwright `page.reload()` 有反爬识别，复盘页返回空壳（body 163 字符，复盘内容完全不渲染）。改回去话术就拿不到。位置：[export_review_table.py](export_review_table.py)
3. **不要删 video checkpoint + React 虚拟列表慢滚逻辑**。这是长直播话术不漏尾部的关键。
4. **登录浏览器只用 Playwright 自带 Chromium + 持久 profile**。统一走 [auth_browser.py](auth_browser.py)：`launch_persistent_context(user_data_dir=".auth/<platform>")`、`headless=False`。不要回退到系统 Edge/Chrome + CDP 端口的老路径。
5. **每个平台一个固定 user-data-dir**：`.auth/douyin-creator/` / `.auth/kuaishou/` ……不要混用 profile，不要去动用户日常浏览器的 profile，不要 kill 用户的 msedge.exe / chrome.exe 进程。
6. **不要再引用 chrome_daemon / CDP_PORT / connect_over_cdp**。这个模块已经删了；新代码全部走 `auth_browser.launch_persistent`。
7. **不要主动 commit 代码**。用户没明确说要 commit。
8. **用户没指定要导哪一场时不要自己挑**。`python douyin_tool.py go` 不带 `--index / --room-id / --title-contains / --start-contains` 时，跑到列出场次就停下，提示用户下一步用 `export --index N`。**不要为了"走通流程"就默认导第 1 场或者上次导过的那一场**——这是 [cmd_go() 当前实现](douyin_tool.py)，别改回"默认值"。

## 项目文件导航

### 主流程（CLI，当前在用，必须维护）
| 你想做的事 | 看哪个文件 |
|---|---|
| CLI 统一入口 | [douyin_tool.py](douyin_tool.py)（含 `go` 一键流程） |
| 专用登录浏览器（多平台） | [auth_browser.py](auth_browser.py) |
| 近 30 场缓存 | [douyin_sessions.py](douyin_sessions.py) |
| 单场抓取 + 染色 Excel | [export_review_table.py](export_review_table.py) |
| 抖音接口适配器 | [sources/anchor.py](sources/anchor.py) |
| 统一数据契约 | [sources/base.py](sources/base.py) |

### Streamlit 看板（旁路，没人用，**不要在主流程里调它**）
- [app.py](app.py) / [analyzer.py](analyzer.py) / [excel_export.py](excel_export.py)
- 这是早期 Streamlit UI 路径，跟 CLI **完全独立的另一套实现**
- 当前没有维护、没在测试矩阵里。**改 CLI 时不要去同步改它**
- 用户决定**保留**作为未来做 UI 的参考。要真启用需要重写让它复用 CLI 的 `export_rows` / `default_out_path`，否则两套代码会持续 drift

### 文档
| 你想做的事 | 看哪个文件 |
|---|---|
| 一句话搞清做什么 | [README.md](README.md) |
| 跑通流程 / 故障排查 | [RUNBOOK.md](RUNBOOK.md) |
| 这个项目走到哪一步、还差什么 | [progress.md](progress.md) |
| 待办清单 | [tasks.md](tasks.md) |
| 长期方法论 / 浏览器优先级 / 选场次约束 | [memory.md](memory.md) |
| 历史 bug 和修复记录 | [bugs.md](bugs.md) |

## 换设备能用的保障

- `requirements.txt` 列了所有依赖，`pip install -r requirements.txt` 即可
- 必须跑一次 `playwright install chromium`（专用登录浏览器用的是 Playwright 自带 Chromium，跟系统 Edge/Chrome 物理隔离）
- 登录态首次扫码后保存在 `.auth/<platform>/`，cookie 不过期就一直有效
- 桌面路径用注册表读，不写死 `E:\桌面`

## 当前已验证

- 场次：`7640044495510866714`（2026-05-15 17:15:01 ~ 17:48:02 聊一聊AI自媒体）
- Excel：35 行 / 33 行话术 / 染色 OK
- 桌面：`E:\桌面\2026-05-15_聊一聊AI自媒体_流量话术复盘.xlsx`
