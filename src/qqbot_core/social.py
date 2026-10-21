"""群聊社交影子模式：记录话题、判断“本来会不会接话”，只写日志不发送。"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger("qqbot.shadow")


class ShadowSocial:
    def __init__(self, get_cfg: Callable[[], Any], get_llm: Callable[[], Any], data_dir: Path):
        self.get_cfg = get_cfg
        self.get_llm = get_llm
        self.db_path = Path(data_dir) / "social.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._busy: set[str] = set()
        self._last_judge: dict[str, float] = {}
        self._last_trim = 0.0
        self._idle_task: asyncio.Task | None = None
        self._init_db()

    @property
    def cfg(self):
        return self.get_cfg().social

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS groups (
                    conv TEXT PRIMARY KEY,
                    topic TEXT DEFAULT '',
                    updated REAL DEFAULT 0,
                    pending INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conv TEXT NOT NULL,
                    user_id INTEGER DEFAULT 0,
                    name TEXT DEFAULT '',
                    text TEXT DEFAULT '',
                    ts REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_messages_conv_ts ON messages(conv, ts);
                CREATE TABLE IF NOT EXISTS summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conv TEXT NOT NULL,
                    text TEXT NOT NULL,
                    ts REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_summaries_conv_ts ON summaries(conv, ts);
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conv TEXT NOT NULL,
                    text TEXT NOT NULL,
                    join_ok INTEGER NOT NULL,
                    score INTEGER NOT NULL,
                    reason TEXT DEFAULT '',
                    source TEXT DEFAULT '',
                    ts REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_decisions_conv_ts ON decisions(conv, ts);
                """
            )

    def _recent(self, conv: str, limit: int = 12) -> list[tuple[str, str]]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT name, text FROM messages WHERE conv=? ORDER BY id DESC LIMIT ?",
                (conv, limit),
            ).fetchall()
        return list(reversed([(str(n or "群友"), str(t or "")) for n, t in rows]))

    def _topic(self, conv: str) -> str:
        with self._lock, self._conn() as conn:
            row = conn.execute("SELECT topic FROM groups WHERE conv=?", (conv,)).fetchone()
        return str(row[0] or "") if row else ""

    def observe(self, incoming: Any, text: str) -> None:
        if not incoming.is_group or not text.strip():
            return
        if not self.cfg.enabled:
            return
        if self._idle_task is None or self._idle_task.done():
            self._idle_task = asyncio.create_task(self._idle_loop())
        now = time.time()
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO messages(conv, user_id, name, text, ts) VALUES (?,?,?,?,?)",
                (incoming.conversation_key, int(incoming.user_id or 0), incoming.sender_name, text[:2000], now),
            )
            conn.execute(
                "INSERT INTO groups(conv, updated, pending) VALUES (?,?,1) "
                "ON CONFLICT(conv) DO UPDATE SET updated=excluded.updated, pending=pending+1",
                (incoming.conversation_key, now),
            )
            pending = conn.execute("SELECT pending FROM groups WHERE conv=?", (incoming.conversation_key,)).fetchone()[0]
        if pending >= max(5, int(self.cfg.summary_every)):
            self._spawn(self._summarize(incoming.conversation_key), incoming.conversation_key, "summary")
        if self._candidate(incoming, text):
            self._spawn(self._judge(incoming, text), incoming.conversation_key, "judge")
        if time.monotonic() - self._last_trim > 60:
            self._last_trim = time.monotonic()
            try:
                self._trim()
            except Exception as exc:
                log.debug("[shadow] 清理失败：%s", exc)

    def _candidate(self, incoming: Any, text: str) -> bool:
        if getattr(incoming, "at_me", False) or getattr(incoming, "reply_id", None):
            return True
        if len(text.strip()) < 3 or text.startswith("["):
            return False
        now = time.monotonic()
        if now - self._last_judge.get(incoming.conversation_key, 0.0) < max(5, int(self.cfg.sample_seconds)):
            return False
        self._last_judge[incoming.conversation_key] = now
        return True

    def _spawn(self, coro, conv: str, kind: str = "judge") -> None:
        key = f"{conv}:{kind}"
        if key in self._busy:
            coro.close()
            return
        self._busy.add(key)

        async def run() -> None:
            try:
                await coro
            finally:
                self._busy.discard(key)

        asyncio.create_task(run())

    async def _judge(self, incoming: Any, text: str) -> None:
        history = self._recent(incoming.conversation_key, 10)
        lines = "\n".join(f"{name}：{value}" for name, value in history)
        topic = self._topic(incoming.conversation_key)
        prompt = (
            "你在观察一个 QQ 群。判断机器人现在该不该接这句话，只输出 JSON："
            '{"join":true/false,"score":0-100,"reason":"不超过30字"}。'
            "考虑：是否在对机器人说、是否与当前话题相关、机器人能否贡献信息或情绪价值、"
            "是否正在打断别人、最近是否已经说过很多。不要输出 JSON 以外的内容。"
        )
        user = f"群话题：{topic or '未知'}\n最近消息：\n{lines}\n新消息（{incoming.sender_name}）：{text}"
        join_ok = False
        score = 0
        reason = ""
        source = "llm"
        try:
            raw = await self.get_llm().complete(
                [{"role": "system", "content": prompt}, {"role": "user", "content": user}],
                temperature=0.2,
                max_tokens=100,
            )
            data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
            join_ok = bool(data.get("join"))
            score = max(0, min(100, int(data.get("score") or 0)))
            reason = str(data.get("reason") or "")[:60]
        except Exception:
            source = "heuristic"
            join_ok = bool(getattr(incoming, "at_me", False) or getattr(incoming, "reply_id", None))
            score = 80 if join_ok else (35 if "?" in text or "？" in text else 10)
            reason = "已被呼叫" if join_ok else "未命中明确呼叫"
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO decisions(conv, text, join_ok, score, reason, source, ts) VALUES (?,?,?,?,?,?,?)",
                (incoming.conversation_key, text[:500], int(join_ok), score, reason, source, time.time()),
            )
        log.info("[shadow] join=%s score=%s reason=%s source=%s text=%s", join_ok, score, reason, source, text[:60])

    async def _summarize(self, conv: str) -> None:
        history = self._recent(conv, max(20, int(self.cfg.summary_every)))
        if not history:
            return
        lines = "\n".join(f"{name}：{value}" for name, value in history)
        prompt = (
            "把下面群聊压缩成一句当前话题摘要，不超过 60 字，只写正在聊什么、"
            "有哪些未解决的问题；不要评价，不要输出引号、标题或解释。"
        )
        try:
            summary = (await self.get_llm().complete(
                [{"role": "system", "content": prompt}, {"role": "user", "content": lines}],
                temperature=0.2,
                max_tokens=100,
            )).strip().replace("\n", " ")[:200]
        except Exception as exc:
            log.warning("[shadow] 摘要失败：%s", exc)
            return
        if not summary:
            return
        with self._lock, self._conn() as conn:
            conn.execute("INSERT INTO summaries(conv, text, ts) VALUES (?,?,?)", (conv, summary, time.time()))
            conn.execute("UPDATE groups SET topic=?, updated=?, pending=0 WHERE conv=?", (summary, time.time(), conv))
        log.info("[shadow] summary %s：%s", conv, summary)

    async def _idle_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            if not self.cfg.enabled:
                continue
            now = time.time()
            with self._lock, self._conn() as conn:
                rows = conn.execute("SELECT conv, updated, pending FROM groups WHERE pending > 0").fetchall()
            for conv, updated, _pending in rows:
                if now - float(updated or 0) >= max(1, int(self.cfg.idle_minutes)) * 60:
                    self._spawn(self._summarize(str(conv)), str(conv), "summary")

    def _trim(self) -> None:
        days = max(1, min(7, int(self.cfg.retention_days)))
        cutoff = time.time() - days * 86400
        max_bytes = max(20, min(100, int(self.cfg.max_mb))) * 1024 * 1024
        with self._lock:
            with self._conn() as conn:
                conn.execute("DELETE FROM messages WHERE ts < ?", (cutoff,))
                conn.execute("DELETE FROM summaries WHERE ts < ?", (cutoff,))
                conn.execute("DELETE FROM decisions WHERE ts < ?", (cutoff,))
                for conv in [r[0] for r in conn.execute("SELECT DISTINCT conv FROM messages")]:
                    conn.execute(
                        "DELETE FROM messages WHERE conv=? AND id NOT IN "
                        "(SELECT id FROM messages WHERE conv=? ORDER BY id DESC LIMIT 200)",
                        (conv, conv),
                    )
            size = self.db_path.stat().st_size if self.db_path.exists() else 0
            if size > max_bytes:
                with self._conn() as conn:
                    for table in ("messages", "summaries", "decisions"):
                        conn.execute(f"DELETE FROM {table} WHERE id IN (SELECT id FROM {table} ORDER BY id ASC LIMIT 500)")
                    conn.commit()
                    conn.execute("VACUUM")

    def stats(self) -> dict:
        with self._lock, self._conn() as conn:
            groups = conn.execute("SELECT COUNT(*) FROM groups").fetchone()[0]
            decisions = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
            joins = conn.execute("SELECT COUNT(*) FROM decisions WHERE join_ok=1").fetchone()[0]
        size = self.db_path.stat().st_size if self.db_path.exists() else 0
        return {"groups": groups, "decisions": decisions, "joins": joins, "mb": round(size / 1024 / 1024, 2)}

    def clear(self) -> None:
        with self._lock, self._conn() as conn:
            for table in ("messages", "summaries", "decisions", "groups"):
                conn.execute(f"DELETE FROM {table}")
            conn.execute("VACUUM")
