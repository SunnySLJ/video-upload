# -*- coding: utf-8 -*-
"""
共享浏览器模块 - nodriver + CDP 连接 Chrome

根据 AUTH_MODE 支持三种模式：
  - cookie : 每次启动新 Chrome，通过 cookie 文件保存/加载登录态
  - connect: 连接已打开的 Chrome（需先启动带 remote-debugging-port 的 Chrome）
  - profile: 使用固定用户目录，登录态持久化（推荐）
"""
import asyncio
import os
import platform
import urllib.request
from pathlib import Path
from typing import Callable, Optional

import nodriver as uc
from nodriver import Config

def _default_chrome_path(chrome_path: Optional[str] = None) -> str:
    if chrome_path:
        return chrome_path
    from common.conf import LOCAL_CHROME_PATH
    return LOCAL_CHROME_PATH


def get_profile_dir(
    account_name: str,
    profile_prefix: str,
    cookies_dir: Path,
    chrome_user_data_dir: str,
) -> Path:
    """AUTH_MODE=profile 时使用的 Chrome 用户目录"""
    base = (chrome_user_data_dir or "").strip() or str(cookies_dir / "chrome_profile")
    name = f"{profile_prefix}_{account_name}" if profile_prefix else account_name
    return Path(base) / name


def _cdp_endpoint_ready(port: int, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=timeout):
            return True
    except Exception:
        return False


async def get_browser(
    *,
    account_name: str = "default",
    profile_prefix: str = "",
    cookies_dir: Path,
    chrome_user_data_dir: str,
    auth_mode: str,
    cdp_endpoint: str,
    cdp_debug_port: int,
    chrome_path: Optional[str] = None,
    headless: Optional[bool] = None,
    try_reuse_chrome: bool = False,
    detach_env_var: Optional[str] = None,
    on_reuse: Optional[Callable[[], None]] = None,
    return_reused: bool = False,
):
    """
    获取 nodriver Browser 实例

    :param profile_prefix: profile 子目录前缀，如 "ks"、"sph"；空则不加前缀
    :param try_reuse_chrome: 是否先尝试连接已存在的 Chrome（固定端口）
    :param detach_env_var: 环境变量名，若为 "1" 则 Chrome 以独立会话启动
    :param on_reuse: 复用 Chrome 成功时的回调（如打日志）
    :param return_reused: 若 True，返回 (browser, was_reused)，was_reused 时调用方不应 stop() 以免关闭用户已打开的浏览器
    """
    from common.conf import LOCAL_CHROME_HEADLESS

    headless = headless if headless is not None else LOCAL_CHROME_HEADLESS
    chrome_path = _default_chrome_path(chrome_path)
    config = Config(
        headless=headless,
        browser_executable_path=chrome_path,
        sandbox=False,
    )

    if auth_mode == "connect":
        # 优先使用 cdp_debug_port（平台专用端口），而不是 cdp_endpoint（全局默认 9222）
        # 这样抖音/小红书/快手/视频号能各自使用正确的 9224/9223/9225/9226
        port = cdp_debug_port
        
        # 先检查端口是否就绪，给一点时间等待
        for retry in range(5):
            if _cdp_endpoint_ready(port, timeout=1.0):
                break
            await asyncio.sleep(0.5)
        else:
            raise RuntimeError(f"CDP endpoint not ready after retries: 127.0.0.1:{port}")
        
        # connect 模式的关键：只 attach 到已有浏览器，避免再拉起临时 Chrome
        # 否则可能出现连接被抢占/端口断连（上传中 ConnectionRefused）。
        # 修复：直接使用 host/port 参数，不使用 Config 对象
        last_error = None
        for attempt in range(3):
            try:
                # 方式 1: 直接用 host/port 参数（最稳定）
                browser = await uc.start(host="127.0.0.1", port=port)
                if return_reused:
                    return browser, True
                return browser
            except Exception as e1:
                last_error = e1
                # 方式 2: 如果直接连接失败，尝试用 Config 方式
                try:
                    connect_config = Config(
                        headless=False,
                        browser_executable_path=chrome_path,
                        sandbox=False,
                        host="127.0.0.1",
                        port=port,
                    )
                    browser = await uc.start(connect_config)
                    if return_reused:
                        return browser, True
                    return browser
                except Exception as e2:
                    last_error = f"{e1}; {e2}"
                    await asyncio.sleep(0.8)
        raise RuntimeError(f"connect browser failed on port {port} after {3} attempts: {last_error}")

    if auth_mode == "profile":
        profile_path = get_profile_dir(
            account_name, profile_prefix, cookies_dir, chrome_user_data_dir
        )
        profile_path.mkdir(parents=True, exist_ok=True)
        config.user_data_dir = str(profile_path)

        if try_reuse_chrome:
            try:
                # 先尝试接管已存在的同端口调试浏览器，减少重复登录。
                connect_config = Config(
                    headless=headless,
                    browser_executable_path=chrome_path,
                    sandbox=False,
                    host="127.0.0.1",
                    port=cdp_debug_port,
                )
                browser = await uc.start(connect_config)
                if on_reuse:
                    on_reuse()
                if return_reused:
                    return browser, True
                return browser
            except Exception:
                pass
            try:
                import nodriver.core.util as _uc_util
                _orig = _uc_util.free_port
                # 复用失败时固定端口新开，保持平台行为可预测。
                _uc_util.free_port = lambda: cdp_debug_port
                try:
                    browser = await uc.start(config)
                    if return_reused:
                        return browser, False
                    return browser
                finally:
                    _uc_util.free_port = _orig
            except Exception:
                pass

    if detach_env_var and auth_mode != "connect":
        _maybe_patch_detach(detach_env_var)

    browser = await uc.start(config)
    if return_reused:
        return browser, False
    return browser


_patch_applied = False


def _maybe_patch_detach(env_var: str) -> None:
    """若环境变量为 1，patch create_subprocess_exec 使 Chrome 独立会话"""
    global _patch_applied
    if _patch_applied:
        return
    if os.environ.get(env_var, "").strip() not in ("1", "true", "yes"):
        return
    if platform.system() not in ("Darwin", "Linux"):
        return

    _orig = asyncio.create_subprocess_exec

    async def _patched(*args, **kwargs):
        kwargs.setdefault("start_new_session", True)
        return await _orig(*args, **kwargs)

    asyncio.create_subprocess_exec = _patched
    _patch_applied = True
