#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一 Python 运行时选择。优先切到仓库内 uv `.venv`，兜底本机 Python 3.11。"""
from __future__ import annotations

import os
import platform
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PREFERRED_MAC_PYTHON = Path.home() / ".local" / "bin" / "python3.11"


def _load_env_python() -> Path | None:
    env_python = (os.environ.get("OPENCLAW_PYTHON") or "").strip()
    if env_python:
        candidate = Path(env_python).expanduser()
        if candidate.exists():
            return candidate

    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or not line.startswith("OPENCLAW_PYTHON="):
                continue
            candidate = Path(line.split("=", 1)[1].strip()).expanduser()
            if candidate.exists():
                return candidate

    repo_candidates = [
        PROJECT_ROOT / ".venv" / "bin" / "python3.11",
        PROJECT_ROOT / ".venv" / "bin" / "python3",
        PROJECT_ROOT / ".venv" / "bin" / "python",
        PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",
        PROJECT_ROOT / ".venv" / "Scripts" / "python",
    ]
    for repo_python in repo_candidates:
        if repo_python.exists():
            return repo_python
    return None


def ensure_preferred_python_3_11() -> None:
    """在 macOS 下优先重进到仓库 uv Python；没有时再回退到本机 Python 3.11。"""
    if os.environ.get("XIAOLONG_PYTHON_LOCK") == "1":
        return
    if platform.system() != "Darwin":
        return
    if sys.version_info[:2] == (3, 11):
        return

    preferred_python = _load_env_python() or PREFERRED_MAC_PYTHON
    if not preferred_python.exists():
        return

    env = os.environ.copy()
    env["XIAOLONG_PYTHON_LOCK"] = "1"
    os.execve(str(preferred_python), [str(preferred_python), *sys.argv], env)


# 兼容旧函数名
ensure_preferred_python_3_11 = ensure_preferred_python_3_11
