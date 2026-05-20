# 抖音直播分析工具运行手册

接手用：登录态全部走 Playwright 持久化 profile，每个平台一个目录，不动用户日常浏览器。

## 固定流程

**一条命令版**（推荐）：
```powershell
cd D:\AIProjects\my-first-peoject\抖音直播分析
python douyin_tool.py go --index 2
```
`go` 自动按 3 步走：检测登录态 → 没登录就弹窗等扫码 → refresh 场次 → export。

**分步版**（调试 / 手动控制时用）：
```powershell
python auth_browser.py login douyin-creator          # 首次：扫码登录，写入 .auth/douyin-creator/
python auth_browser.py status douyin-creator         # 检查登录态是否还有效
python douyin_tool.py sessions refresh --limit 30    # 刷新近 30 场
python douyin_tool.py sessions list --cache-only     # 列场次
python douyin_tool.py export --index 2               # 导出
```

`auth_browser.py` 也提供等价子命令 `python douyin_tool.py auth login|status|open|list`。

首次扫码登录后，登录态永久保存到 `.auth/<platform>/`，下次不用再扫。Cookie 过期再跑一次 `auth login` 即可。

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

## 登录浏览器（专用登录浏览器）

- 实现：Playwright 自带 Chromium + `launch_persistent_context`
- profile 根目录：`.auth/`
- 每个平台一个固定 user-data-dir：
  - `.auth/douyin-creator/` 抖音直播服务平台
  - `.auth/kuaishou/`       快手直播伙伴（已留位，未启用抓取）
- 默认 `headless=False`：登录窗口必须可见，用户能扫码
- 没有 daemon 进程、没有 CDP 端口；每次需要时 `launch_persistent` 启动一次，用完关掉
- 平台扩展：编辑 [auth_browser.py](auth_browser.py) 的 `PLATFORMS` 字典加一项即可

## 关键实现

- [auth_browser.py](auth_browser.py)：专用登录浏览器，多平台 persistent context
- [douyin_sessions.py](douyin_sessions.py)：读当前账号近 30 场，缓存到 `data/sessions_cache.json`
- [export_review_table.py](export_review_table.py)：单场抓取流量 + 话术 + 导出
- [douyin_tool.py](douyin_tool.py)：统一 CLI 入口

## 反爬关键 fix（重要）

抖音对 Playwright CDP 协议的 `page.reload()` 有指纹识别，复盘页会返回空壳（只剩顶部导航 + 底部备案，body 163 字符）。

**修复**：[export_review_table.py](export_review_table.py) 用 `page.evaluate("() => { location.reload(); }")` 在页面主环境触发 reload。改完之后 body 立刻恢复完整（2224 字符），复盘内容正常渲染。

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
