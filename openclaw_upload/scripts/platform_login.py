#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Connect-login helper used by the auth skill.

Legacy multi-platform mappings are kept commented for reference only.
The current project intentionally exposes login checking/relogin for
Shipinhao only.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform as sys_platform
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import websockets

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from common.feishu_notify import send_image_message, send_text_message
from common.python_runtime import ensure_preferred_python_3_11

ensure_preferred_python_3_11()


def _cdp_port() -> int:
    return int(os.environ.get("CDP_PORT", "9226"))


def _cdp_host() -> str:
    return os.environ.get("CDP_HOST", "127.0.0.1")


PLATFORMS = {
    # 历史平台配置先保留注释，避免端口/目录映射丢失；
    # 当前项目的“检查登录/补登录”入口只支持视频号。
    # "douyin": {
    #     "label": "抖音",
    #     "port": 9224,
    #     "profile_dir": "chrome_connect_dy",
    #     "url": "https://creator.douyin.com/creator-micro/content/upload",
    #     "ready_markers": (
    #         "creator.douyin.com/creator-micro/content/upload",
    #         "creator.douyin.com/creator-micro/home",
    #     ),
    #     "login_markers": ("login", "passport", "扫码登录", "手机号登录"),
    #     "qr_switch_texts": ("扫码登录",),
    #     "required_cookie_names": (
    #         "sessionid",
    #         "sessionid_ss",
    #         "sid_tt",
    #         "uid_tt",
    #         "sid_guard",
    #     ),
    #     "required_cookie_hits": 2,
    # },
    # "xiaohongshu": {
    #     "label": "小红书",
    #     "port": 9223,
    #     "profile_dir": "chrome_connect_xhs",
    #     "url": "https://creator.xiaohongshu.com/publish/publish?from=homepage&target=video",
    #     "ready_markers": (
    #         "creator.xiaohongshu.com/publish/publish",
    #         "creator.xiaohongshu.com/creator/home",
    #         "creator.xiaohongshu.com/publish/notemanager",
    #         "creator.xiaohongshu.com/content/upload",
    #     ),
    #     "login_markers": ("login", "短信登录", "扫码登录"),
    #     "qr_switch_texts": ("扫码登录",),
    #     "required_cookie_names": (
    #         "galaxy_creator_session_id",
    #         "access-token-creator.xiaohongshu.com",
    #         "galaxy.creator.beaker.session.id",
    #         "customer-sso-sid",
    #         "x-user-id-creator.xiaohongshu.com",
    #     ),
    #     "required_cookie_hits": 2,
    # },
    # "kuaishou": {
    #     "label": "快手",
    #     "port": 9225,
    #     "profile_dir": "chrome_connect_ks",
    #     "url": "https://cp.kuaishou.com/article/publish/video",
    #     "ready_markers": (
    #         "cp.kuaishou.com/article/publish/video",
    #         "cp.kuaishou.com/article/publish",
    #         "cp.kuaishou.com/home",
    #     ),
    #     "login_markers": ("login", "passport", "扫码登录"),
    #     "qr_switch_texts": ("扫码登录",),
    #     "required_cookie_names": (
    #         "kuaishou.web.cp.api_st",
    #         "kuaishou.web.cp.api_ph",
    #         "userId",
    #         "bUserId",
    #     ),
    #     "required_cookie_hits": 2,
    # },
    "shipinhao": {
        "label": "视频号",
        "port": _cdp_port(),
        "profile_dir": "chrome_connect_sph",
        "url": "https://channels.weixin.qq.com/platform/post/create",
        "ready_markers": ("channels.weixin.qq.com/platform/post/create",),
        "login_markers": ("login", "mp.weixin.qq.com", "微信扫码", "扫码登录"),
        "qr_switch_texts": (),
        "required_cookie_names": (
            "sessionid",
            "wxuin",
        ),
        "required_cookie_hits": 2,
    },
}

CLI_PLATFORMS = (
    # CLI 层只暴露视频号，避免外部继续把本脚本当成四平台登录检查入口。
    # "douyin",
    # "xiaohongshu",
    # "kuaishou",
    "shipinhao",
)

_PROJECT_ROOT_OVERRIDE: Path | None = None


def project_root() -> Path:
    if _PROJECT_ROOT_OVERRIDE is not None:
        return _PROJECT_ROOT_OVERRIDE.resolve()
    env_root = (os.environ.get("OPENCLAW_UPLOAD_ROOT") or "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def chrome_path() -> str:
    env_path = os.environ.get("LOCAL_CHROME_PATH")
    if env_path:
        return env_path
    system = sys_platform.system()
    if system == "Darwin":
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if system == "Windows":
        for p in (
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ):
            if Path(p).exists():
                return p
        return "chrome"
    return "google-chrome"


def profile_dir_for(platform_name: str, root: Path | None = None) -> Path:
    # Support standalone cookies directory via CHROME_COOKIES_ROOT env var
    cookies_root = os.environ.get("CHROME_COOKIES_ROOT")
    if cookies_root:
        return Path(cookies_root) / PLATFORMS[platform_name]["profile_dir"]
    root = root or project_root()
    return root / "cookies" / PLATFORMS[platform_name]["profile_dir"]


def _cdp_host() -> str:
    """Return the host to connect to for Chrome DevTools Protocol.

    Defaults to 127.0.0.1, but can be overridden via CDP_HOST env var
    (e.g. set to 'host.docker.internal' when running inside Docker).
    """
    return os.environ.get("CDP_HOST", "127.0.0.1")


def is_port_listening(port: int, host: str = None) -> bool:
    if host is None:
        host = _cdp_host()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


def _list_listening_pids(port: int) -> list[int]:
    system = sys_platform.system()
    try:
        if system == "Windows":
            result = _run_text_command(
                ["netstat", "-ano", "-p", "tcp"],
                timeout=3,
            )
            pids: list[int] = []
            for line in (result.stdout or "").splitlines():
                parts = line.split()
                if len(parts) < 5 or parts[0].upper() != "TCP":
                    continue
                if parts[1].rsplit(":", 1)[-1] != str(port):
                    continue
                if parts[3].upper() != "LISTENING":
                    continue
                if parts[4].isdigit():
                    pids.append(int(parts[4]))
            return sorted(set(pids))

        result = _run_text_command(
            ["lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"],
            timeout=3,
        )
    except Exception:
        return []

    pids: list[int] = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return sorted(set(pids))


def _normalize_compare_path(value: str | Path) -> str:
    path = Path(value).expanduser()
    try:
        normalized = path.resolve()
    except Exception:
        normalized = path
    result = str(normalized)
    if sys_platform.system() == "Windows":
        result = result.lower()
    return result.rstrip("\\/")


def _extract_user_data_dir(command_line: str) -> str:
    if not command_line:
        return ""
    patterns = (
        r'--user-data-dir="([^"]+)"',
        r"--user-data-dir='([^']+)'",
        r"--user-data-dir=([^\s]+)",
        r'--user-data-dir\s+"([^"]+)"',
        r"--user-data-dir\s+'([^']+)'",
        r"--user-data-dir\s+([^\s]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, command_line)
        if match:
            return (match.group(1) or "").strip()
    return ""


def _process_command_line(pid: int) -> str:
    system = sys_platform.system()
    try:
        if system == "Windows":
            result = _run_text_command(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(Get-CimInstance Win32_Process -Filter \"ProcessId = {pid}\").CommandLine",
                ],
                timeout=6,
            )
            return (result.stdout or "").strip()
        result = _run_text_command(["ps", "-p", str(pid), "-o", "command="], timeout=6)
        return (result.stdout or "").strip()
    except Exception:
        return ""


def validate_connect_profile_dir(
    platform_name: str,
    root: Path | None = None,
) -> tuple[bool, str]:
    actual_root = (root or project_root()).resolve()
    expected_dir = profile_dir_for(platform_name, actual_root)
    expected_norm = _normalize_compare_path(expected_dir)
    cfg = PLATFORMS[platform_name]

    if expected_dir.exists() and not expected_dir.is_dir():
        return False, f"{cfg['label']} 登录目录不是文件夹: {expected_dir}"

    if not is_port_listening(cfg["port"]):
        return True, f"{cfg['label']} connect 端口 {cfg['port']} 当前未监听，预期目录: {expected_dir}"

    pids = _list_listening_pids(cfg["port"])
    if not pids:
        return False, f"{cfg['label']} connect 端口 {cfg['port']} 正在监听，但无法定位监听进程"

    checked_cmdline = False
    mismatches: list[str] = []
    for pid in pids:
        command_line = _process_command_line(pid)
        if not command_line:
            continue
        checked_cmdline = True
        actual_dir = _extract_user_data_dir(command_line)
        if not actual_dir:
            mismatches.append(f"pid={pid} 未发现 --user-data-dir")
            continue
        actual_norm = _normalize_compare_path(actual_dir)
        if actual_norm == expected_norm:
            return True, f"{cfg['label']} connect 目录校验通过: {expected_dir}"
        mismatches.append(f"pid={pid} 使用 {actual_dir}")

    if checked_cmdline:
        detail = "；".join(mismatches) if mismatches else "未解析到有效的 --user-data-dir"
        return False, (
            f"{cfg['label']} connect 目录不匹配，预期应为 {expected_dir}，"
            f"实际监听进程为: {detail}"
        )

    return False, f"{cfg['label']} 无法读取 9226 监听进程命令行，不能确认登录目录是否正确"


def close_connect_browser(platform_name: str, timeout: float = 8.0) -> bool:
    port = PLATFORMS[platform_name]["port"]
    pids = _list_listening_pids(port)
    if not pids:
        return False
    system = sys_platform.system()
    for pid in sorted(set(pids)):
        try:
            if system == "Windows":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            else:
                os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        except Exception:
            return False
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not is_port_listening(port):
            return True
        time.sleep(0.2)
    return not is_port_listening(port)


def _devtools_get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "platform-login-helper"})
    with urllib.request.urlopen(req, timeout=2) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _run_node(command: list[str], timeout: int, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _run_text_command(command: list[str], timeout: int = 5) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def devtools_tabs(port: int) -> list[dict]:
    try:
        return _devtools_get(f"http://{_cdp_host()}:{port}/json/list")
    except Exception:
        return []


async def _cdp_fetch_cookies(ws_url: str, base_url: str, timeout: float = 5.0) -> list[dict]:
    async with websockets.connect(ws_url, open_timeout=timeout, close_timeout=timeout) as ws:
        req_id = 1
        await ws.send(json.dumps({
            "id": req_id,
            "method": "Network.getCookies",
            "params": {"urls": [base_url]},
        }))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            msg = json.loads(raw)
            if msg.get("id") == req_id:
                return msg.get("result", {}).get("cookies", [])


async def _cdp_runtime_evaluate(ws_url: str, expression: str, timeout: float = 5.0):
    async with websockets.connect(ws_url, open_timeout=timeout, close_timeout=timeout) as ws:
        req_id = 1
        await ws.send(json.dumps({"id": req_id, "method": "Runtime.enable", "params": {}}))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            msg = json.loads(raw)
            if msg.get("id") == req_id:
                break
        req_id = 2
        await ws.send(json.dumps({
            "id": req_id,
            "method": "Runtime.evaluate",
            "params": {"expression": expression, "returnByValue": True},
        }))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            msg = json.loads(raw)
            if msg.get("id") == req_id:
                return msg.get("result", {}).get("result", {}).get("value")


def _has_required_login_cookies(platform_name: str, tab: dict) -> bool:
    cfg = PLATFORMS[platform_name]
    cookie_names = tuple(cfg.get("required_cookie_names", ()))
    min_hits = int(cfg.get("required_cookie_hits", 0) or 0)
    if not cookie_names or min_hits <= 0:
        return True
    ws_url = tab.get("webSocketDebuggerUrl") or ""
    base_url = tab.get("url") or cfg["url"]
    if not ws_url or not base_url:
        return False
    try:
        cookies = asyncio.run(_cdp_fetch_cookies(ws_url, base_url, timeout=5.0))
    except Exception:
        return False
    names = {
        str(cookie.get("name") or "")
        for cookie in cookies
        if cookie.get("name") and cookie.get("value")
    }
    hits = sum(1 for name in cookie_names if name in names)
    return hits >= min_hits


def ensure_page_target(platform_name: str, retries: int = 3, wait_seconds: float = 1.0) -> list[dict]:
    port = PLATFORMS[platform_name]["port"]
    tabs = devtools_tabs(port)
    if any(tab.get("type") == "page" for tab in tabs):
        return tabs
    for _ in range(retries):
        open_target_tab(platform_name)
        time.sleep(wait_seconds)
        tabs = devtools_tabs(port)
        if any(tab.get("type") == "page" for tab in tabs):
            return tabs
    return tabs


def open_target_tab(platform_name: str) -> bool:
    port = PLATFORMS[platform_name]["port"]
    tabs = devtools_tabs(port)
    if any(tab.get("type") == "page" for tab in tabs):
        return False
    url = PLATFORMS[platform_name]["url"]
    encoded = urllib.parse.quote(url, safe=":/?&=%")
    try:
        req = urllib.request.Request(
            f"http://{_cdp_host()}:{port}/json/new?{encoded}",
            method="PUT",
            headers={"User-Agent": "platform-login-helper"},
        )
        with urllib.request.urlopen(req, timeout=3):
            return True
    except urllib.error.HTTPError:
        return False
    except Exception:
        return False


def launch_connect_chrome(platform_name: str, root: Path | None = None) -> None:
    root = root or project_root()
    cfg = PLATFORMS[platform_name]
    profile_dir = profile_dir_for(platform_name, root)
    profile_dir.mkdir(parents=True, exist_ok=True)
    port = cfg["port"]

    ssh_host = os.environ.get("SSH_HOST")
    if ssh_host:
        ssh_user = os.environ.get("SSH_USER", "root")
        ssh_port = os.environ.get("SSH_PORT", "22")
        ssh_key = "/root/.ssh/id_ed25519_hermes"
        host_profile_dir = str(profile_dir).replace("/data/", "/Users/h/hermes-agent/data-default/")
        chrome_cmd = (
            f'/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome '
            f'--remote-debugging-port={port} '
            f'--remote-allow-origins=* '
            f'--user-data-dir="{host_profile_dir}" '
            f'--start-maximized '
            f'{cfg["url"]}'
        )
        ssh_cmd = f'ssh -o StrictHostKeyChecking=no -p {ssh_port} -i {ssh_key} {ssh_user}@{ssh_host} "nohup {chrome_cmd} &>/dev/null &"'
        subprocess.Popen(ssh_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return

    system = sys_platform.system()
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if system == "Darwin":
        args = [
            "open",
            "-na",
            "Google Chrome",
            "--args",
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={profile_dir}",
            "--start-maximized",
            cfg["url"],
        ]
        kwargs["start_new_session"] = True
    else:
        args = [
            chrome_path(),
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={profile_dir}",
            "--start-maximized",
            cfg["url"],
        ]
        if system == "Windows":
            kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)
        else:
            kwargs["start_new_session"] = True
    subprocess.Popen(args, **kwargs)


def _send_feishu_notification(platform_name: str, screenshot_path: str) -> bool:
    """登录页打开后发送飞书通知，提醒用户扫码登录。"""
    label = PLATFORMS[platform_name]["label"]
    if not os.path.exists(screenshot_path):
        return False

    try:
        notify_text = (
            f"视频号登录已过期，请扫码登录。\n"
            f"扫码成功后系统会自动恢复发布。"
        )
        text_ok, text_detail = send_text_message(
            notify_text,
            project_root=_PROJECT_ROOT,
        )
        if text_ok:
            print(f"[通知] 飞书文本通知已发送")
        else:
            print(f"[通知] 飞书文本通知发送失败：{text_detail}")

        image_ok, image_detail = send_image_message(
            screenshot_path,
            project_root=_PROJECT_ROOT,
        )
        if not image_ok:
            print(f"[通知] 飞书图片消息发送失败：{image_detail}")
            return False

        print(f"{label} 登录二维码已发送到飞书")
        return True
    except Exception as e:
        print(f"{label} 发送异常：{e}")
        return False


def _extract_qr_image_via_cdp(platform_name: str, output_path: str) -> str | None:
    cfg = PLATFORMS[platform_name]
    page_tabs = [tab for tab in devtools_tabs(cfg["port"]) if tab.get("type") == "page"]
    if not page_tabs:
        return None

    def tab_rank(tab: dict) -> int:
        url = (tab.get("url") or "").lower()
        if platform_name == "douyin":
            if "/login" in url:
                return 0
            if "creator.douyin.com" in url:
                return 1
        if platform_name == "kuaishou":
            if "passport.kuaishou.com" in url:
                return 0
            if "cp.kuaishou.com" in url:
                return 1
        if platform_name == "shipinhao":
            if "login-for-iframe" in url:
                return 0
            if url.endswith("/login.html"):
                return 1
            if "channels.weixin.qq.com" in url:
                return 2
        return 10

    page_tabs.sort(key=tab_rank)
    if platform_name == "douyin":
        douyin_script = r"""
const fs = require("fs");
const wsUrl = process.argv[1];
const outputPath = process.argv[2];
const ws = new WebSocket(wsUrl);
let id = 0;
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const msgId = ++id;
    const onMessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (data.id === msgId) {
        ws.removeEventListener("message", onMessage);
        if (data.error) reject(data.error);
        else resolve(data.result);
      }
    };
    ws.addEventListener("message", onMessage);
    ws.send(JSON.stringify({ id: msgId, method, params }));
  });
}
ws.addEventListener("open", async () => {
  try {
    await send("Runtime.enable");
    await send("Page.enable");
    const expr = `(() => {
      const text = document.body.innerText || '';
      const onLoginPage = /扫码登录|手机号登录|验证码登录|登录抖音创作者中心/.test(text);
      if (!onLoginPage) {
        return { kind: 'not-login-page' };
      }
      if (!/扫码登录/.test(text)) {
        const scanTab = [...document.querySelectorAll('div,span,button,a,p')].find(el =>
          (el.innerText || el.textContent || '').trim() === '扫码登录'
        );
        if (scanTab) {
          scanTab.click();
          return { kind: 'retry-needed', waitMs: 1200 };
        }
      }
      if (/已失效|二维码失效|二维码已失效/.test(text)) {
        const retry = [...document.querySelectorAll('button,div,span,a,p')].find(el =>
          /刷新|重新获取|重新加载/.test((el.innerText || el.textContent || '').trim())
        );
        if (retry) {
          retry.click();
          return { kind: 'retry-needed', waitMs: 1200 };
        }
      }
      const primary = Array.from(document.querySelectorAll('img[class*=qrcode_img]'));
      const fallback = Array.from(document.images).filter(img =>
        (img.src || '').startsWith('data:image/') && img.naturalWidth >= 180 && img.naturalHeight >= 180
      );
      const candidates = [...primary, ...fallback];
      const uniq = [];
      const seen = new Set();
      for (const img of candidates) {
        const key = (img.currentSrc || img.src || '') + '|' + String(img.className || '');
        if (!seen.has(key)) {
          seen.add(key);
          uniq.push(img);
        }
      }
      const img = uniq
        .map(img => {
          const rect = img.getBoundingClientRect();
          const cls = String(img.className || '');
          let score = 0;
          if (/qrcode_img/.test(cls)) score += 100;
          if ((img.src || '').startsWith('data:image/png')) score += 30;
          if (img.naturalWidth >= 256 && img.naturalHeight >= 256) score += 20;
          if (rect.width >= 180 && rect.height >= 180) score += 20;
          return { img, rect, score };
        })
        .sort((a, b) => b.score - a.score)[0];
      if (!img) {
        if (/如何扫码|打开「抖音APP」/.test(text)) {
          return { kind: 'retry-needed', waitMs: 1500 };
        }
        return null;
      }
      const rect = img.rect;
      const src = img.img.currentSrc || img.img.src || '';
      if (!src) {
        return { kind: 'retry-needed', waitMs: 1500 };
      }
      if (src.startsWith('data:image/svg+xml')) {
        return {
          kind: 'clip',
          rect: { x: rect.left, y: rect.top, width: rect.width, height: rect.height }
        };
      }
      if (src.startsWith('data:image/')) {
        return { kind: 'data-url', payload: src };
      }
      return null;
    })()`;
    let attempts = 0;
    while (attempts < 20) {
      let result = await send("Runtime.evaluate", { expression: expr, returnByValue: true });
      let value = result?.result?.value || null;
      if (value && value.kind === "data-url" && typeof value.payload === "string") {
        fs.writeFileSync(outputPath, Buffer.from(value.payload.split(",")[1], "base64"));
        process.exit(0);
      }
      if (value && value.kind === "clip" && value.rect) {
        const pad = 24;
        const clip = {
          x: Math.max(0, Number(value.rect.x || 0) - pad),
          y: Math.max(0, Number(value.rect.y || 0) - pad),
          width: Math.max(120, Number(value.rect.width || 0) + pad * 2),
          height: Math.max(120, Number(value.rect.height || 0) + pad * 2),
          scale: 1,
        };
        const shot = await send("Page.captureScreenshot", {
          format: "png",
          fromSurface: true,
          clip,
        });
        const data = shot?.data || "";
        if (data) {
          fs.writeFileSync(outputPath, Buffer.from(data, "base64"));
          process.exit(0);
        }
      }
      if (value && value.kind === "not-login-page") {
        process.exit(2);
      }
      if (value && value.kind === "retry-needed") {
        await new Promise((resolve) => setTimeout(resolve, value.waitMs || 1200));
        attempts += 1;
        continue;
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
      attempts += 1;
    }
    process.exit(2);
  } catch (err) {
    console.error(String(err));
    process.exit(1);
  } finally {
    ws.close();
  }
});
"""
        for tab in page_tabs:
            ws_url = tab.get("webSocketDebuggerUrl") or ""
            if not ws_url:
                continue
            try:
                _run_node(
                    ["node", "-e", douyin_script, ws_url, output_path],
                    check=True,
                    timeout=20,
                )
            except Exception:
                continue
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path
        return None
    if platform_name == "xiaohongshu":
        xiaohongshu_script = r"""
const fs = require("fs");
const wsUrl = process.argv[1];
const outputPath = process.argv[2];
const ws = new WebSocket(wsUrl);
let id = 0;
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const msgId = ++id;
    const onMessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (data.id === msgId) {
        ws.removeEventListener("message", onMessage);
        if (data.error) reject(data.error);
        else resolve(data.result);
      }
    };
    ws.addEventListener("message", onMessage);
    ws.send(JSON.stringify({ id: msgId, method, params }));
  });
}
ws.addEventListener("open", async () => {
  try {
    await send("Runtime.enable");
    const expr = `(() => {
      const box = document.querySelector('.login-box-container') || document;
      const text = box.innerText || document.body.innerText || '';
      const findByText = (pattern) => [...document.querySelectorAll('button,div,span,a,p')].find(el => {
        const value = (el.innerText || el.textContent || '').trim();
        return value && pattern.test(value);
      });
      if ((/短信登录|验证码登录|手机号登录/.test(text)) && !/APP扫一扫登录|扫码/.test(text)) {
        const qrSwitch = document.querySelector('img.css-wemwzq') ||
          findByText(/APP扫一扫登录|扫码登录|扫码/);
        if (qrSwitch) {
          qrSwitch.click();
          return { kind: 'retry-needed', waitMs: 1800 };
        }
      }
      if (/二维码已过期|返回重新扫描/.test(text)) {
        const retry = findByText(/返回重新扫描|刷新二维码|刷新|重新获取/);
        if (retry) {
          retry.click();
          return { kind: 'retry-needed', waitMs: 1500 };
        }
      }
      const score = (img) => {
        const src = img.getAttribute('src') || '';
        const cls = img.className || '';
        let s = 0;
        if (src.startsWith('data:image/')) s += 5;
        if (/qr|qrcode/i.test(cls)) s += 4;
        if (img.naturalWidth >= 180 && img.naturalHeight >= 180) s += 3;
        if (Math.abs(img.naturalWidth - img.naturalHeight) <= 20) s += 2;
        return s;
      };
      const candidates = Array.from(box.querySelectorAll('img')).concat(Array.from(document.images || []));
      const img = candidates
        .filter(img => img && img.naturalWidth >= 120 && img.naturalHeight >= 120)
        .filter(img => !(img.naturalWidth === 128 && img.naturalHeight === 128 && /css-wemwzq/.test(img.className || '')))
        .sort((a, b) => score(b) - score(a))[0];
      if (img && (img.src || '').startsWith('data:image/')) {
        return { kind: 'data-url', payload: img.src };
      }
      if (img && img.getBoundingClientRect) {
        const rect = img.getBoundingClientRect();
        if (rect.width >= 120 && rect.height >= 120) {
          return {
            kind: 'clip',
            rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
          };
        }
      }
      return null;
    })()`;
    let attempts = 0;
    while (attempts < 8) {
      let result = await send("Runtime.evaluate", { expression: expr, returnByValue: true });
      let value = result?.result?.value || null;
      if (value && value.kind === "data-url" && typeof value.payload === "string") {
        fs.writeFileSync(outputPath, Buffer.from(value.payload.split(",")[1], "base64"));
        process.exit(0);
      }
      if (value && value.kind === "clip" && value.rect) {
        const pad = 20;
        const clip = {
          x: Math.max(0, Number(value.rect.x || 0) - pad),
          y: Math.max(0, Number(value.rect.y || 0) - pad),
          width: Math.max(140, Number(value.rect.width || 0) + pad * 2),
          height: Math.max(140, Number(value.rect.height || 0) + pad * 2),
          scale: 1,
        };
        const shot = await send("Page.captureScreenshot", { format: "png", fromSurface: true, clip });
        const data = shot?.data || "";
        if (data) {
          fs.writeFileSync(outputPath, Buffer.from(data, "base64"));
          process.exit(0);
        }
      }
      if (value && value.kind === "retry-needed") {
        await new Promise((resolve) => setTimeout(resolve, value.waitMs || 1500));
        attempts += 1;
        continue;
      }
      await new Promise((resolve) => setTimeout(resolve, 1200));
      attempts += 1;
    }
    process.exit(2);
  } catch (err) {
    console.error(String(err));
    process.exit(1);
  } finally {
    ws.close();
  }
});
"""
        for tab in page_tabs:
            ws_url = tab.get("webSocketDebuggerUrl") or ""
            if not ws_url:
                continue
            try:
                _run_node(
                    ["node", "-e", xiaohongshu_script, ws_url, output_path],
                    check=True,
                    timeout=20,
                )
            except Exception:
                continue
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path
        return None
    if platform_name == "kuaishou":
        kuaishou_script = r"""
const fs = require("fs");
const wsUrl = process.argv[1];
const outputPath = process.argv[2];
const ws = new WebSocket(wsUrl);
let id = 0;
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const msgId = ++id;
    const onMessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (data.id === msgId) {
        ws.removeEventListener("message", onMessage);
        if (data.error) reject(data.error);
        else resolve(data.result);
      }
    };
    ws.addEventListener("message", onMessage);
    ws.send(JSON.stringify({ id: msgId, method, params }));
  });
}
ws.addEventListener("open", async () => {
  try {
    await send("Runtime.enable");
    await send("Page.enable");
    const expr = `(() => {
      const text = document.body.innerText || '';
      const collectByText = (pattern) => [...document.querySelectorAll('a,button,[role="button"],div,span,p')]
        .map(el => {
          const value = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
          const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : { width: 0, height: 0 };
          const href = el.href || '';
          const cls = String(el.className || '');
          let score = 0;
          if (!value || !pattern.test(value)) return null;
          if (rect.width >= 20 && rect.height >= 20) score += 20;
          if (value.length <= 8) score += 30;
          if (el.tagName === 'A' || el.tagName === 'BUTTON') score += 40;
          if (href) score += 40;
          if (/login|upload/i.test(cls)) score += 20;
          if (getComputedStyle(el).cursor === 'pointer') score += 10;
          return { el, value, href, score };
        })
        .filter(Boolean)
        .sort((a, b) => b.score - a.score);
      const findActionByText = (pattern) => {
        const items = [...document.querySelectorAll('a,button,[role="button"],div,span,p')]
          .map(el => {
            const value = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
            const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : { width: 0, height: 0 };
            const href = el.href || '';
            const cls = String(el.className || '');
            if (!value || !pattern.test(value)) return null;
            if (value.length > 12) return null;
            let score = 0;
            if (rect.width >= 16 && rect.height >= 16) score += 20;
            if (value.length <= 6) score += 40;
            if (el.tagName === 'A' || el.tagName === 'BUTTON') score += 40;
            if (href) score += 40;
            if (/login|upload|switch|tab|refresh|retry/i.test(cls)) score += 20;
            if (getComputedStyle(el).cursor === 'pointer') score += 10;
            return { el, value, href, score };
          })
          .filter(Boolean)
          .sort((a, b) => b.score - a.score);
        return items.length ? items[0] : null;
      };
      const findByText = (pattern) => {
        const items = collectByText(pattern);
        return items.length ? items[0] : null;
      };
      const clickNode = (node) => {
        if (!node) return false;
        const el = node.el || node;
        try { el.scrollIntoView({ block: 'center', inline: 'center' }); } catch (e) {}
        try { el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true })); } catch (e) {}
        try { el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })); } catch (e) {}
        try { el.click(); } catch (e) {}
        try { el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true })); } catch (e) {}
        return true;
      };
      if (!location.href.includes('passport.kuaishou.com')) {
        const loginEntry = findActionByText(/^立即登录$|^去登录$|^登录$/);
        if (loginEntry) {
          if (loginEntry.href && /passport\.kuaishou\.com/.test(loginEntry.href)) {
            location.href = loginEntry.href;
          } else {
            clickNode(loginEntry);
          }
          return { kind: 'retry-needed', waitMs: 1800 };
        }
        const uploadEntry = findActionByText(/^去上传$/);
        if (uploadEntry) {
          if (uploadEntry.href && /passport\.kuaishou\.com/.test(uploadEntry.href)) {
            location.href = uploadEntry.href;
          } else {
            clickNode(uploadEntry);
          }
          return { kind: 'retry-needed', waitMs: 1800 };
        }
      }
      const hasQrCandidate = !!document.querySelector(
        'img[alt="qrcode"], img[class*="qrcode"], img[class*="qr"], canvas[class*="qrcode"], canvas[class*="qr"], [class*="qrcode"] img, [class*="qr"] img'
      );
      if ((/密码登录|验证码登录|手机号登录|短信登录/.test(text)) && !hasQrCandidate) {
        const scanEntry = findActionByText(/^扫码登录$|^APP扫码登录$|^快手APP.*扫码$/) || findByText(/扫码登录|APP扫码登录|快手APP.*扫码/);
        if (scanEntry) {
          clickNode(scanEntry);
          return { kind: 'retry-needed', waitMs: 1500 };
        }
      }
      if (/二维码已失效|二维码过期|点击刷新/.test(text)) {
        const retry = findActionByText(/^点击刷新$|^刷新二维码$|^重新获取$|^点击重试$|^刷新$/) || findByText(/点击刷新|刷新二维码|重新获取|点击重试|刷新/);
        if (retry) {
          clickNode(retry);
          return { kind: 'retry-needed', waitMs: 1200 };
        }
      }

      const scoreImage = (img) => {
        if (!img) return -1;
        const rect = img.getBoundingClientRect ? img.getBoundingClientRect() : { width: 0, height: 0 };
        const src = img.currentSrc || img.src || '';
        const cls = String(img.className || '');
        const alt = String(img.alt || '');
        const parentText = String((img.parentElement && (img.parentElement.innerText || img.parentElement.textContent)) || '');
        let score = 0;
        if (/qrcode|qr-code|qr_code|二维码/i.test(cls)) score += 80;
        if (/qrcode|qr code|二维码/i.test(alt)) score += 60;
        if (/扫码登录|快手APP|二维码/.test(parentText)) score += 40;
        if (src.startsWith('data:image/')) score += 30;
        if (src.startsWith('blob:')) score += 20;
        if (img.naturalWidth >= 160 && img.naturalHeight >= 160) score += 20;
        if (Math.abs(img.naturalWidth - img.naturalHeight) <= 20) score += 10;
        if (rect.width >= 120 && rect.height >= 120) score += 10;
        return score;
      };

      const candidates = [
        ...document.querySelectorAll('img[alt="qrcode"], img[class*="qrcode"], img[class*="qr"], canvas[class*="qrcode"], canvas[class*="qr"]'),
        ...Array.from(document.images || [])
      ];

      const uniq = [];
      const seen = new Set();
      for (const el of candidates) {
        const key = String(el.tagName || '') + '|' + String(el.currentSrc || el.src || '') + '|' + String(el.className || '');
        if (!seen.has(key)) {
          seen.add(key);
          uniq.push(el);
        }
      }

      const best = uniq
        .filter(el => {
          const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : null;
          return rect && rect.width >= 80 && rect.height >= 80;
        })
        .map(el => ({ el, score: scoreImage(el), rect: el.getBoundingClientRect() }))
        .sort((a, b) => b.score - a.score)[0];

      if (!best) {
        if (/扫码登录|快手APP|二维码/.test(text)) {
          return { kind: 'retry-needed', waitMs: 1200 };
        }
        return null;
      }

      const img = best.el;
      if (img.tagName === 'CANVAS') {
        try {
          return { kind: 'data-url', payload: img.toDataURL('image/png') };
        } catch (e) {}
      }

      const src = img.currentSrc || img.src || '';
      if (src.startsWith('data:image/')) {
        return { kind: 'data-url', payload: src };
      }
      if (best.rect && best.rect.width >= 100 && best.rect.height >= 100) {
        return {
          kind: 'clip',
          rect: { x: best.rect.left, y: best.rect.top, width: best.rect.width, height: best.rect.height }
        };
      }
      return null;
    })()`;
    let attempts = 0;
    while (attempts < 10) {
      let result = await send("Runtime.evaluate", { expression: expr, returnByValue: true });
      let value = result?.result?.value || null;
      if (value && value.kind === "data-url" && typeof value.payload === "string") {
        fs.writeFileSync(outputPath, Buffer.from(value.payload.split(",")[1], "base64"));
        process.exit(0);
      }
      if (value && value.kind === "clip" && value.rect) {
        const pad = 20;
        const clip = {
          x: Math.max(0, Number(value.rect.x || 0) - pad),
          y: Math.max(0, Number(value.rect.y || 0) - pad),
          width: Math.max(140, Number(value.rect.width || 0) + pad * 2),
          height: Math.max(140, Number(value.rect.height || 0) + pad * 2),
          scale: 1,
        };
        const shot = await send("Page.captureScreenshot", { format: "png", fromSurface: true, clip });
        const data = shot?.data || "";
        if (data) {
          fs.writeFileSync(outputPath, Buffer.from(data, "base64"));
          process.exit(0);
        }
      }
      if (value && value.kind === "retry-needed") {
        await new Promise((resolve) => setTimeout(resolve, value.waitMs || 1500));
        attempts += 1;
        continue;
      }
      await new Promise((resolve) => setTimeout(resolve, 1200));
      attempts += 1;
    }
    process.exit(2);
  } catch (err) {
    console.error(String(err));
    process.exit(1);
  } finally {
    ws.close();
  }
});
"""
        for tab in page_tabs:
            ws_url = tab.get("webSocketDebuggerUrl") or ""
            if not ws_url:
                continue
            try:
                _run_node(
                    ["node", "-e", kuaishou_script, ws_url, output_path],
                    check=True,
                    timeout=20,
                )
            except Exception:
                continue
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path
        return None
    if platform_name == "shipinhao":
        shipinhao_script = r"""
const fs = require("fs");
const wsUrl = process.argv[1];
const outputPath = process.argv[2];
const ws = new WebSocket(wsUrl);
let id = 0;
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const msgId = ++id;
    const onMessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (data.id === msgId) {
        ws.removeEventListener("message", onMessage);
        if (data.error) reject(data.error);
        else resolve(data.result);
      }
    };
    ws.addEventListener("message", onMessage);
    ws.send(JSON.stringify({ id: msgId, method, params }));
  });
}
ws.addEventListener("open", async () => {
  try {
    await send("Runtime.enable");
    await send("Page.enable");
    const expr = `(() => {
      function isVisible(el, win) {
        if (!el || !win) return false;
        const rect = el.getBoundingClientRect();
        if (!rect || rect.width < 80 || rect.height < 80) return false;
        const style = win.getComputedStyle(el);
        if (!style) return false;
        return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
      }
      function scoreImage(img, doc) {
        const src = img.currentSrc || img.src || '';
        const cls = ((img.className && String(img.className)) || '').toLowerCase();
        const alt = ((img.alt || '') + ' ' + (img.title || '')).toLowerCase();
        const parentText = ((img.parentElement && img.parentElement.innerText) || doc.body?.innerText || '').slice(0, 1000);
        const rect = img.getBoundingClientRect();
        const ratio = rect.height > 0 ? rect.width / rect.height : 0;
        let score = 0;
        if (/qrcode|qr-code|qr_code|二维码/.test(cls)) score += 80;
        if (/qrcode|qr code|二维码/.test(alt)) score += 40;
        if (/微信扫码|扫码登录|请使用微信扫码/.test(parentText)) score += 30;
        if (src.startsWith('data:image/')) score += 25;
        if (src.startsWith('blob:')) score += 15;
        if (rect.width >= 120 && rect.width <= 420 && rect.height >= 120 && rect.height <= 420) score += 20;
        if (ratio > 0.9 && ratio < 1.1) score += 20;
        if (img.naturalWidth >= 120 && img.naturalHeight >= 120) score += 10;
        return score;
      }
      function scanDoc(doc, offsetX, offsetY, depth, out) {
        if (!doc || depth > 4) return;
        const win = doc.defaultView;
        if (!win) return;
        for (const img of Array.from(doc.images || [])) {
          if (!isVisible(img, win)) continue;
          const rect = img.getBoundingClientRect();
          const score = scoreImage(img, doc);
          if (score < 40) continue;
          out.push({
            score,
            src: img.currentSrc || img.src || '',
            rect: {
              x: Math.max(0, offsetX + rect.left),
              y: Math.max(0, offsetY + rect.top),
              width: rect.width,
              height: rect.height,
            },
          });
        }
        for (const frame of Array.from(doc.querySelectorAll('iframe'))) {
          try {
            const child = frame.contentDocument;
            if (!child) continue;
            const frameRect = frame.getBoundingClientRect();
            scanDoc(child, offsetX + frameRect.left, offsetY + frameRect.top, depth + 1, out);
          } catch (e) {}
        }
      }
      function findRefresh(doc, depth) {
        if (!doc || depth > 4) return null;
        const win = doc.defaultView;
        for (const el of Array.from(doc.querySelectorAll('button,div,span,a,p'))) {
          const text = (el.innerText || el.textContent || '').trim();
          if (!text.includes('点击刷新')) continue;
          if (isVisible(el, win)) return el;
        }
        for (const frame of Array.from(doc.querySelectorAll('iframe'))) {
          try {
            const found = findRefresh(frame.contentDocument, depth + 1);
            if (found) return found;
          } catch (e) {}
        }
        return null;
      }
      const candidates = [];
      scanDoc(document, 0, 0, 0, candidates);
      candidates.sort((a, b) => b.score - a.score);
      const best = candidates[0];
      if (best && typeof best.src === 'string' && best.src.startsWith('data:image/')) {
        return { kind: 'data-url', payload: best.src };
      }
      if (best && best.rect && best.rect.width >= 80 && best.rect.height >= 80) {
        return { kind: 'clip', rect: best.rect };
      }
      const retry = findRefresh(document, 0);
      if (retry) {
        retry.click();
        return { kind: 'retry-needed' };
      }
      return { kind: 'not-found' };
    })()`;
    let value = null;
    for (let attempt = 0; attempt < 4; attempt += 1) {
      const result = await send("Runtime.evaluate", { expression: expr, returnByValue: true });
      value = result?.result?.value || null;
      if (value && value.kind === "retry-needed") {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        continue;
      }
      if (value && (value.kind === "data-url" || value.kind === "clip")) {
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    if (!value) {
      process.exit(2);
    }
    if (value.kind === "clip" && value.rect) {
      const pad = 24;
      const clip = {
        x: Math.max(0, Number(value.rect.x || 0) - pad),
        y: Math.max(0, Number(value.rect.y || 0) - pad),
        width: Math.max(120, Number(value.rect.width || 0) + pad * 2),
        height: Math.max(120, Number(value.rect.height || 0) + pad * 2),
        scale: 1,
      };
      const shot = await send("Page.captureScreenshot", {
        format: "png",
        fromSurface: true,
        clip,
      });
      const data = shot?.data || "";
      if (!data) {
        process.exit(3);
      }
      fs.writeFileSync(outputPath, Buffer.from(data, "base64"));
      process.exit(0);
    }
    if (value.kind !== "data-url" || typeof value.payload !== "string") {
      process.exit(2);
    }
    fs.writeFileSync(outputPath, Buffer.from(value.payload.split(",")[1], "base64"));
    process.exit(0);
  } catch (err) {
    console.error(String(err));
    process.exit(1);
  } finally {
    ws.close();
  }
});
"""
        for tab in page_tabs:
            ws_url = tab.get("webSocketDebuggerUrl") or ""
            if not ws_url:
                continue
            try:
                _run_node(
                    ["node", "-e", shipinhao_script, ws_url, output_path],
                    check=True,
                    timeout=20,
                )
            except Exception:
                continue
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path
        return None
    node_script = r"""
const fs = require("fs");
const wsUrl = process.argv[1];
const outputPath = process.argv[2];
const platformName = process.argv[3];
const ws = new WebSocket(wsUrl);
let id = 0;
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const msgId = ++id;
    const onMessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (data.id === msgId) {
        ws.removeEventListener("message", onMessage);
        if (data.error) reject(data.error);
        else resolve(data.result);
      }
    };
    ws.addEventListener("message", onMessage);
    ws.send(JSON.stringify({ id: msgId, method, params }));
  });
}
ws.addEventListener("open", async () => {
  try {
    await send("Runtime.enable");
    const expr = `(() => {
      const selectQr = () => {
        let img = null;
        if (platformName === 'douyin') {
          const text = document.body.innerText || '';
          if (/已失效|二维码失效|二维码已失效/.test(text)) {
            const retry = [...document.querySelectorAll('button,div,span,a,p')].find(el =>
              /刷新|重新获取|重新加载/.test((el.innerText || el.textContent || '').trim())
            );
            if (retry) {
              retry.click();
              return { kind: 'retry-needed' };
            }
          }
          img = document.querySelector('img[class*=qrcode_img]') ||
            Array.from(document.images).find(img => (img.src || '').startsWith('data:image/') && img.naturalWidth >= 180 && img.naturalHeight >= 180);
        } else if (platformName === 'xiaohongshu') {
          const box = document.querySelector('.login-box-container') || document;
          const text = box.innerText || document.body.innerText || '';
          const findByText = (pattern) => [...document.querySelectorAll('button,div,span,a,p')].find(el => {
            const value = (el.innerText || el.textContent || '').trim();
            return value && pattern.test(value);
          });
          if ((/短信登录|验证码登录|手机号登录/.test(text)) && !/APP扫一扫登录|扫码/.test(text)) {
            const qrSwitch = document.querySelector('img.css-wemwzq') || findByText(/APP扫一扫登录|扫码登录|扫码/);
            if (qrSwitch) {
              qrSwitch.click();
              return { kind: 'retry-needed' };
            }
          }
          const candidates = Array.from(box.querySelectorAll('img')).concat(Array.from(document.images));
          img = candidates.find(img => (img.src || '').startsWith('data:image/') && img.naturalWidth >= 160 && img.naturalHeight >= 160) ||
            candidates.find(img => img.naturalWidth >= 160 && img.naturalHeight >= 160 &&
              !(img.naturalWidth === 128 && img.naturalHeight === 128 && /css-wemwzq/.test(img.className || '')));
        } else if (platformName === 'kuaishou') {
          const text = document.body.innerText || '';
          if (text.includes('二维码已失效')) {
            const retry = [...document.querySelectorAll('button,div,span,a,p')].find(el =>
              (el.innerText || el.textContent || '').trim() === '点击刷新'
            );
            if (retry) {
              retry.click();
              return { kind: 'retry-needed' };
            }
          }
          img = document.querySelector('img[alt="qrcode"]') ||
            Array.from(document.images).find(img => (img.src || '').startsWith('data:image/') && img.naturalWidth >= 100 && img.naturalHeight >= 100);
        } else if (platformName === 'shipinhao') {
          const docs = [
            document,
            ...Array.from(document.querySelectorAll('iframe'))
              .map(frame => frame.contentDocument)
              .filter(Boolean),
          ];
          for (const doc of docs) {
            img = doc.querySelector('img.qrcode') ||
              Array.from(doc.images || []).find(img => (img.src || '').startsWith('data:image/') && img.naturalWidth >= 180 && img.naturalHeight >= 180);
            if (img) {
              break;
            }
            const retry = [...doc.querySelectorAll('button,div,span,a,p')].find(el => {
              const text = (el.innerText || el.textContent || '').trim();
              if (!text.includes('点击刷新')) {
                return false;
              }
              const style = el.ownerDocument?.defaultView?.getComputedStyle(el);
              return style && style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
            });
            if (retry) {
              retry.click();
              return { kind: 'retry-needed' };
            }
            const canvas = Array.from(doc.querySelectorAll('canvas')).find(c => c.width >= 180 && c.height >= 180);
            if (canvas) {
              return { kind: 'data-url', payload: canvas.toDataURL('image/png') };
            }
          }
        } else {
          img = Array.from(document.images).find(img => (img.src || '').startsWith('data:image/') && img.naturalWidth >= 180 && img.naturalHeight >= 180);
        }
        if (img && (img.src || '').startsWith('data:image/')) {
          return { kind: 'data-url', payload: img.src };
        }
        const canvas = Array.from(document.querySelectorAll('canvas')).find(c => c.width >= 180 && c.height >= 180);
        if (canvas) {
          return { kind: 'data-url', payload: canvas.toDataURL('image/png') };
        }
        return null;
      };
      if (platformName === 'xiaohongshu') {
        const text = document.querySelector('.login-box-container')?.innerText || document.body.innerText || '';
        if (/二维码已过期|返回重新扫描/.test(text)) {
          const retry = [...document.querySelectorAll('button,div,span,a,p')].find(el =>
            /返回重新扫描|刷新二维码|刷新|重新获取/.test((el.innerText || el.textContent || '').trim())
          );
          if (retry) {
            retry.click();
            return { kind: 'retry-needed' };
          }
        }
      }
      return selectQr();
    })()`;
    let result = await send("Runtime.evaluate", { expression: expr, returnByValue: true });
    let value = result?.result?.value || null;
    if (value && value.kind === "retry-needed") {
      await new Promise((resolve) => setTimeout(resolve, 1800));
      result = await send("Runtime.evaluate", { expression: expr, returnByValue: true });
      value = result?.result?.value || null;
    }
    if (!value || value.kind !== "data-url" || typeof value.payload !== "string") {
      process.exit(2);
    }
    const comma = value.payload.indexOf(",");
    if (comma === -1) {
      process.exit(3);
    }
    const b64 = value.payload.slice(comma + 1);
    fs.writeFileSync(outputPath, Buffer.from(b64, "base64"));
    process.exit(0);
  } catch (err) {
    console.error(String(err));
    process.exit(1);
  } finally {
    ws.close();
  }
});
"""
    for tab in page_tabs:
        ws_url = tab.get("webSocketDebuggerUrl") or ""
        if not ws_url:
            continue
        try:
            _run_node(
                ["node", "-e", node_script, ws_url, output_path, platform_name],
                check=True,
                timeout=20,
            )
        except Exception:
            continue
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
    return output_path if os.path.exists(output_path) and os.path.getsize(output_path) > 0 else None


def _tab_is_logged_in(platform_name: str, tab: dict) -> bool:
    url = (tab.get("url") or "").lower()
    if not url:
        return False
    if url.startswith("chrome-extension://") or url.startswith("devtools://"):
        return False
    if not (url.startswith("http://") or url.startswith("https://")):
        return False
    ready_markers = tuple(m.lower() for m in PLATFORMS[platform_name].get("ready_markers", ()))
    if ready_markers and not any(marker in url for marker in ready_markers):
        return False
    if platform_name == "douyin":
        ws_url = tab.get("webSocketDebuggerUrl") or ""
        if ws_url:
            try:
                node_script = r"""
const wsUrl = process.argv[1];
const ws = new WebSocket(wsUrl);
let id = 0;
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const msgId = ++id;
    const onMessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (data.id === msgId) {
        ws.removeEventListener("message", onMessage);
        if (data.error) reject(data.error);
        else resolve(data.result);
      }
    };
    ws.addEventListener("message", onMessage);
    ws.send(JSON.stringify({ id: msgId, method, params }));
  });
}
ws.addEventListener("open", async () => {
  try {
    await send("Runtime.enable");
    for (let i = 0; i < 3; i += 1) {
      const result = await send("Runtime.evaluate", {
        expression: `(() => {
          const text = (document.body && document.body.innerText || '').slice(0, 12000);
          const title = document.title || '';
          const url = location.href || '';
          const buttons = Array.from(document.querySelectorAll('button, [role="button"], a, span, div'))
            .map(el => (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim())
            .filter(Boolean)
            .slice(0, 80);
          const hasUploadInput = !!document.querySelector(
            'div[class^="container"] input[type="file"], div.progress-div input[type="file"], input[type="file"]'
          );
          const loginSignals = text + '\\n' + title;
          const hasLoginText = /扫码登录|手机号登录|验证码登录|密码登录|登录抖音创作者中心|登录\\/注册|获取验证码|打开「抖音APP」|我是创作者|我是MCN机构/.test(loginSignals);
          const hasLoginForm = !!document.querySelector(
            'input[type="tel"], input[placeholder*="手机号"], input[placeholder*="验证码"]'
          );
          const hasReadyUi = hasUploadInput ||
            /上传视频|发布视频|发布作品|重新上传|作品描述|添加简介|定时发布|封面设置|声明内容由AI生成/.test(text) ||
            buttons.some(v => /上传视频|发布视频|发布作品|选择视频|重新上传|定时发布|作品描述|封面设置|发布/.test(v));
          return {
            url,
            title,
            hasUploadInput,
            hasLoginText: hasLoginText || hasLoginForm,
            hasReadyText: hasReadyUi &&
              /creator\\.douyin\\.com\\/creator-micro\\/content\\/upload/.test(url) &&
              !(hasLoginText || hasLoginForm)
          };
        })()`,
        returnByValue: true
      });
      const payload = result.result.value || {};
      if (payload.hasReadyText && !payload.hasLoginText) {
        console.log(JSON.stringify(payload));
        ws.close();
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    const result = await send("Runtime.evaluate", {
      expression: `(() => {
        const text = (document.body && document.body.innerText || '').slice(0, 12000);
        const title = document.title || '';
        const url = location.href || '';
        const buttons = Array.from(document.querySelectorAll('button, [role="button"], a, span, div'))
          .map(el => (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim())
          .filter(Boolean)
          .slice(0, 80);
        const hasUploadInput = !!document.querySelector(
          'div[class^="container"] input[type="file"], div.progress-div input[type="file"], input[type="file"]'
        );
        const loginSignals = text + '\\n' + title;
        const hasLoginText = /扫码登录|手机号登录|验证码登录|密码登录|登录抖音创作者中心|登录\\/注册|获取验证码|打开「抖音APP」|我是创作者|我是MCN机构/.test(loginSignals);
        const hasLoginForm = !!document.querySelector(
          'input[type="tel"], input[placeholder*="手机号"], input[placeholder*="验证码"]'
        );
        const hasReadyUi = hasUploadInput ||
          /上传视频|发布视频|发布作品|重新上传|作品描述|添加简介|定时发布|封面设置|声明内容由AI生成/.test(text) ||
          buttons.some(v => /上传视频|发布视频|发布作品|选择视频|重新上传|定时发布|作品描述|封面设置|发布/.test(v));
        return {
          url,
          title,
          hasUploadInput,
          hasLoginText: hasLoginText || hasLoginForm,
          hasReadyText: hasReadyUi &&
            /creator\\.douyin\\.com\\/creator-micro\\/content\\/upload/.test(url) &&
            !(hasLoginText || hasLoginForm)
        };
      })()`,
      returnByValue: true
    });
    console.log(JSON.stringify(result.result.value || {}));
  } catch (e) {
    console.log(JSON.stringify({ error: String(e) }));
  }
  ws.close();
});
"""
                last_payload = {}
                for _ in range(3):
                    result = _run_node(
                        ["node", "-e", node_script, ws_url],
                        timeout=10,
                    )
                    payload = json.loads((result.stdout or "").strip() or "{}")
                    last_payload = payload
                    if payload.get("hasReadyText") and not payload.get("hasLoginText") and _has_required_login_cookies(platform_name, tab):
                        return True
                    time.sleep(0.3)
                if last_payload.get("error"):
                    return False
                if last_payload.get("hasLoginText"):
                    return False
                if not last_payload.get("hasReadyText"):
                    return False
                if not _has_required_login_cookies(platform_name, tab):
                    return False
            except Exception:
                return False
    if platform_name == "xiaohongshu":
        ws_url = tab.get("webSocketDebuggerUrl") or ""
        if ws_url:
            try:
                node_script = r"""
const wsUrl = process.argv[1];
const ws = new WebSocket(wsUrl);
let id = 0;
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const msgId = ++id;
    const onMessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (data.id === msgId) {
        ws.removeEventListener("message", onMessage);
        if (data.error) reject(data.error);
        else resolve(data.result);
      }
    };
    ws.addEventListener("message", onMessage);
    ws.send(JSON.stringify({ id: msgId, method, params }));
  });
}
ws.addEventListener("open", async () => {
  try {
    await send("Runtime.enable");
    for (let i = 0; i < 3; i += 1) {
      const result = await send("Runtime.evaluate", {
        expression: `(() => {
          const text = (document.body && document.body.innerText || '').slice(0, 12000);
          const title = document.title || '';
          const url = location.href || '';
          const buttons = Array.from(document.querySelectorAll('button, [role="button"], a, span, div'))
            .map(el => (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim())
            .filter(Boolean)
            .slice(0, 120);
          const hasUploadInput = !!document.querySelector(
            'input[type="file"], input[accept*="video"], input[accept*="image"], [class*="upload"] input[type="file"]'
          );
          const loginSignals = text + '\\n' + title;
          const hasLoginText = /短信登录|验证码登录|扫码登录|APP扫一扫登录|手机号登录|登录小红书创作服务平台|登录小红书|立即登录|同意并登录/.test(loginSignals);
          const hasLoginForm = !!document.querySelector(
            'input[type="tel"], input[type="password"], input[placeholder*="手机号"], input[placeholder*="验证码"], input[placeholder*="密码"]'
          );
          const hasReadyUi = hasUploadInput ||
            /发布笔记|发布视频|上传视频|上传图文|写长文|创作服务平台|专业号中心|内容管理|数据中心|笔记管理|拖拽视频到此或点击上传|草稿箱/.test(text) ||
            buttons.some(v => /发布笔记|发布视频|上传视频|上传图文|写长文|选择视频|点击上传|内容管理|草稿箱/.test(v));
          return {
            url,
            title,
            hasUploadInput,
            hasLoginText: hasLoginText || hasLoginForm,
            hasReadyText: hasReadyUi &&
              /creator\\.xiaohongshu\\.com\\/(publish\\/publish|publish\\/notemanager|content\\/upload|creator\\/home)/.test(url) &&
              !(hasLoginText || hasLoginForm)
          };
        })()`,
        returnByValue: true
      });
      const payload = result.result.value || {};
      if (payload.hasReadyText && !payload.hasLoginText) {
        console.log(JSON.stringify(payload));
        ws.close();
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    const result = await send("Runtime.evaluate", {
      expression: `(() => {
        const text = (document.body && document.body.innerText || '').slice(0, 12000);
        const title = document.title || '';
        const url = location.href || '';
        const buttons = Array.from(document.querySelectorAll('button, [role="button"], a, span, div'))
          .map(el => (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim())
          .filter(Boolean)
          .slice(0, 120);
        const hasUploadInput = !!document.querySelector(
          'input[type="file"], input[accept*="video"], input[accept*="image"], [class*="upload"] input[type="file"]'
        );
        const loginSignals = text + '\\n' + title;
        const hasLoginText = /短信登录|验证码登录|扫码登录|APP扫一扫登录|手机号登录|登录小红书创作服务平台|登录小红书|立即登录|同意并登录/.test(loginSignals);
        const hasLoginForm = !!document.querySelector(
          'input[type="tel"], input[type="password"], input[placeholder*="手机号"], input[placeholder*="验证码"], input[placeholder*="密码"]'
        );
        const hasReadyUi = hasUploadInput ||
          /发布笔记|发布视频|上传视频|上传图文|写长文|创作服务平台|专业号中心|内容管理|数据中心|笔记管理|拖拽视频到此或点击上传|草稿箱/.test(text) ||
          buttons.some(v => /发布笔记|发布视频|上传视频|上传图文|写长文|选择视频|点击上传|内容管理|草稿箱/.test(v));
        return {
          url,
          title,
          hasUploadInput,
          hasLoginText: hasLoginText || hasLoginForm,
          hasReadyText: hasReadyUi &&
            /creator\\.xiaohongshu\\.com\\/(publish\\/publish|publish\\/notemanager|content\\/upload|creator\\/home)/.test(url) &&
            !(hasLoginText || hasLoginForm)
        };
      })()`,
      returnByValue: true
    });
    console.log(JSON.stringify(result.result.value || {}));
  } catch (e) {
    console.log(JSON.stringify({ error: String(e) }));
  }
  ws.close();
});
"""
                last_payload = {}
                for _ in range(3):
                    result = _run_node(
                        ["node", "-e", node_script, ws_url],
                        timeout=10,
                    )
                    payload = json.loads((result.stdout or "").strip() or "{}")
                    last_payload = payload
                    if payload.get("hasReadyText") and not payload.get("hasLoginText") and _has_required_login_cookies(platform_name, tab):
                        return True
                    time.sleep(0.3)
                if last_payload.get("error"):
                    return False
                if last_payload.get("hasLoginText"):
                    return False
                if not last_payload.get("hasReadyText"):
                    return False
                if not _has_required_login_cookies(platform_name, tab):
                    return False
            except Exception:
                return False
    if platform_name == "kuaishou":
        ws_url = tab.get("webSocketDebuggerUrl") or ""
        if ws_url:
            try:
                expression = r"""(() => {
                  const text = (document.body && document.body.innerText || '').slice(0, 12000);
                  const title = document.title || '';
                  const url = location.href || '';
                  const buttons = Array.from(document.querySelectorAll('button, [role="button"], a, span, div'))
                    .map(el => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim())
                    .filter(Boolean)
                    .slice(0, 120);
                  const hasUploadInput = !!document.querySelector(
                    'input[type="file"], input[accept*="video"], input[accept*="mp4"], [class*="upload"] input[type="file"]'
                  );
                  const loginSignals = text + '\n' + title;
                  const hasLoginText = /扫码登录|验证码登录|短信登录|登录快手创作者服务平台|手机号登录|账号登录|请完成验证后继续访问|同意并登录|快手APP扫码/.test(loginSignals);
                  const hasReadyUi = hasUploadInput ||
                    /发布作品|发布视频|上传视频|上传图文|上传全景视频|拖拽视频到此或点击上传|作品描述|封面设置|定时发布/.test(text) ||
                    buttons.some(v => /发布作品|发布视频|上传视频|选择视频|点击上传|发布/.test(v));
                  return {
                    url,
                    title,
                    hasUploadInput,
                    hasLoginText,
                    hasReadyText: hasReadyUi &&
                      /cp\.kuaishou\.com\/article\/publish/.test(url) &&
                      !/passport\.kuaishou\.com/.test(url) &&
                      !hasLoginText
                  };
                })()"""
                last_payload = {}
                for _ in range(3):
                    payload = asyncio.run(_cdp_runtime_evaluate(ws_url, expression, timeout=8.0)) or {}
                    last_payload = payload
                    if payload.get("hasReadyText") and not payload.get("hasLoginText") and _has_required_login_cookies(platform_name, tab):
                        return True
                    time.sleep(0.3)
                if last_payload.get("error"):
                    return False
                if last_payload.get("hasLoginText"):
                    return False
                if not last_payload.get("hasReadyText"):
                    return False
                if not _has_required_login_cookies(platform_name, tab):
                    return False
            except Exception:
                return False
    if platform_name == "shipinhao":
        ws_url = tab.get("webSocketDebuggerUrl") or ""
        if ws_url:
            try:
                node_script = r"""
const wsUrl = process.argv[1];
const ws = new WebSocket(wsUrl);
let id = 0;
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const msgId = ++id;
    const onMessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (data.id === msgId) {
        ws.removeEventListener("message", onMessage);
        if (data.error) reject(data.error);
        else resolve(data.result);
      }
    };
    ws.addEventListener("message", onMessage);
    ws.send(JSON.stringify({ id: msgId, method, params }));
  });
}
ws.addEventListener("open", async () => {
  try {
    await send("Runtime.enable");
    for (let i = 0; i < 3; i += 1) {
      const result = await send("Runtime.evaluate", {
        expression: `(() => {
          const text = (document.body && document.body.innerText || '').slice(0, 12000);
          const title = document.title || '';
          const url = location.href || '';
          const buttons = Array.from(document.querySelectorAll('button, [role="button"], a, span, div'))
            .map(el => (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim())
            .filter(Boolean)
            .slice(0, 120);
          const hasUploadInput = !!document.querySelector(
            'input[type="file"], input[accept*="video"], [class*="upload"] input[type="file"]'
          );
          const loginSignals = text + '\\n' + title;
          const hasLoginText = /微信扫码|扫码登录|请使用微信扫码|登录后继续|登录后可继续|请先登录/.test(loginSignals);
          const hasReadyUi = hasUploadInput ||
            /发表视频|上传视频|拖拽|选择视频|视频描述|扩展链接|首页|内容管理|草稿箱|数据中心|视频号 · 助手/.test(text) ||
            buttons.some(v => /发表视频|上传视频|选择视频|内容管理|草稿箱|数据中心/.test(v));
          return {
            url,
            title,
            hasUploadInput,
            hasLoginText,
            hasReadyText: hasReadyUi &&
              /channels\\.weixin\\.qq\\.com\\/platform\\/post\\/create/.test(url) &&
              !hasLoginText
          };
        })()`,
        returnByValue: true
      });
      const payload = result.result.value || {};
      if (payload.hasReadyText && !payload.hasLoginText) {
        console.log(JSON.stringify(payload));
        ws.close();
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    const result = await send("Runtime.evaluate", {
      expression: `(() => {
        const text = (document.body && document.body.innerText || '').slice(0, 12000);
        const title = document.title || '';
        const url = location.href || '';
        const buttons = Array.from(document.querySelectorAll('button, [role="button"], a, span, div'))
          .map(el => (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim())
          .filter(Boolean)
          .slice(0, 120);
        const hasUploadInput = !!document.querySelector(
          'input[type="file"], input[accept*="video"], [class*="upload"] input[type="file"]'
        );
        const loginSignals = text + '\\n' + title;
        const hasLoginText = /微信扫码|扫码登录|请使用微信扫码|登录后继续|登录后可继续|请先登录/.test(loginSignals);
        const hasReadyUi = hasUploadInput ||
          /发表视频|上传视频|拖拽|选择视频|视频描述|扩展链接|首页|内容管理|草稿箱|数据中心|视频号 · 助手/.test(text) ||
          buttons.some(v => /发表视频|上传视频|选择视频|内容管理|草稿箱|数据中心/.test(v));
        return {
          url,
          title,
          hasUploadInput,
          hasLoginText,
          hasReadyText: hasReadyUi &&
            /channels\\.weixin\\.qq\\.com\\/platform\\/post\\/create/.test(url) &&
            !hasLoginText
        };
      })()`,
      returnByValue: true
    });
    console.log(JSON.stringify(result.result.value || {}));
  } catch (e) {
    console.log(JSON.stringify({ error: String(e) }));
  }
  ws.close();
});
"""
                last_payload = {}
                for _ in range(3):
                    result = _run_node(
                        ["node", "-e", node_script, ws_url],
                        timeout=10,
                    )
                    payload = json.loads((result.stdout or "").strip() or "{}")
                    last_payload = payload
                    if payload.get("hasReadyText") and not payload.get("hasLoginText") and _has_required_login_cookies(platform_name, tab):
                        return True
                    time.sleep(0.3)
                if last_payload.get("error"):
                    return False
                if last_payload.get("hasLoginText"):
                    return False
                if not last_payload.get("hasReadyText"):
                    return False
                if not _has_required_login_cookies(platform_name, tab):
                    return False
            except Exception:
                return False
    markers = tuple(m.lower() for m in PLATFORMS[platform_name]["login_markers"])
    return not any(marker in url for marker in markers)


def capture_login_screenshot(
    platform_name: str,
    root: Path | None = None,
    wait_seconds: float = 12.0,
    poll_interval: float = 1.0,
) -> str | None:
    root = root or project_root()
    screenshot_dir = root / "logs" / "auth_qr"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    output_path = screenshot_dir / f"{platform_name}_login_qr.png"
    try:
        output_path.unlink(missing_ok=True)
    except Exception:
        pass

    ensure_page_target(platform_name, retries=1, wait_seconds=0.8)
    deadline = time.time() + max(wait_seconds, 0.0)

    while True:
        direct_qr_path = _extract_qr_image_via_cdp(platform_name, str(output_path))
        if direct_qr_path and os.path.exists(direct_qr_path) and os.path.getsize(direct_qr_path) > 0:
            return direct_qr_path
        if time.time() >= deadline:
            break
        time.sleep(max(poll_interval, 0.2))
    return None


def _wait_for_connect_port(platform_name: str, timeout: float = 20.0) -> bool:
    port = PLATFORMS[platform_name]["port"]
    deadline = time.time() + max(timeout, 0.0)
    while time.time() < deadline:
        if is_port_listening(port):
            return True
        time.sleep(0.25)
    return is_port_listening(port)


def refresh_login_qr(
    platform_name: str,
    root: Path | None = None,
    *,
    restart_browser: bool = False,
    reason: str = "",
) -> str | None:
    """重新准备登录页二维码；必要时先关闭 connect Chrome 再拉起。"""
    root = (root or project_root()).resolve()
    cfg = PLATFORMS[platform_name]
    label = cfg["label"]

    if restart_browser:
        if close_connect_browser(platform_name):
            print(f"{label} 已关闭旧的登录浏览器，准备重新获取二维码")
            time.sleep(1.0)
        elif is_port_listening(cfg["port"]):
            print(f"{label} 关闭旧的登录浏览器失败，将尝试在现有会话上刷新二维码")
        elif reason:
            print(f"{label} {reason}，准备重新拉起登录浏览器")

    if not is_port_listening(cfg["port"]):
        launch_connect_chrome(platform_name, root)
        if not _wait_for_connect_port(platform_name, timeout=20.0):
            print(f"{label} 登录浏览器启动超时，暂时无法重新获取二维码")
            return None
        time.sleep(1.0)

    open_target_tab(platform_name)
    screenshot_path = capture_login_screenshot(platform_name, root)
    if screenshot_path:
        print(f"{label} 登录二维码已保存：{screenshot_path}")
        _send_feishu_notification(platform_name, screenshot_path)
        return screenshot_path

    print(f"{label} 登录页已打开，但本次未提取到二维码图片")
    return None


def _revive_connect_session_for_check(
    platform_name: str,
    root: Path,
    timeout: float = 12.0,
) -> list[dict]:
    cfg = PLATFORMS[platform_name]
    profile_dir = profile_dir_for(platform_name, root)
    if not profile_dir.exists():
        return []
    try:
        launch_connect_chrome(platform_name, root)
    except Exception:
        return []
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_port_listening(cfg["port"]):
            tabs = ensure_page_target(platform_name, retries=1, wait_seconds=0.5)
            if tabs:
                return tabs
        time.sleep(0.25)
    return []


def _post_revival_stabilize(platform_name: str) -> None:
    if platform_name != "shipinhao":
        return
    time.sleep(2.0)


def check_platform_login(
    platform_name: str,
    root: Path | None = None,
    passive: bool = False,
) -> tuple[bool, str]:
    root = (root or project_root()).resolve()
    cfg = PLATFORMS[platform_name]
    profile_dir = profile_dir_for(platform_name, root)
    revived = False
    profile_ok, profile_msg = validate_connect_profile_dir(platform_name, root)
    if is_port_listening(cfg["port"]) and not profile_ok:
        return False, profile_msg
    if not is_port_listening(cfg["port"]):
        if not profile_dir.exists():
            return False, f"{cfg['label']} 还没有登录目录: {profile_dir}"
        if passive:
            return False, f"{cfg['label']} connect 端口 {cfg['port']} 未监听；预期目录: {profile_dir}"
        tabs = _revive_connect_session_for_check(platform_name, root)
        if not tabs:
            return False, f"{cfg['label']} connect 端口 {cfg['port']} 未监听，且无法恢复本地会话"
        profile_ok, profile_msg = validate_connect_profile_dir(platform_name, root)
        if not profile_ok:
            return False, profile_msg
        _post_revival_stabilize(platform_name)
        tabs = ensure_page_target(platform_name, retries=2, wait_seconds=0.8)
        revived = True
    else:
        tabs = devtools_tabs(cfg["port"]) if passive else ensure_page_target(platform_name)
    if not tabs:
        if passive:
            return False, f"{cfg['label']} connect Chrome 当前没有可复用标签页"
        return False, f"{cfg['label']} connect Chrome 没有可复用标签页"
    for tab in tabs:
        if _tab_is_logged_in(platform_name, tab):
            if not profile_dir.exists():
                return True, f"{cfg['label']} 已登录，可复用外部 connect 会话: {tab.get('url', '')}"
            suffix = "（已自动恢复本地会话）" if revived else ""
            return True, f"{cfg['label']} 已登录，可复用{suffix}: {tab.get('url', '')} | 目录: {profile_dir}"
    if passive:
        return False, f"{cfg['label']} 当前 connect 会话不可直接复用"
    open_target_tab(platform_name)
    time.sleep(1)
    for tab in ensure_page_target(platform_name, retries=1):
        if _tab_is_logged_in(platform_name, tab):
            return True, f"{cfg['label']} 已登录，可复用: {tab.get('url', '')}"
    return False, f"{cfg['label']} 当前仍停在登录页"


def ensure_platform_login(
    platform_name: str,
    timeout: int = 300,
) -> tuple[bool, str]:
    root = project_root()
    cfg = PLATFORMS[platform_name]
    ok, msg = check_platform_login(platform_name, root)
    if ok:
        return True, msg

    screenshot_path = refresh_login_qr(
        platform_name,
        root,
        restart_browser=is_port_listening(cfg["port"]),
        reason="检测到当前仍停在登录页",
    )
    last_qr_refresh = time.time()

    deadline = time.time() + timeout
    while time.time() < deadline:
        ok, msg = check_platform_login(platform_name, root)
        if ok:
            return True, msg
        if time.time() - last_qr_refresh >= 120:
            screenshot_path = refresh_login_qr(
                platform_name,
                root,
                restart_browser=True,
                reason="检测到二维码可能已过期",
            )
            last_qr_refresh = time.time()
        time.sleep(3)
    return False, f"{cfg['label']} 登录超时，请稍后重试"


def login_instruction(platform_name: str, root: Path | None = None) -> str:
    actual_root = (root or project_root()).resolve()
    script = actual_root / "scripts" / "platform_login.py"
    return (
        f"{PLATFORMS[platform_name]['label']} 当前不可复用，请先重新登录。\n"
        f"命令: python {script} --platform {platform_name}"
    )


def _main() -> int:
    parser = argparse.ArgumentParser(description="视频号 connect 登录助手")
    parser.add_argument("--platform", required=True, choices=CLI_PLATFORMS, help="目标平台；当前仅保留视频号入口")
    parser.add_argument("--check-only", action="store_true", help="检查当前登录是否可复用；失败时默认刷新二维码并发送飞书")
    parser.add_argument("--no-auto-qr", action="store_true", help="与 --check-only 一起使用；失败时只报告，不刷新/发送二维码")
    parser.add_argument("--close-after-check", action="store_true", help="仅检查时在返回结果后关闭 connect Chrome")
    parser.add_argument("--timeout", type=int, default=300, help="等待登录超时时间（秒）")
    parser.add_argument("--project-root", default="", help="项目根目录；不传则默认取当前仓库")
    args = parser.parse_args()

    global _PROJECT_ROOT_OVERRIDE
    if args.project_root:
        _PROJECT_ROOT_OVERRIDE = Path(args.project_root).expanduser().resolve()

    if args.check_only:
        ok, msg = check_platform_login(args.platform)
        if not ok and not args.no_auto_qr:
            qr_path = refresh_login_qr(
                args.platform,
                project_root(),
                restart_browser=is_port_listening(PLATFORMS[args.platform]["port"]),
                reason="登录状态查询不可复用，自动刷新二维码",
            )
            if qr_path:
                msg = f"{msg}\n{PLATFORMS[args.platform]['label']} 登录二维码已刷新并发送到飞书: {qr_path}"
            else:
                msg = f"{msg}\n{PLATFORMS[args.platform]['label']} 登录页已打开，但本次未提取到二维码图片"
        if args.close_after_check:
            closed = close_connect_browser(args.platform)
            msg = f"{msg}\n{PLATFORMS[args.platform]['label']} connect Chrome 已关闭" if closed else f"{msg}\n{PLATFORMS[args.platform]['label']} connect Chrome 未关闭（可能本来就未启动）"
    else:
        ok, msg = ensure_platform_login(
            args.platform,
            timeout=args.timeout,
        )

    print(msg)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(_main())
