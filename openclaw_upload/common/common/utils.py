# -*- coding: utf-8 -*-
"""共享工具函数"""
import os
import random
import re
from typing import Tuple, List, Any


async def has_text_in_page(tab: Any, text: str, timeout: float = 2) -> bool:
    """检测页面中是否存在指定文本（nodriver Tab 对象）"""
    try:
        el = await tab.find(text, best_match=True, timeout=timeout)
        return el is not None
    except Exception:
        return False


def need_cookie_file(auth_mode: str) -> bool:
    """判断当前模式是否依赖 cookie 文件（cookie 模式需要，profile/connect 不需要）"""
    return auth_mode == "cookie"


async def load_cookies_from_file(browser: Any, cookie_file: str) -> bool:
    """从 JSON cookie 文件加载到浏览器。"""
    if not cookie_file or not os.path.exists(cookie_file):
        return False
    await browser.cookies.load(cookie_file)
    return True


async def save_cookies_to_json(browser: Any, cookie_file: str) -> bool:
    """将当前浏览器 cookie 保存到 JSON 文件。"""
    if not cookie_file:
        return False
    os.makedirs(os.path.dirname(cookie_file), exist_ok=True)
    await browser.cookies.save(cookie_file)
    return True


def extract_tags_from_description(desc: str, max_tags: int = 10) -> Tuple[str, List[str]]:
    """
    从文案中提取 #标签（如 OpenClaw 合并传入）。
    返回 (去掉标签后的文案, 标签列表)。
    """
    if not desc:
        return "", []
    pattern = r"#([^\s#]+)"
    found = re.findall(pattern, desc)
    tags = [str(t).replace("#", "").strip() for t in found if t][:max_tags]
    clean = re.sub(r"\s*#[^\s#]+\s*", " ", desc).strip()
    clean = re.sub(r"\s+", " ", clean)
    return clean, tags


# 默认标题/文案模板（simple 风格）
_DEFAULT_TITLE = "记录生活中的小确幸"
_DEFAULT_DESC = "每一个平凡的日子都藏着惊喜 ✨"

# rich 风格多组模板
_RICH_TEMPLATES = [
    ("记录生活中的小确幸", "每一个平凡的日子都藏着惊喜 ✨ 用心感受，用视频记录"),
    ("今日份快乐已送达", "生活中的美好瞬间都值得被记录 🌟"),
    ("分享精彩一刻", "捕捉生活的每一份小美好 ✨"),
    ("日常碎片", "平凡日子里的小确幸，与你分享 💕"),
    ("美好时光", "记录当下，留住感动 📷"),
    ("小日常", "把普通的日子过得浪漫一些 ✨"),
    ("随手记", "记录那些闪闪发光的瞬间 🌟"),
]

_RICH_DESC_TEMPLATES = [
    "分享 {name} 的精彩瞬间 ✨",
    "{name}｜记录生活中的小美好 🌟",
    "每一个平凡的日子都藏着惊喜～ {name}",
    "用视频记录 {name} 的美好时刻 📷",
]


def gen_title_desc_from_path(
    file_path: str,
    title_max: int = 20,
    style: str = "simple",
    tags: list = None,
) -> Tuple[str, str]:
    """
    根据文件名生成默认标题和文案
    :param file_path: 视频路径
    :param title_max: 标题最大字数
    :param style: "simple" 固定模板；"rich" 随机多模板
    :param tags: 预留，兼容调用
    """
    name = os.path.splitext(os.path.basename(file_path))[0].strip()
    is_hash = len(name) >= 16 and all(c in "0123456789abcdef" for c in name.lower())

    if not name or is_hash:
        if style == "rich":
            return random.choice(_RICH_TEMPLATES)
        return _DEFAULT_TITLE, _DEFAULT_DESC

    if len(name) <= title_max:
        title = name
    else:
        title = name[: title_max - 3] + "..."

    if style == "rich":
        desc = random.choice(_RICH_DESC_TEMPLATES).format(name=name)
        return title, desc
    return title, "分享精彩一刻 ✨"


def gen_desktop_content(
    video_path: str,
    title_max: int = 20,
    tags_max: int = 5,
    default_tags: list = None,
) -> Tuple[str, str, List[str]]:
    """
    一键上传用：根据视频路径生成标题、文案、标签
    :param default_tags: 默认标签列表，如 ["生活记录", "日常分享", "美好时光", "vlog"]
    """
    default_tags = default_tags or ["生活记录", "日常分享", "美好时光", "vlog"]
    title, desc = gen_title_desc_from_path(video_path, title_max=title_max, style="simple")
    description = "每一个平凡的日子都藏着惊喜 ✨ 用视频记录下这些美好瞬间，生活需要仪式感"
    return title, description, default_tags[:tags_max]
