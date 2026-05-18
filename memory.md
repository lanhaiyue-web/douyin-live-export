# 长期方法论 / 规则

## 核心技术原理：为什么这工具能碾压 RPA（影刀/扣子）
- **RPA 路线**：模拟鼠标点击 + OCR 截图，UI 上没画的数据它一概拿不到
- **本工具路线**：Playwright + **XHR 响应拦截**。前端从抖音后台请求的数据 JSON 包含完整字段，UI 只渲染了一部分（比如曲线只画 2 条，但响应里有 4 条；UI 只显示近 7 日，但响应里能带近 30 日参数）。我们直接读响应 JSON，绕开 UI 渲染层
- 结论：**任何"前端展示是后端数据的子集"的场景，浏览器自动化 + 抓包都比 RPA 更强**

## 关于"会不会封号"的判定标准
- **登录自己的后台 + 做自己每天会做的操作（看复盘）= 风险约等于自己开浏览器**
- **登录别人/批量账号 + 高频读取陌生数据 = 高危**
- 自动化是否被风控关键看：行为指纹（频率、UA、设备 ID）、是否触发 webdriver detection
- 缓解方式：`storage_state` 持久化登录态、Playwright 启动加 `--disable-blink-features=AutomationControlled`、非高频访问、保留真实 UA

## 染色算法
- 阈值 = `全场平均在线人数 × threshold_ratio`（默认 `0.1`）
- 净进出（这一分钟在线 - 上一分钟在线） ≥ +阈值 → 绿
- 净进出 ≤ -阈值 → 红
- 中间 → 白
- 阈值用比例而不是绝对值，是因为大场（4000 人）和小场（100 人）的"正常波动幅度"不一样

## 抖音网页版直播复盘的 UI 结构（人工导航路径）
```
anchor.douyin.com/anchor/review
└── 直播复盘
    └── 选场次（history_list 接口列出）
        ├── 趋势明细：营收 / 流量 / 互动指标 / 粉丝（4 个 tab）← 全部对应 minute_trend 接口的不同字段
        ├── 内容分析（这一块是产品核心）
        │   ├── 回放视频（左侧）
        │   ├── 文字记录 ← 主播口播转文字，整个工具的灵魂
        │   ├── PK 玩法
        │   ├── 关键片段
        │   ├── 违规片段
        │   └── 回溯录制片段
        ├── 互动 / 礼物 / 商品 / 粉丝...
        └── AI 复盘建议（replay_recommend/metric_name 接口）
```
**重要：低活跃账号显示"开播时间过短未生成回放内容"**——文字记录功能存在但要求开播时长达到阈值。开发时要假设它有数据，等用户切换到活跃账号就能跑。

## 抖音后台 URL 对照（容易搞混，记死）
- `creator.douyin.com` —— **创作者中心**（短视频数据为主，**没有**直播复盘菜单）
- `anchor.douyin.com/anchor/review` —— **直播服务中心**（直播复盘、流量曲线、话术在这里，**v1.0 主入口**）
- `buyin.jinritemai.com` —— **巨量百应**（带货主播专属）
- `compass.jinritemai.com` —— **抖店罗盘**（抖店商家专属）
- 直播伴侣 —— PC 桌面 App，单独攻
- 登录 cookie 在 `.douyin.com` 域共享 → 登一次 creator，anchor 自动是登录态

## 多数据源架构（卖给别人必须做到）
统一数据契约 + 插件化数据源适配器：
```
LiveSession / MinuteData / TranscriptSegment  ← 统一数据结构
DataSource (抽象)
├── AnchorSource          # 直播服务中心（v0.1 主攻）
├── BuyinSource           # 巨量百应
├── CompassSource         # 抖店罗盘
├── LivePartnerSource     # 直播伴侣（桌面 App，读本地缓存）
└── ManualUploadSource    # 上传 Excel 兜底，永远不被反爬影响
```
analyzer / app 层不知道数据来自哪个源。
手机 App 后台 = 网页版同源后端，**不单独做手机抓取**。

## 浏览器反爬关键
- 抖音 anchor / creator / passport 会用 `navigator.webdriver` 等指纹识别 Playwright Chromium → 触发"系统繁忙"
- 唯一稳定方案：`channel="chrome"` 调用本机真实 Chrome（不用 Playwright bundled chromium）+ `add_init_script` 抹掉指纹 + `launch_persistent_context` 持久化用户目录
- 登录态用 user_data_dir 持久化，不用 storage_state.json

## 模块边界
- `login.py`：弹浏览器登录，持久化用户目录
- `crawler.py`：拦截 XHR，分两个模式 —— 侦察模式（记日志）/ 抓取模式（按已知接口取数据）
- `analyzer.py`：纯函数，输入约定结构，输出染色行 + Claude 总结
- `app.py`：只做展示和编排
- → 每个模块独立测试，crawler 改不影响 analyzer

## 项目目标定位（避免做歪）
- 不是飞瓜蝉妈妈那种"全量数据看板"，是"AI 句子级复盘教练"
- 卖点不是"数据多"，是"看完就知道明天怎么改"
- 永远把"对齐 + 染色 + 总结"这三件事做到极致，其他功能先不加

## 浏览器优先级（产品级硬约束）
- **Edge 必须跑通**，是第一优先级。原因：Edge 是 Windows 自带浏览器，目标用户（普通主播）不会装 Chrome
- 不要默认走 Chrome / 不要为了好测试就启 chrome_daemon；用户桌面那只 Edge 是真实交付场景
- 任何接入路径（CDP / 扩展 / 调试口）都先在 Edge 上验通，再考虑兼容其他 Chromium
- 用户已经明确否决过用托管 Chrome 替代他自己的 Edge 这条路径
