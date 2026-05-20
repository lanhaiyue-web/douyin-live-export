# Claude Code Handoff

Read [RUNBOOK.md](RUNBOOK.md) first. Current stable workflow:

```powershell
python auth_browser.py login douyin-creator      # 首次：弹窗扫码，登录态写入 .auth/douyin-creator/
python douyin_tool.py sessions refresh --limit 30
python douyin_tool.py sessions list --cache-only
python douyin_tool.py export --index 2
```

## Hard constraints

1. **不要改回多 sheet Excel**。只要一张表：`分钟 / 时间 / 在线人数 / 净进出 / 进入 / 离开 / 话术`。
2. **不要改回 `page.reload()`**。必须用 `page.evaluate("() => { location.reload(); }")`，否则抖音反爬把复盘页变空壳。
3. **不要删 video checkpoint + 虚拟列表慢滚逻辑**。长直播尾部话术全靠它。
4. **登录用 Playwright 自带 Chromium + 持久 profile**。统一走 [auth_browser.py](auth_browser.py)：`launch_persistent_context(user_data_dir=".auth/<platform>")`，`headless=False`，不连系统 Edge/Chrome，不开 CDP 端口。
5. **每个平台一个固定的 user-data-dir**：`.auth/douyin-creator/` / `.auth/kuaishou/` ……不要把多个平台塞到同一个 profile，不要去动用户日常浏览器的 profile。
6. **不要再引用 chrome_daemon / CDP_PORT / connect_over_cdp**。旧的托管浏览器方案已废弃；新代码全部走 `auth_browser.launch_persistent`。
