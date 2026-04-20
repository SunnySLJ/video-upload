#!/usr/bin/env python3
"""兼容旧模板入口：转发到统一轮询实现。"""

from __future__ import annotations

import os
import sys

from poll_and_notify import process_single_task


def main() -> int:
    if len(sys.argv) < 3:
        print("用法：python3 poll_task_template.py <TASK_ID> <TOKEN> [FEISHU_TARGET]")
        return 1

    task_id = sys.argv[1]
    token = sys.argv[2]
    feishu_target = sys.argv[3] if len(sys.argv) > 3 else ""
    if feishu_target:
        os.environ["FLASH_LONGXIA_FEISHU_TARGET"] = feishu_target

    print(f"[兼容入口] 开始轮询任务 {task_id}...")
    return process_single_task(task_id, token)


if __name__ == "__main__":
    sys.exit(main())
