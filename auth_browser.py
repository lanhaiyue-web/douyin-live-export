"""专用登录浏览器：用 Playwright persistent context 给每个平台维护持久登录态。

设计原则：
- 每个平台 = 一个固定的 user-data-dir（`.auth/<platform>/`），Playwright 自带 Chromium。
- 登录态完全靠磁盘 profile 持久化。下次启动同一目录 = 自动登录。
- 默认 headless=False，登录窗口必须可见，用户能扫码。
- 没有 CDP 端口、没有 daemon 进程；调用方在用的时候 launch，用完 close。

CLI:
    python auth_browser.py login [platform]       # 打开可见窗口，等扫码或人工关闭
    python auth_browser.py status [platform]      # 检查持久 profile 是否已登录
    python auth_browser.py open [platform]        # 仅打开窗口（不等待登录信号），便于日常保活
    python auth_browser.py list                   # 列出已配置的平台

调用方接入：
    with launch_persistent("douyin-creator") as ctx:
        page = ctx.new_page()
        page.goto(...)
"""
from __future__ import annotations

import argparse
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from playwright.sync_api import BrowserContext, sync_playwright

AUTH_ROOT = Path(__file__).parent / ".auth"


@dataclass(frozen=True)
class PlatformSpec:
    key: str
    name_zh: str
    home_url: str
    login_check_url: str
    login_cookie_names: frozenset[str]
    cookie_origin: str


PLATFORMS: dict[str, PlatformSpec] = {
    "douyin-creator": PlatformSpec(
        key="douyin-creator",
        name_zh="抖音直播服务平台",
        home_url="https://anchor.douyin.com/anchor/review",
        login_check_url="https://anchor.douyin.com",
        login_cookie_names=frozenset({"sessionid", "sessionid_ss", "sid_tt", "sid_guard", "uid_tt"}),
        cookie_origin="https://anchor.douyin.com",
    ),
    "kuaishou": PlatformSpec(
        key="kuaishou",
        name_zh="快手直播伙伴",
        home_url="https://zs.kwaixiaodian.com/page/anchor-data/live-replay",
        login_check_url="https://zs.kwaixiaodian.com",
        login_cookie_names=frozenset({"passToken", "userId", "kuaishou.live.web_st"}),
        cookie_origin="https://zs.kwaixiaodian.com",
    ),
}

DEFAULT_PLATFORM = "douyin-creator"

LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-features=IsolateOrigins,site-per-process",
    "--lang=zh-CN",
]

IGNORE_DEFAULT_ARGS = ["--enable-automation"]


def resolve_platform(key: str | None) -> PlatformSpec:
    name = (key or DEFAULT_PLATFORM).strip().lower()
    if name not in PLATFORMS:
        available = ", ".join(PLATFORMS.keys())
        raise SystemExit(f"未知平台：{name}（支持：{available}）")
    return PLATFORMS[name]


def user_data_dir(platform: PlatformSpec | str) -> Path:
    spec = platform if isinstance(platform, PlatformSpec) else resolve_platform(platform)
    path = AUTH_ROOT / spec.key
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def launch_persistent(
    platform: str | PlatformSpec,
    *,
    headless: bool = False,
    viewport: dict | None = None,
    extra_args: list[str] | None = None,
) -> Iterator[BrowserContext]:
    """打开持久化 Chromium 上下文，with 退出时自动关闭。

    Args:
        platform: 平台 key（或 PlatformSpec）
        headless: 默认 False（可见窗口）。仅 status 检查这种短任务会用 True。
        viewport: None 时跟随 OS 窗口尺寸
        extra_args: 追加给 Chromium 的参数
    """
    spec = platform if isinstance(platform, PlatformSpec) else resolve_platform(platform)
    profile = user_data_dir(spec)

    args = list(LAUNCH_ARGS)
    if extra_args:
        args.extend(extra_args)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=headless,
            viewport=viewport,
            no_viewport=viewport is None,
            args=args,
            ignore_default_args=IGNORE_DEFAULT_ARGS,
            locale="zh-CN",
        )
        try:
            yield context
        finally:
            try:
                context.close()
            except Exception:
                pass


def has_login_cookies(context: BrowserContext, spec: PlatformSpec) -> bool:
    try:
        cookies = context.cookies([spec.cookie_origin])
    except Exception:
        return False
    names = {c.get("name") for c in cookies}
    return bool(names & spec.login_cookie_names)


def is_logged_in(platform: str | PlatformSpec = DEFAULT_PLATFORM) -> bool:
    """无窗口检查持久 profile 是否还带着登录 cookie。"""
    spec = platform if isinstance(platform, PlatformSpec) else resolve_platform(platform)
    with launch_persistent(spec, headless=True) as context:
        return has_login_cookies(context, spec)


def login_window(
    platform: str | PlatformSpec = DEFAULT_PLATFORM,
    *,
    timeout_sec: int = 600,
    poll_sec: float = 3.0,
) -> bool:
    """打开可见窗口，等待用户扫码登录或主动关窗。

    返回 True = 检测到登录成功；False = 超时或用户提前关掉窗口。
    """
    spec = platform if isinstance(platform, PlatformSpec) else resolve_platform(platform)
    print(f"打开持久浏览器：{spec.name_zh}")
    print(f"  profile: {user_data_dir(spec)}")
    print(f"  home:    {spec.home_url}")

    with launch_persistent(spec) as context:
        if context.pages:
            page = context.pages[0]
        else:
            page = context.new_page()

        try:
            page.goto(spec.home_url, wait_until="domcontentloaded", timeout=60_000)
        except Exception as exc:
            print(f"[!] 打开首页失败：{type(exc).__name__}: {exc}")

        if has_login_cookies(context, spec):
            print("[OK] 当前 profile 已经处于登录状态。窗口保持打开，关掉它即可退出。")
        else:
            print(f"[..] 请在弹出的窗口里扫码登录{spec.name_zh}。最长等 {timeout_sec}s。")

        import time

        deadline = time.time() + timeout_sec
        waited = 0.0
        success = False
        while time.time() < deadline:
            if not context.pages:
                print("[!] 用户关闭了窗口，登录流程中止。")
                break
            if has_login_cookies(context, spec):
                print("[OK] 检测到登录成功。等 3 秒确保 cookie 刷新写盘…")
                page.wait_for_timeout(3_000)
                success = True
                break
            try:
                page.wait_for_timeout(int(poll_sec * 1000))
            except Exception:
                break
            waited += poll_sec
            if int(waited) % 30 == 0:
                remaining = max(0, int(deadline - time.time()))
                print(f"    ...等待中（已等 {int(waited)}s / 剩余 {remaining}s）")
        else:
            print(f"[!] {timeout_sec}s 内没检测到登录，超时。")

        return success


def open_window(platform: str | PlatformSpec = DEFAULT_PLATFORM) -> None:
    """仅打开窗口，不轮询登录信号；用户关窗时本进程退出。

    用于日常保活：偶尔进去刷新一下 cookie，或者就让浏览器开着。
    """
    spec = platform if isinstance(platform, PlatformSpec) else resolve_platform(platform)
    print(f"打开持久浏览器：{spec.name_zh}")
    print(f"  profile: {user_data_dir(spec)}")
    print("  关掉这个窗口本进程就退出。")

    with launch_persistent(spec) as context:
        if context.pages:
            page = context.pages[0]
        else:
            page = context.new_page()
        try:
            page.goto(spec.home_url, wait_until="domcontentloaded", timeout=60_000)
        except Exception as exc:
            print(f"[!] 打开首页失败：{type(exc).__name__}: {exc}")
        # 阻塞到 context 关闭
        try:
            context.wait_for_event("close", timeout=0)
        except Exception:
            pass


def status(platform: str | PlatformSpec = DEFAULT_PLATFORM) -> None:
    spec = platform if isinstance(platform, PlatformSpec) else resolve_platform(platform)
    profile = user_data_dir(spec)
    print(f"平台:    {spec.key} ({spec.name_zh})")
    print(f"profile: {profile}")
    print(f"home:    {spec.home_url}")
    has_profile = any(profile.iterdir())
    print(f"profile 已写入文件: {'是' if has_profile else '否'}")
    if not has_profile:
        print("登录态: 还没初始化，先跑 python auth_browser.py login")
        return
    print("登录态: 检测中（headless 启动 Chromium 读 cookie）...")
    try:
        ok = is_logged_in(spec)
    except Exception as exc:
        print(f"登录态: 检测失败 {type(exc).__name__}: {exc}")
        return
    print(f"登录态: {'已登录' if ok else '未登录 / 已过期'}")


def list_platforms() -> None:
    print("支持的平台：")
    for spec in PLATFORMS.values():
        profile = AUTH_ROOT / spec.key
        exists = profile.exists() and any(profile.iterdir())
        flag = "✓" if exists else "·"
        print(f"  {flag} {spec.key:<18} {spec.name_zh:<14} profile={profile}")


def main() -> None:
    parser = argparse.ArgumentParser(description="专用登录浏览器（Playwright 持久化 Chromium）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_login = sub.add_parser("login", help="打开可见窗口，等待扫码登录")
    p_login.add_argument("platform", nargs="?", default=DEFAULT_PLATFORM)
    p_login.add_argument("--timeout", type=int, default=600, help="最长等待秒数")

    p_status = sub.add_parser("status", help="检查持久 profile 是否还在登录状态")
    p_status.add_argument("platform", nargs="?", default=DEFAULT_PLATFORM)

    p_open = sub.add_parser("open", help="只开窗口，便于保活；关窗退出")
    p_open.add_argument("platform", nargs="?", default=DEFAULT_PLATFORM)

    sub.add_parser("list", help="列出所有支持的平台")

    args = parser.parse_args()
    if args.cmd == "login":
        ok = login_window(args.platform, timeout_sec=args.timeout)
        sys.exit(0 if ok else 2)
    elif args.cmd == "status":
        status(args.platform)
    elif args.cmd == "open":
        open_window(args.platform)
    elif args.cmd == "list":
        list_platforms()


if __name__ == "__main__":
    main()
