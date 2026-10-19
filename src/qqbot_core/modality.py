"""按聊天语义选择回复载体：文字 / 语音 / 图片 / 文件。"""

from __future__ import annotations

import re

VOICE_HINTS = (
    "语音",
    "声音",
    "听你",
    "叫一声",
    "叫句",
    "叫妈妈",
    "叫爸爸",
    "哄我",
    "哄睡",
    "唱",
    "撒娇",
    "晚安",
    "抱抱",
    "亲口",
    "说给我听",
)
IMAGE_PATTERNS = (
    r"(发|来|给|整|画|找).{0,6}(图|照片|图片|表情包)",
    r"(长什么样|长啥样|什么样子|啥样子)",
    r"(看看|瞧瞧).{1,20}(长什么样|什么样子|啥样)",
)
FILE_HINTS = ("文件", "文档", "表格", "导出", "发我一份", "整理成")


def choose_modality(user_text: str, voice_threshold: int = 50, image_threshold: int = 50, reply: str = "") -> str:
    text = (user_text or "").strip()
    if not text:
        return "text"
    if any(word in text for word in FILE_HINTS):
        return "file"
    image_score = 0
    if re.search(r"(发|来|给|整|画|找).{0,6}(图|照片|图片|表情包)", text) or re.search(r"(长什么样|长啥样|什么样子|啥样子)", text):
        image_score = 90
    elif any(word in text for word in ("图", "照片", "图片", "表情包", "截图")):
        image_score = 60
    elif "看看" in text or "瞧瞧" in text:
        image_score = 40
    voice_score = 0
    if re.search(r"(语音|声音|叫妈妈|叫爸爸|哄睡|念一下|读一下|说给我听|撒娇|唱)", text):
        voice_score = 90
    elif any(word in text for word in ("听你", "晚安", "抱抱", "亲", "哄", "叫我", "喊我")):
        voice_score = 55
    if voice_score >= voice_threshold and voice_score > 0:
        return "voice"
    if image_score >= image_threshold and image_score > 0:
        return "image"
    return "text"
