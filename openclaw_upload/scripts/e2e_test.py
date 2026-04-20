#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end test: image -> generate -> download -> publish."""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.feishu_notify import send_text_message
from common.python_runtime import ensure_preferred_python_3_11

ensure_preferred_python_3_11()

from flash_longxia.poll_and_notify import process_single_task
from flash_longxia.zhenlongxia_workflow import load_saved_token, run_workflow
from upload import upload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OpenClaw 视频工作流端到端测试")
    parser.add_argument("image_path", help="用于测试的视频生成图片路径")
    parser.add_argument("--title", help="发布标题")
    parser.add_argument("--description", help="发布文案")
    parser.add_argument("--tags", default="自动测试,openclaw", help="逗号分隔标签")
    parser.add_argument("--token", help="帧龙虾 token；默认读取 token.txt")
    return parser.parse_args()


def notify(text: str) -> None:
    ok, detail = send_text_message(text, project_root=PROJECT_ROOT)
    if ok:
        print(f"[通知] 飞书文本通知已发送: {text}")
    else:
        print(f"[通知] 飞书文本通知失败: {detail}")


def main() -> int:
    args = parse_args()
    image_path = str(Path(args.image_path).expanduser().resolve())
    if not Path(image_path).exists():
        print(f"错误：图片不存在: {image_path}")
        return 1

    token = args.token or load_saved_token()
    if not token:
        print("错误：缺少 token，请设置 flash_longxia/token.txt 或传 --token")
        return 1

    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title = args.title or f"OpenClaw 自动流程测试 {datetime.now().strftime('%m%d %H%M')}"
    description = args.description or "OpenClaw 自动测试视频流程，请忽略。"
    tags = [item.strip() for item in args.tags.split(",") if item.strip()]

    notify(
        "OpenClaw 自动流程测试已开始。\n"
        f"开始时间: {started_at}\n"
        f"图片: {image_path}\n"
        "阶段 1/3: 发起图生视频"
    )

    task_id = run_workflow(
        [image_path],
        token=token,
        auto_confirm=True,
    )
    print(f"[E2E] 任务已提交: {task_id}")
    notify(
        "OpenClaw 自动流程测试已提交视频生成任务。\n"
        f"任务 ID: {task_id}\n"
        "阶段 2/3: 轮询并下载视频"
    )

    poll_status = process_single_task(task_id, token)
    if poll_status != 0:
        notify(
            "OpenClaw 自动流程测试失败。\n"
            f"任务 ID: {task_id}\n"
            "阶段 2/3 轮询或下载失败。"
        )
        return poll_status

    video_path = PROJECT_ROOT / "flash_longxia" / "output" / f"{task_id}.mp4"
    if not video_path.exists():
        notify(
            "OpenClaw 自动流程测试失败。\n"
            f"任务 ID: {task_id}\n"
            f"未找到下载视频: {video_path}"
        )
        return 1

    notify(
        "OpenClaw 自动流程测试进入发布阶段。\n"
        f"任务 ID: {task_id}\n"
        f"视频路径: {video_path}\n"
        "阶段 3/3: 视频号发布"
    )

    ok = upload(
        platform="shipinhao",
        video_path=str(video_path),
        title=title,
        description=description,
        tags=tags,
        account_name="default",
        handle_login=True,
        close_browser=True,
    )
    if ok:
        notify(
            "OpenClaw 自动流程测试已完成。\n"
            f"任务 ID: {task_id}\n"
            f"视频已发布到视频号。\n"
            f"标题: {title}"
        )
        print("[E2E] 端到端测试成功")
        return 0

    notify(
        "OpenClaw 自动流程测试在发布阶段失败。\n"
        f"任务 ID: {task_id}\n"
        f"标题: {title}"
    )
    print("[E2E] 发布失败")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
