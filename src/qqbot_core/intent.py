"""意图判定：区分“对 bot 提任务”与“普通聊天”。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .semantic import SemanticPlan, parse

PAST = ("搜了", "搜过", "搜到", "查了", "查过", "发了", "发过", "找到", "买了", "有一张", "有一份")


@dataclass
class Intent:
    kind: str  # task / chat
    reason: str
    plan: SemanticPlan | None = None


def classify(text: str, *, vision: bool, search: bool) -> Intent:
    raw = (text or "").strip()
    if not raw:
        return Intent("chat", "空消息")
    if any(word in raw for word in PAST):
        return Intent("chat", "过去时/陈述句")
    plan = parse(raw)

    request = plan.action == "search"
    if not request and re.match(r"^(再|又|还|继续)?\s*(搜|查|找|发|来|画|整|要|给)", plan.normalized or raw):
        request = True
    if not request and re.search(r"(帮我|给我|替我|能不能|可以|麻烦|请).{0,8}(搜|查|找|发|来|画|整)", raw):
        request = True
    if not request and re.search(r"(搜|查|找|发|来|画).{0,4}(张|个|条|幅|段)", raw):
        request = True
    if not request:
        return Intent("chat", "没有明确请求动作", plan)

    wants_image = plan.measure in ("张", "一张", "两张", "几张", "张图", "个图", "幅")
    if wants_image and not vision:
        return Intent("chat", "图片能力已关闭", plan)
    if not wants_image and plan.action == "search" and not search:
        return Intent("chat", "搜索能力已关闭", plan)
    return Intent("task", "明确请求 + 能力可用", plan)
