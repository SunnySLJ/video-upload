#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""桥接 auth skill 的登录检查/补登录能力。

当前项目对外只开放视频号入口，因此这里也只作为视频号登录桥接使用。
其他平台实现文件仍保留在仓库中，但不再视为公开能力。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUTH_SCRIPT = PROJECT_ROOT / "skills" / "auth" / "scripts" / "platform_login.py"


def _load_auth_module():
    spec = importlib.util.spec_from_file_location(
        "skill_auth_platform_login_bridge",
        AUTH_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 auth 脚本: {AUTH_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_AUTH = _load_auth_module()


def check_platform_login(
    platform_name: str,
    project_root: Path | None = None,
    passive: bool = False,
) -> tuple[bool, str]:
    root = project_root or PROJECT_ROOT
    return _AUTH.check_platform_login(platform_name, root, passive=passive)


def ensure_platform_login(
    platform_name: str,
    project_root: Path | None = None,
    timeout: int = 300,
    notify_wechat: bool = False,
) -> tuple[bool, str]:
    root = project_root or PROJECT_ROOT
    _AUTH._PROJECT_ROOT_OVERRIDE = root
    return _AUTH.ensure_platform_login(
        platform_name,
        timeout=timeout,
        notify_wechat=notify_wechat,
    )
