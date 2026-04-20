#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Feishu notification helpers for login, generation, and publish workflows."""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_env_values(project_root: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    env_path = project_root / ".env"
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def normalize_receive_id(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if ":" in raw:
        prefix, payload = raw.split(":", 1)
        if prefix in {"user", "open_id", "openid"}:
            return payload.strip()
    return raw


def resolve_feishu_config(
    project_root: str | Path | None = None,
    *,
    receive_id: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    root = Path(project_root).expanduser().resolve() if project_root else _default_project_root()
    env_values = _load_env_values(root)
    app_id = (os.getenv("FEISHU_APP_ID") or env_values.get("FEISHU_APP_ID") or "").strip()
    app_secret = (os.getenv("FEISHU_APP_SECRET") or env_values.get("FEISHU_APP_SECRET") or "").strip()
    target = normalize_receive_id(
        receive_id
        or os.getenv("FEISHU_NOTIFY_TARGET")
        or env_values.get("FEISHU_NOTIFY_TARGET")
        or (os.getenv("FEISHU_ALLOWED_USERS") or "").split(",", 1)[0]
    )
    return (app_id or None, app_secret or None, target or None)


def get_tenant_access_token(
    project_root: str | Path | None = None,
    *,
    receive_id: str | None = None,
) -> tuple[str | None, str | None]:
    app_id, app_secret, _ = resolve_feishu_config(project_root, receive_id=receive_id)
    if not app_id or not app_secret:
        return None, "飞书凭证未配置"

    try:
        response = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=10,
        )
        data = response.json()
    except Exception as exc:
        return None, f"飞书获取 tenant_access_token 异常: {exc}"

    if data.get("code") != 0:
        return None, f"飞书获取 tenant_access_token 失败: {data}"
    return data.get("tenant_access_token"), None


def send_text_message(
    text: str,
    *,
    project_root: str | Path | None = None,
    receive_id: str | None = None,
) -> tuple[bool, str]:
    token, error = get_tenant_access_token(project_root, receive_id=receive_id)
    _, _, target = resolve_feishu_config(project_root, receive_id=receive_id)
    if error:
        return False, error
    if not target:
        return False, "飞书接收人未配置"

    try:
        response = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "receive_id": target,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            timeout=30,
        )
        data = response.json()
    except Exception as exc:
        return False, f"飞书文本通知异常: {exc}"

    if data.get("code") != 0:
        return False, f"飞书文本通知失败: status={response.status_code} body={response.text[:300]}"
    return True, "ok"


def send_image_message(
    image_path: str | Path,
    *,
    project_root: str | Path | None = None,
    receive_id: str | None = None,
) -> tuple[bool, str]:
    token, error = get_tenant_access_token(project_root, receive_id=receive_id)
    _, _, target = resolve_feishu_config(project_root, receive_id=receive_id)
    path = Path(image_path).expanduser().resolve()
    if error:
        return False, error
    if not target:
        return False, "飞书接收人未配置"
    if not path.exists():
        return False, f"图片不存在: {path}"

    try:
        with path.open("rb") as f_img:
            upload_resp = requests.post(
                "https://open.feishu.cn/open-apis/im/v1/images",
                headers={"Authorization": f"Bearer {token}"},
                files={"image": (path.name, f_img, "image/png")},
                data={"image_type": "message"},
                timeout=60,
            )
        upload_data = upload_resp.json()
    except Exception as exc:
        return False, f"飞书图片上传异常: {exc}"

    if upload_data.get("code") != 0:
        return False, f"飞书图片上传失败: status={upload_resp.status_code} body={upload_resp.text[:300]}"

    image_key = upload_data.get("data", {}).get("image_key")
    if not image_key:
        return False, f"飞书图片上传成功但缺少 image_key: {upload_data}"

    try:
        message_resp = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "receive_id": target,
                "msg_type": "image",
                "content": json.dumps({"image_key": image_key}, ensure_ascii=False),
            },
            timeout=60,
        )
        message_data = message_resp.json()
    except Exception as exc:
        return False, f"飞书图片消息异常: {exc}"

    if message_data.get("code") != 0:
        return False, f"飞书图片消息失败: status={message_resp.status_code} body={message_resp.text[:300]}"
    return True, "ok"


def send_file_message(
    file_path: str | Path,
    *,
    project_root: str | Path | None = None,
    receive_id: str | None = None,
) -> tuple[bool, str]:
    token, error = get_tenant_access_token(project_root, receive_id=receive_id)
    _, _, target = resolve_feishu_config(project_root, receive_id=receive_id)
    path = Path(file_path).expanduser().resolve()
    if error:
        return False, error
    if not target:
        return False, "飞书接收人未配置"
    if not path.exists():
        return False, f"文件不存在: {path}"

    try:
        with path.open("rb") as f_obj:
            upload_resp = requests.post(
                "https://open.feishu.cn/open-apis/im/v1/files",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (path.name, f_obj, "application/octet-stream")},
                data={"file_type": "stream", "file_name": path.name},
                timeout=120,
            )
        upload_data = upload_resp.json()
    except Exception as exc:
        return False, f"飞书文件上传异常: {exc}"

    if upload_data.get("code") != 0:
        return False, f"飞书文件上传失败: status={upload_resp.status_code} body={upload_resp.text[:300]}"

    file_key = upload_data.get("data", {}).get("file_key")
    if not file_key:
        return False, f"飞书文件上传成功但缺少 file_key: {upload_data}"

    try:
        message_resp = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "receive_id": target,
                "msg_type": "file",
                "content": json.dumps({"file_key": file_key}, ensure_ascii=False),
            },
            timeout=60,
        )
        message_data = message_resp.json()
    except Exception as exc:
        return False, f"飞书文件消息异常: {exc}"

    if message_data.get("code") != 0:
        return False, f"飞书文件消息失败: status={message_resp.status_code} body={message_resp.text[:300]}"
    return True, "ok"
