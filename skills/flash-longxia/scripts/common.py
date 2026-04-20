#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""flash-longxia skill 共享运行时辅助函数。"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def resolve_repo_root() -> Path | None:
    """优先定位 Hermes 内的 openclaw_upload 根目录。"""
    candidates: list[Path] = []

    env_root = os.environ.get("OPENCLAW_UPLOAD_ROOT")
    if env_root:
        candidates.append(Path(env_root).expanduser())

    home = Path.home()
    candidates.extend([
        home / ".hermes" / "workspace" / "openclaw_upload",
        home / "Desktop" / "openclaw_upload",
        home / "workspace" / "openclaw_upload",
        home / "openclaw_upload",
    ])

    cwd = Path.cwd().resolve()
    candidates.extend([cwd, *cwd.parents])

    script_dir = Path(__file__).resolve().parent
    candidates.extend([script_dir, *script_dir.parents])

    candidates.append(home / ".openclaw" / "workspace" / "openclaw_upload")

    for candidate in candidates:
        try:
            candidate = candidate.resolve()
        except FileNotFoundError:
            continue

        workflow = candidate / "flash_longxia" / "zhenlongxia_workflow.py"
        if workflow.exists():
            return candidate
    return None


def resolve_venv_python(repo_root: Path) -> Path | None:
    """兼容 macOS/Linux 与 Windows 的虚拟环境 Python。"""
    candidates: list[Path] = []
    env_python = (os.environ.get("OPENCLAW_PYTHON") or "").strip()
    if env_python:
        candidates.append(Path(env_python).expanduser())

    candidates.extend([
        repo_root / ".venv" / "bin" / "python3.11",
        repo_root / ".venv" / "bin" / "python3",
        repo_root / ".venv" / "bin" / "python",
        repo_root / ".venv" / "Scripts" / "python.exe",
        repo_root / ".venv" / "Scripts" / "python",
        repo_root / "venv" / "bin" / "python3.11",
        repo_root / "venv" / "bin" / "python3",
        repo_root / "venv" / "bin" / "python",
        repo_root / "venv" / "Scripts" / "python.exe",
        repo_root / "venv" / "Scripts" / "python",
    ])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def ensure_project_python(repo_root: Path) -> None:
    """优先切换到仓库内的 Python 3.11 运行时。"""
    venv_python = resolve_venv_python(repo_root)
    if venv_python is None:
        return

    if Path(sys.executable).resolve() == venv_python.resolve():
        return

    os.execv(str(venv_python), [str(venv_python), *sys.argv])
