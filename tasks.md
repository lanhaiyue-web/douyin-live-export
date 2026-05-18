# 任务清单

## 已交付（v1.0 跑通 + 整理打包）

- [x] 单场提取：`python douyin_tool.py export --index N` → 桌面单 sheet Excel
- [x] 输出列：`分钟 / 时间 / 在线人数 / 净进出 / 进入 / 离开 / 话术`
- [x] 染色：净进出正绿、负红、零白
- [x] 长直播话术不漏尾部：video checkpoint + React 虚拟列表慢滚
- [x] 反爬 fix：`page.evaluate("location.reload()")` 绕过抖音 CDP `page.reload()` 指纹检测
- [x] 托管浏览器自动选系统默认浏览器（Edge 优先）
- [x] 项目整理打包：删 11 个一次性脚本 + 整个 browser_connector + 30+ 调试文件
- [x] 文档完善：README / RUNBOOK / AGENTS / CLAUDE / progress / memory 全部对齐当前实现
- [x] requirements.txt + .gitignore 完整
- [x] 端到端验证：场次 7640044495510866714，35 行流量 + 33 行话术 + 染色

## 长期方向（按需做）

- [ ] 把 `douyin_tool.py export` 接进 Streamlit UI 的导出按钮（让非命令行用户也能用）
- [ ] 多账号支持：环境变量切换 `data/user_data_<name>/`
- [ ] 接入巨量百应（buyin.jinritemai.com）数据源
- [ ] 接入抖店罗盘（compass.jinritemai.com）数据源
- [ ] 接入直播伴侣 PC 端（读本地缓存）
- [ ] PyInstaller 打独立 exe，独立站 + 支付码
- [ ] Whisper 录屏转录兜底（应对抖音改话术接口的极端情况）

## 用户已确认的关键决策

- 输出固定单 sheet 7 列，不要多 sheet 指标表
- 话术兜底优先抓抖音原生接口，Whisper 是 plan B
- 数据源先做 anchor.douyin.com，后续加百应/罗盘/直播伴侣
- 浏览器优先 Edge（Windows 自带，目标用户默认就是这个）
- Excel 保存到桌面（注册表自动检测真实路径）
- 商业化方向：自己用 + 卖给主播 SaaS
