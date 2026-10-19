"""消息调度：判断要不要回、拼上下文、调模型、拆句发送。"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from collections import deque
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from .archive import Archive, classify_text
from .commands import CommandContext, parse_command
from .commands import handle as handle_command
from .config import Config
from .features import style_prompt
from .keyvault import get_key
from .llm import LLMError
from .media import extract_frames, media_sources, read_text_attachment
from .memory import Memory
from .message import Incoming, parse_event
from .modality import choose_modality
from .persona import PRESETS, build_system_prompt, load_preset, style_of
from .plugins import PluginManager
from .tools import ToolError, brave_image, brave_search, download, make_card, make_file
from .util import RateLimiter, clean_reply, pretty_seconds, split_text
from .vision import look_at_frames, looks_like_image_question
from .voice import prepare as prepare_voice
from .voice import synthesize, transcribe, voice_sources, wants_voice

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
        self._auto_task: asyncio.Task | None = None
        self._search_day = ""
        self._search_used = 0
        self.features = cfg.features
        self.archive = Archive(cfg.data_dir / "archive.db") if cfg.features.archive else None
        self.plugins = PluginManager(self)
        if self.archive is not None:
            try:
                self.archive.prune(cfg.features.archive_days)
            except Exception:
                pass

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
        self.plugins.load()
        log.info(
            "能力：识图=%s(%s) 搜索=%s 归档=%s 自动搜索=%s",
            self.features.vision,
            self.features.vision_model,
            self.features.search,
            self.features.archive,
            self.features.auto_search,
        )
        if self.features.auto_search and (self._auto_task is None or self._auto_task.done()):
            self._auto_task = asyncio.create_task(self._auto_search_loop())

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

        tags = classify_text(incoming.text) if (self.features.classify and incoming.text) else []
        if self.archive is not None:
            try:
                self.archive.add(incoming, tags)
            except Exception as exc:
                log.warning("归档失败：%s", exc)

        text = incoming.text.strip()
        voices = voice_sources(incoming.segments)
        if voices and self.features.voice_in:
            log.info("收到语音，开始识别")
            await self._deliver(incoming, "我听听…")
            try:
                src = await asyncio.to_thread(prepare_voice, voices[0], self.cfg.data_dir / "downloads" / "voice")
                text = await asyncio.to_thread(transcribe, src, self.features.voice_model)
                log.info("语音识别：%s", text[:80])
                if incoming.is_group:
                    incoming.at_me = True
            except Exception as exc:
                log.warning("语音识别失败：%s", exc)
                await self._deliver(incoming, f"这段语音我没听清：{exc}")
                return
        if await self.plugins.dispatch(incoming, text):
            return
        media = media_sources(incoming.segments)
        if media:
            if not self.features.vision:
                log.info("收到媒体，但识图开关是关的")
            elif not self._want_vision(incoming, text):
                log.info("收到媒体，但没带问题也没 @，跳过：%s", text[:30])
            else:
                await self._vision_reply(incoming, text, media)
                return
        if not text:
            return

        if self.features.voice_out and wants_voice(text):
            spoken = re.sub(r"(用语音|发条语音|发个语音|语音说|念一下|读一下|说给我听|来段语音)", "", text).strip(" ：:，,")
            if spoken:
                await self._deliver(incoming, "等我清清嗓子…")
                try:
                    path = await synthesize(spoken, self.cfg.data_dir / "downloads" / "voice", self.features.voice_name)
                    await self._send_voice(incoming, str(path))
                except Exception as exc:
                    await self._deliver(incoming, f"语音合成失败：{exc}")
                return

        if await self._natural_intent(text, incoming):
            return

        prefix = self.cfg.chat.prefixes
        at_me_or_private = incoming.at_me or not incoming.is_group
        command = parse_command(text, prefix, allow_bare=at_me_or_private)
        if command is not None:
            if await self._run_capability(command[0], command[1], incoming):
                return
            await self._run_command(command[0], command[1], incoming)
            return

        if not self._should_reply(incoming, text):
            return

        if not self._rate.allow(str(incoming.user_id)):
            log.info("限流：%s 触发太频繁，跳过", incoming.user_id)
            return

        await self._reply(incoming, text)

    # ---------------- 指令 ----------------

    def _want_vision(self, incoming: Incoming, text: str) -> bool:
        if not incoming.is_group:
            return True
        if incoming.at_me or (incoming.reply_id in self._sent_set):
            return True
        return looks_like_image_question(text)

    async def _vision_reply(self, incoming: Incoming, text: str, media: list[dict]) -> None:
        log.info("识图/媒体触发：%s（%s）", (text or "无文字")[:60], ",".join(m["kind"] for m in media))
        key = get_key(self.cfg.data_dir, "qwen")
        if not key:
            await self._deliver(incoming, "识图还没配 Key，去「能力」页填百炼的 Key。")
            return
        await self._deliver(incoming, "我看看…")
        cache = self.cfg.data_dir / "downloads" / "vision"
        frames: list[Path] = []
        notes: list[str] = []
        for item in media[:4]:
            if item["kind"] == "file":
                extra = await asyncio.to_thread(read_text_attachment, item, cache)
                if extra:
                    notes.append(extra)
                continue
            got, note = await asyncio.to_thread(extract_frames, item, cache, 3)
            frames.extend(got)
            if note:
                notes.append(note)
        answer = ""
        if frames:
            answer = await asyncio.to_thread(
                look_at_frames,
                frames,
                key,
                self.features.vision_model,
                text,
                "\n".join(notes),
            )
        elif notes:
            answer = await self.llm.complete(
                [
                    {"role": "system", "content": "对方发来一个文件。用 2~3 句口语说文件大概是什么、有什么值得注意的，不列点、不贴链接。"},
                    {"role": "user", "content": "\n".join(notes)[:3000]},
                ],
                temperature=0.4,
                max_tokens=260,
            )
        else:
            answer = "这个文件/视频我这边解析不了。"
        for part in split_text(answer, limit=600):
            await self._deliver(incoming, part)

    async def _natural_intent(self, text: str, incoming: Incoming) -> bool:
        """不用 / 指令：直接说“搜一下…”也能触发。"""
        compact = text.strip()
        if compact.startswith(("搜不到", "搜不着", "搜了", "搜过", "搜完")):
            return False
        search = re.match(
            r"^(?:你|现在|帮我|给我|替我|能不能|可以|麻烦)?\s*"
            r"(?:搜索一下|搜一下|搜搜看|搜搜|搜(?=\s|[:：,，])|查一下|查查)\s*[:：,，]?\s*(.+)$",
            compact,
            re.I,
        )
        if search and self.features.search:
            query = search.group(1).strip(" ：:，,")
            if not query:
                return False
            log.info("自然语言搜索：%s", query[:60])
            await self._deliver(incoming, "我去网上看看…")
            await self._deliver(incoming, await self._search(query))
            return True
        summary = re.match(
            r"^(?:你|帮我|给我)?\s*(?:总结|汇总)(?:一下|下)?(?:\s*(?:最近)?\s*(\d{1,4})\s*条)?\s*$",
            compact,
        )
        if summary and self.features.summarize:
            log.info("自然语言总结：%s 条", summary.group(1) or self.features.summary_max)
            count = int(summary.group(1) or self.features.summary_max)
            count = max(10, min(count, self.features.summary_max))
            await self._deliver(incoming, "正在翻记录，等我一下…")
            for part in split_text(await self._summarize(incoming.conversation_key, count), limit=1600):
                await self._deliver(incoming, part)
            return True
        if self.features.download and ("下载" in compact or "存一下" in compact or "保存" in compact):
            url = re.search(r"https?://\S+", compact)
            if url:
                await self._deliver(incoming, await self._download(url.group(0)))
                return True
        return False

    async def _auto_search_loop(self) -> None:
        while True:
            interval = max(5, int(self.features.auto_search_interval or 60))
            await asyncio.sleep(interval * 60)
            if not self.features.auto_search:
                continue
            if not get_key(self.cfg.data_dir, "brave"):
                continue
            conv = self.features.auto_search_target.strip()
            if not conv and self.archive:
                rows = self.archive.conversations()
                conv = rows[0][0] if rows else ""
            if not conv:
                continue
            topic = self._pick_topic()
            try:
                result = await self._search(topic)
            except Exception as exc:
                log.warning("自动搜索失败：%s", exc)
                continue
            if result.startswith(("搜索失败", "还没配置", "没搜到", "今天搜索")):
                continue
            await self._send_to(conv, f"闲着刷到点东西：{result[:600]}")

    def _pick_topic(self) -> str:
        custom = [x.strip() for x in re.split(r"[,，;；\n]", self.features.auto_search_topics) if x.strip()]
        if custom:
            return random.choice(custom)
        if self.archive:
            rows = self.archive.recent(self.features.auto_search_target or (self.archive.conversations()[0][0] if self.archive.conversations() else ""), 30)
            words = [w for row in rows for w in re.findall(r"[\u4e00-\u9fff]{2,6}", row["text"])]
            if words:
                return random.choice(words) + " 最近有什么新消息"
        return random.choice(["今天有什么科技新闻", "最近有什么有趣的冷知识", "这周有什么值得看的新电影"])

    async def _send_to(self, conversation: str, text: str) -> None:
        if self.link is None or ":" not in conversation:
            return
        kind, _, raw = conversation.partition(":")
        try:
            target = int(raw)
        except ValueError:
            return
        await self.link.send_text("group" if kind == "group" else "private", target, text)

    async def _run_capability(self, name: str, arg: str, incoming: Incoming) -> bool:
        key = name.lower().strip()
        if key in ("总结", "摘要", "summary") and self.features.summarize and self.archive:
            limit = self.features.summary_max
            try:
                limit = max(10, min(int(arg.strip() or limit), limit))
            except ValueError:
                limit = self.features.summary_max
            await self._deliver(incoming, "正在翻记录，等我一下…")
            text = await self._summarize(incoming.conversation_key, limit)
            for part in split_text(text, limit=1600):
                await self._deliver(incoming, part)
            return True
        if key in ("搜", "搜索", "search") and self.features.search:
            if not arg.strip():
                await self._deliver(incoming, "用法：/搜 关键词")
                return True
            await self._deliver(incoming, "我去网上看看…")
            await self._deliver(incoming, await self._search(arg.strip()))
            return True
        if key in ("下载", "download") and self.features.download:
            if not arg.strip():
                await self._deliver(incoming, "用法：/下载 https://…")
                return True
            await self._deliver(incoming, await self._download(arg.strip()))
            return True
        if key in ("做图", "画图", "卡片", "card") and self.features.gen_image:
            await self._make_image(incoming, arg.strip())
            return True
        if key in ("做文件", "文件", "file") and self.features.gen_file:
            await self._make_file(incoming, arg.strip())
            return True
        return False

    async def _summarize(self, conversation: str, limit: int) -> str:
        rows = self.archive.recent(conversation, limit) if self.archive else []
        if len(rows) < 3:
            return f"这个会话只归档到 {len(rows)} 条，至少 3 条才能总结。"
        lines = []
        for row in rows:
            stamp = time.strftime("%m-%d %H:%M", time.localtime(row["ts"] or 0))
            lines.append(f"[{stamp}] {row['name']}：{row['text']}")
        partials: list[str] = []
        for start in range(0, len(lines), 200):
            chunk = "\n".join(lines[start:start + 200])
            partials.append(
                await self.llm.complete(
                    [
                        {"role": "system", "content": "你是群聊记录总结器。提取这段聊天的主要话题、结论、分歧和待办，中文，200 字以内。"},
                        {"role": "user", "content": chunk[:12000]},
                    ],
                    temperature=0.3,
                    max_tokens=500,
                )
            )
        merged = "\n".join(partials)
        final = await self.llm.complete(
            [
                {"role": "system", "content": "把多段摘要合并成一份群聊总结：3~6 条要点，最后一行写“整体氛围”。中文，不要 Markdown。"},
                {"role": "user", "content": merged[:12000]},
            ],
            temperature=0.4,
            max_tokens=700,
        )
        if self.archive:
            self.archive.save_summary(conversation, len(rows), final)
        return f"最近 {len(rows)} 条总结：\n{final.strip()}"

    async def _search(self, query: str) -> str:
        today = time.strftime("%Y-%m-%d")
        if today != self._search_day:
            self._search_day = today
            self._search_used = 0
        if self._search_used >= self.features.search_daily_limit:
            return "今天搜索次数用完了，明天再来。"
        key = get_key(self.cfg.data_dir, "brave")
        if not key:
            return "还没配置 Brave Key，去「能力」页填一下。"
        try:
            results = await asyncio.to_thread(brave_search, key, query, 5)
        except ToolError as exc:
            return f"搜索失败：{exc}"
        self._search_used += 1
        if not results:
            return "没搜到结果。"
        context = "\n".join(f"- {r['title']}：{r['description']}" for r in results)
        try:
            answer = await self.llm.complete(
                [
                    {
                        "role": "system",
                        "content": (
                            "你刚随手在网上查了一下，现在用聊天的方式把结果告诉对方。"
                            "要求：2~4 句口语，直接说结论；不要列点、不要标题、不要贴链接、"
                            "不要说“根据搜索结果/来源/资料显示”；不要重复对方的问题；"
                            "不确定就直说没查到，不要编。"
                        ),
                    },
                    {"role": "user", "content": f"对方问：{query}\n\n我查到的零碎信息：\n{context[:5000]}"},
                ],
                temperature=0.6,
                max_tokens=260,
            )
        except Exception:
            answer = "\n".join(r["description"] for r in results[:2])
        answer = re.sub(r"https?://\S+", "", answer)
        answer = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", answer)
        answer = re.sub(r"(来源|参考|链接)[:：].*", "", answer)
        answer = re.sub(r"\n{2,}", "\n", answer).strip()
        return answer[:600]

    async def _download(self, url: str) -> str:
        try:
            path = await asyncio.to_thread(download, url, self.cfg.data_dir / "downloads", self.features.download_max_mb)
        except (ToolError, OSError) as exc:
            return f"下载失败：{exc}"
        return f"已下载：{path.name}（{path.stat().st_size // 1024} KB）\n{path}"

    async def _make_image(self, incoming: Incoming, text: str) -> None:
        if not text:
            await self._deliver(incoming, "用法：/做图 想写在卡片上的字")
            return
        try:
            path = await asyncio.to_thread(make_card, text, self.cfg.data_dir / "downloads", self.cfg.bot_name)
        except Exception as exc:
            await self._deliver(incoming, f"做图失败：{exc}")
            return
        await self._send_media(incoming, "image", str(path), caption="给你做了一张")

    async def _make_file(self, incoming: Incoming, arg: str) -> None:
        if "|" in arg:
            name, content = arg.split("|", 1)
        else:
            name, content = "note.txt", arg
        if not content.strip():
            await self._deliver(incoming, "用法：/做文件 文件名|内容")
            return
        try:
            path = await asyncio.to_thread(make_file, name.strip(), content, self.cfg.data_dir / "downloads")
        except Exception as exc:
            await self._deliver(incoming, f"做文件失败：{exc}")
            return
        await self._send_media(incoming, "file", str(path), caption="")

    async def _image_for(self, user_text: str, reply: str) -> Path:
        key = get_key(self.cfg.data_dir, "brave")
        if not key:
            raise ToolError("没配 Brave Key，发不了图")
        try:
            raw = await self.llm.complete(
                [
                    {
                        "role": "system",
                        "content": (
                            "判断对方是不是在明确要求你发一张图。只输出 JSON："
                            '{"need":true,"query":"适合图片搜索的中文关键词"} 或 {"need":false}。'
                            "没有具体对象、只是让你看文字/看聊天记录时 need=false。"
                        ),
                    },
                    {"role": "user", "content": user_text},
                ],
                temperature=0.1,
                max_tokens=80,
            )
            data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        except Exception:
            raise ToolError("没听懂要什么图") from None
        query = str(data.get("query") or "").strip()
        if not query:
            query = re.sub(
                r"^(能不能|可以|帮我|给我|麻烦)?\s*(发张|发个|来张|来个|整张|画一个|画个|看看|瞧瞧|找张|找张图)",
                "",
                user_text,
            )
            query = re.sub(r"(长什么样|长啥样|什么样子|啥样子|图片|照片|表情包|图)$", "", query).strip(" 的：:，,")
        if not query:
            raise ToolError("没提取到图片主体")
        url = await asyncio.to_thread(brave_image, key, query)
        if not url:
            raise ToolError("没搜到合适的图")
        path = await asyncio.to_thread(download, url, self.cfg.data_dir / "downloads" / "images", 8)
        from PIL import Image

        with Image.open(path) as img:
            if img.width < 200 or img.height < 200:
                raise ToolError("搜到的图太小")
        return path

    async def _send_voice(self, incoming: Incoming, path: str) -> None:
        if self.link is None:
            await self._deliver(incoming, f"[语音] {path}")
            return
        try:
            await self.link.send_voice("group" if incoming.is_group else "private", incoming.target_id, path)
        except Exception as exc:
            await self._deliver(incoming, f"语音发送失败：{exc}")

    async def _send_media(self, incoming: Incoming, kind: str, path: str, caption: str = "") -> None:
        target_type = "group" if incoming.is_group else "private"
        if self.link is None:
            await self._deliver(incoming, f"[{kind}] {path}")
            return
        try:
            if kind == "image":
                await self.link.send_image(target_type, incoming.target_id, path, caption)
            else:
                await self.link.send_file(target_type, incoming.target_id, path)
        except Exception as exc:
            self.stats["errors"] += 1
            log.error("发送媒体失败：%s", exc)
            await self._deliver(incoming, f"发送失败：{exc}")

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

        mode = choose_modality(text, self.features.voice_threshold, self.features.image_threshold) if self.features.reply_format == "auto" else self.features.reply_format
        joined = "".join(parts)
        if mode in ("voice", "image", "file") and self.link is not None:
            try:
                if mode == "voice":
                    path = await synthesize(joined, self.cfg.data_dir / "downloads" / "voice", self.features.voice_name)
                    await self._send_voice(incoming, str(path))
                elif mode == "image":
                    path = await self._image_for(text, joined)
                    await self._send_media(incoming, "image", str(path), caption=joined[:80])
                else:
                    path = make_file("回复.txt", joined, self.cfg.data_dir / "downloads")
                    await self._send_media(incoming, "file", str(path))
                self.stats["replied"] += 1
                self.last_replies.append(joined)
                log.info("按语义用%s回复：%s", mode, joined[:50])
                return
            except Exception as exc:
                log.warning("%s 回复失败，退回文字：%s", mode, exc)

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
            extra=f"现在是 {clock}。" + ((" 表达风格：" + style_prompt(self.features)) if style_prompt(self.features) else ""),
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
