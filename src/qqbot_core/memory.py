"""会话记忆与设置持久化。

一个 JSON 文件存三样东西：
  conversations[会话键] -> 该会话的智商 / 人格 / 静音 / 聊天历史
  users[QQ号]          -> 昵称缓存（让模型知道在跟谁说话）
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .util import JsonStore

MAX_TURNS_CAP = 40


class Memory:
    def __init__(self, path: Path, default_iq: int = 100, max_turns: int = 12):
        self.store = JsonStore(path, {"version": 1, "conversations": {}, "users": {}})
        self.default_iq = default_iq
        self.max_turns = max(1, min(MAX_TURNS_CAP, max_turns))
        self._ensure_shape()

    # ---------- 内部 ----------

    def _ensure_shape(self) -> None:
        data = self.store.data
        data.setdefault("version", 1)
        data.setdefault("conversations", {})
        data.setdefault("users", {})

    def _conv(self, key: str) -> dict[str, Any]:
        convs = self.store.data["conversations"]
        conv = convs.get(key)
        if not isinstance(conv, dict):
            conv = {}
            convs[key] = conv
        conv.setdefault("iq", self.default_iq)
        conv.setdefault("persona", None)
        conv.setdefault("muted", False)
        conv.setdefault("history", [])
        conv.setdefault("last_chat", 0.0)
        conv.setdefault("updated", time.time())
        return conv

    # ---------- 设置 ----------

    def iq(self, key: str) -> int:
        value = self._conv(key).get("iq", self.default_iq)
        try:
            return max(1, min(200, int(value)))
        except (TypeError, ValueError):
            return self.default_iq

    def set_iq(self, key: str, value: int) -> None:
        conv = self._conv(key)
        conv["iq"] = max(1, min(200, int(value)))
        conv["updated"] = time.time()
        self.store.save()

    def apply_default_iq(self, value: int) -> None:
        self.default_iq = max(1, min(200, int(value)))
        for conv in self.store.data.get("conversations", {}).values():
            if isinstance(conv, dict):
                conv["iq"] = self.default_iq
        self.store.save()

    def persona(self, key: str, fallback: str) -> str:
        value = self._conv(key).get("persona")
        return value if isinstance(value, str) and value else fallback

    def set_persona(self, key: str, preset: str | None) -> None:
        conv = self._conv(key)
        conv["persona"] = preset
        conv["updated"] = time.time()
        self.store.save()

    def muted(self, key: str) -> bool:
        return bool(self._conv(key).get("muted", False))

    def set_muted(self, key: str, muted: bool) -> None:
        conv = self._conv(key)
        conv["muted"] = bool(muted)
        conv["updated"] = time.time()
        self.store.save()

    def last_chat(self, key: str) -> float:
        try:
            return float(self._conv(key).get("last_chat", 0.0))
        except (TypeError, ValueError):
            return 0.0

    def mark_chat(self, key: str) -> None:
        self._conv(key)["last_chat"] = time.time()
        self.store.save()

    # ---------- 历史 ----------

    def history(self, key: str) -> list[dict[str, Any]]:
        hist = self._conv(key).get("history", [])
        return hist if isinstance(hist, list) else []

    def add(self, key: str, role: str, text: str, name: str = "") -> None:
        conv = self._conv(key)
        hist = conv.setdefault("history", [])
        hist.append({"role": role, "text": text, "name": name, "ts": time.time()})
        limit = self.max_turns * 2
        if len(hist) > limit:
            del hist[: len(hist) - limit]
        conv["updated"] = time.time()
        self.store.save()

    def reset(self, key: str) -> None:
        conv = self._conv(key)
        conv["history"] = []
        conv["updated"] = time.time()
        self.store.save()

    # ---------- 用户 ----------

    def remember_user(self, qq: int, nickname: str) -> None:
        users = self.store.data["users"]
        if not nickname:
            return
        old = users.get(str(qq))
        if old != nickname:
            users[str(qq)] = nickname

    def nickname(self, qq: int) -> str:
        return self.store.data["users"].get(str(qq), "") or str(qq)

    # ---------- 维护 ----------

    def prune(self, days: int = 30) -> int:
        """清理长期不活跃的会话，返回删除数量。"""
        cutoff = time.time() - days * 86400
        convs = self.store.data["conversations"]
        doomed = [k for k, v in convs.items() if float(v.get("updated", 0)) < cutoff]
        for key in doomed:
            convs.pop(key, None)
        if doomed:
            self.store.save()
        return len(doomed)

    def stats(self) -> dict[str, int]:
        convs = self.store.data["conversations"]
        return {
            "conversations": len(convs),
            "messages": sum(len(v.get("history", [])) for v in convs.values()),
            "users": len(self.store.data["users"]),
        }

    def save(self) -> None:
        self.store.save()
