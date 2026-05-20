"""抖音直播服务中心（anchor.douyin.com）数据源。

实现策略：用持久化登录的真实 Chrome 打开复盘页，
让前端自己发请求（自动带 msToken / a_bogus 签名），
我们用 Playwright 的 response 监听器拦截 JSON 响应。

零加密参数处理 → 抖音改签名算法也不影响我们。
"""
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from urllib.parse import parse_qs, urlencode, urlparse

from playwright.async_api import async_playwright

from .base import DataSource, LiveSession, MinuteData, TranscriptSegment

DATA_DIR = Path(__file__).parent.parent / "data"
AUTH_ROOT = Path(__file__).parent.parent / ".auth"
USER_DATA_DIR = AUTH_ROOT / "douyin-creator"
COOKIES_FILE = DATA_DIR / "cookies.json"

REVIEW_URL = "https://anchor.douyin.com/anchor/review"

# 接口路径片段（用 in 匹配，URL 里带签名参数无所谓）
EP_HISTORY_LIST = "room/replay/history_list"
EP_MINUTE_TREND = "room/replay/minute_trend"
EP_TRAFFIC_CONV = "room/replay/common_traffic_conversion"
EP_ROOM_BASE = "room/replay/room_base_v2"
EP_TRANSCRIPT = "room/detail/room_stats_content_list"  # type=1 是文字记录
MINUTE_TREND_URL = (
    "https://anchor.douyin.com/anchor_pc_tinker_proxy/lego/native/"
    "webcast_api/room/replay/minute_trend"
)
TRANSCRIPT_URL = (
    "https://anchor.douyin.com/anchor_pc_tinker_proxy/lego/native/"
    "webcast_api/room/detail/room_stats_content_list"
)


async def _inject_cookies(context) -> None:
    """显式注入 cookies.json（对抗会话级 cookie 丢失）。"""
    if not COOKIES_FILE.exists():
        return
    try:
        cookies = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
        await context.add_cookies(cookies)
    except Exception as e:
        print(f"[warn] cookies.json 注入失败：{e}")


async def _launch_context(playwright, headless: bool):
    """启动持久化登录 Chromium（Playwright 自带内核，profile 在 .auth/douyin-creator）。"""
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        headless=headless,
        viewport=None,
        no_viewport=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=IsolateOrigins,site-per-process",
            "--lang=zh-CN",
        ],
        ignore_default_args=["--enable-automation"],
        locale="zh-CN",
    )
    await _inject_cookies(context)
    return context


async def _open_context(playwright, headless: bool):
    """启动持久化 Chromium，返回 (context, owned_context=True)。

    新方案没有 daemon/CDP；每次调用都自己拥有 context，用完关掉即可。
    """
    return await _launch_context(playwright, headless=headless), True


async def _cleanup_context(context, page, owned_context: bool) -> None:
    """关闭自有 context。"""
    try:
        if owned_context:
            await context.close()
        elif page:
            await page.close()
    except Exception:
        pass


def _unwrap(resp_json: dict) -> dict:
    """抖音返回的 JSON 有两种嵌套形式，统一展平到能取 series 的层。"""
    if "data" in resp_json and isinstance(resp_json["data"], dict):
        inner = resp_json["data"]
        if "data" in inner and isinstance(inner["data"], str):
            try:
                inner = json.loads(inner["data"])
            except Exception:
                pass
        if isinstance(inner, dict) and "data" in inner and isinstance(inner["data"], dict):
            return inner["data"]
        return inner
    return resp_json


def _parse_session(d: dict) -> Optional[LiveSession]:
    """从 history_list 的 series 元素解析出 LiveSession。"""
    try:
        start_unix = int(d.get("startTimeUnix") or d.get("createTimeUnix") or 0)
        end_unix = int(d.get("endTimeUnix") or 0)
        start = datetime.fromtimestamp(start_unix) if start_unix else datetime.now()
        end = datetime.fromtimestamp(end_unix) if end_unix else start
        duration = max(0, int((end - start).total_seconds() // 60))
        return LiveSession(
            source="anchor.douyin.com",
            session_id=str(d.get("roomID", "")),
            title=str(d.get("roomTitle", "")),
            start_time=start,
            end_time=end,
            duration_min=duration,
            cover_url=str(d.get("coverURL") or d.get("coverUri") or ""),
            watch_ucnt=int(d.get("serverWatchUcntTdDirect") or 0),
            raw=d,
        )
    except Exception:
        return None


def _parse_minute(d: dict, idx: int, prev_online: int) -> MinuteData:
    """从 minute_trend 的 series 元素解析出 MinuteData。"""
    online = int(d.get("watchUcnt") or 0)
    leave = int(d.get("leaveUcnt") or 0)
    # 推算这一分钟新进入：在线变化 + 离开 = 进入
    enter = max(0, (online - prev_online) + leave)
    ts_str = d.get("timeMinute", "")
    try:
        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        ts = datetime.now()
    return MinuteData(
        minute_index=idx,
        timestamp=ts,
        online=online,
        enter=enter,
        leave=leave,
        comments=int(d.get("commentUcnt") or 0),
        likes=int(d.get("likeCnt") or 0),
        shares=int(d.get("shareCnt") or 0),
        gifts=int(d.get("giftNum") or 0),
        follows=int(d.get("followUcnt") or 0),
        raw=d,
    )


def _parse_time(value, fallback: datetime) -> datetime:
    """兼容抖音接口里多种时间字段形态。"""
    if value in (None, ""):
        return fallback
    if isinstance(value, (int, float)):
        # 10 位秒级 / 13 位毫秒级时间戳
        seconds = value / 1000 if value > 10_000_000_000 else value
        try:
            return datetime.fromtimestamp(seconds)
        except Exception:
            return fallback
    text = str(value).strip()
    if text.isdigit():
        return _parse_time(int(text), fallback)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%H:%M:%S", "%H:%M"):
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt.startswith("%H"):
                return fallback.replace(hour=parsed.hour, minute=parsed.minute, second=parsed.second)
            return parsed
        except ValueError:
            continue
    return fallback


def _first_text(d: dict) -> str:
    """从未知 schema 的文字记录项里尽量取出话术文本。"""
    text_keys = (
        "text", "content", "speak_text", "speakText", "speech_text", "speechText",
        "asr_text", "asrText", "sentence", "words", "msg", "message", "comment",
    )
    for key in text_keys:
        value = d.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for value in d.values():
        if isinstance(value, dict):
            nested = _first_text(value)
            if nested:
                return nested
    return ""


def _parse_transcript_response(
    body_json: dict,
    session_start: datetime,
    fallback_time: Optional[datetime] = None,
) -> List[TranscriptSegment]:
    """从 room_stats_content_list 响应解析文字记录。

    目前已侦察到端点，但真实账号返回过空 series，所以这里按多字段名容错解析。
    """
    data = _unwrap(body_json)
    series = data.get("series", []) if isinstance(data, dict) else []
    segs: List[TranscriptSegment] = []
    fallback_time = fallback_time or session_start
    for i, d in enumerate(series):
        if not isinstance(d, dict):
            continue
        text = _first_text(d)
        if not text:
            continue
        ts = _parse_time(
            d.get("time")
            or d.get("timeMinute")
            or d.get("contentTime")
            or d.get("content_time")
            or d.get("createTime")
            or d.get("create_time")
            or d.get("startTime")
            or d.get("start_time")
            or d.get("timestamp")
            or d.get("ts"),
            fallback_time,
        )
        minute_index = max(0, int((ts - session_start).total_seconds() // 60))
        # 如果接口只给相对 offset，也兼容一下。
        for key in ("minute", "minuteIndex", "minute_index"):
            if key in d:
                try:
                    minute_index = max(0, int(d[key]))
                    break
                except Exception:
                    pass
        if "offset" in d:
            try:
                minute_index = max(0, int(float(d["offset"]) // 60))
            except Exception:
                pass
        segs.append(TranscriptSegment(
            minute_index=minute_index,
            timestamp=ts,
            text=text,
            source="anchor",
        ))
    return segs


def _transcript_fallback_time(url: str, session_start: datetime) -> datetime:
    try:
        qs = parse_qs(urlparse(url).query)
        start_value = (qs.get("startTime") or qs.get("start_time") or [None])[0]
        return _parse_time(start_value, session_start)
    except Exception:
        return session_start


def _is_transcript_url(url: str) -> bool:
    """文字记录是 roomStatsContentType=1；同端点的 2/4 是其他内容分析子类。"""
    if EP_TRANSCRIPT not in url:
        return False
    try:
        qs = parse_qs(urlparse(url).query)
        content_type = (qs.get("roomStatsContentType") or ["1"])[0]
        return str(content_type) == "1"
    except Exception:
        return True


def _dedupe_transcript(segs: List[TranscriptSegment]) -> List[TranscriptSegment]:
    seen = set()
    out: List[TranscriptSegment] = []
    for seg in sorted(segs, key=lambda x: (x.minute_index, x.timestamp, x.text)):
        key = (seg.minute_index, seg.text)
        if key in seen:
            continue
        seen.add(key)
        out.append(seg)
    return out


def _transcript_url(session: LiveSession, start: datetime, end: datetime) -> str:
    params = {
        "roomID": session.session_id,
        "roomStatsContentType": 1,
        "startTime": start.strftime("%Y-%m-%d %H:%M:%S"),
        "endTime": end.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return f"{TRANSCRIPT_URL}?{urlencode(params)}"


def _minute_trend_url(session: LiveSession) -> str:
    params = {
        "roomID": session.session_id,
        # 侦察日志里 minute_trend 的稳定组件 id；缺它时部分账号会只触发局部窗口。
        "cid": "d2nc8ubc77u8uot7jfe0",
        "commonParams": "{}",
    }
    return f"{MINUTE_TREND_URL}?{urlencode(params)}"


def _merge_minute_series(traffic_by_minute: dict, body_json: dict) -> None:
    data = _unwrap(body_json)
    series = data.get("series", []) if isinstance(data, dict) else []
    for d in series:
        if not isinstance(d, dict):
            continue
        tm = d.get("timeMinute")
        if not tm:
            continue
        if tm not in traffic_by_minute:
            traffic_by_minute[tm] = d
        else:
            # 不同 tab/批次会补不同字段；保留已有非空值，补齐空字段。
            for k, v in d.items():
                if traffic_by_minute[tm].get(k) in ("0", 0, "", None):
                    traffic_by_minute[tm][k] = v


class AnchorSource(DataSource):
    name = "anchor.douyin.com"

    def __init__(self, headless: bool = False, timeout: int = 60):
        # headless=True 会被抖音风控识别 → 服务器端失效 sessionid，必须 False
        self.headless = headless
        self.timeout = timeout

    # ---------- 同步入口（Streamlit 用） ----------

    def list_sessions(self, days: int = 30) -> List[LiveSession]:
        return asyncio.run(self._list_sessions_async(days))

    def fetch_traffic(self, session: LiveSession) -> List[MinuteData]:
        return asyncio.run(self._fetch_traffic_async(session))

    def fetch_transcript(self, session: LiveSession) -> List[TranscriptSegment]:
        return asyncio.run(self._fetch_transcript_async(session))

    # ---------- 异步实现 ----------

    async def _list_sessions_async(self, days: int) -> List[LiveSession]:
        sessions: List[LiveSession] = []
        result_event = asyncio.Event()

        async with async_playwright() as p:
            context, owned_context = await _open_context(p, headless=self.headless)
            page = await context.new_page()

            async def on_response(resp):
                if EP_HISTORY_LIST in resp.url and not result_event.is_set():
                    try:
                        body = await resp.json()
                    except Exception:
                        return
                    data = _unwrap(body)
                    series = data.get("series", []) if isinstance(data, dict) else []
                    for d in series:
                        s = _parse_session(d)
                        if s and s.session_id:
                            sessions.append(s)
                    if series is not None:
                        result_event.set()

            page.on("response", on_response)
            await page.goto(REVIEW_URL, wait_until="domcontentloaded", timeout=90000)

            try:
                await asyncio.wait_for(result_event.wait(), timeout=self.timeout)
            except asyncio.TimeoutError:
                pass

            await _cleanup_context(context, page, owned_context)

        # 按时间倒序，取最近 days 天的
        cutoff = datetime.now() - timedelta(days=days)
        sessions = [s for s in sessions if s.start_time >= cutoff]
        sessions.sort(key=lambda s: s.start_time, reverse=True)
        return sessions

    async def _fetch_traffic_async(self, session: LiveSession) -> List[MinuteData]:
        traffic_by_minute: dict = {}
        data_event = asyncio.Event()

        async with async_playwright() as p:
            context, owned_context = await _open_context(p, headless=self.headless)
            page = await context.new_page()

            async def on_response(resp):
                if EP_MINUTE_TREND in resp.url:
                    try:
                        body = await resp.json()
                    except Exception:
                        return
                    _merge_minute_series(traffic_by_minute, body)
                    if traffic_by_minute:
                        data_event.set()

            page.on("response", on_response)
            # 直接打开这场复盘
            replay_url = f"{REVIEW_URL}?type=0&roomId={session.session_id}"
            await page.goto(replay_url, wait_until="domcontentloaded", timeout=90000)

            # 直接请求已知完整分钟趋势端点，避免前端只触发视频局部时间窗。
            try:
                body_text = await page.evaluate(
                    """async (url) => {
                        const resp = await fetch(url, {credentials: 'include'});
                        return await resp.text();
                    }""",
                    _minute_trend_url(session),
                )
                if body_text:
                    _merge_minute_series(traffic_by_minute, json.loads(body_text))
                    if traffic_by_minute:
                        data_event.set()
            except Exception:
                pass

            try:
                await asyncio.wait_for(data_event.wait(), timeout=min(12, self.timeout))
            except asyncio.TimeoutError:
                pass

            # 抖音会把同一个 minute_trend 拆给多个 tab/局部时间窗；主动切 tab 让前端补发请求。
            for label in ("营收", "互动指标", "粉丝", "流量"):
                try:
                    el = await page.wait_for_selector(f"text={label}", timeout=2000)
                    if el:
                        await el.click()
                        await asyncio.sleep(2)
                except Exception:
                    pass

            # 给最后一批 XHR 一点落地时间。
            await asyncio.sleep(2)

            await _cleanup_context(context, page, owned_context)

        rows: List[MinuteData] = []
        prev_online = 0
        for idx, (_, d) in enumerate(sorted(traffic_by_minute.items(), key=lambda x: x[0])):
            m = _parse_minute(d, idx, prev_online)
            prev_online = m.online
            rows.append(m)
        return rows

    async def _fetch_transcript_async(self, session: LiveSession) -> List[TranscriptSegment]:
        segs: List[TranscriptSegment] = []
        passive_event = asyncio.Event()

        async with async_playwright() as p:
            context, owned_context = await _open_context(p, headless=self.headless)
            page = await context.new_page()

            async def on_response(resp):
                if not _is_transcript_url(resp.url):
                    return
                try:
                    body = await resp.json()
                except Exception:
                    return
                parsed = _parse_transcript_response(
                    body,
                    session.start_time,
                    fallback_time=_transcript_fallback_time(resp.url, session.start_time),
                )
                if parsed:
                    segs.extend(parsed)
                    passive_event.set()

            page.on("response", on_response)
            replay_url = f"{REVIEW_URL}?type=0&roomId={session.session_id}"
            await page.goto(replay_url, wait_until="domcontentloaded", timeout=90000)

            # 先等前端自己触发文字记录接口；它会携带正确的时间窗。
            start = session.start_time
            end = session.end_time if session.end_time > start else start + timedelta(minutes=max(session.duration_min, 1))
            try:
                await asyncio.wait_for(passive_event.wait(), timeout=min(8, self.timeout))
            except asyncio.TimeoutError:
                pass

            # 前端没触发时，按 1 分钟窗口补抓；响应无时间字段时用窗口 startTime 对齐。
            if not segs:
                cursor = start
                max_chunks = 360
                chunks = 0
                while cursor < end and chunks < max_chunks:
                    chunk_end = min(cursor + timedelta(minutes=1), end)
                    url = _transcript_url(session, cursor, chunk_end)
                    try:
                        body_text = await page.evaluate(
                            """async (url) => {
                                const resp = await fetch(url, {credentials: 'include'});
                                return await resp.text();
                            }""",
                            url,
                        )
                        if body_text:
                            segs.extend(_parse_transcript_response(
                                json.loads(body_text),
                                session.start_time,
                                fallback_time=cursor,
                            ))
                    except Exception:
                        pass
                    cursor = chunk_end
                    chunks += 1

            # 直接请求仍为空时，尝试点前端 tab 触发同一接口，给未来页面改版留兜底。
            if not segs:
                for label in ("内容分析", "文字记录"):
                    try:
                        el = await page.wait_for_selector(f"text={label}", timeout=4000)
                        if el:
                            await el.click()
                            await asyncio.sleep(1)
                    except Exception:
                        pass
                try:
                    await asyncio.wait_for(passive_event.wait(), timeout=min(10, self.timeout))
                except asyncio.TimeoutError:
                    pass

            await _cleanup_context(context, page, owned_context)

        return _dedupe_transcript(segs)
