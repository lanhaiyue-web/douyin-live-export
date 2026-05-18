# Claude Code Handoff

Read [RUNBOOK.md](RUNBOOK.md) first. Current stable workflow:

```powershell
python douyin_tool.py browser start              # 启动托管浏览器（首次扫码登录）
python douyin_tool.py sessions refresh --limit 30
python douyin_tool.py sessions list --cache-only
python douyin_tool.py export --index 2
```

## Hard constraints

1. **不要改回多 sheet Excel**。只要一张表：`分钟 / 时间 / 在线人数 / 净进出 / 进入 / 离开 / 话术`。
2. **不要改回 `page.reload()`**。必须用 `page.evaluate("() => { location.reload(); }")`，否则抖音反爬把复盘页变空壳。[export_review_table.py:454](export_review_table.py#L454)
3. **不要删 video checkpoint + 虚拟列表慢滚逻辑**。长直播尾部话术全靠它。
4. **浏览器优先 Edge**（Windows 默认）。`chrome_daemon.find_browser()` 已经先读 HKCU UserChoice 取系统默认浏览器。不要再加 `Chrome` 优先的逻辑。
5. **托管浏览器 user_data 用 `data/user_data/`**（项目独立），不要去动用户日常浏览器的 profile，不要 kill 用户的 msedge 进程。
