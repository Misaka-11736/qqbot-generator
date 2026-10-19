"""把 OneBot 11 的消息事件解析成好用的结构。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

CQ_PATTERN = re.compile(r"\[CQ:([a-zA-Z_]+)((?:,[^\]]*)?)\]")

SEGMENT_PLACEHOLDERS = {
    "image": "[图片]",
    "record": "[语音]",
    "video": "[视频]",
    "file": "[文件]",
    "face": "[表情]",
    "mface": "[表情]",
    "dice": "[骰子]",
    "rps": "[猜拳]",
    "forward": "[聊天记录]",
    "json": "[卡片]",
    "xml": "[卡片]",
    "share": "[链接]",
    "music": "[音乐]",
    "poke": "[戳一戳]",
}


@dataclass
class Incoming:
    message_id: int = 0
    message_type: str = "private"  # group / private
    group_id: int = 0
    user_id: int = 0
    self_id: int = 0
    sender_name: str = ""
    text: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    at_me: bool = False
    reply_id: int | None = None
    is_self: bool = False
    segments: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_group(self) -> bool:
        return self.message_type == "group"

    @property
    def conversation_key(self) -> str:
        return f"group:{self.group_id}" if self.is_group else f"private:{self.user_id}"

    @property
    def target_id(self) -> int:
        return self.group_id if self.is_group else self.user_id


def _sender_name(event: dict[str, Any]) -> str:
    sender = event.get("sender") or {}
    for key in ("card", "nickname", "name"):
        value = sender.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(event.get("user_id", ""))


def _parse_cq_string(message: str, self_id: int) -> tuple[str, bool, int | None, list[dict[str, Any]]]:
    text_parts: list[str] = []
    at_me = False
    reply_id: int | None = None
    segments: list[dict[str, Any]] = []
    cursor = 0
    for match in CQ_PATTERN.finditer(message):
        if match.start() > cursor:
            plain = message[cursor : match.start()]
            text_parts.append(plain)
            segments.append({"type": "text", "data": {"text": plain}})
        kind = match.group(1)
        params: dict[str, str] = {}
        for pair in match.group(2).lstrip(",").split(","):
            if "=" in pair:
                key, value = pair.split("=", 1)
                params[key] = value
        if kind == "at":
            qq = params.get("qq", "")
            segments.append({"type": "at", "data": {"qq": qq}})
            if qq == str(self_id):
                at_me = True
            else:
                text_parts.append("@某人")
        elif kind == "reply":
            try:
                reply_id = int(params.get("id", "0"))
            except ValueError:
                reply_id = None
            segments.append({"type": "reply", "data": {"id": params.get("id", "")}})
        else:
            placeholder = SEGMENT_PLACEHOLDERS.get(kind, f"[{kind}]")
            text_parts.append(placeholder)
            segments.append({"type": kind, "data": params})
        cursor = match.end()
    if cursor < len(message):
        tail = message[cursor:]
        text_parts.append(tail)
        segments.append({"type": "text", "data": {"text": tail}})
    return "".join(text_parts).strip(), at_me, reply_id, segments


def _parse_array(message: list[Any], self_id: int) -> tuple[str, bool, int | None, list[dict[str, Any]]]:
    text_parts: list[str] = []
    at_me = False
    reply_id: int | None = None
    segments: list[dict[str, Any]] = []
    for seg in message:
        if not isinstance(seg, dict):
            continue
        kind = seg.get("type")
        data = seg.get("data") or {}
        segments.append({"type": kind, "data": data})
        if kind == "text":
            text_parts.append(str(data.get("text") or ""))
        elif kind == "at":
            qq = str(data.get("qq") or "")
            if qq == str(self_id):
                at_me = True
            elif qq:
                text_parts.append("@某人")
        elif kind == "reply":
            try:
                reply_id = int(data.get("id") or 0)
            except (TypeError, ValueError):
                reply_id = None
        else:
            text_parts.append(SEGMENT_PLACEHOLDERS.get(str(kind), f"[{kind}]"))
    return "".join(text_parts).strip(), at_me, reply_id, segments


def parse_event(event: dict[str, Any], self_id: int) -> Incoming | None:
    if event.get("post_type") != "message":
        return None
    message = event.get("message")
    if isinstance(message, list):
        text, at_me, reply_id, segments = _parse_array(message, self_id)
    else:
        text, at_me, reply_id, segments = _parse_cq_string(str(message or event.get("raw_message") or ""), self_id)

    sender_id = int(event.get("user_id") or 0)
    incoming = Incoming(
        message_id=int(event.get("message_id") or 0),
        message_type=str(event.get("message_type") or "private"),
        group_id=int(event.get("group_id") or 0),
        user_id=sender_id,
        self_id=self_id,
        sender_name=_sender_name(event),
        text=re.sub(r"[ \t]{2,}", " ", text).strip(),
        raw=event,
        at_me=at_me,
        reply_id=reply_id,
        is_self=sender_id == self_id and self_id != 0,
        segments=segments,
    )
    return incoming
