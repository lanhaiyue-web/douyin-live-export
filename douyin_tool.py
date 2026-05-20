"""One-command CLI for the Douyin live analysis workflow."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from auth_browser import (
    DEFAULT_PLATFORM,
    is_logged_in,
    list_platforms,
    login_window,
    open_window,
    status as auth_status,
)
from douyin_sessions import (
    SESSION_CACHE_PATH,
    format_session_list,
    load_session_cache,
    refresh_sessions,
    select_cached_session,
)
from export_review_table import (
    capture_review_page,
    default_out_path,
    export_rows,
    load_rows_json,
)


def print_sessions(refresh: bool, limit: int, auto_start: bool = False, cache_only: bool = False) -> None:
    del auto_start  # 兼容旧签名，新方案不再使用
    if refresh and not cache_only:
        refresh_sessions(limit=limit)
    items = load_session_cache()
    print(f"CACHE={SESSION_CACHE_PATH}")
    print(format_session_list(items))


def cmd_go(args) -> None:
    """一条命令完成全部：检查登录 → 必要时弹窗扫码 → refresh → export。

    每个步骤都用持久 profile 启动一次 Chromium；窗口短暂可见，关掉自动继续。
    """
    print(f"[1/3] 检测 {DEFAULT_PLATFORM} 登录态...")
    if is_logged_in(DEFAULT_PLATFORM):
        print("    ✓ 已登录")
    else:
        print(f"    ⏳ 当前 profile 没登录，弹出窗口扫码（最长等 {args.wait_login_sec}s）")
        ok = login_window(DEFAULT_PLATFORM, timeout_sec=args.wait_login_sec)
        if not ok:
            raise SystemExit(
                f"等了 {args.wait_login_sec}s 没检测到登录。退出。\n"
                "重跑：python douyin_tool.py go --index N"
            )

    print("[2/3] 刷新近 30 场直播缓存...")
    refresh_sessions(limit=args.limit)
    items = load_session_cache()
    print(format_session_list(items))

    has_selector = any([args.index, args.room_id, args.title_contains, args.start_contains])
    if not has_selector:
        print("\n[3/3] 没指定要导哪一场。下一步：")
        print("  python douyin_tool.py export --index N")
        print("  (N 是上面列表里的序号)")
        return

    print("[3/3] 导出指定场次...")
    cmd_export(args)


def cmd_export(args) -> None:
    meta = {"title": "直播复盘", "start_time": ""}
    if args.rows_json:
        rows = load_rows_json(args.rows_json)
        title = args.rows_json.stem.replace("_flow_transcript_rows", "")
    else:
        session = None
        if args.index or args.title_contains or args.start_contains:
            if args.refresh_sessions or not SESSION_CACHE_PATH.exists():
                refresh_sessions(limit=args.limit)
            session = select_cached_session(
                index=args.index,
                title_contains=args.title_contains,
                start_contains=args.start_contains,
            )
            room_id = session.session_id
        elif args.room_id:
            room_id = args.room_id
            if SESSION_CACHE_PATH.exists():
                try:
                    session = select_cached_session(room_id=room_id)
                except Exception:
                    session = None
        else:
            raise SystemExit("导出必须指定 --index / --room-id / --title-contains / --rows-json 之一")

        meta, rows = capture_review_page(
            room_id=room_id,
            session=session,
            reload_page=not args.no_reload,
            navigate=True,
        )
        title = meta.get("title") or (session.title if session else "直播复盘")
        if meta.get("room_id"):
            raw_path = Path("data") / f"{meta['room_id']}_flow_transcript_rows.json"
            raw_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"ROWS_JSON={raw_path}")

    out = args.out or default_out_path(meta, title)
    saved = export_rows(rows, out)
    filled = sum(1 for row in rows if str(row.get("话术") or "").strip())
    print(f"EXCEL={saved}")
    print(f"ROWS={len(rows)}")
    print(f"TEXT_ROWS={filled}")


def main() -> None:
    parser = argparse.ArgumentParser(description="抖音直播数据分析工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    auth = sub.add_parser("auth", help="专用登录浏览器（持久 Chromium profile）")
    auth_sub = auth.add_subparsers(dest="auth_cmd", required=True)
    auth_login = auth_sub.add_parser("login", help="打开窗口等待扫码")
    auth_login.add_argument("platform", nargs="?", default=DEFAULT_PLATFORM)
    auth_login.add_argument("--timeout", type=int, default=600)
    auth_status_cmd = auth_sub.add_parser("status", help="检查登录态")
    auth_status_cmd.add_argument("platform", nargs="?", default=DEFAULT_PLATFORM)
    auth_open = auth_sub.add_parser("open", help="只开窗口，便于保活")
    auth_open.add_argument("platform", nargs="?", default=DEFAULT_PLATFORM)
    auth_sub.add_parser("list", help="列出已配置平台")

    sessions = sub.add_parser("sessions", help="近 30 场直播缓存")
    sessions_sub = sessions.add_subparsers(dest="sessions_cmd", required=True)
    sessions_refresh = sessions_sub.add_parser("refresh", help="刷新当前账号近 30 场")
    sessions_refresh.add_argument("--limit", type=int, default=30)
    sessions_list = sessions_sub.add_parser("list", help="显示场次列表")
    sessions_list.add_argument("--limit", type=int, default=30)
    sessions_list.add_argument("--refresh", action="store_true")
    sessions_list.add_argument("--cache-only", action="store_true")

    go = sub.add_parser(
        "go",
        help="一键: 检查登录 + 必要时扫码 + 刷新场次 + 导出指定场次",
    )
    go.add_argument("--index", type=int, help="按场次列表序号导出（缺省则跑到列表停下来）")
    go.add_argument("--room-id")
    go.add_argument("--title-contains")
    go.add_argument("--start-contains")
    go.add_argument("--limit", type=int, default=30)
    go.add_argument("--out", type=Path)
    go.add_argument("--wait-login-sec", type=int, default=600, help="扫码最长等多久")
    # cmd_export 期望的属性，避免 AttributeError
    go.add_argument("--rows-json", type=Path, help=argparse.SUPPRESS)
    go.add_argument("--refresh-sessions", action="store_true", help=argparse.SUPPRESS)
    go.add_argument("--no-reload", action="store_true", help=argparse.SUPPRESS)

    export = sub.add_parser("export", help="导出单场流量话术复盘 Excel")
    export.add_argument("--index", type=int, help="按 sessions_cache.json 序号导出")
    export.add_argument("--room-id", help="按 room_id 导出")
    export.add_argument("--title-contains", help="按标题关键词导出")
    export.add_argument("--start-contains", help="按开播时间片段匹配")
    export.add_argument("--rows-json", type=Path, help="离线 rows JSON")
    export.add_argument("--refresh-sessions", action="store_true")
    export.add_argument("--limit", type=int, default=30)
    export.add_argument("--no-reload", action="store_true")
    export.add_argument("--out", type=Path)

    args = parser.parse_args()

    if args.cmd == "auth":
        if args.auth_cmd == "login":
            ok = login_window(args.platform, timeout_sec=args.timeout)
            raise SystemExit(0 if ok else 2)
        elif args.auth_cmd == "status":
            auth_status(args.platform)
        elif args.auth_cmd == "open":
            open_window(args.platform)
        elif args.auth_cmd == "list":
            list_platforms()
        return

    if args.cmd == "sessions":
        if args.sessions_cmd == "refresh":
            refresh_sessions(limit=args.limit)
            print_sessions(refresh=False, limit=args.limit, auto_start=False)
        elif args.sessions_cmd == "list":
            print_sessions(
                refresh=args.refresh,
                limit=args.limit,
                auto_start=False,
                cache_only=args.cache_only,
            )
        return

    if args.cmd == "export":
        cmd_export(args)

    if args.cmd == "go":
        cmd_go(args)


if __name__ == "__main__":
    main()
