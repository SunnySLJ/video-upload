#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
帧龙虾视频生成 - 技能封装脚本

用法:
    python generate_video.py <图片路径1> [图片路径2] [图片路径3] [图片路径4] [选项]
    python generate_video.py --list-models [--token=xxx]
    python generate_video.py --list-templates [--mediaType=1] [--menuType=1] [--pageNum=1] [--pageSize=10] [--token=xxx]
    python generate_video.py --list-templates --mediaType=1 --menuType=1 --tabType=<上一步选择的tabType> [--pageNum=1] [--pageSize=10] [--token=xxx]

示例:
    python generate_video.py --list-models
    python generate_video.py --list-templates --mediaType=1 --menuType=1
    python generate_video.py --list-templates --mediaType=1 --menuType=1 --tabType=17
    python generate_video.py image.jpg --model=sora2-new --duration=10 --variants=1
    python generate_video.py image.jpg --tmpplateId=1001 --title=产品名 --yes
    python generate_video.py img1.jpg img2.jpg img3.jpg img4.jpg --model=grok_imagine --duration=10 --yes
    python generate_video.py image.jpg --yes
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

# 导入工作流模块
sys.path.insert(0, str(workflow_path.parent))
from zhenlongxia_workflow import (
    find_template_category,
    fetch_model_options,
    fetch_template_categories,
    fetch_template_options,
    load_config,
    load_saved_token,
    print_model_options,
    print_template_categories,
    print_template_options,
    run_workflow,
)

def main():
    if len(sys.argv) < 2:
        print("用法：python generate_video.py <图片路径1> [图片路径2] [图片路径3] [图片路径4] [选项]")
        print("      python generate_video.py --list-models [--token=xxx]")
        print("      python generate_video.py --list-templates [--mediaType=1] [--menuType=1] [--pageNum=1] [--pageSize=10] [--token=xxx]")
        print("      python generate_video.py --list-templates --mediaType=1 --menuType=1 --tabType=<上一步选择的tabType> [--pageNum=1] [--pageSize=10] [--token=xxx]")
        print()
        print("选项:")
        print("  --list-models     查询可用模型、时长与比例")
        print("  --list-templates  先查模板分类，再按 tabType 查询行业模板")
        print("  --mediaType=N     模板分类 mediaType，默认 1")
        print("  --menuType=N      模板列表 menuType，默认 1")
        print("  --token=xxx       Token（也可写入 token.txt）")
        print("  --tabType=N       模板 tabType；首轮不传，选定分类后再传")
        print("  --pageNum=N       模板页码，默认 1")
        print("  --pageSize=N      模板分页大小，默认 10")
        print("  --model=MODEL     模型值，来自模型配置接口")
        print("  --duration=N      时长，需匹配所选模型")
        print("  --aspectRatio=X   比例，需匹配所选模型")
        print("  --variants=N      变体数量")
        print("  --tmpplateId=ID   模板 ID，透传给 generateVideo")
        print("  --templateId=ID   模板 ID，兼容别名，透传为 tmpplateId")
        print("  --title=TEXT      模板标题/产品名称；交互选模板时默认取模板标题")
        print("  --yes             跳过发起视频前的人工确认")
        print("  说明              最多传 4 张图片，最终生成 1 个视频")
        sys.exit(1)

    image_paths: list[str] = []
    list_models = False
    list_templates = False

    # 解析参数
    kwargs = {}
    for arg in sys.argv[1:]:
        if arg == "--list-models":
            list_models = True
        elif arg == "--list-templates":
            list_templates = True
        elif arg.startswith("--token="):
            kwargs["token"] = arg.split("=", 1)[1]
        elif arg.startswith("--mediaType="):
            kwargs["media_type"] = int(arg.split("=", 1)[1])
        elif arg.startswith("--menuType="):
            kwargs["menu_type"] = int(arg.split("=", 1)[1])
        elif arg.startswith("--tabType="):
            kwargs["tab_type"] = int(arg.split("=", 1)[1])
        elif arg.startswith("--pageNum="):
            kwargs["page_num"] = int(arg.split("=", 1)[1])
        elif arg.startswith("--pageSize="):
            kwargs["page_size"] = int(arg.split("=", 1)[1])
        elif arg.startswith("--model="):
            kwargs["model"] = arg.split("=", 1)[1]
        elif arg.startswith("--duration="):
            kwargs["duration"] = int(arg.split("=", 1)[1])
        elif arg.startswith("--aspectRatio="):
            kwargs["aspectRatio"] = arg.split("=", 1)[1]
        elif arg.startswith("--variants="):
            kwargs["variants"] = int(arg.split("=", 1)[1])
        elif arg.startswith("--tmpplateId="):
            kwargs["tmpplateId"] = int(arg.split("=", 1)[1])
        elif arg.startswith("--templateId="):
            kwargs["tmpplateId"] = int(arg.split("=", 1)[1])
        elif arg.startswith("--title="):
            kwargs["title"] = arg.split("=", 1)[1]
        elif arg == "--yes":
            kwargs["auto_confirm"] = True
        elif not arg.startswith("--"):
            image_paths.append(arg)

    if list_models:
        config = load_config()
        base_url = config["base_url"].rstrip("/")
        model_config_url = config.get("model_config_url", f"{base_url}/api/v1/globalConfig/getModel")
        token_val = kwargs.get("token") or load_saved_token()
        if not token_val:
            print("错误：请将 Token 写入 flash_longxia/token.txt 或使用 --token=xxx")
            sys.exit(1)

        import requests

        session = requests.Session()
        session.headers.update({
            "token": token_val,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        })
        model_items = fetch_model_options(base_url, session, model_config_url=model_config_url)
        print_model_options(model_items)
        return

    if list_templates:
        config = load_config()
        base_url = config["base_url"].rstrip("/")
        token_val = kwargs.get("token") or load_saved_token()
        if not token_val:
            print("错误：请将 Token 写入 flash_longxia/token.txt 或使用 --token=xxx")
            sys.exit(1)

        import requests

        session = requests.Session()
        session.headers.update({
            "token": token_val,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        })
        category_items = fetch_template_categories(
            base_url,
            session,
            media_type=kwargs.get("media_type", 1),
        )
        print_template_categories(category_items)
        tab_type = kwargs.get("tab_type")
        if tab_type is None:
            print(
                f"未指定 tabType。先从上面的行业分类里选择一个 tabType，下一次再带 --tabType=<选中的tabType> 获取模板；当前 menuType={kwargs.get('menu_type', 1)}"
            )
            return

        category = find_template_category(category_items, tab_type=tab_type)
        mapped_title = (category or {}).get("tabName") or ""
        print(f"分类映射: title={mapped_title or '-'}, tabType={tab_type}")
        print(f"tabType={tab_type} 的行业模板:")
        template_items = fetch_template_options(
            base_url,
            session,
            page_num=kwargs.get("page_num", 1),
            page_size=kwargs.get("page_size", 10),
            tab_type=tab_type,
            menu_type=kwargs.get("menu_type", 1),
        )
        print_template_options(template_items)
        return

    if not image_paths:
        print("错误：缺少图片路径")
        sys.exit(1)
    if len(image_paths) > 4:
        print(f"错误：最多只支持 4 张图片，当前传入 {len(image_paths)} 张")
        sys.exit(1)

    # 运行工作流
    try:
        workflow_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key not in {"media_type", "menu_type", "page_num", "page_size", "tab_type"}
        }
        task_id = run_workflow(image_paths, **workflow_kwargs)
        print(f"\n已提交视频生成任务，任务 ID：{task_id}")
    except SystemExit as e:
        sys.exit(e.code)
    except Exception as e:
        print(f"\n❌ 错误：{e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
