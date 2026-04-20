# -*- coding: utf-8 -*-
"""视频号助手相关配置"""
import sys
import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from common.conf import (
    LOCAL_CHROME_PATH, LOCAL_CHROME_HEADLESS, get_platform_cookies_dir,
)

# 视频号固定使用 connect 模式，登录态保存在 chrome_connect_sph/
AUTH_MODE = "connect"
CDP_ENDPOINT = "http://127.0.0.1:9226"
CDP_DEBUG_PORT = 9226

PROJECT_ROOT = _ROOT
BASE_DIR = Path(__file__).resolve().parent
COOKIES_DIR, CHROME_USER_DATA_DIR = get_platform_cookies_dir(PROJECT_ROOT, "shipinhao")
