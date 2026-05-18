# 抖音直播分析工具运行手册

接手用：所有脚本只走本项目的托管浏览器（项目独立 `data/user_data/`），不动用户日常浏览器。

## 固定流程

**一条命令版**（推荐）：
```powershell
cd D:\AIProjects\my-first-peoject\抖音直播分析
python douyin_tool.py go --index 2
```
`go` 自动按 4 步走：检查浏览器 → 检测登录（轮询 cookies，未登录就等扫码）→ refresh 场次 → export。

**分步版**（调试 / 手动控制时用）：
```powershell
python douyin_tool.py browser start                # 启动托管浏览器
python douyin_tool.py sessions refresh --limit 30  # 刷新近 30 场
python douyin_tool.py sessions list --cache-only   # 列场次
python douyin_tool.py export --index 2             # 导出
```

首次扫码登录后，登录态永久保存到 `data/user_data/`，下次不用再扫。

## 输出格式

只导出一个 sheet：`直播复盘`。列固定：

```
分钟 / 时间 / 在线人数 / 净进出 / 进入 / 离开 / 话术
```

染色：
- `净进出 > 0` → 整行绿色（涨人）
- `净进出 < 0` → 整行红色（掉人）
- `净进出 = 0` → 白色

**不要改回多 sheet 表格。** 用户已经明确要求只要这一张。

## 浏览器选择优先级

`chrome_daemon.find_browser()` 顺序：

1. 环境变量 `DOUYIN_BROWSER_PATH`（手动指定）
2. Windows 注册表读 HKCU UserChoice（系统当前默认浏览器）
3. `BROWSER_CANDIDATES` 列表：Edge → Chrome → Brave → Chromium → 360 → QQ

把 Edge 放第一是产品决策：目标用户（普通主播）默认浏览器就是 Windows 自带的 Edge，详见 [memory.md](memory.md) 「浏览器优先级」。

## 关键实现

- `chrome_daemon.py`：托管浏览器；环境变量 `DOUYIN_BROWSER_PATH`、`DOUYIN_CDP_PORT` 可覆盖
- `douyin_sessions.py`：读当前账号近 30 场，缓存到 `data/sessions_cache.json`
- `export_review_table.py`：单场抓取流量 + 话术 + 导出
- `douyin_tool.py`：统一 CLI 入口

## 反爬关键 fix（重要）

抖音对 Playwright CDP 协议的 `page.reload()` 有指纹识别，复盘页会返回空壳（只剩顶部导航 + 底部备案，body 163 字符）。

**修复**：[export_review_table.py:454](export_review_table.py#L454) 用 `page.evaluate("() => { location.reload(); }")` 在页面主环境触发 reload。改完之后 body 立刻恢复完整（2224 字符），复盘内容正常渲染。

**不要回退**这个 fix —— 改回 `page.reload()` 就拿不到话术。

## 文字记录不要再漏尾部

抖音「文字记录」列表跟回放 video 进度联动。`export_review_table.py` 已经做了两层处理：

- React 虚拟列表慢速重叠滚动，避免滚太快漏
- 尾部话术离关播时间太远时，自动把回放 video 跳到 20 分钟 / 尾部等 checkpoint，再次滚动采集并去重

这套逻辑支撑几小时长直播，不要删。

## 当前已验证场次

- room_id：`7640044495510866714`
- 标题：`聊一聊AI自媒体`
- 时间：`2026-05-15 17:15:01` ~ `2026-05-15 17:48:02`
- Excel：35 行 / 33 行有话术
- 桌面文件：`E:\桌面\2026-05-15_聊一聊AI自媒体_流量话术复盘.xlsx`

## 换设备 onboarding 详见 [README.md](README.md)
