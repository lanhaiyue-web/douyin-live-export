# 已知问题与修复记录

## 待验证风险
- 抖音网页版直播服务中心的"文字记录"接口路径**未知**——用户当前账号开播时长不够，前端直接显示"开播时间过短未生成回放内容"，没发请求。等有数据的账号上再侦察一次（5 分钟就能搞定）
- 持久化 Chrome profile + 反指纹脚本若仍被风控（极端情况下出现滑块/手机验证）→ 没有完美方案，只能换抖音号或等几小时再试

## 已修复
- 2026-05-18：`page.reload()`（Playwright CDP）触发抖音前端反自动化指纹，复盘页返回空壳（只剩导航/备案，body 163 字符，复盘内容完全不渲染）→ 改成 `page.evaluate("() => { location.reload(); }")` 在主环境调用，body 立刻完整（2224 字符）。文件位置：[export_review_table.py:454-457](export_review_table.py#L454)。**没修这个之前，话术怎么都拿不到**


- 2026-05-16：扫码登录页报"系统繁忙，请重启应用或刷新页面后重试" → 抖音检测到 Playwright Chromium 自动化指纹。改用 `channel="chrome"` 调用本机真实 Chrome + `add_init_script` 覆盖 `navigator.webdriver` / `languages` / `plugins` / `window.chrome` 等指纹 → 反爬绕过
- 2026-05-16：`page.goto` 默认 30s 超时不够抖音首页加载 → 改 `wait_until="domcontentloaded"` + `timeout=90000` + try/except 容忍超时
- 2026-05-16：原始用 `storage_state.json` 保存登录态在抖音上不够稳 → 升级为持久化用户目录 `user_data/`，行为模式跟真实 Chrome 一致
- 2026-05-16：`login.py` 字符串里嵌套双引号导致 SyntaxError → 外层改单引号
- 2026-05-16：登录检测**误报**——把 `passport_csrf_token` 当成登录指标，但这 cookie 任何抖音页都会种 → 移除该 cookie，改为 `sessionid` / `sessionid_ss` / `sid_tt` / `sid_guard` / `uid_tt` 任一存在，**并加 URL 必须离开 login/passport 页**才算登录成功
- 2026-05-16：Chrome 弹出后被其他窗口挡住，用户找不到 → 加 `page.bring_to_front()` 强制弹到最前面 + 终端打印明显提示

## 跑过但有趣的细节
- crawler.py 拦截 XHR 时同一接口可能出现在多个 URL（如 `webcast/data/...` 和 `anchor_pc_tinker_proxy/...` 是抖音两套后端代理，返回相同数据但 URL 路径不同）→ AnchorSource 用 `in url` 匹配关键路径片段，两套都能命中
- 抖音前端把 `minute_trend` 返回的 4 维数据**拆成 4 个 tab**（营收/流量/互动指标/粉丝），但一次请求就返回全量 → 我们读 JSON 比手动切 tab 快得多
- 抖音直播服务中心的"文字记录"在低活跃账号上是**前端直接 disable**（连请求都不发），不是返回空数据 → 想侦察必须用真活跃的号
- `analyze_log.py` / `diff_log.py` / `peek_schema.py` 这三个是一次性侦察脚本，下次有新账号侦察时直接复用
