"""Session cache helpers for Douyin live replay.

The product flow is:
1. Keep one managed browser open and logged in.
2. Refresh the latest live-session list for the current logged-in account.
3. Select a session by index / room_id / title and export it.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from auth_browser import DEFAULT_PLATFORM, has_login_cookies, launch_persistent, resolve_platform
from sources.anchor import EP_HISTORY_LIST, REVIEW_URL, _parse_session, _unwrap
from sources.base import LiveSession

DATA_DIR = Path(__file__).parent / "data"
SESSION_CACHE_PATH = DATA_DIR / "sessions_cache.json"


def _dt_text(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _parse_dt(value: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return datetime.fromisoformat(value)


def session_to_dict(session: LiveSession, index: int | None = None) -> dict[str, Any]:
    data = {
        "room_id": session.session_id,
        "title": session.title,
        "start_time": _dt_text(session.start_time),
        "end_time": _dt_text(session.end_time),
        "duration_min": session.duration_min,
        "watch_ucnt": session.watch_ucnt,
        "cover_url": session.cover_url,
        "source": session.source,
        "raw": session.raw,
    }
    if index is not None:
        data["index"] = index
    return data


def session_from_dict(data: dict[str, Any]) -> LiveSession:
    return LiveSession(
        source=str(data.get("source") or "anchor.douyin.com"),
        session_id=str(data.get("room_id") or data.get("session_id") or ""),
        title=str(data.get("title") or "直播复盘"),
        start_time=_parse_dt(str(data.get("start_time"))),
        end_time=_parse_dt(str(data.get("end_time") or data.get("start_time"))),
        duration_min=int(data.get("duration_min") or 0),
        cover_url=str(data.get("cover_url") or ""),
        watch_ucnt=int(data.get("watch_ucnt") or 0),
        raw=data.get("raw") if isinstance(data.get("raw"), dict) else {},
    )


def _choose_page(context, room_id: str | None = None):
    pages = [pg for pg in context.pages if not pg.is_closed()]
    if room_id:
        for page in pages:
            if "anchor/review" in page.url and room_id in page.url:
                return page
    for page in pages:
        if "anchor/review" in page.url:
            return page
    if pages:
        return pages[0]
    return context.new_page()


def _dedupe_sessions(sessions: list[LiveSession], limit: int) -> list[LiveSession]:
    by_id: dict[str, LiveSession] = {}
    for session in sessions:
        if not session.session_id:
            continue
        old = by_id.get(session.session_id)
        if old is None or session.start_time > old.start_time:
            by_id[session.session_id] = session
    out = sorted(by_id.values(), key=lambda s: s.start_time, reverse=True)
    return out[:limit]


def refresh_sessions(
    limit: int = 30,
    wait_ms: int = 12_000,
    platform: str = DEFAULT_PLATFORM,
    auto_start: bool = False,  # 兼容旧 CLI 参数；新方案不再需要
) -> list[LiveSession]:
    """Refresh latest sessions for the account logged into the persistent profile."""
    del auto_start  # 保留参数签名兼容，不再使用

    spec = resolve_platform(platform)
    captured: list[LiveSession] = []

    with launch_persistent(spec) as context:
        if not has_login_cookies(context, spec):
            raise RuntimeError(
                f"持久 profile 未登录{spec.name_zh}。先跑：python auth_browser.py login {spec.key}"
            )
        page = _choose_page(context)

        def on_response(resp) -> None:
            if EP_HISTORY_LIST not in resp.url:
                return
            try:
                body = resp.json()
            except Exception:
                return
            data = _unwrap(body)
            series = data.get("series", []) if isinstance(data, dict) else []
            for item in series:
                if not isinstance(item, dict):
                    continue
                session = _parse_session(item)
                if session and session.session_id:
                    captured.append(session)

        page.on("response", on_response)
        page.goto(REVIEW_URL, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(wait_ms)
        if not captured:
            page.evaluate("() => { location.reload(); }")
            page.wait_for_timeout(min(wait_ms, 8_000))

    sessions = _dedupe_sessions(captured, limit)
    save_session_cache(sessions, limit=limit)
    return sessions


def save_session_cache(sessions: list[LiveSession], limit: int = 30) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": _dt_text(datetime.now()),
        "limit": limit,
        "platform": DEFAULT_PLATFORM,
        "sessions": [session_to_dict(session, i) for i, session in enumerate(sessions, start=1)],
    }
    SESSION_CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return SESSION_CACHE_PATH


def load_session_cache(path: Path = SESSION_CACHE_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"还没有场次缓存：{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    sessions = payload.get("sessions", [])
    if not isinstance(sessions, list):
        raise ValueError(f"场次缓存格式不对：{path}")
    return sessions


def select_cached_session(
    *,
    index: int | None = None,
    room_id: str | None = None,
    title_contains: str | None = None,
    start_contains: str | None = None,
    cache_path: Path = SESSION_CACHE_PATH,
) -> LiveSession:
    cached = load_session_cache(cache_path)

    matches = cached
    if index is not None:
        matches = [item for item in cached if int(item.get("index") or 0) == index]
    if room_id:
        matches = [item for item in matches if str(item.get("room_id") or "") == str(room_id)]
    if title_contains:
        matches = [item for item in matches if title_contains in str(item.get("title") or "")]
    if start_contains:
        matches = [item for item in matches if start_contains in str(item.get("start_time") or "")]

    if not matches:
        raise ValueError("没有在 sessions_cache.json 里找到匹配场次，请先刷新场次或换一个条件。")
    if len(matches) > 1 and index is None and not room_id:
        lines = "\n".join(format_cached_session(item) for item in matches[:10])
        raise ValueError(f"匹配到多场，请加 --index 或 --room-id：\n{lines}")
    return session_from_dict(matches[0])


def format_cached_session(item: dict[str, Any]) -> str:
    idx = item.get("index", "?")
    title = item.get("title") or "直播复盘"
    start = item.get("start_time") or ""
    duration = item.get("duration_min") or 0
    watch = item.get("watch_ucnt") or 0
    room_id = item.get("room_id") or ""
    return f"{idx:>2}. {start} | {duration:>3}分钟 | 观看{watch:>5} | {room_id} | {title}"


def format_session_list(items: list[dict[str, Any]]) -> str:
    return "\n".join(format_cached_session(item) for item in items)
