#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""设备号验证（预留）"""

from __future__ import annotations
import uuid
import requests


def get_mac_address() -> str:
    mac = uuid.getnode()
    return ":".join(("%012X" % mac)[i : i + 2] for i in range(0, 12, 2))


def verify_device_permission(mac: str, base_url: str, session: requests.Session, *, api_path: str | None = None, method: str = "GET") -> bool:
    path = api_path or "/api/v1/device/verify"
    url = f"{base_url.rstrip('/')}{path}"
    params = {"mac": mac}
    try:
        if method.upper() == "GET":
            r = session.get(url, params=params, timeout=15)
        else:
            r = session.post(url, json=params, timeout=15)
        d = r.json()
        if d.get("code") in (200, 0):
            data = d.get("data")
            if isinstance(data, dict):
                return bool(data.get("permitted", data.get("allowed", True)))
            return True
        return False
    except Exception:
        return False


def run_device_verify(base_url: str, session: requests.Session, *, api_path: str | None = None) -> bool:
    mac = get_mac_address()
    print(f"[设备验证] 本机 MAC: {mac}")
    ok = verify_device_permission(mac, base_url, session, api_path=api_path)
    print("[设备验证] 通过" if ok else "[设备验证] 未通过")
    return ok


if __name__ == "__main__":
    print("MAC:", get_mac_address())
