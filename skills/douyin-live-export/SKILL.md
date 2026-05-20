---
name: douyin-live-export
description: 从抖音直播服务平台导出某场直播的「分钟流量 × 主播话术」染色 Excel 到桌面。触发词：「抖音直播复盘」/「导出抖音直播 Excel」/「抖音直播话术」/「直播流量染色」/「douyin live export」/「我要分析我的抖音直播」。第一次跑会弹一个专用登录浏览器（Playwright 自带 Chromium）让用户扫码登录抖音直播服务平台。
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

Plugin 安装后，项目代码在这个 SKILL.md 的**爷爷目录**（含 `douyin_tool.py` 的目录）。用 Glob 找：

```bash
# 用 Glob 模式 **/douyin_tool.py 找项目根，然后所有命令都在那里跑
```

### Phase 1 — 检查依赖

```bash
cd <项目根>
python -c "import playwright, pandas, openpyxl" 2>&1
```

如果报 ModuleNotFoundError：
```bash
pip install -r requirements.txt
```

**必须**跑一次 `playwright install chromium`——专用登录浏览器用的是 Playwright 自带 Chromium 内核，跟系统 Edge/Chrome 物理隔离。

```bash
playwright install chromium
```

### Phase 2 — 一键跑通

跑 `go` 子命令（**它自己会做**所有事：检测登录、必要时弹窗扫码、刷场次、列出来停下）：

```bash
cd <项目根>
python douyin_tool.py go
```

观察输出，会按 `[N/3]` 打进度：
- `[1/3]` 检测登录态（cookies 没种上就弹专用登录浏览器，最多 10 分钟等扫码）
- `[2/3]` 刷新近 30 场缓存 → **列出场次表**
- `[3/3]` 没指定场次 → 停下来

首次登录后，登录态写入项目根的 `.auth/douyin-creator/`，下次自动复用（cookie 不过期就一直免登录）。

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
2. **不要把 `page.evaluate("() => { location.reload(); }")` 改回 `page.reload()`**。抖音对 Playwright `page.reload()` 有反爬识别，复盘页会变空壳。文件位置：项目根的 `export_review_table.py` 的 `capture_review_page()`。
3. **不要默认导第 1 场或上次导过的那一场**。用户没说就停在 Phase 3 等。
4. **不要回退到系统 Edge / Chrome + CDP 端口的老登录路径**。统一走 `auth_browser.launch_persistent`，profile 在项目根的 `.auth/<platform>/`，跟用户日常浏览器物理隔离。
5. **不要主动 commit 代码**，除非用户明确说。

## 故障排查

| 症状 | 原因 | 解决 |
|---|---|---|
| `Executable doesn't exist` (Playwright) | 没装 Chromium 内核 | `playwright install chromium` |
| `持久 profile 未登录抖音直播服务平台` | `.auth/douyin-creator/` 里 cookie 没了 | `python auth_browser.py login douyin-creator` 重新扫码 |
| 浏览器弹出但抖音页空白 | 反爬没绕过 | 确认代码没改回 `page.reload()` |
| `没有捕获到 minute_trend` | navigate 后没等够 | 重跑一次 |
| 卡在 `[1/3] 等待扫码` 超过 10 分钟 | 用户没真的扫码 | 提示用户：在弹出的窗口里扫码登录抖音直播服务平台 |
| 话术列空 | 复盘页 DOM 没渲染完 | 多等几秒重跑 export |

## 完整接手文档（深入修改时看）

项目根有完整文档：
1. `README.md` — 一句话原理 + 用法
2. `AGENTS.md` — LLM 接手必看，含「不要做的事」
3. `RUNBOOK.md` — 故障排查
4. `progress.md` / `bugs.md` — 历史踩坑 + 修复

主要代码：`douyin_tool.py` → `auth_browser.py` / `export_review_table.py`
