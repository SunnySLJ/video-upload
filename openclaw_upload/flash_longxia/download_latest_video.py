#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按任务 id 下载已生成的视频
==========================

场景：主流程中断或仅需补下载时，用 generateVideo 返回的 id 调 getById，
从返回中取 mediaUrl / videoUrl 等字段，流式保存为 MP4。
"""

import sys

if sys.version_info[:2] not in {(3, 11), (3, 12)}:
    print(f"[错误] 当前 Python 版本是 {sys.version.split()[0]}，请改用 python3.11/3.12 运行。")
    sys.exit(1)

from flash_longxia.zhenlongxia_workflow import fetch_generated_video


def main():
    if len(sys.argv) < 2:
        print("用法: python download_latest_video.py <视频id>")
        return

    video_id = sys.argv[1]
    path = fetch_generated_video(id=video_id)
    print(f"已保存: {path}")


if __name__ == "__main__":
    main()
