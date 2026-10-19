"""消息调度：判断要不要回、拼上下文、调模型、拆句发送。"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from .commands import CommandContext, parse_command
from .commands import handle as handle_command
from .config import Config
from .llm import LLMError
from .memory import Memory
from .message import Incoming, parse_event
from .persona import PRESETS, build_system_prompt, load_preset, style_of
from .util import RateLimiter, clean_reply, pretty_seconds, split_text

log = logging.getLogger("qqbot")

Sender = Callable[[str, int, str, int | None], Awaitable[None]]

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

FALLBACK_LINES = [
    "……我这边卡了一下，你再说一遍？",
    "刚走神了，再说一次。",
    "脑子突然空了，等我两秒。",
]


class Engine:
    def __init__(self, cfg: Config, memory: Memory, llm: Any, provider_label: str):
        self.cfg = cfg
        self.memory = memory
        self.llm = llm
        self.provider_label = provider_label
        self.started_at = time.time()
        self.self_id = int(cfg.onebot.self_id or 0)
        self.link: Any = None
        self.sender: Sender | None = None

        self.stats = {"received": 0, "replied": 0, "errors": 0}
        self._locks: dict[str, asyncio.Lock] = {}
        self._seen: deque[int] = deque(maxlen=800)
        self._seen_set: set[int] = set()
        self._sent: deque[int] = deque(maxlen=200)
        self._sent_set: set[int] = set()
        self._last_random: dict[str, float] = {}
        self._rate = RateLimiter(cfg.chat.rate_limit_per_minute, 60.0)
        self.last_replies: list[str] = []

    # ---------------- 连接就绪 ----------------

    async def on_ready(self) -> None:
        if self.link is None:
            return
        try:
            self_id, nickname = await self.link.get_login_info()
        except Exception as exc:
            log.warning("读取登录信息失败：%s", exc)
            return
        if self_id:
            self.self_id = self_id
        log.info("登录账号：%s（%s）", nickname or "?", self.self_id)

    # ---------------- 事件入口 ----------------

    async def handle_event(self, event: dict[str, Any]) -> None:
        if event.get("post_type") != "message":
            return
        incoming = parse_event(event, self.self_id)
        if incoming is None:
            return
        self.stats["received"] += 1
        if incoming.is_self or (self.self_id and incoming.user_id == self.self_id):
            return
        if incoming.user_id in self.cfg.chat.ignore_qq:
            return
        if incoming.message_id and incoming.message_id in self._seen_set:
            return
        self._remember_seen(incoming.message_id)
        self.memory.remember_user(incoming.user_id, incoming.sender_name)

        text = incoming.text.strip()
        if not text:
            return

        prefix = self.cfg.chat.prefixes
        at_me_or_private = incoming.at_me or not incoming.is_group
        command = parse_command(text, prefix, allow_bare=at_me_or_private)
        if command is not None:
            await self._run_command(command[0], command[1], incoming)
            return

        if not self._should_reply(incoming, text):
            return

        if not self._rate.allow(str(incoming.user_id)):
            log.info("限流：%s 触发太频繁，跳过", incoming.user_id)
            return

        await self._reply(incoming, text)

    # ---------------- 指令 ----------------

    async def _run_command(self, name: str, arg: str, incoming: Incoming) -> None:
        ctx = CommandContext(
            cfg=self.cfg,
            memory=self.memory,
            conv_key=incoming.conversation_key,
            user_id=incoming.user_id,
            user_name=incoming.sender_name,
            is_group=incoming.is_group,
            provider_label=self.provider_label,
            uptime_text=pretty_seconds(time.time() - self.started_at),
            stats=self.memory.stats(),
        )
        result = handle_command(name, arg, ctx)
        if not result.handled:
            return
        log.info("指令 %s -> %s", name, "silent" if result.silent else f"{len(result.texts)} 条回复")
        if result.silent:
            return
        for text in result.texts:
            await self._deliver(incoming, text)

    # ---------------- 判定 ----------------

    def _should_reply(self, incoming: Incoming, text: str) -> bool:
        key = incoming.conversation_key
        if self.memory.muted(key):
            return False
        if incoming.is_group:
            if not self.cfg.chat.enable_group:
                return False
            scope = self.cfg.chat.group_scope
            if scope == "whitelist" and incoming.group_id not in self.cfg.chat.group_list:
                return False
            if scope == "blacklist" and incoming.group_id in self.cfg.chat.group_list:
                return False
        elif not self.cfg.chat.enable_private:
            return False
        if incoming.at_me:
            return True
        if incoming.reply_id and incoming.reply_id in self._sent_set:
            return True
        if not incoming.is_group:
            return True

        # 群聊：按概率搭话，且受冷却和最短长度限制
        if len(text) < 2 or text.startswith("["):
            return False
        now = time.monotonic()
        if now - self._last_random.get(key, 0.0) < self.cfg.chat.group_cooldown:
            return False
        if random.random() >= self.cfg.chat.group_chat_probability:
            return False
        self._last_random[key] = now
        return True

    # ---------------- 回复 ----------------

    async def _reply(self, incoming: Incoming, text: str) -> None:
        key = incoming.conversation_key
        lock = self._locks.setdefault(key, asyncio.Lock())
        iq = self.memory.iq(key)
        preset = self.memory.persona(key, self.cfg.persona.preset)

        async with lock:
            messages = self._build_messages(incoming, text, iq, preset)
            temperature, max_tokens, max_chars = style_of(iq)
            # 说话越少脑子越笨，温度再抬一点，制造“不靠谱”感
            if iq <= 30:
                temperature = min(1.3, temperature + 0.05)
            try:
                raw = await self.llm.complete(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    meta={"iq": iq, "user_name": incoming.sender_name, "bot_name": self.cfg.bot_name},
                )
            except LLMError as exc:
                self.stats["errors"] += 1
                log.error("模型调用失败：%s", exc)
                raw = random.choice(FALLBACK_LINES)
            except Exception as exc:
                self.stats["errors"] += 1
                log.exception("模型调用异常：%s", exc)
                raw = random.choice(FALLBACK_LINES)

        reply = clean_reply(raw)
        if not reply:
            return
        if len(reply) > max_chars:
            reply = reply[:max_chars].rstrip("，,、") + "……"
        parts = split_text(reply, limit=max(80, min(self.cfg.chat.max_reply_chars, max_chars + 40)))
        if not self.cfg.chat.split_long_reply:
            parts = ["".join(parts)]

        self.memory.add(key, "user", text, incoming.sender_name)
        self.memory.add(key, "assistant", "".join(parts), self.cfg.bot_name)
        self.memory.mark_chat(key)

        for index, part in enumerate(parts):
            if self.cfg.chat.reply_delay:
                delay = min(3.2, 0.6 + len(part) * 0.035)
                if index:  # 后续分段稍快
                    delay = min(1.2, delay)
                await asyncio.sleep(delay)
            await self._deliver(incoming, part, quote=self.cfg.chat.quote_reply and index == 0)
        self.stats["replied"] += 1
        self.last_replies.append("".join(parts))
        log.info(
            "回复 %s(%s) [IQ %s] %s",
            incoming.sender_name,
            incoming.user_id,
            iq,
            ("".join(parts))[:60].replace("\n", " "),
        )

    def _build_messages(self, incoming: Incoming, text: str, iq: int, preset: str) -> list[dict[str, str]]:
        preset_text = load_preset(preset)
        now = time.localtime()
        clock = f"{time.strftime('%m月%d日 %H:%M', now)} {WEEKDAYS[now.tm_wday]}"
        system = build_system_prompt(
            preset_text=preset_text,
            persona_label=PRESETS.get(preset, preset),
            bot_name=self.cfg.bot_name,
            iq=iq,
            user_name=incoming.sender_name,
            is_group=incoming.is_group,
            extra=f"现在是 {clock}。",
        )
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        history = self.memory.history(incoming.conversation_key)
        limit = max(2, self.cfg.chat.context_turns * 2)
        for item in history[-limit:]:
            role = item.get("role")
            content = item.get("text", "")
            if role not in ("user", "assistant") or not content:
                continue
            if role == "user":
                name = item.get("name") or "对方"
                content = f"{name}：{content}"
            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": f"{incoming.sender_name}：{text}"})
        return messages

    # ---------------- 发送 ----------------

    async def _deliver(self, incoming: Incoming, text: str, quote: bool = False) -> None:
        text = text.strip()
        if not text:
            return
        reply_to = incoming.message_id if (quote and incoming.message_id) else None
        try:
            if self.sender is not None:
                await self.sender("group" if incoming.is_group else "private", incoming.target_id, text, reply_to)
            elif self.link is not None:
                data = await self.link.send_text(
                    "group" if incoming.is_group else "private",
                    incoming.target_id,
                    text,
                    reply_to=reply_to,
                )
                if isinstance(data, dict) and data.get("message_id"):
                    self._track_sent(int(data["message_id"]))
            else:
                log.warning("没有可用的发送通道，丢弃回复：%s", text)
        except Exception as exc:
            self.stats["errors"] += 1
            log.error("发送失败：%s", exc)

    def _track_sent(self, message_id: int) -> None:
        if not message_id:
            return
        if len(self._sent) >= (self._sent.maxlen or 0):
            self._sent_set.discard(self._sent.popleft())
        self._sent.append(message_id)
        self._sent_set.add(message_id)

    def _remember_seen(self, message_id: int) -> None:
        if not message_id:
            return
        if len(self._seen) >= (self._seen.maxlen or 0):
            self._seen_set.discard(self._seen.popleft())
        self._seen.append(message_id)
        self._seen_set.add(message_id)

    # ---------------- 展示 ----------------

    def banner(self) -> str:
        cfg = self.cfg
        mode = "反向（本机监听，等 NapCat 连入）" if cfg.onebot.mode == "reverse" else "正向（主动连 NapCat）"
        return "\n".join(
            [
                f"  名称      {cfg.bot_name}",
                f"  模型      {self.provider_label}",
                f"  接入      {mode} {cfg.onebot.host}:{cfg.onebot.port}{cfg.onebot.path}",
                f"  默认智商  {cfg.persona.default_iq}/200",
                f"  群聊搭话  {cfg.chat.group_chat_probability:.0%} 概率",
                f"  数据目录  {cfg.data_dir}",
            ]
        )
