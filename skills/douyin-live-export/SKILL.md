---
name: douyin-live-export
description: 从抖音直播服务平台导出某场直播的「分钟流量 × 主播话术」染色 Excel 到桌面。触发词：「抖音直播复盘」/「导出抖音直播 Excel」/「抖音直播话术」/「直播流量染色」/「douyin live export」/「我要分析我的抖音直播」。第一次跑会启动用户的默认浏览器让他扫码登录抖音直播服务平台。
argument-hint: [—— 可选: --index N / --room-id X / --title-contains TEXT / --start-contains TEXT]
allowed-tools: Bash(*), Read, Write, Edit, AskUserQuestion, Glob, Grep
---

# /douyin-live-export — 抖音直播复盘 Excel 一键导出

## 这工具做什么

输入：用户在抖音直播服务平台「直播复盘」里能看到的某一场直播。
输出：桌面单 sheet Excel `<日期>_<场次标题>_流量话术复盘.xlsx`，列固定为：

```
分钟 / 时间 / 在线人数 / 净进出 / 进入 / 离开 / 话术
```

- `净进出 > 0` → 整行绿色（涨人）
- `净进出 < 0` → 整行红色（掉人）
- `净进出 = 0` → 白色
- `话术` 列放同一分钟主播说的所有话（带时间戳）

## 标准流程（按这个走，不要自己想路径）

### Phase 0 — 定位项目根

Plugin 安装后，项目代码在这个 SKILL.md 的**爷爷目录**（含 `douyin_tool.py` 的目录）。用 Glob 或 Bash 自动定位：

```bash
# 假设 SKILL.md 在 ~/.claude/plugins/douyin-live-export/<...>/skills/douyin-live-export/SKILL.md
# 那么项目根 = SKILL.md 的爷爷目录的爷爷目录
# 用 Glob 找一下 douyin_tool.py 在哪
```

用 Glob 模式 `**/douyin_tool.py` 找到项目根，然后所有命令都在那里跑。

### Phase 1 — 检查依赖

```bash
cd <项目根>
python -c "import playwright, pandas, openpyxl" 2>&1
```

如果报 ModuleNotFoundError：
```bash
pip install -r requirements.txt
```

**不需要** `playwright install`——工具复用本机 Edge / Chrome，不用 Playwright bundled chromium。

### Phase 2 — 一键跑通

跑 `go` 子命令（**它自己会做**所有事：启浏览器、等扫码登录、刷场次、列出来停下）：

```bash
cd <项目根>
python douyin_tool.py go
```

观察输出，会按 `[N/4]` 打进度：
- `[1/4]` 检查托管浏览器（没起就启系统默认浏览器，Windows 默认是 Edge）
- `[2/4]` 检测登录态（cookies 没种上就轮询等用户扫码，最多 10 分钟）
- `[3/4]` 刷新近 30 场缓存 → **列出场次表**
- `[4/4]` 没指定场次 → 停下来

### Phase 3 — 让用户选场次

**关键约束**：用户没明确指定要导哪一场时，**不要自己挑**。把场次表列出来，问用户「要导哪一场？告诉我序号」。

格式示例：

```
我看到这 N 场：
1. 2026-XX-XX HH:MM | NN分钟 | 观看 N | <roomID> | <标题>
2. ...
要导哪一场？告诉我序号（1-N）。
```

### Phase 4 — 导出

拿到用户回复的 N 后：

```bash
cd <项目根>
python douyin_tool.py export --index <N>
```

输出会有：
```
EXCEL=<桌面路径>\<日期>_<标题>_流量话术复盘.xlsx
ROWS=<行数>
TEXT_ROWS=<有话术的行数>
```

把这三个值告诉用户，让他直接打开桌面 Excel。

## 不要做的事（之前踩过的坑）

1. **不要把单 sheet Excel 改回多 sheet**。
2. **不要把 `page.evaluate("() => { location.reload(); }")` 改回 `page.reload()`**。抖音对 Playwright CDP `page.reload()` 有反爬识别，复盘页会变空壳。文件位置：项目根的 `export_review_table.py` 的 `capture_review_page()`。
3. **不要默认导第 1 场或上次导过的那一场**。用户没说就停在 Phase 3 等。
4. **不要 kill 用户日常浏览器进程**（msedge.exe / chrome.exe）。项目用独立的 `data/user_data/`（在项目根），跟用户日常浏览器物理隔离。
5. **不要主动 commit 代码**，除非用户明确说。

## 故障排查

| 症状 | 原因 | 解决 |
|---|---|---|
| `CDP 端口 9222 没有托管浏览器` | daemon 没起 | `python douyin_tool.py browser start` |
| 浏览器弹出但抖音页空白 | 反爬没绕过 | 确认代码没改回 `page.reload()` |
| `没有捕获到 minute_trend` | navigate 后没等够 | 重跑一次 |
| 卡在 `[2/4] 等待扫码` 超过 10 分钟 | 用户没真的扫码 | 提示用户：在弹出的浏览器里扫码登录抖音直播服务平台 |
| 话术列空 | 复盘页 DOM 没渲染完 | 多等几秒重跑 export |

## 完整接手文档（深入修改时看）

项目根有完整文档：
1. `README.md` — 一句话原理 + 用法
2. `AGENTS.md` — LLM 接手必看，含「不要做的事」
3. `RUNBOOK.md` — 故障排查
4. `progress.md` / `bugs.md` — 历史踩坑 + 修复

主要代码：`douyin_tool.py` → `chrome_daemon.py` / `export_review_table.py`
