"""中文任务语义分割：动作 / 量词 / 主体 / 输出形式 / 是否发送。"""

from __future__ import annotations

import re
from dataclasses import dataclass

MEASURE_MODALITY = {
    "张": "image",
    "幅": "image",
    "张图": "image",
    "个图": "image",
    "段": "video",
    "个视频": "video",
    "份": "file",
    "个文件": "file",
}

SEARCH_ACTIONS = ("搜索一下", "搜一下", "搜搜", "搜索", "搜", "查一下", "查查", "查找", "查", "找一下", "找")
SEND_WORDS = ("发来", "发给我", "发我", "发到", "发在", "发群里", "发送", "给我", "来一张", "来张")


@dataclass
class SemanticPlan:
    action: str = ""
    normalized: str = ""
    measure: str = ""
    query: str = ""
    modality: str = "text"
    send: bool = False
    raw: str = ""


def parse(text: str) -> SemanticPlan:
    raw = (text or "").strip()
    original = raw
    raw = re.sub(r"^在(?=(搜|查|找|发|来|整|看|画))", "再", raw)
    raw = re.sub(r"^(再|又|还|继续|接着)\s*", "", raw)
    plan = SemanticPlan(raw=original)
    if raw != original:
        plan.normalized = raw
    if not raw:
        return plan

    for word in SEARCH_ACTIONS:
        if raw.startswith(word):
            plan.action = "search"
            raw = raw[len(word):].lstrip(" ：:，,")
            break

    if any(word in raw for word in SEND_WORDS) or raw.startswith(("来", "发")):
        plan.send = True

    match = re.search(r"(一张|两张|几张|张图|个图|张|幅|段|个视频|份|个文件)", raw)
    if match:
        plan.measure = match.group(1)
        plan.modality = MEASURE_MODALITY.get(plan.measure, "image" if "图" in plan.measure else "text")
        raw = raw[: match.start()] + raw[match.end():]

    for word in SEND_WORDS:
        raw = raw.replace(word, "")
    raw = re.sub(r"^(帮我|给我|替我|麻烦|请|随便|随意|随便来|来|发|整|要)+", "", raw)
    raw = re.sub(r"^(一|两|几)", "", raw)
    raw = re.sub(r"(一下|一张|一个|一条|一段|吧|呗|啊|呀|看看|瞧瞧)+$", "", raw)
    raw = raw.strip(" 的：:，,。！!？?")
    plan.query = raw
    return plan


def describe(plan: SemanticPlan) -> str:
    labels = {"search": "搜索", "": "无动作"}
    modality = {"image": "图片", "video": "视频", "file": "文件", "text": "文字"}
    return (
        f"动作={labels.get(plan.action, plan.action)} "
        f"量词={plan.measure or '无'}→{modality.get(plan.modality, plan.modality)} "
        f"主体={plan.query or '无'} 发送={'是' if plan.send else '否'}"
    )
