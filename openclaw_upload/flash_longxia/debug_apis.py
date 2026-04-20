#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""帧龙虾 API 分步调试脚本"""

from pathlib import Path
import requests

BASE = "http://123.56.58.223:8081"
UPLOAD_URL = "http://123.56.58.223:8081/api/v1/file/upload"
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
})


def step1_upload(image_path: str):
    url = UPLOAD_URL
    with open(image_path, "rb") as f:
        files = {"file": (Path(image_path).name, f)}
        r = session.post(url, files=files, timeout=30)
    d = r.json()
    if d.get("code") in (200, 0):
        data = d.get("data")
        return data if isinstance(data, str) else (data.get("url") or data.get("path") or data.get("fileUrl"))
    print("失败:", d)
    return None


def step2_image_to_text(image_url: str):
    url = f"{BASE}/api/v1/aiMediaGenerations/imageToText"
    r = session.post(url, json={"imageType": 1, "urlList": [image_url]}, timeout=60)
    d = r.json()
    if d.get("code") in (200, 0):
        data = d.get("data")
        return data if isinstance(data, str) else (data.get("systemPrompt") or data.get("prompt") or data.get("text"))
    print("失败:", d)
    return None


def step4_get_by_id(video_id: str):
    url = f"{BASE}/api/v1/aiMediaGenerations/getById"
    r = session.get(url, params={"id": video_id}, timeout=15)
    d = r.json()
    print(f"Response code: {d.get('code')}, msg: {d.get('msg')}")
    return d.get("data")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, choices=[1, 2, 3, 4])
    ap.add_argument("--id")
    ap.add_argument("--token")
    ap.add_argument("--image")
    args = ap.parse_args()

    tok_path = Path(__file__).parent / "token.txt"
    tok = args.token or (tok_path.read_text(encoding="utf-8").strip() if tok_path.exists() else None)
    if not tok:
        print("请提供 --token 或将 Token 放入 token.txt")
        raise SystemExit(1)
    session.headers["token"] = tok

    if args.step == 1 and args.image:
        print(step1_upload(args.image))
    elif args.step == 2 and args.image:
        url = step1_upload(args.image)
        if url:
            print(step2_image_to_text(url))
    elif args.step == 4 and args.id:
        print(step4_get_by_id(args.id))
    else:
        print("参数不完整")
