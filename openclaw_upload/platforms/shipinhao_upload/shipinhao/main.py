# -*- coding: utf-8 -*-
"""
视频号助手上传 - 纯 CDP（nodriver）

视频号助手：https://channels.weixin.qq.com/platform
发表视频：https://channels.weixin.qq.com/platform/post/create
登录方式：微信扫码
"""
from datetime import datetime
import os
import asyncio
import json
import urllib.parse
import urllib.request
from pathlib import Path

import nodriver as uc
from conf import LOCAL_CHROME_PATH, LOCAL_CHROME_HEADLESS, AUTH_MODE
from shipinhao.browser import (
    get_browser,
    try_connect_existing_chrome,
    ensure_connect_login_chrome,
    attach_login_chrome,
)
from common.utils import need_cookie_file, has_text_in_page as _has_text
from common.loggers import shipinhao_logger


# 视频号助手发表视频页面
SPH_UPLOAD_URL = "https://channels.weixin.qq.com/platform/post/create"
SPH_BASE_URL = "https://channels.weixin.qq.com"
# 视频号标题建议简短，描述可达 1000 字
SPH_TITLE_MAX = 64
SPH_TAGS_MAX = 10


def _open_target_tab(url: str, port: int = 9226) -> bool:
    encoded = urllib.parse.quote(url, safe=":/?&=%")
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/json/new?{encoded}",
            method="PUT",
            headers={"User-Agent": "shipinhao-upload"},
        )
        with urllib.request.urlopen(req, timeout=3):
            return True
    except Exception:
        return False


def _js_find_file_input():
    """查找 file input：iframe 内 + shadow DOM"""
    return """
    (function(){
        function findIn(el){
            var inp = el.querySelector('input[type=file][accept*="video"]');
            if(inp) return inp;
            inp = el.querySelector('input[type=file]');
            return inp || null;
        }
        function search(doc, depth){
            if(!doc || depth>4) return null;
            var r = findIn(doc);
            if(r) return r;
            var ifs = doc.querySelectorAll('iframe');
            for(var i=0;i<ifs.length;i++){
                try{
                    if(ifs[i].contentDocument){
                        r = search(ifs[i].contentDocument, depth+1);
                        if(r) return r;
                    }
                }catch(e){}
            }
            var all = doc.querySelectorAll('*');
            for(var j=0;j<all.length;j++){
                if(all[j].shadowRoot){
                    r = search(all[j].shadowRoot, depth+1);
                    if(r) return r;
                }
            }
            return null;
        }
        return search(document, 0);
    })()
    """


async def _upload_file_via_cdp(tab, file_path: str) -> bool:
    """通过 CDP 设置文件，支持 iframe + shadow DOM 内的 input"""
    try:
        from nodriver import cdp
        abs_path = os.path.abspath(file_path)
        result = await tab.send(
            cdp.runtime.evaluate(
                expression=_js_find_file_input(),
                return_by_value=False,
            )
        )
        robj = result[0] if isinstance(result, (list, tuple)) else result
        err = result[1] if isinstance(result, (list, tuple)) and len(result) > 1 else None
        if err or not robj:
            return False
        oid = getattr(robj, "object_id", None)
        if not oid or (hasattr(robj, "type_") and getattr(robj, "subtype", None) == "null"):
            return False
        await tab.send(cdp.dom.set_file_input_files(files=[abs_path], object_id=oid))
        return True
    except Exception as e:
        shipinhao_logger.info(f"[-] CDP 上传失败：{e}")
        return False


async def _wait_and_upload_file_via_cdp(tab, file_path: str, retries: int = 6, delay: float = 1.0) -> bool:
    """等待上传控件渲染完成后再设置文件，降低页面慢加载时的误判。"""
    for attempt in range(1, retries + 1):
        if await _upload_file_via_cdp(tab, file_path):
            if attempt > 1:
                shipinhao_logger.info(f"[-] Step 1 重试成功（第 {attempt} 次）")
            return True
        if attempt < retries:
            shipinhao_logger.info(f"[-] Step 1 等待上传控件... ({attempt}/{retries})")
            await tab.sleep(delay)
    return False


def _normalize_eval_payload(payload):
    if isinstance(payload, (list, tuple)) and payload:
        payload = payload[0]
    if hasattr(payload, "value"):
        payload = getattr(payload, "value", None)
    if isinstance(payload, str):
        payload = payload.strip()
        if payload.startswith("{") and payload.endswith("}"):
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                return {"text": payload}
    return payload or {}


def _compact_payload_text(payload: dict, limit: int = 240) -> str:
    text = str((payload or {}).get("text") or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _js_collect_page_state(file_name: str = "") -> str:
    file_name_json = json.dumps(file_name or "", ensure_ascii=False)
    return f"""
    (() => {{
        const fileName = {file_name_json};
        const uploadStatePattern = /上传成功|上传完成|100%|处理中|转码|替换视频|重新上传|视频时长|视频封面|上传中|上传进度|预览/;
        const loginPattern = /微信扫码|扫码登录|请使用微信扫码|刷新二维码|登录后使用/;
        const publishPattern = /发表|发布|上传视频|替换视频|重新上传|视频封面|内容管理/;
        const previewSelectors = [
            'video',
            'img[class*="cover"]',
            'img[class*="thumb"]',
            '[class*="poster"] img',
            '[class*="preview"] video',
            '[class*="preview"] img',
            '[class*="upload"] [class*="item"]',
            '[class*="upload"] [class*="card"]',
            '[class*="upload"] [class*="preview"]',
            '[class*="post"] [class*="preview"]',
            '[class*="upload"] canvas',
        ];
        const seen = new Set();
        const snippets = [];
        let hasFileName = false;
        let hasPreview = false;
        let hasUploadState = false;
        let hasLoginPrompt = false;
        let hasPublishEntry = false;
        let fileInputCount = 0;

        function normalizeText(value) {{
            return (value || '').replace(/\\s+/g, ' ').trim();
        }}

        function inspect(root, depth) {{
            if (!root || depth > 5 || seen.has(root)) return;
            seen.add(root);

            let text = '';
            try {{
                text = normalizeText(root.body ? root.body.innerText : root.innerText);
            }} catch (e) {{}}
            if (text) {{
                snippets.push(text.slice(0, 320));
                if (fileName && text.includes(fileName)) hasFileName = true;
                if (uploadStatePattern.test(text)) hasUploadState = true;
                if (loginPattern.test(text)) hasLoginPrompt = true;
                if (publishPattern.test(text)) hasPublishEntry = true;
            }}

            try {{
                for (const sel of previewSelectors) {{
                    if (root.querySelector(sel)) {{
                        hasPreview = true;
                        break;
                    }}
                }}
            }} catch (e) {{}}

            try {{
                const fileInputs = root.querySelectorAll('input[type=file]');
                for (const input of fileInputs) {{
                    const count = input.files ? input.files.length : 0;
                    if (count > 0) {{
                        fileInputCount = Math.max(fileInputCount, count);
                        const names = Array.from(input.files).map(file => file && file.name || '');
                        if (fileName && names.includes(fileName)) hasFileName = true;
                    }}
                }}
            }} catch (e) {{}}

            try {{
                root.querySelectorAll('iframe').forEach((frame) => {{
                    try {{
                        if (frame.contentDocument) inspect(frame.contentDocument, depth + 1);
                    }} catch (e) {{}}
                }});
            }} catch (e) {{}}

            try {{
                root.querySelectorAll('*').forEach((el) => {{
                    if (el.shadowRoot) inspect(el.shadowRoot, depth + 1);
                }});
            }} catch (e) {{}}
        }}

        inspect(document, 0);
        return JSON.stringify({{
            hasFileName,
            hasPreview,
            hasUploadState,
            hasLoginPrompt,
            hasPublishEntry,
            fileInputCount,
            text: normalizeText(snippets.join(' | ')).slice(0, 2400),
        }});
    }})()
    """


def _js_detect_uploaded_video(file_path: str) -> str:
    return _js_collect_page_state(os.path.basename(file_path))


def _preview_ready(payload: dict) -> bool:
    return bool(
        payload.get("hasFileName")
        or payload.get("hasPreview")
        or payload.get("hasUploadState")
        or int(payload.get("fileInputCount") or 0) > 0
    )


async def _wait_uploaded_preview(tab, file_path: str, retries: int = 80, delay: float = 0.5):
    last_payload = {}
    for attempt in range(1, retries + 1):
        try:
            payload = await tab.evaluate(_js_detect_uploaded_video(file_path), return_by_value=True)
        except Exception:
            payload = None
        payload = _normalize_eval_payload(payload)
        last_payload = payload
        if _preview_ready(payload):
            if attempt > 1:
                shipinhao_logger.info(f"[-] Step 2 预览确认成功（第 {attempt} 次）")
            return payload
        if attempt < retries and attempt % 8 == 0:
            shipinhao_logger.info(
                f"[-] Step 2 等待上传预览... ({attempt}/{retries}) | "
                f"publish={payload.get('hasPublishEntry')} login={payload.get('hasLoginPrompt')}"
            )
        await tab.sleep(delay)
    return last_payload


async def _fill_text(el, text: str) -> bool:
    if not text:
        return True
    try:
        await el.click()
        await el.send_keys(text)
        return True
    except Exception:
        pass
    try:
        j = json.dumps(text, ensure_ascii=False)
        await el.apply(f"""(el) => {{
            el.focus();
            const t = {j};
            if (el.contentEditable === 'true') {{
                el.innerText = t;
                el.dispatchEvent(new InputEvent('input', {{bubbles: true}}));
            }} else {{
                el.value = t;
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
            }}
        }}""")
        return True
    except Exception as e:
        shipinhao_logger.debug(f"_fill_text 失败：{e}")
        return False


def _js_fill_title_desc(title: str, desc: str, tags: list) -> str:
    """在 iframe + shadow DOM 内查找并填充标题、文案"""
    t = json.dumps(title[:SPH_TITLE_MAX], ensure_ascii=False)
    d = json.dumps(desc or "", ensure_ascii=False)
    return f"""
    (function() {{
        var foundTitle = null, foundDesc = null;
        function setVal(el, val) {{
            if (!el) return false;
            el.focus();
            if (el.contentEditable === 'true') {{
                el.innerText = val;
                el.dispatchEvent(new InputEvent('input', {{bubbles: true, data: val}}));
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
            }} else {{
                el.value = val;
                el.dispatchEvent(new Event('input', {{bubbles: true}}));
            }}
            return true;
        }}
        function search(doc, depth) {{
            if (!doc || depth > 4) return;
            if (!foundTitle) {{
                var el = doc.querySelector('input[placeholder*="标题"]') || doc.querySelector('input[placeholder*="填写"]')
                    || doc.querySelector('.title-input') || doc.querySelector('input.weui-desktop-form__input');
                if (el) foundTitle = el;
            }}
            if (!foundDesc) {{
                var ed = doc.querySelector('.input-editor') || doc.querySelector('.ql-editor');
                if (ed) foundDesc = ed;
                else {{
                    var ce = doc.querySelectorAll('[contenteditable="true"]');
                    for (var i = 0; i < ce.length; i++) {{
                        if (ce[i].classList.contains('input-editor') || ce[i].classList.contains('ql-editor')) {{ foundDesc = ce[i]; break; }}
                    }}
                    if (!foundDesc && ce.length > 1) foundDesc = ce[1];
                    if (!foundDesc && ce.length) foundDesc = ce[0];
                }}
            }}
            if (foundTitle && foundDesc) return;
            doc.querySelectorAll('iframe').forEach(function(fr) {{
                try {{ if (fr.contentDocument) search(fr.contentDocument, depth + 1); }} catch(e) {{}}
            }});
            doc.querySelectorAll('*').forEach(function(el) {{
                if (el.shadowRoot) search(el.shadowRoot, depth + 1);
            }});
        }}
        search(document, 0);
        var ok = 0;
        if (foundTitle) {{ setVal(foundTitle, {t}); ok++; }}
        if (foundDesc) {{ setVal(foundDesc, {d}); ok++; }}
        return ok;
    }})()
    """


async def _try_fill_topics_via_click(tab, tags: list) -> bool:
    """点击 #话题 按钮并输入每个话题"""
    if not tags:
        return True
    try:
        js = """
        (function(tags) {
            var found = null;
            function search(doc, depth) {
                if (!doc || depth > 4) return;
                var ed = doc.querySelector('.input-editor');
                if (ed) { found = ed; return; }
                doc.querySelectorAll('iframe').forEach(function(fr) {
                    try { if (fr.contentDocument) search(fr.contentDocument, depth + 1); } catch(e) {}
                });
                doc.querySelectorAll('*').forEach(function(el) {
                    if (el.shadowRoot) search(el.shadowRoot, depth + 1);
                });
            }
            search(document, 0);
            if (!found) return false;
            found.focus();
            var sel = window.getSelection();
            sel.selectAllChildren(found);
            sel.collapseToEnd();
            var toAdd = tags.map(function(t) { return '#' + t; }).join(' ');
            document.execCommand('insertText', false, ' ' + toAdd);
            return true;
        })(%s)
        """ % json.dumps(tags, ensure_ascii=False)
        ok = await tab.evaluate(js, return_by_value=True)
        if ok:
            shipinhao_logger.info(f"[-] 已追加话题：{', '.join(tags)}")
            return True
    except Exception as e:
        shipinhao_logger.debug(f"追加话题失败：{e}")
    return False


def _gen_title_desc_from_path(file_path: str, tags: list = None) -> tuple:
    from common.utils import gen_title_desc_from_path
    return gen_title_desc_from_path(file_path, title_max=SPH_TITLE_MAX, style="rich", tags=tags)


def _find_existing_shipinhao_tab(browser):
    try:
        tabs = getattr(browser, "tabs", None) or []
    except Exception:
        return None
    for tab in tabs:
        try:
            url = (getattr(tab, "url", None) or getattr(getattr(tab, "target", None), "url", None) or "").lower()
        except Exception:
            continue
        if "channels.weixin.qq.com" not in url:
            continue
        if any(marker in url for marker in ("platform/post/create", "platform/post/list", "platform/content")):
            return tab
    return None


async def _list_page_contains_title(tab, title: str) -> bool:
    normalized = (title or "").strip()
    if not normalized:
        return False
    probes = []
    for size in (16, 12, 8):
        snippet = normalized[:size].strip()
        if snippet and snippet not in probes:
            probes.append(snippet)
    for probe in probes:
        try:
            if await _has_text(tab, probe, timeout=1):
                return True
        except Exception:
            continue
    return False


def _js_publish_button_probe() -> str:
    return """
    (() => {
        const labels = new Set(["发表", "发布", "视频发表", "立即发表", "发布视频"]);
        const seen = new Set();
        const candidates = [];

        function textOf(el) {
            return (el && (el.innerText || el.textContent || "") || "").replace(/\\s+/g, " ").trim();
        }

        function visible(el) {
            if (!el || !el.isConnected) return false;
            const style = window.getComputedStyle(el);
            if (!style || style.display === "none" || style.visibility === "hidden" || Number(style.opacity || "1") === 0) {
                return false;
            }
            const rect = el.getBoundingClientRect();
            return rect.width >= 40 && rect.height >= 24 && rect.bottom > 0 && rect.right > 0;
        }

        function disabled(el) {
            return !!(
                el.disabled ||
                el.getAttribute("disabled") !== null ||
                el.getAttribute("aria-disabled") === "true" ||
                /disabled|ban/.test((el.className || "").toString())
            );
        }

        function collect(root, depth) {
            if (!root || depth > 4 || seen.has(root)) return;
            seen.add(root);
            let elements = [];
            try {
                elements = root.querySelectorAll("button, [role=button], .weui-desktop-btn, .weui-desktop-btn_primary, div, span, a");
            } catch (e) {}
            for (const el of elements) {
                const text = textOf(el);
                if (!labels.has(text) || !visible(el) || disabled(el)) continue;
                const rect = el.getBoundingClientRect();
                const primary = /primary|publish|submit|weui-desktop-btn_primary/.test((el.className || "").toString()) ? 1 : 0;
                const exactPublish = text === "发表" ? 1 : 0;
                candidates.push({
                    text,
                    rect,
                    primary,
                    exactPublish,
                    score: exactPublish * 1000 + primary * 200 + Math.round(rect.bottom) + Math.round(rect.right / 10),
                });
                el.__openclawPublishCandidate = true;
            }
            try {
                root.querySelectorAll("iframe").forEach((frame) => {
                    try { if (frame.contentDocument) collect(frame.contentDocument, depth + 1); } catch (e) {}
                });
            } catch (e) {}
            try {
                root.querySelectorAll("*").forEach((el) => {
                    if (el.shadowRoot) collect(el.shadowRoot, depth + 1);
                });
            } catch (e) {}
        }

        collect(document, 0);
        candidates.sort((a, b) => b.score - a.score);
        const best = candidates[0] || null;
        return JSON.stringify({
            found: !!best,
            text: best ? best.text : "",
            score: best ? best.score : 0,
            count: candidates.length,
            rect: best ? best.rect : null,
        });
    })()
    """


def _js_click_publish_button(force_native: bool = False) -> str:
    force_native_json = "true" if force_native else "false"
    return """
    (() => {
        const labels = new Set(["发表", "发布", "视频发表", "立即发表", "发布视频"]);
        const seen = new Set();
        let best = null;
        const forceNative = %s;

        function textOf(el) {
            return (el && (el.innerText || el.textContent || "") || "").replace(/\\s+/g, " ").trim();
        }

        function visible(el) {
            if (!el || !el.isConnected) return false;
            const style = window.getComputedStyle(el);
            if (!style || style.display === "none" || style.visibility === "hidden" || Number(style.opacity || "1") === 0) {
                return false;
            }
            const rect = el.getBoundingClientRect();
            return rect.width >= 40 && rect.height >= 24 && rect.bottom > 0 && rect.right > 0;
        }

        function disabled(el) {
            return !!(
                el.disabled ||
                el.getAttribute("disabled") !== null ||
                el.getAttribute("aria-disabled") === "true" ||
                /disabled|ban/.test((el.className || "").toString())
            );
        }

        function visit(root, depth) {
            if (!root || depth > 4 || seen.has(root)) return;
            seen.add(root);
            let elements = [];
            try {
                elements = root.querySelectorAll("button, [role=button], .weui-desktop-btn, .weui-desktop-btn_primary, div, span, a");
            } catch (e) {}
            for (const el of elements) {
                const text = textOf(el);
                if (!labels.has(text) || !visible(el) || disabled(el)) continue;
                const rect = el.getBoundingClientRect();
                const primary = /primary|publish|submit|weui-desktop-btn_primary/.test((el.className || "").toString()) ? 1 : 0;
                const exactPublish = text === "发表" ? 1 : 0;
                const score = exactPublish * 1000 + primary * 200 + Math.round(rect.bottom) + Math.round(rect.right / 10);
                if (!best || score > best.score) {
                    best = { el, text, rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height }, score };
                }
            }
            try {
                root.querySelectorAll("iframe").forEach((frame) => {
                    try { if (frame.contentDocument) visit(frame.contentDocument, depth + 1); } catch (e) {}
                });
            } catch (e) {}
            try {
                root.querySelectorAll("*").forEach((el) => {
                    if (el.shadowRoot) visit(el.shadowRoot, depth + 1);
                });
            } catch (e) {}
        }

        visit(document, 0);
        if (!best || !best.el) {
            return JSON.stringify({ clicked: false, reason: "not_found" });
        }

        const el = best.el;
        try { el.scrollIntoView({ block: "center", inline: "center" }); } catch (e) {}
        try { el.focus(); } catch (e) {}
        try {
            if (forceNative) {
                el.click();
            } else {
                el.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, cancelable: true, pointerType: "mouse", isPrimary: true, button: 0, buttons: 1 }));
                el.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, view: window, button: 0, buttons: 1 }));
                el.dispatchEvent(new PointerEvent("pointerup", { bubbles: true, cancelable: true, pointerType: "mouse", isPrimary: true, button: 0, buttons: 0 }));
                el.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true, view: window, button: 0, buttons: 0 }));
                el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window, button: 0, buttons: 0 }));
            }
        } catch (e) {
            return JSON.stringify({ clicked: false, reason: "click_failed", text: best.text, score: best.score, error: String(e) });
        }
        return JSON.stringify({
            clicked: true,
            text: best.text,
            score: best.score,
            rect: best.rect,
        });
    })()
    """ % force_native_json


def _js_publish_submission_state() -> str:
    return """
    (() => {
        const labels = new Set(["发表", "发布", "视频发表", "立即发表", "发布视频"]);
        const loadingPattern = /发表中|发布中|提交中|处理中|请稍候|上传中/;
        const successPattern = /发表成功|发布成功|已发表/;
        const pageText = (document.body && document.body.innerText || "").replace(/\\s+/g, " ").trim();
        const state = {
            url: location.href,
            hasLoadingText: loadingPattern.test(pageText),
            hasSuccessText: successPattern.test(pageText),
            buttonVisible: false,
            buttonDisabled: false,
        };
        const nodes = document.querySelectorAll("button, [role=button], .weui-desktop-btn, .weui-desktop-btn_primary, div, span, a");
        for (const el of nodes) {
            const text = (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
            if (!labels.has(text)) continue;
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            const visible = style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || "1") !== 0 && rect.width >= 40 && rect.height >= 24;
            if (!visible) continue;
            state.buttonVisible = true;
            state.buttonDisabled = !!(el.disabled || el.getAttribute("disabled") !== null || el.getAttribute("aria-disabled") === "true");
            break;
        }
        return JSON.stringify(state);
    })()
    """


def _js_neutralize_publish_overlays() -> str:
    return """
    (() => {
        const selectors = [
            '[class*="mask"]',
            '[class*="modal"]',
            '[class*="dialog"]',
            '[class*="popover"]',
            '[class*="tooltip"]',
            '[class*="guide"]',
            '[class*="tour"]',
            '[class*="layer"]',
            '[class*="banner"]',
            '[class*="toast"]',
        ];
        let touched = 0;
        for (const sel of selectors) {
            try {
                document.querySelectorAll(sel).forEach((el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity || "1") === 0) return;
                    if (rect.width < 40 || rect.height < 40) return;
                    el.style.pointerEvents = "none";
                    touched += 1;
                });
            } catch (e) {}
        }
        return touched;
    })()
    """


def _js_focus_publish_button_and_press_enter() -> str:
    return """
    (() => {
        const labels = new Set(["发表", "发布", "视频发表", "立即发表", "发布视频"]);
        const seen = new Set();
        let best = null;

        function textOf(el) {
            return (el && (el.innerText || el.textContent || "") || "").replace(/\\s+/g, " ").trim();
        }

        function visible(el) {
            if (!el || !el.isConnected) return false;
            const style = window.getComputedStyle(el);
            if (!style || style.display === "none" || style.visibility === "hidden" || Number(style.opacity || "1") === 0) {
                return false;
            }
            const rect = el.getBoundingClientRect();
            return rect.width >= 40 && rect.height >= 24 && rect.bottom > 0 && rect.right > 0;
        }

        function disabled(el) {
            return !!(
                el.disabled ||
                el.getAttribute("disabled") !== null ||
                el.getAttribute("aria-disabled") === "true" ||
                /disabled|ban/.test((el.className || "").toString())
            );
        }

        function visit(root, depth) {
            if (!root || depth > 4 || seen.has(root)) return;
            seen.add(root);
            let elements = [];
            try {
                elements = root.querySelectorAll("button, [role=button], .weui-desktop-btn, .weui-desktop-btn_primary, div, span, a");
            } catch (e) {}
            for (const el of elements) {
                const text = textOf(el);
                if (!labels.has(text) || !visible(el) || disabled(el)) continue;
                const rect = el.getBoundingClientRect();
                const primary = /primary|publish|submit|weui-desktop-btn_primary/.test((el.className || "").toString()) ? 1 : 0;
                const exactPublish = text === "发表" ? 1 : 0;
                const score = exactPublish * 1000 + primary * 200 + Math.round(rect.bottom) + Math.round(rect.right / 10);
                if (!best || score > best.score) {
                    best = { el, text, score };
                }
            }
            try {
                root.querySelectorAll("iframe").forEach((frame) => {
                    try { if (frame.contentDocument) visit(frame.contentDocument, depth + 1); } catch (e) {}
                });
            } catch (e) {}
            try {
                root.querySelectorAll("*").forEach((el) => {
                    if (el.shadowRoot) visit(el.shadowRoot, depth + 1);
                });
            } catch (e) {}
        }

        visit(document, 0);
        if (!best || !best.el) {
            return JSON.stringify({ clicked: false, reason: "not_found" });
        }

        const el = best.el;
        try { el.scrollIntoView({ block: "center", inline: "center" }); } catch (e) {}
        try { el.focus(); } catch (e) {}
        try {
            el.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: "Enter", code: "Enter" }));
            el.dispatchEvent(new KeyboardEvent("keypress", { bubbles: true, cancelable: true, key: "Enter", code: "Enter" }));
            el.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true, cancelable: true, key: "Enter", code: "Enter" }));
            return JSON.stringify({ clicked: true, text: best.text, mode: "keyboard_enter", score: best.score });
        } catch (e) {
            return JSON.stringify({ clicked: false, reason: "keyboard_failed", text: best.text, score: best.score, error: String(e) });
        }
    })()
    """


async def _click_via_cdp(tab, rect: dict) -> bool:
    try:
        from nodriver import cdp
        x = float(rect["x"]) + float(rect["width"]) / 2.0
        y = float(rect["y"]) + float(rect["height"]) / 2.0
        await tab.send(cdp.input_.dispatch_mouse_event("mouseMoved", x=x, y=y, button=cdp.input_.MouseButton.LEFT, buttons=1, pointer_type="mouse"))
        await tab.send(cdp.input_.dispatch_mouse_event("mousePressed", x=x, y=y, button=cdp.input_.MouseButton.LEFT, buttons=1, click_count=1, pointer_type="mouse"))
        await tab.send(cdp.input_.dispatch_mouse_event("mouseReleased", x=x, y=y, button=cdp.input_.MouseButton.LEFT, buttons=0, click_count=1, pointer_type="mouse"))
        return True
    except Exception as e:
        shipinhao_logger.warning(f"[-] CDP 鼠标点击失败：{e}")
        return False


async def _wait_publish_submission_state(tab, checks: int = 20, delay: float = 0.3) -> bool:
    for _ in range(checks):
        await tab.sleep(delay)
        state = _normalize_eval_payload(await tab.evaluate(_js_publish_submission_state(), return_by_value=True))
        url = (state.get("url") or "").lower()
        if state.get("hasSuccessText") or state.get("hasLoadingText"):
            return True
        if "success" in url or "post/list" in url or "content" in url:
            return True
        if state.get("buttonVisible") and state.get("buttonDisabled"):
            return True
    return False


async def _click_publish_button(tab) -> tuple[bool, str]:
    payload = _normalize_eval_payload(await tab.evaluate(_js_publish_button_probe(), return_by_value=True))
    if not payload.get("found"):
        return False, "未找到真实发表按钮"

    try:
        await tab.evaluate(_js_neutralize_publish_overlays(), return_by_value=True)
    except Exception:
        pass

    clicked_text = payload.get("text") or "发表"
    rect = payload.get("rect") or {}
    attempts = []
    if rect:
        attempts.append(("cdp", rect))
    attempts.append(("dom", None))
    attempts.append(("native", None))
    attempts.append(("keyboard", None))

    for mode, mode_rect in attempts:
        if mode == "cdp":
            clicked = await _click_via_cdp(tab, mode_rect)
            click_payload = {"clicked": clicked, "text": clicked_text}
        elif mode == "dom":
            click_payload = _normalize_eval_payload(await tab.evaluate(_js_click_publish_button(False), return_by_value=True))
        elif mode == "keyboard":
            click_payload = _normalize_eval_payload(await tab.evaluate(_js_focus_publish_button_and_press_enter(), return_by_value=True))
        else:
            click_payload = _normalize_eval_payload(await tab.evaluate(_js_click_publish_button(True), return_by_value=True))

        if not click_payload.get("clicked"):
            continue

        clicked_text = click_payload.get("text") or clicked_text
        if await _wait_publish_submission_state(tab):
            return True, clicked_text
        try:
            await tab.evaluate(_js_neutralize_publish_overlays(), return_by_value=True)
        except Exception:
            pass
    return False, f"按钮“{clicked_text}”未进入提交态"


async def _prepare_publish_retry(tab, aggressive: bool = False) -> None:
    try:
        await tab.evaluate(_js_neutralize_publish_overlays(), return_by_value=True)
    except Exception:
        pass

    scroll_times = 5 if aggressive else 3
    for _ in range(scroll_times):
        try:
            await tab.evaluate("""
                window.scrollTo(0, 9e9);
                document.documentElement.scrollTop = 9e9;
                document.body && (document.body.scrollTop = 9e9);
            """)
            await tab.sleep(0.4 if aggressive else 0.3)
        except Exception:
            pass


async def _publish_with_three_layer_fallback(browser, tab) -> tuple[bool, str, object]:
    layers = [
        ("第一层", "当前页直接点击", tab, False),
        ("第二层", "当前页滚动到底并强力重试", tab, True),
    ]

    current_tab = tab
    for layer_name, layer_desc, target_tab, aggressive in layers:
        await _prepare_publish_retry(target_tab, aggressive=aggressive)
        clicked, publish_message = await _click_publish_button(target_tab)
        if clicked:
            return True, f"{layer_name}成功：{layer_desc}，按钮「{publish_message or '发表'}」", target_tab
        shipinhao_logger.warning(f"[-] Step 5 {layer_name}未进入提交态：{publish_message}")

    recovered_tab = await _recover_shipinhao_tab(browser)
    if recovered_tab is not None:
        current_tab = recovered_tab
        shipinhao_logger.warning("[-] Step 5 第三层：已恢复标签页，准备最终重试")
        await _prepare_publish_retry(current_tab, aggressive=True)
        clicked, publish_message = await _click_publish_button(current_tab)
        if clicked:
            return True, f"第三层成功：恢复标签页后按钮「{publish_message or '发表'}」", current_tab
        return False, f"第三层失败：{publish_message}", current_tab

    return False, "第三层失败：无法恢复发布标签页", current_tab


async def _recover_shipinhao_tab(browser):
    tab = _find_existing_shipinhao_tab(browser)
    if tab is not None:
        return tab
    for target_url in (
        "https://channels.weixin.qq.com/platform/post/list",
        "https://channels.weixin.qq.com/platform/content",
        SPH_UPLOAD_URL,
    ):
        try:
            return await browser.get(target_url)
        except Exception:
            continue
    return None


async def _confirm_publish_result(browser, tab, title: str) -> bool:
    current_tab = tab
    list_page_checks = 0
    max_list_page_checks = 3
    for _ in range(240):
        await asyncio.sleep(0.5)
        try:
            url = (current_tab.url or "").lower()
        except Exception:
            url = ""
        try:
            if "success" in url:
                shipinhao_logger.success("[-] 视频发表成功")
                return True
            if "post/list" in url or "content" in url:
                list_page_checks += 1
                if await _list_page_contains_title(current_tab, title):
                    shipinhao_logger.success("[-] 视频发表成功（列表页已出现本次标题）")
                    return True
                if list_page_checks >= max_list_page_checks:
                    return True
                continue
            if (
                await _has_text(current_tab, "发表成功", timeout=1)
                or await _has_text(current_tab, "发布成功", timeout=1)
                or await _has_text(current_tab, "已发表", timeout=1)
            ):
                shipinhao_logger.success("[-] 视频发表成功")
                return True
            shipinhao_logger.info("[-] 视频正在发表中...")
        except Exception as e:
            shipinhao_logger.warning(f"[-] 提交后状态检查异常，尝试恢复会话：{e}")
            recovered = await _recover_shipinhao_tab(browser)
            if recovered is None:
                await asyncio.sleep(1)
                continue
            current_tab = recovered
            try:
                await current_tab.sleep(1)
            except Exception:
                pass
    shipinhao_logger.warning("[-] Step 6 超时：已触发表达流程，但未确认成功")
    return False


async def _check_logged_in(browser, account_file: str, account_name: str) -> tuple[bool, object]:
    """返回 (是否已登录，tab)。登录成功时 tab 已在发表页"""
    if need_cookie_file(AUTH_MODE) and os.path.exists(account_file):
        try:
            await browser.cookies.load(account_file)
        except Exception:
            pass

    tab = _find_existing_shipinhao_tab(browser)
    if tab is None:
        # connect 模式下 browser.get() 可能抛出 StopIteration，重试一次
        for retry in range(2):
            try:
                tab = await browser.get(SPH_UPLOAD_URL)
                break
            except (StopIteration, RuntimeError) as e:
                if retry == 0:
                    shipinhao_logger.warning(f"[-] browser.get() 失败，重试：{e}")
                    _open_target_tab(SPH_UPLOAD_URL)
                    await asyncio.sleep(1)
                else:
                    shipinhao_logger.error("[-] browser.get() 重试失败")
                    return False, None
    if tab is None:
        return False, None
    
    # 视频号登录页检测
    await tab.sleep(5)
    
    url_lower = (tab.url or "").lower()
    if "login" in url_lower or "mp.weixin.qq.com" in url_lower:
        shipinhao_logger.info("[+] 检测到登录页，cookie/会话已失效")
        return False, None
    
    await tab.sleep(3)

    for i in range(3):
        try:
            payload = await tab.evaluate(_js_collect_page_state(), return_by_value=True)
        except Exception:
            payload = None
        payload = _normalize_eval_payload(payload)

        if payload.get("hasLoginPrompt") and not payload.get("hasPublishEntry"):
            if i < 2:
                await tab.sleep(2)
                continue
            shipinhao_logger.info("[+] 检测到登录页，需要微信扫码登录")
            return False, None

        if payload.get("hasPublishEntry"):
            shipinhao_logger.info("[+] 已登录（检测到发布态页面元素）")
            return True, tab

        if i < 2:
            await tab.sleep(2)

    if "post/create" in url_lower and not payload.get("hasLoginPrompt"):
        shipinhao_logger.info("[+] 已登录（URL 与页面状态显示在发布页）")
        return True, tab

    shipinhao_logger.warning(f"[-] 登录状态不明确，按未登录处理：{_compact_payload_text(payload)}")
    return False, None


async def cookie_auth(account_file: str, account_name: str = "default") -> tuple[bool, object, object]:
    """返回 (是否已登录，browser, tab) 或 (False, None, None)"""
    for try_reuse in (True, False):
        res = await get_browser(
            headless=LOCAL_CHROME_HEADLESS, account_name=account_name, try_reuse=try_reuse
        )
        browser, was_reused = res if isinstance(res, tuple) else (res, False)
        try:
            ok, tab = await _check_logged_in(browser, account_file, account_name)
            if ok and tab is not None:
                return True, browser, tab
        except (StopIteration, RuntimeError) as e:
            if try_reuse:
                shipinhao_logger.warning(f"[-] 复用 Chrome 失败 ({e})，改用新浏览器")
                continue
            raise
        if not was_reused:
            browser.stop()
    return False, None, None


async def shipinhao_setup(account_file: str, handle: bool = False, account_name: str = "default"):
    existing = await try_connect_existing_chrome()
    if existing:
        shipinhao_logger.info("[+] 已连接并复用已有浏览器")
        return True, existing

    # 视频号优先保证自己的 connect 会话（9226 + cookies/chrome_connect_sph）可用，
    # 避免 OpenClaw 默认走 profile 校验后又提示重新扫码。
    if ensure_connect_login_chrome():
        try:
            browser, tab = await attach_login_chrome()
            ok, checked_tab = await _check_logged_in(browser, account_file, account_name)
            if ok and checked_tab is not None:
                shipinhao_logger.info("[+] 已连接视频号专用 connect Chrome")
                return True, (browser, checked_tab)
            if handle:
                shipinhao_logger.info("[+] 需要登录，即将打开视频号专用 connect Chrome...")
                return True, (browser, tab)
        except Exception as e:
            shipinhao_logger.warning(f"[-] connect Chrome 预检失败 ({e})，继续尝试其他登录方式")

    if need_cookie_file(AUTH_MODE) and not os.path.exists(account_file):
        if not handle:
            shipinhao_logger.info("[+] cookie 文件不存在，请先登录（handle=True）")
            return False, None
    else:
        ok, browser, tab = await cookie_auth(account_file, account_name)
        if ok and browser is not None and tab is not None:
            return True, (browser, tab)

    if not handle:
        return False, None

    shipinhao_logger.info("[+] 需要登录，即将打开浏览器...")
    browser, tab = await shipinhao_cookie_gen(account_file, account_name)
    return True, (browser, tab)


async def _is_login_page(tab) -> bool:
    url = (tab.url or "").lower()
    if "platform" in url and "post" in url:
        return False
    if "channels.weixin.qq.com" in url and "login" not in url and "mp.weixin" not in url:
        return False
    if "login" in url or "mp.weixin" in url:
        return True
    if await _has_text(tab, "微信扫码", timeout=1):
        return True
    if await _has_text(tab, "扫码登录", timeout=1):
        return True
    if await _has_text(tab, "请使用微信扫码", timeout=1):
        return True
    return False


async def shipinhao_cookie_gen(account_file: str, account_name: str = "default"):
    connect_bootstrap_ok = ensure_connect_login_chrome()
    if connect_bootstrap_ok:
        try:
            browser, tab = await attach_login_chrome()
            shipinhao_logger.info("[+] 已连接视频号专用 connect Chrome，请在浏览器中用微信扫码登录视频号助手")
            await tab.sleep(2)
        except Exception as e:
            shipinhao_logger.warning(f"[-] 连接 connect Chrome 失败：{e}，改用新浏览器")
            browser = None
    else:
        browser = None

    if not browser:
        browser = await uc.start(uc.Config(
            headless=False,
            browser_executable_path=LOCAL_CHROME_PATH,
            sandbox=False,
        ))
        tab = await browser.get(SPH_BASE_URL)
        shipinhao_logger.info("[+] 请用微信扫码登录视频号助手，登录成功约 15 秒内会自动跳转")

    poll_interval = 15
    max_wait = 600
    for elapsed in range(0, max_wait, poll_interval):
        await tab.sleep(poll_interval)
        for retry in range(2):
            try:
                tab = await browser.get(SPH_UPLOAD_URL)
                break
            except (StopIteration, RuntimeError):
                if retry == 0:
                    _open_target_tab(SPH_UPLOAD_URL)
                    await asyncio.sleep(1)
        await tab.sleep(2)
        if not await _is_login_page(tab):
            shipinhao_logger.info("[+] 检测到已登录，正在保存...")
            break
        shipinhao_logger.info(f"[-] 等待登录中... ({elapsed + poll_interval}s)")
    else:
        shipinhao_logger.error("[-] 登录超时")
        browser.stop()
        raise TimeoutError("登录超时，请重试")

    if need_cookie_file(AUTH_MODE):
        try:
            cookie_dir = os.path.dirname(account_file)
            os.makedirs(cookie_dir, exist_ok=True)
            shipinhao_logger.info(f"[-] 保存 cookie...")
            await asyncio.wait_for(browser.cookies.save(account_file), timeout=5.0)
            shipinhao_logger.info("[+] 登录信息已保存")
        except (asyncio.TimeoutError, Exception) as e:
            shipinhao_logger.warning(f"[-] 保存 cookie 跳过：{e}")

    shipinhao_logger.info("[+] 已在发表页，准备进入上传流程")
    return browser, tab


class ShipinhaoVideo(object):
    def __init__(
        self,
        title: str,
        file_path: str,
        tags: list,
        publish_date: datetime,
        account_file: str,
        thumbnail_path=None,
        description: str = "",
        account_name: str = "default",
    ):
        _title = (title or "").strip()
        _desc = (description or "").strip()
        if not _title or not _desc:
            def_title, def_desc = _gen_title_desc_from_path(file_path)
            _title = _title or def_title
            _desc = _desc or def_desc
        self.title = _title[:SPH_TITLE_MAX]
        self.file_path = file_path
        self.tags = (tags or [])[:SPH_TAGS_MAX]
        self.description = _desc
        self.publish_date = publish_date
        self.account_file = account_file
        self.account_name = account_name
        self.date_format = "%Y年%m月%d日 %H:%M"
        self.local_executable_path = LOCAL_CHROME_PATH
        self.headless = LOCAL_CHROME_HEADLESS
        self.thumbnail_path = thumbnail_path

    async def upload(self, existing_browser=None, existing_tab=None) -> bool:
        reuse = existing_browser is not None and existing_tab is not None
        keep_browser_open = reuse
        if reuse:
            browser, tab = existing_browser, existing_tab
        else:
            for try_reuse in (True, False):
                res = await get_browser(
                    headless=self.headless, account_name=self.account_name, try_reuse=try_reuse
                )
                browser, was_reused = res if isinstance(res, tuple) else (res, False)
                keep_browser_open = was_reused
                if need_cookie_file(AUTH_MODE) and os.path.exists(self.account_file):
                    try:
                        await browser.cookies.load(self.account_file)
                    except Exception:
                        pass
                try:
                    tab = await browser.get(SPH_UPLOAD_URL)
                    break
                except (StopIteration, RuntimeError) as e:
                    if try_reuse:
                        shipinhao_logger.warning(f"[-] 复用 Chrome 失败 ({e})，改用新浏览器")
                    else:
                        raise
        try:
            shipinhao_logger.info(f"[+] 正在上传 - {os.path.basename(self.file_path)}")
            shipinhao_logger.info("[-] Step 0: 打开发表页...")
            await tab.sleep(3)

            ok_step1 = await _wait_and_upload_file_via_cdp(tab, self.file_path)
            if ok_step1:
                shipinhao_logger.info("[-] Step 1 完成：已设置文件")
            else:
                shipinhao_logger.error("[-] Step 1 失败：未找到上传 input")
                return False

            preview_payload = await _wait_uploaded_preview(tab, self.file_path)
            if _preview_ready(preview_payload):
                shipinhao_logger.success("[-] 视频上传完毕")
                shipinhao_logger.info("[-] Step 2 完成")
            else:
                shipinhao_logger.error(
                    "[-] Step 2 失败：页面未出现视频预览/上传卡片"
                    f" | publish={preview_payload.get('hasPublishEntry')}"
                    f" login={preview_payload.get('hasLoginPrompt')}"
                    f" fileInputCount={preview_payload.get('fileInputCount')}"
                    f" | text={_compact_payload_text(preview_payload)}"
                )
                return False

            await tab.sleep(0.5)

            shipinhao_logger.info("[-] 正在填充标题、文案和话题...")
            try:
                filled = await tab.evaluate(
                    _js_fill_title_desc(self.title, self.description, self.tags),
                    return_by_value=True,
                )
                if filled and int(filled) >= 1:
                    shipinhao_logger.info(f"[-] Step 3+4 完成：标题和文案已填充")
                    if self.tags:
                        await asyncio.sleep(0.3)
                        await _try_fill_topics_via_click(tab, self.tags)
                        shipinhao_logger.info(f"[-] 已添加 {len(self.tags)} 个话题")
                else:
                    shipinhao_logger.warning("[-] JS 填充未命中")
            except Exception as e:
                shipinhao_logger.debug(f"填充失败：{e}")

            shipinhao_logger.info("[-] Step 5: 点击发表...")
            clicked, publish_message, submit_tab = await _publish_with_three_layer_fallback(browser, tab)
            if not clicked:
                shipinhao_logger.error(f"[-] Step 5 失败：{publish_message}")
                return False
            tab = submit_tab or tab
            shipinhao_logger.info(f"[-] Step 5 完成：{publish_message}")

            await tab.sleep(1)
            publish_confirmed = await _confirm_publish_result(browser, tab, self.title)

            if need_cookie_file(AUTH_MODE):
                try:
                    await asyncio.wait_for(browser.cookies.save(self.account_file), timeout=5.0)
                    shipinhao_logger.success("[-] cookie 更新完毕")
                except (asyncio.TimeoutError, Exception) as e:
                    shipinhao_logger.warning(f"[-] 保存 cookie 跳过：{e}")
            
            await tab.sleep(1)
            if keep_browser_open:
                try:
                    uc.util.get_registered_instances().discard(browser)
                except Exception:
                    pass
            return publish_confirmed
        finally:
            if not keep_browser_open:
                browser.stop()

    async def main(self):
        await self.upload()
