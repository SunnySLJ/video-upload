#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频号自动化上传 - 统一入口

命令行：python upload.py <视频路径> <标题> [文案] [标签 1，标签 2,...]
API:    from upload import upload
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

_PROJECT_ROOT = Path(__file__).resolve().parent
_ROOT = _PROJECT_ROOT.parent.parent  # longxia_upload
for p in (_ROOT, _PROJECT_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from common.console import ensure_console_ready, safe_print

ensure_console_ready()

if sys.version_info < (3, 10):
    safe_print("错误：需要 Python 3.10+")
    sys.exit(1)

from conf import COOKIES_DIR
from shipinhao.main import shipinhao_setup, ShipinhaoVideo


def upload(
    video_path: str,
    title: str = "",
    description: str = "",
    tags: Optional[List[str]] = None,
    account_name: str = "default",
    handle_login: bool = True,
    publish_date: Union[datetime, int] = 0,
) -> bool:
    """
    上传视频到视频号

    :param video_path: 视频文件路径
    :param title: 标题（64 字内，空则自动生成）
    :param description: 文案（空则自动生成）
    :param tags: 话题标签，如 ["生活记录", "日常分享"]
    :param account_name: 账号名
    :param handle_login: 未登录时是否打开浏览器扫码
    :param publish_date: 定时发表时间（0=立即）
    :return: 是否成功
    """
    tags = tags or []
    tags = [t.strip() for t in tags if t.strip()][:10]
    video_path = str(Path(video_path).resolve())

    if not Path(video_path).exists():
        safe_print(f"错误：视频不存在：{video_path}")
        return False

    COOKIES_DIR.mkdir(parents=True, exist_ok=True)
    account_file = str(COOKIES_DIR / f"shipinhao_{account_name}.json")

    async def _do() -> bool:
        try:
            result = await shipinhao_setup(
                account_file, handle=handle_login, account_name=account_name
            )
            # 兼容新旧返回值：(ok, browser_tab) 或 (ok, browser_tab, screenshot_path)
            ok = result[0] if isinstance(result, tuple) else result
            browser_tab = result[1] if isinstance(result, tuple) and len(result) > 1 else None
            screenshot_path = result[2] if isinstance(result, tuple) and len(result) > 2 else None
        except Exception as e:
            import traceback
            safe_print(f"错误：登录异常：{e}")
            traceback.print_exc()
            return False
        if not ok:
            safe_print("错误：请先用微信扫码登录")
            if screenshot_path:
                safe_print(f"[+] 登录二维码已保存：{screenshot_path}")
            return False

        safe_print("登录完成，开始上传...")
        pub_date = publish_date if isinstance(publish_date, datetime) else 0
        app = ShipinhaoVideo(
            title=(title or "")[:64],
            file_path=video_path,
            tags=tags,
            publish_date=pub_date,
            account_file=account_file,
            description=description or "",
            account_name=account_name,
        )
        try:
            if browser_tab:
                ok = await app.upload(
                    existing_browser=browser_tab[0],
                    existing_tab=browser_tab[1],
                )
            else:
                ok = await app.upload()
        except Exception as e:
            import traceback
            safe_print(f"错误：上传异常：{e}")
            traceback.print_exc()
            return False
        return ok is True

    try:
        return asyncio.run(_do())
    except Exception as e:
        import traceback
        safe_print(f"错误：异常：{e}")
        traceback.print_exc()
        return False


def _main():
    import argparse

    parser = argparse.ArgumentParser(
        description="视频号自动化上传",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python upload.py /path/to/video.mp4 "标题" "文案" "标签 1，标签 2"
  python upload.py video.mp4 "" "" "生活记录，日常，vlog"   # 空标题/文案则自动生成
        """,
    )
    parser.add_argument("video_path", help="视频路径")
    parser.add_argument("title", nargs="?", default="", help="标题（空则自动生成）")
    parser.add_argument("description", nargs="?", default="", help="文案（空则自动生成）")
    parser.add_argument("tags", nargs="?", default="", help="话题，逗号分隔")
    parser.add_argument("--account", default="default", help="账号名")
    parser.add_argument("--no-login", action="store_true", help="未登录时不自动打开浏览器")
    args = parser.parse_args()

    tags_list = [t.strip() for t in args.tags.split(",") if t.strip()][:10]
    ok = upload(
        video_path=args.video_path,
        title=args.title,
        description=args.description,
        tags=tags_list,
        account_name=args.account,
        handle_login=not args.no_login,
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    _main()
