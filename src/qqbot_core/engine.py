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

from . import cache as cache_store
from .archive import Archive, classify_text
from .config import Config, load_config
from .features import style_prompt
from .intent import classify as classify_intent
from .keyvault import get_key
from .llm import LLMError, make_llm
from .media import extract_frames, media_sources, read_text_attachment
from .memory import Memory
from .message import Incoming, parse_event
from .modality import choose_modality
from .persona import PRESETS, build_system_prompt, load_preset, style_of
from .plugins import PluginManager
from .providers import get as get_provider
from .semantic import describe as describe_plan
from .social import ShadowSocial
from .tools import ToolError, brave_image, brave_search, download, duckduckgo_search, make_card, make_file, tavily_search
from .util import RateLimiter, clean_reply, split_text
from .vision import caption_frames, look_at_frames, looks_like_image_question
from .voice import VoiceError, synthesize, synthesize_cloud, transcribe, transcribe_cloud, voice_sources, wants_voice
from .voice import prepare as prepare_voice

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
        self._cache_task: asyncio.Task | None = None
        self._last_tasks: dict[str, dict] = {}
        self._summary_counts: dict[str, int] = {}
        self.social = ShadowSocial(lambda: self.cfg, lambda: self.llm, cfg.data_dir)
        self._config_task: asyncio.Task | None = None
        self._llm_signature = (
            cfg.llm.provider_id,
            cfg.llm.base_url,
            cfg.llm.model,
            cfg.resolve_api_key() if hasattr(cfg, "resolve_api_key") else "",
        )
        self._search_day = ""
        self._search_used = 0
        self.features = cfg.features
        try:
            self._cfg_mtime = cfg.source.stat().st_mtime if cfg.source else 0.0
        except OSError:
            self._cfg_mtime = 0.0
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
        if self._cache_task is None or self._cache_task.done():
            self._cache_task = asyncio.create_task(self._cache_cleanup_loop())
        if self._config_task is None or self._config_task.done():
            self._config_task = asyncio.create_task(self._config_watch_loop())

    # ---------------- 事件入口 ----------------

    def _maybe_reload(self) -> None:
        path = self.cfg.source
        if path is None:
            return
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return
        if mtime <= self._cfg_mtime:
            return
        try:
            new = load_config(path)
            new.data_dir = self.cfg.data_dir
            if new.persona.default_iq != self.cfg.persona.default_iq:
                self.memory.apply_default_iq(new.persona.default_iq)
            self.cfg = new
            self.features = new.features
            self._cfg_mtime = mtime
            try:
                signature = (new.llm.provider_id, new.llm.base_url, new.llm.model, new.resolve_api_key())
            except Exception:
                signature = (new.llm.provider_id, new.llm.base_url, new.llm.model, "")
            if signature != self._llm_signature:
                self.llm, self.provider_label = make_llm(new)
                self._llm_signature = signature
                log.info("[config] Provider 切换为 %s / %s", new.llm.provider_id, new.llm.model)
            log.info(
                "[config] IQ=%s preset=%s tone=%s verbosity=%s emoji=%s reply=%s "
                "image_thr=%s voice_thr=%s search_thr=%s vision=%s search=%s voice_in=%s voice_out=%s",
                new.persona.default_iq,
                new.persona.preset,
                new.features.tone,
                new.features.verbosity,
                new.features.emoji,
                new.features.reply_format,
                new.features.image_threshold,
                new.features.voice_threshold,
                new.features.search_threshold,
                new.features.vision,
                new.features.search,
                new.features.voice_in,
                new.features.voice_out,
            )
        except Exception as exc:
            log.warning("配置热加载失败：%s", exc)

    async def handle_event(self, event: dict[str, Any]) -> None:
        self._maybe_reload()
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
        if not self._in_scope(incoming):
            return
        if incoming.message_id and incoming.message_id in self._seen_set:
            return
        self._remember_seen(incoming.message_id)
        self.memory.remember_user(incoming.user_id, incoming.sender_name)

        count = self._summary_counts.get(incoming.conversation_key, 0) + 1
        self._summary_counts[incoming.conversation_key] = count
        if count % 30 == 0 and self.archive is not None:
            asyncio.create_task(self._log_context_summary(incoming.conversation_key))

        tags = classify_text(incoming.text) if (self.features.classify and incoming.text) else []
        if self.archive is not None:
            try:
                self.archive.add(incoming, tags)
            except Exception as exc:
                log.warning("归档失败：%s", exc)

        text = incoming.text.strip()
        log.info(
            "[recv] %s %s(%s)：%s%s",
            incoming.conversation_key,
            incoming.sender_name,
            incoming.user_id,
            text[:1000] or "（无文字）",
            "  media=" + ",".join(str(s.get("type")) for s in incoming.segments if s.get("type") not in ("text", "at", "reply")) if incoming.segments else "",
        )
        voices = voice_sources(incoming.segments)
        if voices and self.features.voice_in:
            log.info("收到语音，开始识别")
            await self._deliver(incoming, "我听听…")
            try:
                src = await asyncio.to_thread(prepare_voice, voices[0], self.cfg.data_dir / "cache" / "voice")
                text = await self._transcribe_voice(src)
                log.info("语音识别：%s", text[:80])
                if incoming.is_group:
                    incoming.at_me = True
            except Exception as exc:
                log.warning("语音识别失败：%s", exc)
                await self._deliver(incoming, f"这段语音我没听清：{exc}")
                return
        if incoming.is_group:
            try:
                self.social.observe(incoming, text)
            except Exception as exc:
                log.debug("[shadow] 记录失败：%s", exc)
        if incoming.is_group and not incoming.at_me and incoming.reply_id not in self._sent_set:
            if self.cfg.chat.address_awareness and not await self._semantic_connected(incoming, text):
                return
        if await self.plugins.dispatch(incoming, text):
            return
        media = media_sources(incoming.segments)
        if not media and incoming.reply_id:
            media = await self._reply_media(incoming)
            if media:
                log.info("[media] 从被回复消息取到 %s 个媒体", len(media))
        if media:
            if not self.features.vision:
                log.info("收到媒体，但识图开关是关的")
            elif not self._want_vision(incoming, text):
                log.info("收到媒体，但没带问题也没 @，跳过：%s", text[:30])
            else:
                search_like = bool(re.search(r"(搜|找|查).{0,6}(这个|这张|它|同款|类似)", text))
                await self._vision_reply(incoming, text, media, search=search_like)
                return
        if not text:
            return

        if self.features.voice_out and wants_voice(text):
            spoken = re.sub(r"(用语音|发条语音|发个语音|语音说|念一下|读一下|说给我听|来段语音)", "", text).strip(" ：:，,")
            if spoken:
                await self._deliver(incoming, "等我清清嗓子…")
                try:
                    path = await self._synthesize_voice(spoken)
                    await self._send_voice(incoming, str(path))
                except Exception as exc:
                    await self._deliver(incoming, f"语音合成失败：{exc}")
                return

        if await self._natural_intent(text, incoming):
            return

        if text.startswith("/"):
            if text.strip().lower().startswith("/reset"):
                if incoming.user_id in self.cfg.admin_qq:
                    self.memory.reset(incoming.conversation_key)
                    log.info("[command] /reset by %s", incoming.user_id)
                    await self._deliver(incoming, "已重置当前会话。")
                    return
                log.info("[command] 非管理员 /reset，按普通聊天处理")
            else:
                log.info("[command] 忽略旧指令，按普通聊天处理：%s", text[:40])

        if not self._should_reply(incoming, text):
            return

        if not self._rate.allow(str(incoming.user_id)):
            log.info("限流：%s 触发太频繁，跳过", incoming.user_id)
            return

        await self._reply(incoming, text)

    # ---------------- 指令 ----------------

    async def _log_context_summary(self, conversation: str) -> None:
        if self.archive is None:
            return
        rows = self.archive.recent(conversation, 40)
        if len(rows) < 10:
            return
        text = "\n".join(f"{r['name']}：{r['text']}" for r in rows)
        try:
            summary = await self.llm.complete(
                [
                    {"role": "system", "content": "总结这段群聊：当前话题、主要结论、未解决的问题。中文，200 字以内。"},
                    {"role": "user", "content": text[:8000]},
                ],
                temperature=0.3,
                max_tokens=300,
            )
            self.archive.save_summary(conversation, len(rows), summary)
            log.info("[summary] %s %s", conversation, summary.strip()[:500])
        except Exception as exc:
            log.warning("[summary] 失败：%s", exc)

    def _want_vision(self, incoming: Incoming, text: str) -> bool:
        if not incoming.is_group:
            return True
        if incoming.at_me or (incoming.reply_id in self._sent_set):
            return True
        return looks_like_image_question(text)

    async def _vision_reply(self, incoming: Incoming, text: str, media: list[dict], search: bool = False) -> None:
        log.info("识图/媒体触发：%s（%s）", (text or "无文字")[:60], ",".join(m["kind"] for m in media))
        vision_id = self.features.vision_provider or self.cfg.llm.provider_id
        provider = get_provider(vision_id)
        if provider is None or "vision" not in provider.capabilities:
            await self._deliver(incoming, "当前视觉 Provider 不支持看图，去「能力」页换一个支持视觉的。")
            return
        if self.features.vision_provider:
            key = get_key(self.cfg.data_dir, f"cap_vision_{provider.id}")
        else:
            key = self.cfg.resolve_api_key()
        if not key and provider.id == "ollama":
            key = "ollama"
        if not key:
            await self._deliver(incoming, "看图 Provider 还没填 Key，去「能力」页填一下。")
            return
        vision_base = provider.base_url
        vision_model = provider.vision_model or self.features.vision_model
        await self._deliver(incoming, "我看看…")
        cache = self.cfg.data_dir / "cache" / "vision"
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
        facts = ""
        if frames:
            if search:
                query = await asyncio.to_thread(caption_frames, frames, key, vision_model, vision_base)
                if query:
                    log.info("[vision] 以图搜图关键词：%s", query)
                    try:
                        path = await self._image_for(query, "按图搜的", direct=True)
                        await self._send_media(incoming, "image", str(path), caption=f"这张图我查到的是：{query}")
                        return
                    except ToolError as exc:
                        log.info("[vision] 以图搜图失败：%s", exc)
            facts = await asyncio.to_thread(
                look_at_frames,
                frames,
                key,
                vision_model,
                text,
                "\n".join(notes),
                vision_base,
            )
        elif notes:
            facts = "\n".join(notes)[:3000]
        else:
            await self._deliver(incoming, "这个文件/视频我这边解析不了。")
            return
        answer = await self._persona_rewrite(facts, incoming, "识图")
        if not answer:
            log.warning("[vision] 人格重写失败，未发送客观摘要")
            return
        for part in split_text(answer, limit=600):
            await self._deliver(incoming, part)

    async def _natural_intent(self, text: str, incoming: Incoming) -> bool:
        compact = text.strip()

        summary = re.match(
            r"^(?:你|帮我|给我)?\s*(?:总结|汇总)(?:一下|下)?(?:\s*(?:最近)?\s*(\d{1,4})\s*条)?\s*$",
            compact,
        )
        if summary and self.features.summarize:
            log.info("[task] 总结 %s 条", summary.group(1) or self.features.summary_max)
            count = int(summary.group(1) or self.features.summary_max)
            count = max(10, min(count, self.features.summary_max))
            await self._deliver(incoming, "正在翻记录，等我一下…")
            for part in split_text(await self._summarize(incoming.conversation_key, count, incoming), limit=1600):
                await self._deliver(incoming, part)
            return True

        if self.features.download and ("下载" in compact or "存一下" in compact or "保存" in compact):
            url = re.search(r"https?://\S+", compact)
            if url:
                await self._deliver(incoming, await self._download(url.group(0)))
                return True

        decision = classify_intent(compact, vision=self.features.vision, search=self.features.search)
        log.info("[intent] %s（%s）", decision.kind, decision.reason)
        if decision.kind != "task" or decision.plan is None:
            return False
        plan = decision.plan
        log.info("[plan] %s", describe_plan(plan))
        if plan.normalized:
            log.info("[normalize] %s → %s", plan.raw, plan.normalized)

        context = self._last_tasks.get(incoming.conversation_key, {})
        query = plan.query or str(context.get("query") or "")
        if not query:
            await self._deliver(incoming, "搜什么？给我个词。")
            return True
        if context and not plan.query:
            log.info("[context] 回填上一次主体：%s", query)
        image_task = plan.modality == "image" or bool(plan.measure)
        self._last_tasks[incoming.conversation_key] = {
            "query": query,
            "modality": "image" if image_task else plan.modality,
        }
        if image_task and self.features.vision:
            log.info("[task] 图片搜索：%s", query)
            try:
                path = await self._image_for(query, "给你找的", direct=True)
                await self._send_media(incoming, "image", str(path), caption=f"搜到一张：{query}")
            except ToolError as exc:
                log.info("[task] 图片失败：%s", exc)
                await self._deliver(incoming, str(exc))
            return True
        if self.features.search and plan.action == "search":
            log.info("[task] 网页搜索：%s", query)
            await self._deliver(incoming, "我去网上看看…")
            await self._deliver(incoming, await self._search(query, incoming))
            return True
        return False

    async def _config_watch_loop(self) -> None:
        while True:
            self._maybe_reload()
            await asyncio.sleep(1)

    async def _cache_cleanup_loop(self) -> None:
        while True:
            try:
                removed, size = await asyncio.to_thread(
                    cache_store.cleanup,
                    self.cfg.data_dir,
                    self.features.cache_keep_days,
                    self.features.cache_max_mb,
                )
                if removed:
                    log.info("缓存清理：删除 %s 个文件，剩余 %.1f MB", removed, size / 1024 / 1024)
            except Exception as exc:
                log.warning("缓存清理失败：%s", exc)
            await asyncio.sleep(6 * 3600)

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

    async def _summarize(self, conversation: str, limit: int, incoming: Incoming | None = None) -> str:
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
        if incoming is not None:
            rewritten = await self._persona_rewrite(final.strip(), incoming, "群聊总结")
            if not rewritten:
                return ""
            return f"最近 {len(rows)} 条总结：\n{rewritten}"
        return f"最近 {len(rows)} 条总结：\n{final.strip()}"

    async def _search(self, query: str, incoming: Incoming | None = None) -> str:
        today = time.strftime("%Y-%m-%d")
        if today != self._search_day:
            self._search_day = today
            self._search_used = 0
        if self._search_used >= self.features.search_daily_limit:
            return "今天搜索次数用完了，明天再来。"
        provider = self.features.search_provider
        try:
            if provider == "tavily":
                key = get_key(self.cfg.data_dir, "tavily")
                if not key:
                    return "还没配置 Tavily Key，去「能力」页填一下。"
                results = await asyncio.to_thread(tavily_search, key, query, 5)
            elif provider == "duckduckgo":
                results = await asyncio.to_thread(duckduckgo_search, query, 5)
            else:
                key = get_key(self.cfg.data_dir, "brave")
                if not key:
                    return "还没配置 Brave Key，去「能力」页填一下。"
                results = await asyncio.to_thread(brave_search, key, query, 5)
        except ToolError as exc:
            log.warning("[search] 失败：%s", exc)
            return str(exc)
        self._search_used += 1
        if not results:
            return "没搜到结果。"
        facts = "\n".join(f"- {r['title']}：{r['description']}" for r in results)
        if incoming is not None:
            answer = await self._persona_rewrite(f"查询内容：{query}\n\n{facts}", incoming, "搜索")
            if not answer:
                return ""
        else:
            try:
                answer = await self.llm.complete(
                    [
                        {
                            "role": "system",
                            "content": (
                                "你刚查到了以下信息。用 2~4 句口语直接说结论；不要列点、不要标题、不要贴链接、"
                                "不要说“根据搜索结果/来源/资料显示”；不确定就直说没查到，不要编。"
                            ),
                        },
                        {"role": "user", "content": f"查询：{query}\n\n信息：\n{facts[:5000]}"},
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
            path = await asyncio.to_thread(download, url, self.cfg.data_dir / "cache" / "files", self.features.download_max_mb)
        except (ToolError, OSError) as exc:
            return f"下载失败：{exc}"
        return f"已下载：{path.name}（{path.stat().st_size // 1024} KB）\n{path}"

    async def _make_image(self, incoming: Incoming, text: str) -> None:
        if not text:
            await self._deliver(incoming, "用法：/做图 想写在卡片上的字")
            return
        try:
            path = await asyncio.to_thread(make_card, text, self.cfg.data_dir / "cache" / "files", self.cfg.bot_name)
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
            path = await asyncio.to_thread(make_file, name.strip(), content, self.cfg.data_dir / "cache" / "files")
        except Exception as exc:
            await self._deliver(incoming, f"做文件失败：{exc}")
            return
        await self._send_media(incoming, "file", str(path), caption="")

    async def _image_for(self, user_text: str, reply: str, direct: bool = False) -> Path:
        key = get_key(self.cfg.data_dir, "brave")
        if not key:
            raise ToolError("没配 Brave Key，发不了图")
        query = user_text.strip() if direct else ""
        if not query:
            try:
                raw = await self.llm.complete(
                    [
                        {
                            "role": "system",
                            "content": (
                                "从这句话里提取要搜索的图片主体，只输出 JSON："
                                '{"query":"简短中文关键词"} 或 {"query":""}。不要解释。'
                            ),
                        },
                        {"role": "user", "content": user_text},
                    ],
                    temperature=0.1,
                    max_tokens=60,
                )
                data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
                query = str(data.get("query") or "").strip()
            except Exception:
                query = ""
        if not query:
            query = re.sub(
                r"^(能不能|可以|帮我|给我|麻烦)?\s*(搜张|搜个|找张|找张图|发张|发个|来张|来个|整张|画一个|画个|看看|瞧瞧|搜|找|发|来)",
                "",
                user_text,
            )
            query = re.sub(r"(长什么样|长啥样|什么样子|啥样子|图片|照片|表情包|图)$", "", query)
        query = re.sub(r"(发来|发给我|给我|看看|一下|呗|吧|啊)$", "", query).strip(" 的：:，,")
        if not query:
            raise ToolError("没提取到图片主体")
        url = await asyncio.to_thread(brave_image, key, query)
        if not url:
            raise ToolError("没搜到合适的图")
        path = await asyncio.to_thread(download, url, self.cfg.data_dir / "cache" / "images", 8)
        from PIL import Image

        with Image.open(path) as img:
            if img.width < 200 or img.height < 200:
                raise ToolError("搜到的图太小")
        return path

    async def _reply_media(self, incoming: Incoming) -> list[dict]:
        if self.link is None or not incoming.reply_id:
            return []
        try:
            data = await self.link.call("get_msg", {"message_id": incoming.reply_id}, timeout=10)
        except Exception as exc:
            log.info("[media] 取被回复消息失败：%s", exc)
            return []
        if not isinstance(data, dict):
            return []
        message = data.get("message") or data.get("messages") or []
        if isinstance(message, str):
            return []
        media = media_sources(message) if isinstance(message, list) else []
        for seg in message if isinstance(message, list) else []:
            if not isinstance(seg, dict) or seg.get("type") != "forward":
                continue
            fid = str((seg.get("data") or {}).get("id") or "")
            if not fid:
                continue
            try:
                fwd = await self.link.call("get_forward_msg", {"id": fid}, timeout=15)
            except Exception as exc:
                log.info("[media] 展开合并转发失败：%s", exc)
                continue
            nodes = []
            if isinstance(fwd, dict):
                nodes = fwd.get("messages") or fwd.get("message") or []
            for node in nodes if isinstance(nodes, list) else []:
                content = node.get("message") if isinstance(node, dict) else None
                if isinstance(content, list):
                    media += media_sources(content)
        return media

    def _cap_key(self, kind: str, provider_id: str) -> str:
        key = get_key(self.cfg.data_dir, f"cap_{kind}_{provider_id}")
        if not key and provider_id == self.cfg.llm.provider_id:
            key = self.cfg.resolve_api_key()
        return key

    async def _transcribe_voice(self, src: Path) -> str:
        provider_id = self.features.asr_provider or "local"
        if provider_id == "local":
            return await asyncio.to_thread(transcribe, src, self.features.voice_model)
        provider = get_provider(provider_id)
        if provider is None or "asr" not in provider.capabilities:
            raise VoiceError("当前语音识别 Provider 不支持 ASR，去「能力」页换一个")
        key = self._cap_key("asr", provider.id)
        if not key:
            raise VoiceError("语音识别 Provider 还没填 Key")
        model = self.features.asr_model or provider.asr_model
        text = await asyncio.to_thread(transcribe_cloud, src, provider.base_url, key, model)
        if not text:
            raise VoiceError("语音识别结果为空，可能音频格式不支持")
        return text

    async def _synthesize_voice(self, text: str) -> Path:
        provider_id = self.features.tts_provider or "edge"
        if provider_id == "edge":
            return await synthesize(text, self.cfg.data_dir / "cache" / "voice", self.features.voice_name)
        provider = get_provider(provider_id)
        if provider is None or "tts" not in provider.capabilities:
            raise VoiceError("当前语音合成 Provider 不支持 TTS，去「能力」页换一个")
        key = self._cap_key("tts", provider.id)
        if not key:
            raise VoiceError("语音合成 Provider 还没填 Key")
        model = self.features.tts_model or provider.tts_model
        voice = self.features.tts_voice or provider.tts_voice or "alloy"
        return await asyncio.to_thread(
            synthesize_cloud, text, self.cfg.data_dir / "cache" / "voice", provider.base_url, key, model, voice
        )

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

    async def _semantic_connected(self, incoming: Incoming, text: str) -> bool:
        """用模型判断新消息和机器人上一句是否语义相接；接不上就不插话。"""
        if incoming.at_me:
            log.info("[dialog] 硬回复：被 @")
            return True
        history = self.memory.history(incoming.conversation_key)[-8:]
        last_assistant = next((h for h in reversed(history) if h.get("role") == "assistant"), None)
        if last_assistant is None:
            log.info("[dialog] 不接：没有可接的上一句")
            return False
        lines = []
        for item in history[-6:]:
            who = self.cfg.bot_name if item.get("role") == "assistant" else (item.get("name") or "群友")
            lines.append(f"{who}：{item.get('text') or ''}")
        context = "\n".join(lines)
        try:
            raw = await self.llm.complete(
                [
                    {
                        "role": "system",
                        "content": (
                            "判断群里这条新消息是不是在接机器人的话。看语义关系，不看关键词："
                            "补充、反驳、顺着说、回答都算连接；各说各的、换话题不算。"
                            '只输出 JSON：{"connected":true,"score":85} 或 {"connected":false,"score":10}。'
                        ),
                    },
                    {"role": "user", "content": f"最近对话：\n{context}\n\n新消息（{incoming.sender_name}）：{text}"},
                ],
                temperature=0.1,
                max_tokens=60,
            )
            data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
            score = int(data.get("score") or (80 if data.get("connected") else 0))
        except Exception:
            score = self._addressing_score(incoming, text)
        if score >= self.cfg.chat.address_threshold:
            log.info("[dialog] 接话：语义分 %s ≥ 门槛 %s", score, self.cfg.chat.address_threshold)
            incoming.at_me = True  # 语义相接也按硬回复处理
            return True
        log.info("[dialog] 不接：语义分 %s < 门槛 %s", score, self.cfg.chat.address_threshold)
        return False

    def _addressing_score(self, incoming: Incoming, text: str) -> int:
        if incoming.at_me:
            return 100
        score = 0
        name = self.cfg.bot_name
        if name and name in text:
            score += 45
        if "你" in text:
            score += 15
        history = self.memory.history(incoming.conversation_key)[-8:]
        last_assistant = next((h for h in reversed(history) if h.get("role") == "assistant"), None)
        last_user = next((h for h in reversed(history) if h.get("role") == "user"), None)
        if last_user and last_user.get("name") == incoming.sender_name and last_assistant:
            score += 30
        if last_assistant:
            bot_text = str(last_assistant.get("text") or "")
            grams = {bot_text[i:i + 2] for i in range(len(bot_text) - 1)}
            hits = sum(1 for i in range(len(text) - 1) if text[i:i + 2] in grams)
            score += min(30, hits * 6)
        if "?" in text or "？" in text:
            score += 10
        return min(100, score)

    def _in_scope(self, incoming: Incoming) -> bool:
        cfg = self.cfg
        if not incoming.is_group:
            return cfg.chat.enable_private
        if not cfg.chat.enable_group:
            return False
        scope = cfg.chat.group_scope
        if scope == "whitelist" and incoming.group_id not in cfg.chat.group_list:
            return False
        return not (scope == "blacklist" and incoming.group_id in cfg.chat.group_list)

    def _should_reply(self, incoming: Incoming, text: str) -> bool:
        key = incoming.conversation_key
        if self.memory.muted(key):
            log.info("[dialog] 不回复：当前会话已静音")
            return False
        if incoming.is_group:
            if not self.cfg.chat.enable_group:
                log.info("[dialog] 不回复：群聊能力已关闭")
                return False
            scope = self.cfg.chat.group_scope
            if scope == "whitelist" and incoming.group_id not in self.cfg.chat.group_list:
                return False
            if scope == "blacklist" and incoming.group_id in self.cfg.chat.group_list:
                return False
        elif not self.cfg.chat.enable_private:
            return False
        if incoming.at_me:
            log.info("[dialog] 硬回复：被 @")
            return True
        if incoming.reply_id and incoming.reply_id in self._sent_set:
            log.info("[dialog] 硬回复：回复了它的消息")
            return True
        if not incoming.is_group:
            log.info("[dialog] 回复：私聊")
            return True
        if self.cfg.chat.address_awareness:
            score = self._addressing_score(incoming, text)
            if score >= self.cfg.chat.address_threshold:
                log.info("判定为对话（%s 分）：%s", score, text[:40])
                return True
            return False

        # 群聊：按概率搭话，且受冷却和最短长度限制
        if len(text) < 2 or text.startswith("["):
            log.info("[dialog] 不插话：消息太短")
            return False
        now = time.monotonic()
        if now - self._last_random.get(key, 0.0) < self.cfg.chat.group_cooldown:
            log.info("[dialog] 不插话：冷却中")
            return False
        if random.random() >= self.cfg.chat.group_chat_probability:
            log.info("[dialog] 不插话：概率未命中")
            return False
        self._last_random[key] = now
        return True

    # ---------------- 回复 ----------------

    async def _reply(self, incoming: Incoming, text: str) -> None:
        key = incoming.conversation_key
        lock = self._locks.setdefault(key, asyncio.Lock())
        iq = int(self.cfg.persona.default_iq)
        preset = self.cfg.persona.preset

        async with lock:
            messages = self._build_messages(incoming, text, iq, preset)
            plan = await self._plan_reply(incoming, text)
            if plan:
                messages[0]["content"] += f"\n【这一轮怎么接】{plan}"
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

        log.info("[llm] raw=%s", (raw or "")[:1200].replace("\n", " "))
        reply = clean_reply(raw)
        reply = self._de_assistant(reply)
        if not reply:
            return
        if len(reply) > max_chars:
            reply = reply[:max_chars].rstrip("，,、") + "……"
        parts = split_text(reply, limit=max(80, min(self.cfg.chat.max_reply_chars, max_chars + 40)))
        if not self.cfg.chat.split_long_reply:
            parts = ["".join(parts)]

        log.info("[state] IQ=%s preset=%s style(tone=%s verbosity=%s emoji=%s)", iq, preset, self.features.tone, self.features.verbosity, self.features.emoji)
        self.memory.add(key, "user", text, incoming.sender_name)
        self.memory.add(key, "assistant", "".join(parts), self.cfg.bot_name)
        self.memory.mark_chat(key)

        mode = choose_modality(text, self.features.voice_threshold, self.features.image_threshold) if self.features.reply_format == "auto" else self.features.reply_format
        joined = "".join(parts)
        if mode in ("voice", "image", "file") and self.link is not None:
            try:
                if mode == "voice":
                    path = await self._synthesize_voice(joined)
                    await self._send_voice(incoming, str(path))
                elif mode == "image":
                    path = await self._image_for(text, joined)
                    await self._send_media(incoming, "image", str(path), caption=joined[:80])
                else:
                    path = make_file("回复.txt", joined, self.cfg.data_dir / "cache" / "files")
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

    async def _plan_reply(self, incoming: Incoming, text: str) -> str:
        history = self.memory.history(incoming.conversation_key)[-4:]
        last = next((h.get("text", "") for h in reversed(history) if h.get("role") == "assistant"), "")
        try:
            plan = await self.llm.complete(
                [
                    {
                        "role": "system",
                        "content": "用不超过 12 个字说这一轮该怎么接：接梗/反驳/关心/敷衍/提问/顺着聊。只输出这几个词之一加半句理由。",
                    },
                    {"role": "user", "content": f"我上一句：{last}\n对方：{text}"},
                ],
                temperature=0.2,
                max_tokens=30,
            )
            return plan.strip()[:40]
        except Exception:
            return ""

    async def _persona_rewrite(self, facts: str, incoming: Incoming, kind: str) -> str:
        facts = (facts or "").strip()
        if not facts:
            return ""
        iq = int(self.cfg.persona.default_iq)
        preset = self.cfg.persona.preset
        now = time.localtime()
        clock = f"{time.strftime('%m月%d日 %H:%M', now)} {WEEKDAYS[now.tm_wday]}"
        extra = (
            f"现在是 {clock}。你刚通过「{kind}」拿到一些事实，准备在群里接话。"
            "只以第一人称说给当前会话的人听；禁止出现“对方/用户/提问者/提问的人”这些第三人称。"
            "只能改写语气、人称、节奏，绝对不能增加事实里没有的信息；"
            "事实里标了不确定的地方，必须保留不确定，不要说得像确定。"
        )
        style = style_prompt(self.features)
        if style:
            extra += " 表达风格：" + style
        system = build_system_prompt(
            preset_text=load_preset(preset),
            persona_label=PRESETS.get(preset, preset),
            bot_name=self.cfg.bot_name,
            iq=iq,
            user_name=incoming.sender_name,
            is_group=incoming.is_group,
            extra=extra,
        )
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        history = self.memory.history(incoming.conversation_key)
        limit = max(2, self.cfg.chat.context_turns * 2)
        for item in history[-limit:]:
            if item.get("role") in ("user", "assistant") and item.get("text"):
                messages.append({"role": item["role"], "content": item["text"]})
        messages.append(
            {
                "role": "user",
                "content": (
                    f"工具事实：\n{facts[:4000]}\n\n"
                    f"请把上述事实改写成一条{kind}后的自然回复。"
                    "不要提“工具/搜索/识图/事实”这些词，不要复述整段摘要，不要新增信息。"
                ),
            }
        )
        temperature, max_tokens, max_chars = style_of(iq)
        for attempt in range(2):
            try:
                raw = await self.llm.complete(messages, temperature=temperature, max_tokens=max_tokens)
                reply = self._de_assistant(clean_reply(raw))
                reply = re.sub(r"(对方|提问者|提问的人)", "你", reply)
                if reply:
                    return reply[:max_chars]
                log.warning("[persona] %s 重写为空（第 %s 次）", kind, attempt + 1)
            except Exception as exc:
                log.warning("[persona] %s 重写失败（第 %s 次）：%s", kind, attempt + 1, exc)
        log.warning("[persona] %s 重写两次失败，放弃发送", kind)
        return ""

    def _de_assistant(self, text: str) -> str:
        text = re.sub(r"^(首先|其次|总之|总的来说|希望对你有帮助)[，,：:\s]*", "", text)
        text = text.replace("作为AI", "我").replace("作为 AI", "我")
        return text.strip()

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
                    log.info("[send] text msg_id=%s len=%s", data.get("message_id"), len(text))
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
