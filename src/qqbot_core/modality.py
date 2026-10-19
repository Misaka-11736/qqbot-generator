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
IMAGE_HINTS = (
    "看看",
    "发张",
    "来张",
    "整张",
    "画一个",
    "画个",
    "长什么样",
    "照片",
    "图片",
    "截图",
    "表情包",
    "证件照",
    "图看看",
)
FILE_HINTS = ("文件", "文档", "表格", "导出", "发我一份", "整理成")


def choose_modality(user_text: str, reply: str = "") -> str:
    text = (user_text or "").strip()
    if not text:
        return "text"
    if any(word in text for word in FILE_HINTS):
        return "file"
    if any(word in text for word in VOICE_HINTS):
        return "voice"
    if any(word in text for word in IMAGE_HINTS):
        return "image"
    if re.search(r"(叫我|喊我).{0,4}(妈妈|爸爸|主人|哥哥|姐姐)", text):
        return "voice"
    return "text"
