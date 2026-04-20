#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一 Python 运行时选择。macOS 下优先切到当前用户的 Python 3.11。"""
from __future__ import annotations

import os
import platform
import sys
from pathlib import Path


PREFERRED_MAC_PYTHON = Path.home() / ".local" / "bin" / "python3.11"


def ensure_preferred_python_3_11() -> None:
    """在 macOS 下优先重进到当前用户 ~/.local/bin/python3.11。"""
    if os.environ.get("XIAOLONG_PYTHON_LOCK") == "1":
        return
    if platform.system() != "Darwin":
        return
    if sys.version_info[:2] == (3, 11):
        return
    if not PREFERRED_MAC_PYTHON.exists():
        return

    env = os.environ.copy()
    env["XIAOLONG_PYTHON_LOCK"] = "1"
    os.execve(str(PREFERRED_MAC_PYTHON), [str(PREFERRED_MAC_PYTHON), *sys.argv], env)


ensure_preferred_python_3_11 = ensure_preferred_python_3_11
