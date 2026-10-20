"""本地试聊：把机器人内核跑在后台线程，直接在界面里聊天。"""

from __future__ import annotations

import asyncio
import copy
import threading
import time

from PySide6.QtCore import QObject, Signal

from qqbot_core.config import Config
from qqbot_core.engine import Engine
from qqbot_core.llm import MockBrain, make_llm
from qqbot_core.memory import Memory

from .. import paths

KEY = "private:local"


class ChatSession(QObject):
    replied = Signal(str)
    failed = Signal(str)

    def __init__(self, cfg: Config, parent: QObject | None = None):
        super().__init__(parent)
        local = copy.deepcopy(cfg)
        local.chat.reply_delay = False
        local.chat.group_chat_probability = 0.0
        local.chat.context_turns = max(6, min(20, cfg.chat.context_turns))
        self._cfg = local
        self._counter = 0

        try:
            llm, label = make_llm(local)
        except Exception:
            llm, label = MockBrain(), "离线兜底大脑"
        self.provider_label = label

        memory = Memory(paths.data_dir() / "chat_memory.json", local.persona.default_iq, local.chat.context_turns)
        memory.set_iq(KEY, local.persona.default_iq)
        memory.set_persona(KEY, local.persona.preset)
        self.engine = Engine(local, memory, llm, label)

        async def sender(kind: str, target: int, text: str, quote: int | None) -> None:
            self.replied.emit(text)

        self.engine.sender = sender
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="chat-session", daemon=True)
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def send(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self._counter += 1
        event = {
            "post_type": "message",
            "message_type": "private",
            "message_id": 900000 + self._counter,
            "user_id": 1,
            "self_id": 10000,
            "time": int(time.time()),
            "sender": {"nickname": "你"},
            "message": [{"type": "text", "data": {"text": text}}],
            "raw_message": text,
        }
        try:
            asyncio.run_coroutine_threadsafe(self.engine.handle_event(event), self._loop)
        except RuntimeError as exc:
            self.failed.emit(str(exc))

    def iq(self) -> int:
        return int(self._cfg.persona.default_iq)

    def history(self) -> list[dict]:
        return self.engine.memory.history(KEY)

    def reset(self) -> None:
        self.engine.memory.reset(KEY)

    def close(self) -> None:
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=2)
        except RuntimeError:
            pass
