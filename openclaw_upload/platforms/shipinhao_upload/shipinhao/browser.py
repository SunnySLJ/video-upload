# -*- coding: utf-8 -*-
"""
纯 CDP 模式：使用 nodriver 连接 Chrome
委托 common.browser，支持复用已打开的 Chrome
"""
import os
import platform
import re
import socket
import subprocess
import time
import sys
import urllib.parse
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from conf import (
    LOCAL_CHROME_PATH,
    LOCAL_CHROME_HEADLESS,
    AUTH_MODE,
    CDP_ENDPOINT,
    CDP_DEBUG_PORT,
    CHROME_USER_DATA_DIR,
    COOKIES_DIR,
)
from common.browser import get_browser as _get_browser
from common.loggers import shipinhao_logger

SPH_UPLOAD_URL = "https://channels.weixin.qq.com/platform/post/create"
SPH_CONNECT_PORT = 9226
SPH_CONNECT_PROFILE_DIR = COOKIES_DIR.parent / "chrome_connect_sph"


def _on_reuse():
    shipinhao_logger.info("[+] 复用已打开的 Chrome")


def _find_existing_upload_tab(browser, url_hint: str = SPH_UPLOAD_URL):
    hint = (url_hint or "").lower()
    try:
        tabs = getattr(browser, "tabs", None) or []
        for tab in tabs:
            try:
                url = (getattr(tab, "url", None) or getattr(getattr(tab, "target", None), "url", None) or "").lower()
                if "channels.weixin.qq.com" in url and "platform/post/create" in url:
                    return tab
                if hint and url == hint:
                    return tab
            except Exception:
                continue
    except Exception:
        pass
    return None


def _open_target_tab(port: int, url: str) -> bool:
    encoded = urllib.parse.quote(url, safe=":/?&=%")
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/json/new?{encoded}",
            method="PUT",
            headers={"User-Agent": "shipinhao-connect"},
        )
        with urllib.request.urlopen(req, timeout=3):
            return True
    except Exception:
        return False


async def get_browser(*, headless=None, account_name: str = "default", return_reused: bool = True, try_reuse: bool = True):
    """获取浏览器，return_reused=True 时返回 (browser, was_reused)，复用时不调用 stop()"""
    return await _get_browser(
        account_name=account_name,
        profile_prefix="sph",
        cookies_dir=COOKIES_DIR,
        chrome_user_data_dir=CHROME_USER_DATA_DIR,
        auth_mode=AUTH_MODE,
        cdp_endpoint=CDP_ENDPOINT,
        cdp_debug_port=CDP_DEBUG_PORT,
        chrome_path=LOCAL_CHROME_PATH,
        headless=headless,
        try_reuse_chrome=try_reuse,
        detach_env_var=None,
        on_reuse=_on_reuse,
        return_reused=return_reused,
    )


def _port_listening(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


def _list_listening_pids(port: int) -> list[int]:
    try:
        result = subprocess.run(
            ["lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return []
    return sorted({int(line) for line in result.stdout.splitlines() if line.strip().isdigit()})


def _process_user_data_dir(pid: int) -> Path | None:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return None
    command = result.stdout or ""
    for pattern in (
        r'--user-data-dir="([^"]+)"',
        r"--user-data-dir='([^']+)'",
        r"--user-data-dir=([^\s]+)",
    ):
        match = re.search(pattern, command)
        if match:
            return Path(match.group(1)).expanduser()
    return None


def _ensure_port_uses_expected_profile(port: int, expected_profile: Path) -> bool:
    expected = expected_profile.expanduser().resolve()
    pids = _list_listening_pids(port)
    if not pids:
        return True
    for pid in pids:
        actual = _process_user_data_dir(pid)
        if actual and actual.expanduser().resolve() == expected:
            return True
    shipinhao_logger.warning(f"[-] 端口 {port} 被非当前 profile 占用，准备关闭旧 connect Chrome")
    for pid in pids:
        try:
            os.kill(pid, 15)
        except Exception:
            pass
    deadline = time.time() + 8
    while time.time() < deadline:
        if not _port_listening(port):
            return True
        time.sleep(0.2)
    return not _port_listening(port)


def _launch_debug_chrome(port: int, url: str) -> None:
    SPH_CONNECT_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    kwargs = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    system = platform.system()
    if system == "Darwin":
        args = [
            "open",
            "-na",
            "Google Chrome",
            "--args",
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={SPH_CONNECT_PROFILE_DIR}",
            "--start-maximized",
            url,
        ]
        kwargs["start_new_session"] = True
    else:
        chrome = LOCAL_CHROME_PATH or None
        args = [
            chrome,
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={SPH_CONNECT_PROFILE_DIR}",
            "--start-maximized",
            url,
        ]
        if system == "Linux":
            kwargs["start_new_session"] = True
        elif system == "Windows":
            kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(args, **kwargs)


def ensure_connect_login_chrome(port: int = SPH_CONNECT_PORT, url: str = SPH_UPLOAD_URL, timeout: float = 15.0) -> bool:
    """确保视频号 connect 调试 Chrome 已启动，并固定落盘到 cookies/chrome_connect_sph。"""
    if _port_listening(port):
        if not _ensure_port_uses_expected_profile(port, SPH_CONNECT_PROFILE_DIR):
            shipinhao_logger.warning(f"[-] 端口 {port} 正被错误 profile 占用，无法启动当前 connect Chrome")
            return False
        if _port_listening(port):
            SPH_CONNECT_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            return True
        SPH_CONNECT_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        _launch_debug_chrome(port, url)
    except Exception as e:
        shipinhao_logger.warning(f"[-] 启动 connect Chrome 失败: {e}")
        return False

    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_listening(port):
            shipinhao_logger.info(f"[+] 已启动 connect Chrome，目录: {SPH_CONNECT_PROFILE_DIR}")
            return True
        time.sleep(0.25)
    shipinhao_logger.warning("[-] connect Chrome 启动超时，继续走默认登录流程")
    return False


async def attach_login_chrome(port: int = SPH_CONNECT_PORT):
    """连接视频号专用调试 Chrome，不要求当前已登录。"""
    import nodriver as uc
    from nodriver import Config

    config = Config(
        port=port,
        host="127.0.0.1",
        headless=False,
        browser_executable_path=LOCAL_CHROME_PATH or None,
        sandbox=False,
    )
    browser = await uc.start(config)
    tab = _find_existing_upload_tab(browser, SPH_UPLOAD_URL)
    if tab is None:
        try:
            tab = await browser.get(SPH_UPLOAD_URL)
        except (StopIteration, RuntimeError):
            _open_target_tab(port, SPH_UPLOAD_URL)
            tab = await browser.get(SPH_UPLOAD_URL)
    await tab.sleep(2)
    return browser, tab


async def try_connect_existing_chrome(port: int = None) -> "tuple|None":
    """尝试连接已打开的 Chrome（带 --remote-debugging-port）。若已登录则返回 (browser, tab)。"""
    import nodriver as uc
    from nodriver import Config

    # 视频号固定优先探测自己的 connect 端口 9226。
    # 否则在未显式传 AUTH_MODE=connect 时，会错误落回全局默认 9222。
    port = port or SPH_CONNECT_PORT
    try:
        config = Config(
            port=port,
            host="127.0.0.1",
            headless=False,
            browser_executable_path=LOCAL_CHROME_PATH or None,
            sandbox=False,
        )
        browser = await uc.start(config)
        tab = _find_existing_upload_tab(browser, SPH_UPLOAD_URL)
        if tab is None:
            try:
                tab = await browser.get(SPH_UPLOAD_URL)
            except (StopIteration, RuntimeError):
                _open_target_tab(port, SPH_UPLOAD_URL)
                tab = await browser.get(SPH_UPLOAD_URL)
        await tab.sleep(2)
        url = (tab.url or "").lower()
        if "login" in url or "mp.weixin" in url:
            browser.stop()
            return None
        try:
            if await tab.find("微信扫码", timeout=1):
                browser.stop()
                return None
        except Exception:
            pass
        try:
            if await tab.find("扫码登录", timeout=1):
                browser.stop()
                return None
        except Exception:
            pass
        return (browser, tab)
    except Exception:
        return None
