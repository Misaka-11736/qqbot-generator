"""意图判定：区分“对 bot 提任务”与“普通聊天”。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .semantic import SemanticPlan, parse

PAST = ("搜了", "搜过", "搜到", "查了", "查过", "发了", "发过", "找到", "买了", "有一张", "有一份")
SPLIT = re.compile(r"[，,。；;！!？?\n]+")


@dataclass
class Intent:
    kind: str  # task / chat
    reason: str
    plan: SemanticPlan | None = None


def _is_request(clause: str, plan: SemanticPlan) -> bool:
    if any(word in clause for word in PAST):
        return False
    if plan.action == "search":
        return True
    if re.match(
        r"^(再|又|还|继续|帮我|给我|替我|麻烦|请|能不能|可以)?\s*(搜|查|找|发|来|画|整|要|给)",
        plan.normalized or clause,
    ):
        return True
    if re.search(r"(帮我|给我|替我|能不能|可以|麻烦|请).{0,8}(搜|查|找|发|来|画|整)", clause):
        return True
    return bool(re.search(r"(搜|查|找|发|来|画)(一下|一搜|个)?[^，,。；;]{1,20}", clause))


def classify(text: str, *, vision: bool, search: bool) -> Intent:
    raw = (text or "").strip()
    if not raw:
        return Intent("chat", "空消息")
    clauses = [c.strip() for c in SPLIT.split(raw) if c.strip()]
    if not clauses:
        return Intent("chat", "空消息")
    for clause in reversed(clauses):
        plan = parse(clause)
        if not _is_request(clause, plan):
            continue
        wants_image = plan.measure in ("张", "一张", "两张", "几张", "张图", "个图", "幅")
        if wants_image and not vision:
            return Intent("chat", "图片能力已关闭", plan)
        if not wants_image and plan.action == "search" and not search:
            return Intent("chat", "搜索能力已关闭", plan)
        return Intent("task", f"请求子句：{clause}", plan)
    return Intent("chat", "没有明确请求子句", parse(raw))
