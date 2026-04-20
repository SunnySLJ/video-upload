#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""兼容旧入口：转发到 poll_and_notify.py 的单任务轮询实现。"""

from __future__ import annotations

import argparse
import sys

from flash_longxia.poll_and_notify import process_single_task


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按任务 ID 轮询视频状态并下载成片")
    parser.add_argument("task_id", help="任务 ID")
    parser.add_argument("--token", dest="token", help="接口 Token；默认读取 token.txt")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(f"[兼容入口] 开始轮询任务 {args.task_id}...")
    return process_single_task(args.task_id, args.token)


if __name__ == "__main__":
    sys.exit(main())
