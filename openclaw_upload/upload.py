#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频号上传统一入口。
"""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from common.console import ensure_console_ready, safe_print
from common.feishu_notify import send_text_message
from common.platform_auth import check_platform_login, ensure_platform_login
from common.python_runtime import ensure_preferred_python_3_11

try:
    from scripts.platform_login import close_connect_browser
except ImportError:
    close_connect_browser = None

ensure_preferred_python_3_11()
ensure_console_ready()

if sys.version_info < (3, 10):
    safe_print("错误: 需要 Python 3.10+")
    raise SystemExit(1)


SUPPORTED_PLATFORM = "shipinhao"
SUPPORTED_PLATFORMS = (SUPPORTED_PLATFORM,)


def _notify_publish_status(text: str) -> None:
    ok, detail = send_text_message(text, project_root=_PROJECT_ROOT)
    if ok:
        safe_print(f"[通知] 飞书文本通知已发送：{text}")
    else:
        safe_print(f"[通知] 飞书文本通知发送失败：{detail}")


def _dispatch_shipinhao(
    video_path: str,
    title: str,
    description: str,
    tags: list[str],
    **kwargs,
) -> bool:
    from platforms.shipinhao_upload.api import upload_to_shipinhao

    return upload_to_shipinhao(
        video_path=video_path,
        title=title,
        description=description,
        tags=tags,
        **kwargs,
    )


_DISPATCH = {
    SUPPORTED_PLATFORM: _dispatch_shipinhao,
}


def _normalize_platform(platform: str) -> str:
    return (platform or "").strip().lower()


def upload(
    platform: str,
    video_path: str,
    title: str = "",
    description: str = "",
    tags: list[str] | None = None,
    account_name: str = "default",
    handle_login: bool = True,
    login_only: bool = False,
    close_browser: bool = True,
) -> bool:
    """
    统一上传入口（当前仅支持视频号）。
    """
    normalized_platform = _normalize_platform(platform)
    if normalized_platform not in _DISPATCH:
        safe_print(
            f"错误: 当前只开放视频号发布，收到平台: {platform or '<empty>'}。"
        )
        safe_print("请使用 --platform shipinhao。")
        return False

    normalized_tags = [tag.strip() for tag in (tags or []) if tag and tag.strip()]
    _notify_publish_status(
        "OpenClaw 已开始执行视频号发布流程。\n"
        f"视频: {video_path}\n"
        f"标题: {title or '自动生成'}"
    )

    if handle_login:
        ok, msg = ensure_platform_login(
            normalized_platform,
            project_root=_PROJECT_ROOT,
            timeout=300,
        )
    else:
        ok, msg = check_platform_login(
            normalized_platform,
            project_root=_PROJECT_ROOT,
            passive=True,
        )

    if not ok:
        safe_print(f"错误: {msg}")
        _notify_publish_status(
            "OpenClaw 视频号发布流程失败。\n"
            f"阶段: 登录检查\n"
            f"原因: {msg}"
        )
        return False

    safe_print(msg)

    if login_only:
        safe_print("视频号登录检查完成，按要求不继续发布。")
        _notify_publish_status("OpenClaw 视频号登录检查完成，可继续发布。")
        return True

    ok = _DISPATCH[normalized_platform](
        video_path=video_path,
        title=title,
        description=description,
        tags=normalized_tags,
        account_name=account_name,
        handle_login=False,
    )

    if ok and close_connect_browser and close_browser:
        safe_print("视频号发布成功，准备关闭 connect Chrome...")
        try:
            close_connect_browser(normalized_platform)
            safe_print("视频号 connect Chrome 已关闭")
        except Exception as exc:
            safe_print(f"警告: 关闭浏览器失败: {exc}")

    if ok:
        _notify_publish_status(
            "OpenClaw 视频号发布成功。\n"
            f"视频: {video_path}\n"
            f"标题: {title or '自动生成'}"
        )
    else:
        _notify_publish_status(
            "OpenClaw 视频号发布失败。\n"
            f"视频: {video_path}\n"
            f"标题: {title or '自动生成'}"
        )

    return ok


def _build_parser():
    import argparse

    parser = argparse.ArgumentParser(
        description="视频号上传统一入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python upload.py --platform shipinhao video.mp4 "标题" "文案" "标签1,标签2"
        """.strip(),
    )
    parser.add_argument(
        "--platform",
        "-p",
        required=True,
        choices=SUPPORTED_PLATFORMS,
        help="目标平台；当前仅支持 shipinhao",
    )
    parser.add_argument("video_path", help="视频文件路径")
    parser.add_argument("title", nargs="?", default="", help="标题")
    parser.add_argument("description", nargs="?", default="", help="文案")
    parser.add_argument("tags", nargs="?", default="", help="标签，逗号分隔")
    parser.add_argument("--account", default="default", help="账号名")
    parser.add_argument(
        "--no-login",
        action="store_true",
        help="若当前会话不可复用，则不自动拉起登录流程",
    )
    parser.add_argument(
        "--login-only",
        action="store_true",
        help="只完成登录检查/补登录，不继续发布",
    )
    return parser


def _main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    tags = [tag.strip() for tag in args.tags.split(",") if tag.strip()]
    ok = upload(
        platform=args.platform,
        video_path=args.video_path,
        title=args.title,
        description=args.description,
        tags=tags,
        account_name=args.account,
        handle_login=not args.no_login,
        login_only=args.login_only,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_main())


# AFTER_UPLOAD_NOTIFY: best-effort notification hook lives in the outer orchestrator.
