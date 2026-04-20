# -*- coding: utf-8 -*-
"""
共享配置：Chrome 路径、Auth 模式等，兼容 Mac 与 Windows

各平台 conf.py 引用此模块，并定义自己的 BASE_DIR、COOKIES_DIR。
"""
import os
import platform
from pathlib import Path


def get_chrome_path() -> str:
    """根据系统和环境变量返回 Chrome 可执行路径"""
    if os.environ.get("LOCAL_CHROME_PATH"):
        return os.environ.get("LOCAL_CHROME_PATH")
    if platform.system() == "Darwin":
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if platform.system() == "Windows":
        for p in [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]:
            if Path(p).exists():
                return p
        return "chrome"
    return "google-chrome"


# Chrome
LOCAL_CHROME_PATH = os.environ.get("LOCAL_CHROME_PATH") or get_chrome_path()
LOCAL_CHROME_HEADLESS = os.environ.get("LOCAL_CHROME_HEADLESS", "false").lower() == "true"

# 登录授权模式: profile | connect | cookie
AUTH_MODE = os.environ.get("AUTH_MODE", "profile").lower()

# CDP 连接配置（AUTH_MODE=connect 时使用）
CDP_ENDPOINT = os.environ.get("CDP_ENDPOINT", "http://127.0.0.1:9222")
CDP_DEBUG_PORT = int(os.environ.get("CDP_DEBUG_PORT", "9222"))


def get_platform_cookies_dir(project_root: Path, platform_name: str) -> tuple[Path, str]:
    """返回 (COOKIES_DIR, CHROME_USER_DATA_DIR) 供各平台 conf 使用"""
    cookies_dir = project_root / "cookies" / platform_name
    chrome_user_data = os.environ.get("CHROME_USER_DATA_DIR", str(cookies_dir))
    return cookies_dir, chrome_user_data
