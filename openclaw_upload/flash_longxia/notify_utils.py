#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通知相关公共工具，供轮询和补发脚本复用。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common.feishu_notify import resolve_feishu_config, send_file_message, send_text_message

try:
    from flash_longxia.zhenlongxia_workflow import load_config
except ImportError:
    from zhenlongxia_workflow import load_config


def resolve_notify_settings() -> tuple[str | None, str | None]:
    """从环境变量或 config.yaml 读取通知配置。"""
    env_target = (os.getenv("FLASH_LONGXIA_FEISHU_TARGET") or os.getenv("OPENCLAW_FEISHU_TARGET") or "").strip()
    env_channel = (os.getenv("FLASH_LONGXIA_NOTIFY_CHANNEL") or "").strip()
    if env_target:
        return env_target, env_channel or None

    config = load_config()
    notify_cfg = config.get("notify", {}) or {}
    target = str(notify_cfg.get("feishu_target") or "").strip()
    channel = str(notify_cfg.get("channel") or "").strip()
    if target and "YOUR_FEISHU_OPEN_ID" not in target:
        return target, channel or None

    _, _, env_file_target = resolve_feishu_config(PROJECT_ROOT)
    return (env_file_target or None, channel or None)


def load_processed_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        return {str(item) for item in json.loads(path.read_text(encoding="utf-8"))}
    except json.JSONDecodeError:
        return set()


def save_processed_ids(path: Path, processed: set[str]) -> None:
    path.write_text(
        json.dumps(sorted(processed), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def send_feishu_notification(
    task_id: str,
    *,
    video_path: str | None = None,
    message: str,
    follow_up: str,
    video_message: str | None = None,
) -> bool:
    """生成通知数据，并直接发送飞书文本/文件消息。"""
    feishu_target, notify_channel = resolve_notify_settings()
    if not feishu_target:
        print("[通知] 未配置飞书目标，跳过发送")
        return False

    payload = {
        "target": feishu_target,
        "channel": notify_channel or "feishu",
        "text": (
            "🦋 **视频生成完成通知**\n\n"
            f"✅ 任务 {task_id} 已完成\n\n"
            f"{message}\n\n"
            "---\n"
            f"{follow_up}"
        ),
        "video_path": video_path,
        "video_message": video_message or f"📹 视频文件：任务 {task_id}",
    }
    path = Path(__file__).parent / f"notify_{task_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[通知] 已写入飞书通知载荷：{path}")
    ok_text, text_detail = send_text_message(payload["text"], project_root=PROJECT_ROOT, receive_id=feishu_target)
    if ok_text:
        print("[通知] 飞书文本通知已发送")
    else:
        print(f"[通知] 飞书文本通知发送失败：{text_detail}")

    ok_file = True
    if video_path:
        ok_file, file_detail = send_file_message(video_path, project_root=PROJECT_ROOT, receive_id=feishu_target)
        if ok_file:
            print("[通知] 飞书视频文件已发送")
        else:
            print(f"[通知] 飞书视频文件发送失败：{file_detail}")

    return ok_text and ok_file
