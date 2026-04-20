#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared runtime path resolution for local skills."""
from __future__ import annotations

import json
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "skills" / "runtime_config.json"


def _load_config() -> dict:
    if not CONFIG_PATH.is_file():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _pick_path(*values: str | Path | None) -> Path | None:
    for value in values:
        if not value:
            continue
        return Path(value).expanduser().resolve()
    return None


def resolve_project_root(default: str | Path | None = None) -> Path:
    config = _load_config()
    return (
        _pick_path(
            os.environ.get("XIAOLONG_UPLOAD_ROOT", "").strip(),
            config.get("project_root", ""),
            default,
            REPO_ROOT,
        )
        or REPO_ROOT
    )


def resolve_workspace_root(
    project_root: str | Path | None = None,
    default: str | Path | None = None,
) -> Path:
    config = _load_config()
    project = _pick_path(project_root) or resolve_project_root()
    return (
        _pick_path(
            os.environ.get("XIAOLONG_WORKSPACE_ROOT", "").strip(),
            config.get("workspace_root", ""),
            default,
            project.parent,
        )
        or project.parent
    )


def resolve_flash_longxia_root(
    project_root: str | Path | None = None,
    workspace_root: str | Path | None = None,
    default: str | Path | None = None,
) -> Path:
    config = _load_config()
    project = _pick_path(project_root) or resolve_project_root()
    workspace = _pick_path(workspace_root) or resolve_workspace_root(project)
    configured = _pick_path(
        os.environ.get("FLASH_LONGXIA_ROOT", "").strip(),
        config.get("flash_longxia_root", ""),
        default,
    )
    if configured is not None:
        return configured

    candidates = (
        workspace / "openclaw_upload" / "flash_longxia",
        workspace / "flash_longxia",
        project / "flash_longxia",
    )
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]
