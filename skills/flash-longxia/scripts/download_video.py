#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按任务 ID 下载帧龙虾已生成的视频

用法:
    python download_video.py <任务ID> [--token=xxx] [--output-dir=目录] [--filename=文件名]
    python download_video.py <任务ID> --check-only [--token=xxx]
"""

import sys
import os
from pathlib import Path

def resolve_repo_root() -> Path | None:
    """优先从 cwd、环境变量和 OpenClaw 常见目录定位仓库。"""
    candidates: list[Path] = []

    env_root = os.environ.get("OPENCLAW_UPLOAD_ROOT")
    if env_root:
        candidates.append(Path(env_root).expanduser())

    cwd = Path.cwd().resolve()
    candidates.extend([cwd, *cwd.parents])

    script_dir = Path(__file__).resolve().parent
    candidates.extend([script_dir, *script_dir.parents])

    home = Path.home()
    candidates.extend([
        home / ".openclaw" / "workspace" / "openclaw_upload",
        home / "Desktop" / "openclaw_upload",
        home / "workspace" / "openclaw_upload",
        home / "openclaw_upload",
    ])

    for candidate in candidates:
        try:
            candidate = candidate.resolve()
        except FileNotFoundError:
            continue

        workflow = candidate / "flash_longxia" / "zhenlongxia_workflow.py"
        if workflow.exists():
            return candidate
    return None


repo_root = resolve_repo_root()
if repo_root is None:
    print("错误：找不到 openclaw_upload 仓库根目录，请在项目目录运行，或设置 OPENCLAW_UPLOAD_ROOT 指向包含 flash_longxia 的目录")
    sys.exit(1)


def ensure_project_venv() -> None:
    """优先切换到仓库内虚拟环境 Python，避免依赖缺失。"""
    venv_root = None
    venv_python = None
    for name in (".venv", "venv"):
        candidate_root = repo_root / name
        for candidate_python in (
            candidate_root / "bin" / "python3.11",
            candidate_root / "bin" / "python3",
            candidate_root / "bin" / "python",
            candidate_root / "Scripts" / "python.exe",
            candidate_root / "Scripts" / "python",
        ):
            if candidate_python.exists():
                venv_root = candidate_root
                venv_python = candidate_python
                break
        if venv_python is not None:
            break

    if venv_root is None or venv_python is None:
        return

    if Path(sys.prefix).resolve() == venv_root.resolve():
        return

    os.execv(str(venv_python), [str(venv_python), *sys.argv])


ensure_project_venv()

if sys.version_info[:2] != (3, 11):
    print(f"错误：当前 Python 版本是 {sys.version.split()[0]}，请改用 python3.11 运行")
    sys.exit(1)

workflow_path = repo_root / "flash_longxia" / "zhenlongxia_workflow.py"

if not workflow_path.exists():
    print(f"错误：找不到工作流脚本 {workflow_path}")
    sys.exit(1)

sys.path.insert(0, str(workflow_path.parent))
from zhenlongxia_workflow import (
    _extract_rep_status,
    _extract_video_url_from_rep_msg,
    fetch_generated_video,
    fetch_video_by_id,
    get_video_url,
    load_config,
    load_saved_token,
    requests,
)


def print_task_summary(task_id: str, token: str | None = None) -> int:
    """查询任务状态并输出摘要。"""
    config = load_config()
    token_val = token or load_saved_token()
    if not token_val:
        print("错误：请将 Token 写入 flash_longxia/token.txt 或使用 --token=xxx")
        return 1

    session = requests.Session()
    session.headers.update({
        "token": token_val,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    })

    record = fetch_video_by_id(config["base_url"].rstrip("/"), session, task_id)
    if not record:
        print(f"错误：未查询到任务 {task_id} 的视频信息")
        return 1

    top_status = record.get("status") or record.get("videoStatus") or record.get("taskStatus")
    rep_status = _extract_rep_status(record)
    video_url = get_video_url(record) or _extract_video_url_from_rep_msg(record)

    print(f"任务ID: {task_id}")
    print(f"顶层状态: {top_status}")
    print(f"下游状态: {rep_status}")
    print(f"视频地址: {video_url or '无'}")

    if video_url and str(top_status) not in {"2", "completed", "success", "SUCCESS"}:
        print("说明: 顶层状态未同步，但已返回视频地址，可直接下载")

    return 0


def main():
    if len(sys.argv) < 2:
        print("用法：python download_video.py <任务ID> [--token=xxx] [--output-dir=目录] [--filename=文件名]")
        print("      python download_video.py <任务ID> --check-only [--token=xxx]")
        sys.exit(1)

    task_id = None
    token = None
    output_dir = None
    filename = None
    check_only = False
    for arg in sys.argv[1:]:
        if arg.startswith("--token="):
            token = arg.split("=", 1)[1]
        elif arg.startswith("--output-dir="):
            output_dir = arg.split("=", 1)[1]
        elif arg.startswith("--filename="):
            filename = arg.split("=", 1)[1]
        elif arg == "--check-only":
            check_only = True
        elif not arg.startswith("--") and task_id is None:
            task_id = arg.strip()

    if not task_id:
        print("错误：任务 ID 不能为空")
        sys.exit(1)

    if check_only:
        sys.exit(print_task_summary(task_id, token=token))

    try:
        local_path = fetch_generated_video(
            id=task_id,
            token=token,
            output_dir=output_dir,
            filename=filename,
        )
        print(f"已下载视频：{local_path}")
    except SystemExit as e:
        sys.exit(e.code)
    except Exception as e:
        print(f"错误：{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
