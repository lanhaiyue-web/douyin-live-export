"""Managed Chromium browser for Douyin live replay extraction.

This script owns one dedicated browser profile under ``data/user_data`` and
exposes Chrome DevTools Protocol on ``127.0.0.1:9222``. All extraction scripts
connect to this managed browser instead of trying to control random desktop
browser windows.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

DATA_DIR = Path(__file__).parent / "data"
USER_DATA_DIR = DATA_DIR / "user_data"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
PID_FILE = DATA_DIR / "chrome_daemon.pid"

CDP_PORT = int(os.environ.get("DOUYIN_CDP_PORT", "9222"))
ANCHOR_HOME = "https://anchor.douyin.com/anchor/review"

# User can override browser selection for any customer machine:
#   setx DOUYIN_BROWSER_PATH "C:\Program Files\Google\Chrome\Application\chrome.exe"
BROWSER_ENV = "DOUYIN_BROWSER_PATH"


def _expand(path: str) -> Path:
    return Path(os.path.expandvars(path)).expanduser()


BROWSER_CANDIDATES: list[tuple[str, str]] = [
    # Edge 排第一：Windows 系统自带，目标用户（主播）默认就是这个
    ("Edge", r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    ("Edge", r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
    ("Edge", r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
    ("Chrome", r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
    ("Chrome", r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
    ("Chrome", r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ("Brave", r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"),
    ("Brave", r"%ProgramFiles(x86)%\BraveSoftware\Brave-Browser\Application\brave.exe"),
    ("Brave", r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe"),
    ("Chromium", r"%ProgramFiles%\Chromium\Application\chrome.exe"),
    ("Chromium", r"%ProgramFiles(x86)%\Chromium\Application\chrome.exe"),
    ("360Chrome", r"%LocalAppData%\360Chrome\Chrome\Application\360chrome.exe"),
    ("360Chrome", r"%ProgramFiles%\360\360Chrome\Chrome\Application\360chrome.exe"),
    ("360Chrome", r"%ProgramFiles(x86)%\360\360Chrome\Chrome\Application\360chrome.exe"),
    ("360ChromeX", r"%LocalAppData%\360ChromeX\Chrome\Application\360ChromeX.exe"),
    ("360ChromeX", r"%ProgramFiles%\360ChromeX\Chrome\Application\360ChromeX.exe"),
    ("360ChromeX", r"%ProgramFiles(x86)%\360ChromeX\Chrome\Application\360ChromeX.exe"),
    ("QQBrowser", r"%ProgramFiles(x86)%\Tencent\QQBrowser\QQBrowser.exe"),
    ("QQBrowser", r"%LocalAppData%\Tencent\QQBrowser\QQBrowser.exe"),
]


def _detect_windows_default_browser() -> tuple[str, Path] | None:
    """从 Windows 注册表读用户当前默认浏览器的 exe 路径。"""
    if sys.platform != "win32":
        return None
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice",
        ) as key:
            prog_id, _ = winreg.QueryValueEx(key, "ProgId")
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"{prog_id}\shell\open\command") as key:
            command, _ = winreg.QueryValueEx(key, None)
        # command 形如 "C:\Program Files...\msedge.exe" --single-argument %1
        if command.startswith('"'):
            exe_path = command.split('"', 2)[1]
        else:
            exe_path = command.split(" ", 1)[0]
        path = Path(exe_path)
        if not path.exists():
            return None
        lname = path.name.lower()
        if "msedge" in lname:
            return ("Edge", path)
        if "chrome" in lname:
            return ("Chrome", path)
        if "brave" in lname:
            return ("Brave", path)
        return ("Default", path)
    except Exception:
        return None


def find_browser() -> tuple[str, Path]:
    override = os.environ.get(BROWSER_ENV, "").strip().strip('"')
    if override:
        path = _expand(override)
        if path.exists():
            return ("custom", path)
        raise SystemExit(f"{BROWSER_ENV} 指向的浏览器不存在：{path}")

    # 优先使用系统当前的默认浏览器，符合用户习惯
    default = _detect_windows_default_browser()
    if default:
        return default

    for name, raw_path in BROWSER_CANDIDATES:
        path = _expand(raw_path)
        if path.exists():
            return name, path

    raise SystemExit(
        "找不到可托管的 Chromium 浏览器。请安装 Edge / Chrome，"
        f"或设置环境变量 {BROWSER_ENV} 指向浏览器 exe。"
    )


def is_cdp_alive(port: int = CDP_PORT) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


# 抖音登录成功后种的 cookies；任一存在 = 已登录
_LOGIN_COOKIE_NAMES = {"sessionid", "sessionid_ss", "sid_tt", "sid_guard", "uid_tt"}


def is_logged_in(port: int = CDP_PORT) -> bool:
    """通过 CDP 连接拿 anchor.douyin.com 的 cookies，看登录态有没有种上。"""
    if not is_cdp_alive(port):
        return False
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            for ctx in browser.contexts:
                try:
                    cookies = ctx.cookies(["https://anchor.douyin.com"])
                except Exception:
                    continue
                names = {c.get("name") for c in cookies}
                if names & _LOGIN_COOKIE_NAMES:
                    return True
    except Exception:
        pass
    return False


def wait_for_login(port: int = CDP_PORT, timeout_sec: int = 600, poll_sec: float = 3.0) -> bool:
    """轮询登录态，登录成功返回 True；超时返回 False。"""
    deadline = time.time() + timeout_sec
    waited = 0.0
    while time.time() < deadline:
        if is_logged_in(port):
            return True
        time.sleep(poll_sec)
        waited += poll_sec
        if int(waited) % 15 == 0:
            remaining = max(0, int(deadline - time.time()))
            print(f"    ...等待扫码登录中（已等 {int(waited)}s / 剩余 {remaining}s）")
    return False


def read_cdp_version(port: int = CDP_PORT) -> dict:
    try:
        with urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return {}


def start_daemon(minimized: bool = False, url: str = ANCHOR_HOME) -> None:
    if is_cdp_alive():
        print(f"[OK] 托管浏览器已在运行，CDP 端口：{CDP_PORT}")
        version = read_cdp_version()
        if version.get("Browser"):
            print(f"     Browser: {version['Browser']}")
        if PID_FILE.exists():
            print(f"     PID: {PID_FILE.read_text(encoding='utf-8').strip()}")
        return

    browser_name, browser_path = find_browser()
    args = [
        str(browser_path),
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--remote-allow-origins=*",
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=IsolateOrigins,site-per-process",
        "--lang=zh-CN",
    ]
    if minimized:
        args.append("--start-minimized")
    args.append(url)

    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(
        args,
        creationflags=flags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")

    print(f"[OK] 已启动托管浏览器：{browser_name}")
    print(f"     exe: {browser_path}")
    print(f"     PID: {proc.pid}")
    print(f"     CDP: http://127.0.0.1:{CDP_PORT}")
    print(f"     登录态目录: {USER_DATA_DIR}")
    print("     等待 CDP 端口就绪...")

    for i in range(30):
        if is_cdp_alive():
            print(f"     [OK] CDP 已就绪（{i + 1}s）")
            print()
            print("=" * 66)
            print("第一次使用：在这个托管浏览器里扫码登录抖音直播服务平台。")
            print("登录后可以把窗口最小化；不要关闭它，后续工具会精准连接这一只浏览器。")
            print("换账号：在这个托管浏览器里退出/重新扫码，然后刷新场次缓存即可。")
            print("=" * 66)
            return
        time.sleep(1)

    print("[!] 30 秒内没有等到 CDP 端口，浏览器可能启动失败。")


def stop_daemon() -> None:
    if not PID_FILE.exists():
        print("[!] 没有 PID 记录。为了避免误关用户自己的浏览器，这里不盲杀进程。")
        return

    raw_pid = PID_FILE.read_text(encoding="utf-8").strip()
    if not raw_pid.isdigit():
        PID_FILE.unlink(missing_ok=True)
        print("[!] PID 记录损坏，已清理。")
        return

    pid = int(raw_pid)
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/PID", str(pid), "/T"], check=False)
    else:
        subprocess.run(["kill", "-TERM", str(pid)], check=False)
    PID_FILE.unlink(missing_ok=True)
    print(f"[OK] 已停止托管浏览器 PID={pid}")


def status() -> None:
    alive = is_cdp_alive()
    print(f"CDP 端口 {CDP_PORT}: {'运行中' if alive else '未运行'}")
    if alive:
        version = read_cdp_version()
        if version.get("Browser"):
            print(f"Browser: {version['Browser']}")
        if version.get("webSocketDebuggerUrl"):
            print("连接目标: 托管浏览器 CDP")
    if PID_FILE.exists():
        print(f"PID: {PID_FILE.read_text(encoding='utf-8').strip()}")
    else:
        print("PID: 无记录")
    print(f"user_data: {USER_DATA_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser(description="抖音直播分析托管浏览器")
    sub = parser.add_subparsers(dest="cmd")

    start = sub.add_parser("start", help="启动托管浏览器")
    start.add_argument("--minimized", action="store_true", help="启动后最小化")
    start.add_argument("--url", default=ANCHOR_HOME, help="启动后打开的页面")

    sub.add_parser("status", help="查看托管浏览器状态")
    sub.add_parser("stop", help="停止托管浏览器")

    args = parser.parse_args()
    cmd = args.cmd or "start"
    if cmd == "start":
        start_daemon(minimized=args.minimized, url=args.url)
    elif cmd == "status":
        status()
    elif cmd == "stop":
        stop_daemon()


if __name__ == "__main__":
    main()
