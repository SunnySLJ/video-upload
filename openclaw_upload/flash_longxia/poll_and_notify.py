#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""轮询视频生成状态，完成后自动下载并写入完成通知。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from notify_utils import load_processed_ids, save_processed_ids, send_feishu_notification
from zhenlongxia_workflow import (
    _STATUS_FAILED,
    _STATUS_SUCCESS,
    _build_status_text,
    _extract_rep_status,
    _extract_video_url_from_rep_msg,
    download_video,
    fetch_video_by_id,
    get_video_url,
    load_config,
    load_saved_token,
    resolve_runtime_path,
)

TASK_FILE = Path(__file__).parent / "pending_tasks.json"
NOTIFY_FILE = Path(__file__).parent / "completed_notification.json"
PROCESSED_FILE = Path(__file__).parent / ".processed_notifications.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="轮询视频生成任务，完成后自动下载")
    parser.add_argument("task_id", nargs="?", help="任务 ID；未传时处理 pending_tasks.json")
    parser.add_argument("--token", dest="token", help="接口 Token；默认读取 token.txt")
    return parser.parse_args()


def build_session(token: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "token": token,
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    })
    return session


def build_task_info(task_info: dict, *, config: dict | None = None) -> dict:
    """补齐轮询任务缺省配置，兼容旧 pending_tasks.json 格式。"""
    runtime_config = config or load_config()
    video_cfg = runtime_config.get("video", {}) or {}
    normalized = dict(task_info)
    normalized["base_url"] = str(
        normalized.get("base_url") or runtime_config["base_url"]
    ).rstrip("/")
    normalized["poll_interval"] = int(
        normalized.get("poll_interval") or video_cfg.get("poll_interval", 30)
    )
    normalized["max_wait_minutes"] = int(
        normalized.get("max_wait_minutes") or video_cfg.get("max_wait_minutes", 30)
    )
    normalized["output_dir"] = str(
        resolve_runtime_path(normalized.get("output_dir") or video_cfg.get("output_dir", "../output"), base_dir=Path(__file__).parent)
    )
    return normalized


def write_notification(video_path: str, task_info: dict) -> None:
    """写入完成通知并立即发送飞书。"""
    task_id = str(task_info.get("task_id", "unknown"))

    print("[通知] 尝试生成飞书通知载荷...")
    sent = send_feishu_notification(
        task_id,
        video_path=video_path,
        message="视频已下载完成，正在发送给您～",
        follow_up='请说"**可以发布**"或"**确认发布**"，我会上传到视频号！',
    )

    if sent:
        print(f"[通知] 飞书通知载荷已生成：{video_path}")
        processed = load_processed_ids(PROCESSED_FILE)
        processed.add(task_id)
        save_processed_ids(PROCESSED_FILE, processed)
        return

    notification = {
        "type": "video_completed",
        "video_path": video_path,
        "task_id": task_id,
        "image_path": task_info.get("image_path"),
        "message": "视频生成完成！请确认是否发布～",
    }

    NOTIFY_FILE.write_text(
        json.dumps(notification, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[通知] 已写入通知文件：{NOTIFY_FILE}")


def poll_task(task_info: dict, session: requests.Session) -> bool:
    task_id = str(task_info.get("task_id") or "").strip()
    base_url = str(task_info.get("base_url") or "").rstrip("/")
    poll_interval = int(task_info.get("poll_interval") or 30)
    max_wait_minutes = int(task_info.get("max_wait_minutes") or 30)
    max_elapsed = max_wait_minutes * 60
    elapsed = 0
    attempt = 0

    if not task_id or not base_url:
        print(f"[错误] 任务信息不完整：{task_info}")
        return False

    print(f"[轮询] 开始检查任务 {task_id}...")
    output_dir = str(task_info.get("output_dir") or resolve_runtime_path("../output", base_dir=Path(__file__).parent))

    while elapsed < max_elapsed:
        attempt += 1
        record = fetch_video_by_id(base_url, session, task_id)

        if record:
            status = record.get("status") or record.get("videoStatus") or record.get("taskStatus")
            rep_status = _extract_rep_status(record)
            print(f"[轮询] 第{attempt}次：{_build_status_text(record)}")

            video_url = get_video_url(record)
            if not video_url:
                video_url = _extract_video_url_from_rep_msg(record)
                if video_url:
                    record["mediaUrl"] = record.get("mediaUrl") or video_url

            if video_url:
                print(f"[完成] 任务 {task_id} 已完成 (mediaUrl 有值)")
                filename = f"{task_id}.mp4"
                video_path = download_video(video_url, output_dir, filename, session=session)
                write_notification(video_path, task_info)
                return True

            if status in _STATUS_SUCCESS or rep_status in _STATUS_SUCCESS:
                print(f"[完成] 任务 {task_id} 已完成 (status 判断)")
                if not video_url:
                    print(f"[错误] 任务 {task_id} 已完成但未找到视频地址")
                    return False
                filename = f"{task_id}.mp4"
                video_path = download_video(video_url, output_dir, filename, session=session)
                write_notification(video_path, task_info)
                return True

            if status in _STATUS_FAILED or rep_status in _STATUS_FAILED:
                print(f"[失败] 任务 {task_id} 失败")
                return False
        else:
            print(f"[轮询] 第{attempt}次：接口未返回任务数据")

        sleep_sec = min(poll_interval, max_elapsed - elapsed)
        if sleep_sec <= 0:
            break
        elapsed += sleep_sec
        time.sleep(sleep_sec)

    print(f"[超时] 任务 {task_id} 轮询超时")
    return False


def process_single_task(task_id: str, token: str | None) -> int:
    config = load_config()
    token_val = token or load_saved_token()
    if not token_val:
        print("[错误] 缺少 Token，请传 --token 或写入 token.txt")
        return 1

    task_info = build_task_info({
        "task_id": task_id,
        "token": token_val,
    }, config=config)
    session = build_session(token_val)
    success = poll_task(task_info, session)
    return 0 if success else 1


def process_pending_tasks() -> int:
    if not TASK_FILE.exists():
        print("[INFO] 没有待处理的任务")
        return 0

    data = json.loads(TASK_FILE.read_text(encoding="utf-8"))
    if not data:
        print("[INFO] 任务列表为空")
        return 0

    if isinstance(data, dict):
        pending_tasks = [data]
        print("[INFO] 检测到单个任务格式（对象）")
    elif isinstance(data, list):
        pending_tasks = data
        print(f"[INFO] 检测到任务列表格式（数组），共 {len(pending_tasks)} 个任务")
    else:
        print(f"[错误] 任务文件格式错误：{type(data)}")
        return 1

    if not pending_tasks:
        print("[INFO] 任务列表为空")
        return 0

    print(f"[INFO] 开始处理 {len(pending_tasks)} 个待处理任务")
    completed_indices: list[int] = []
    config = load_config()

    for idx, task_info in enumerate(pending_tasks):
        normalized_task_info = build_task_info(task_info, config=config)
        token = normalized_task_info.get("token")
        if not token:
            print(f"[错误] 任务缺少 token，跳过：{task_info}")
            continue
        session = build_session(token)
        success = poll_task(normalized_task_info, session)
        if success:
            completed_indices.append(idx)

    if completed_indices:
        remaining = [task for idx, task in enumerate(pending_tasks) if idx not in completed_indices]
        if len(remaining) == 1:
            TASK_FILE.write_text(json.dumps(remaining[0], indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            TASK_FILE.write_text(json.dumps(remaining, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[INFO] 已移除 {len(completed_indices)} 个已完成任务")

    return 0


def main() -> int:
    args = parse_args()

    if args.task_id:
        return process_single_task(args.task_id, args.token)

    return process_pending_tasks()


if __name__ == "__main__":
    sys.exit(main())
