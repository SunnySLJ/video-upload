#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bridge the OpenClaw auth skill to the synced openclaw_upload implementation."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path


DEFAULT_ROOT = Path.home() / ".openclaw" / "workspace" / "openclaw_upload"
_PROJECT_ROOT_OVERRIDE: Path | None = None
_AUTH_MODULE = None
_AUTH_ROOT: Path | None = None


def _default_root() -> Path:
    env_root = (os.environ.get("OPENCLAW_UPLOAD_ROOT") or "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()
    return DEFAULT_ROOT.resolve()


def project_root() -> Path:
    if _PROJECT_ROOT_OVERRIDE is not None:
        return _PROJECT_ROOT_OVERRIDE.resolve()
    return _default_root()


def _load_auth_module(root: Path):
    script = root / "scripts" / "platform_login.py"
    if not script.exists():
        raise RuntimeError(f"找不到已同步的 auth 实现: {script}")
    spec = importlib.util.spec_from_file_location("openclaw_synced_auth_platform_login", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 auth 脚本: {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if hasattr(module, "_PROJECT_ROOT_OVERRIDE"):
        module._PROJECT_ROOT_OVERRIDE = root
    return module


def _auth(root: Path | None = None):
    global _AUTH_MODULE, _AUTH_ROOT
    actual_root = (root or project_root()).resolve()
    if _AUTH_MODULE is None or _AUTH_ROOT != actual_root:
        _AUTH_MODULE = _load_auth_module(actual_root)
        _AUTH_ROOT = actual_root
    if hasattr(_AUTH_MODULE, "_PROJECT_ROOT_OVERRIDE"):
        _AUTH_MODULE._PROJECT_ROOT_OVERRIDE = actual_root
    return _AUTH_MODULE


def check_platform_login(platform_name: str, root: Path | None = None, passive: bool = False):
    actual_root = (root or project_root()).resolve()
    return _auth(actual_root).check_platform_login(platform_name, actual_root, passive=passive)


def ensure_platform_login(
    platform_name: str,
    timeout: int = 300,
    root: Path | None = None,
    notify_wechat: bool = False,
):
    actual_root = (root or project_root()).resolve()
    del notify_wechat
    return _auth(actual_root).ensure_platform_login(platform_name, timeout=timeout)


def __getattr__(name: str):
    return getattr(_auth(), name)


def _main() -> int:
    return _auth()._main()


if __name__ == "__main__":
    raise SystemExit(_main())
