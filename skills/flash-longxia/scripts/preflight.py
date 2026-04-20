#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
flash-longxia skill 自检脚本

检查项：
1. 是否能定位 openclaw_upload 仓库
2. 是否存在 flash_longxia 工作流脚本
3. Python 3.11 / .venv 是否可用
4. config.yaml / token.txt 是否存在
5. 是否能导入工作流依赖
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from common import resolve_repo_root, resolve_venv_python


def print_result(label: str, ok: bool, detail: str) -> None:
    status = "OK" if ok else "FAIL"
    print(f"[{status}] {label}: {detail}")


def run_import_check(python_bin: Path, repo_root: Path) -> tuple[bool, str]:
    workflow_dir = repo_root / "flash_longxia"
    code = (
        "import sys; "
        f"sys.path.insert(0, {str(workflow_dir)!r}); "
        "import zhenlongxia_workflow; "
        "print('import-ok')"
    )
    try:
        result = subprocess.run(
            [str(python_bin), "-c", code],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except Exception as exc:
        return False, str(exc)

    if result.returncode == 0 and "import-ok" in result.stdout:
        return True, "工作流模块和依赖可导入"

    detail = (result.stderr or result.stdout or f"返回码 {result.returncode}").strip()
    return False, detail


def main() -> int:
    repo_root = resolve_repo_root()
    if not repo_root:
        print_result("repo_root", False, "找不到 openclaw_upload；请设置 OPENCLAW_UPLOAD_ROOT")
        return 1

    print_result("repo_root", True, str(repo_root))

    workflow = repo_root / "flash_longxia" / "zhenlongxia_workflow.py"
    config = repo_root / "flash_longxia" / "config.yaml"
    token = repo_root / "flash_longxia" / "token.txt"
    venv_python = resolve_venv_python(repo_root)
    token_ok = token.exists() and bool(token.read_text(encoding="utf-8").strip())

    print_result("workflow", workflow.exists(), str(workflow))
    print_result("config", config.exists(), str(config))
    print_result("token", token_ok, str(token))

    if venv_python is not None:
        print_result("python3.11", True, f"使用项目虚拟环境 {venv_python}")
        import_ok, detail = run_import_check(venv_python, repo_root)
        print_result("imports", import_ok, detail)
        return 0 if workflow.exists() and config.exists() and token_ok and import_ok else 1

    current_python_ok = sys.version_info[:2] == (3, 11)
    print_result(
        "python3.11",
        current_python_ok,
        f"未找到项目虚拟环境；当前解释器为 {sys.executable}",
    )
    if current_python_ok:
        import_ok, detail = run_import_check(Path(sys.executable), repo_root)
        print_result("imports", import_ok, detail)
        return 0 if workflow.exists() and config.exists() and token_ok and import_ok else 1

    print_result("imports", False, "未找到项目虚拟环境，且当前解释器不是 Python 3.11")
    return 1


if __name__ == "__main__":
    sys.exit(main())
