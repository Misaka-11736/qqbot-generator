"""人工标注驱动的迭代：记录回复、收集评审、生成低风险规则。"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterable
from pathlib import Path

log = logging.getLogger("qqbot.learning")

REASONS = {
    "logic": "逻辑",
    "tone": "语气",
    "length": "长度",
    "timing": "时机",
    "fact": "事实",
    "repeat": "重复",
}
LOW_RISK = {"tone", "length", "timing", "repeat"}
HIGH_RISK = {"logic", "fact", "persona", "group_rule"}


class LearningStore:
    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "learning.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init(self) -> None:
        with self._lock, self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS replies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conv TEXT NOT NULL,
                    trigger_id INTEGER DEFAULT 0,
                    user_text TEXT DEFAULT '',
                    reply TEXT NOT NULL,
                    ts REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_replies_ts ON replies(ts);
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reply_id INTEGER UNIQUE NOT NULL,
                    verdict INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    note TEXT DEFAULT '',
                    ts REAL NOT NULL,
                    processed INTEGER DEFAULT 0
                );
                """
            )

    def record_reply(self, conv: str, trigger_id: int, user_text: str, reply: str) -> int:
        if not reply.strip():
            return 0
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO replies(conv, trigger_id, user_text, reply, ts) VALUES (?,?,?,?,?)",
                (conv, int(trigger_id or 0), user_text[:1000], reply[:2000], time.time()),
            )
            return int(cur.lastrowid or 0)

    def recent(self, limit: int = 100) -> list[dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT r.id, r.conv, r.user_text, r.reply, r.ts, f.verdict, f.reason, f.note "
                "FROM replies r LEFT JOIN feedback f ON f.reply_id=r.id ORDER BY r.id DESC LIMIT ?",
                (max(1, min(500, limit)),),
            ).fetchall()
        return [
            {"id": r[0], "conv": r[1], "user": r[2], "reply": r[3], "ts": r[4],
             "verdict": r[5], "reason": r[6] or "", "note": r[7] or ""}
            for r in rows
        ]

    def add_feedback(self, reply_id: int, verdict: int, reason: str, note: str = "") -> None:
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO feedback(reply_id, verdict, reason, note, ts, processed) VALUES (?,?,?,?,?,0) "
                "ON CONFLICT(reply_id) DO UPDATE SET verdict=excluded.verdict, reason=excluded.reason, "
                "note=excluded.note, ts=excluded.ts, processed=0",
                (reply_id, 1 if verdict > 0 else -1, reason if reason in REASONS else "tone", note[:300], time.time()),
            )

    def unprocessed(self) -> list[dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT f.id, f.reply_id, f.verdict, f.reason, f.note, r.user_text, r.reply "
                "FROM feedback f JOIN replies r ON r.id=f.reply_id WHERE f.processed=0 ORDER BY f.id"
            ).fetchall()
        return [
            {"feedback_id": r[0], "reply_id": r[1], "verdict": r[2], "reason": r[3],
             "note": r[4], "user": r[5], "reply": r[6]}
            for r in rows
        ]

    def mark_processed(self, feedback_ids: Iterable[int]) -> None:
        ids = [int(i) for i in feedback_ids]
        if not ids:
            return
        with self._lock, self._conn() as conn:
            conn.executemany("UPDATE feedback SET processed=1 WHERE id=?", [(i,) for i in ids])

    def counts(self) -> dict[str, int]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT reason, COUNT(*) FROM feedback WHERE processed=0 GROUP BY reason"
            ).fetchall()
        return {str(r[0]): int(r[1]) for r in rows}

    def stats(self) -> dict:
        with self._lock, self._conn() as conn:
            replies = conn.execute("SELECT COUNT(*) FROM replies").fetchone()[0]
            labels = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM feedback WHERE processed=0").fetchone()[0]
        return {"replies": replies, "labels": labels, "pending": pending}


class RuleStore:
    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "rules.json"
        self._lock = threading.Lock()
        self._mtime = self.path.stat().st_mtime if self.path.exists() else 0.0
        self.data = self._load()

    def _empty(self) -> dict:
        return {"version": 0, "active": [], "pending": [], "history": []}

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text("utf-8"))
            if isinstance(data, dict):
                data.setdefault("active", [])
                data.setdefault("pending", [])
                data.setdefault("history", [])
                data.setdefault("version", 0)
                return data
        except (OSError, json.JSONDecodeError):
            pass
        return self._empty()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), "utf-8")
        self._mtime = self.path.stat().st_mtime

    def refresh(self) -> None:
        try:
            mtime = self.path.stat().st_mtime if self.path.exists() else 0.0
        except OSError:
            return
        if mtime != self._mtime:
            self._mtime = mtime
            self.data = self._load()

    def active_text(self, scope: str = "") -> str:
        self.refresh()
        now = time.time()
        lines = []
        for rule in self.data.get("active", []):
            if float(rule.get("expires") or 0) <= now:
                continue
            if rule.get("scope") and rule.get("scope") != scope:
                continue
            lines.append(f"- {rule.get('text')}")
        return "近期适应（来自人工标注）：\n" + "\n".join(lines[:20]) if lines else ""

    def pending(self) -> list[dict]:
        self.refresh()
        return list(self.data.get("pending", []))

    def active(self) -> list[dict]:
        self.refresh()
        return list(self.data.get("active", []))

    def apply(self, rules: list[dict], ttl_days: int = 14) -> tuple[int, int]:
        """低风险直接生效，高风险进入待确认；同类别低风险替换，避免冲突。"""
        now = time.time()
        low = 0
        high = 0
        with self._lock:
            for item in rules:
                text = str(item.get("text") or "").strip()[:160]
                category = str(item.get("category") or "tone")
                if not text:
                    continue
                rule = {
                    "id": uuid.uuid4().hex[:10],
                    "text": text,
                    "category": category,
                    "risk": "low" if category in LOW_RISK else "high",
                    "scope": str(item.get("scope") or ""),
                    "created": now,
                    "expires": now + max(1, min(90, ttl_days)) * 86400,
                    "evidence": item.get("evidence") or [],
                }
                if rule["risk"] == "low":
                    self.data["active"] = [
                        old for old in self.data["active"]
                        if not (old.get("category") == category and old.get("scope") == rule["scope"])
                    ]
                    self.data["active"].append(rule)
                    low += 1
                else:
                    if not any(old.get("text") == text for old in self.data["pending"]):
                        self.data["pending"].append(rule)
                        high += 1
            self.data["active"] = [
                r for r in self.data["active"] if float(r.get("expires") or 0) > now
            ][-20:]
            if low or high:
                self._snapshot()
                self._save()
        return low, high

    def _snapshot(self) -> None:
        self.data["version"] = int(self.data.get("version") or 0) + 1
        self.data["history"].append({
            "version": self.data["version"],
            "ts": time.time(),
            "active": json.loads(json.dumps(self.data["active"], ensure_ascii=False)),
            "pending": json.loads(json.dumps(self.data["pending"], ensure_ascii=False)),
        })
        self.data["history"] = self.data["history"][-20:]

    def approve(self, rule_id: str) -> bool:
        with self._lock:
            for rule in list(self.data.get("pending", [])):
                if rule.get("id") == rule_id:
                    self.data["pending"].remove(rule)
                    rule["created"] = time.time()
                    rule["expires"] = time.time() + 14 * 86400
                    self.data["active"].append(rule)
                    self._snapshot()
                    self._save()
                    return True
        return False

    def reject(self, rule_id: str) -> bool:
        with self._lock:
            before = len(self.data.get("pending", []))
            self.data["pending"] = [r for r in self.data.get("pending", []) if r.get("id") != rule_id]
            if len(self.data["pending"]) != before:
                self._snapshot()
                self._save()
                return True
        return False

    def previous_version(self) -> int | None:
        history = self.data.get("history", [])
        return int(history[-2].get("version") or 0) if len(history) >= 2 else None

    def rollback_previous(self) -> bool:
        version = self.previous_version()
        return self.rollback(version) if version is not None else False

    def rollback(self, version: int) -> bool:
        with self._lock:
            target = next((h for h in self.data.get("history", []) if int(h.get("version") or 0) == version), None)
            if target is None:
                return False
            self.data["active"] = json.loads(json.dumps(target.get("active", [])))
            self.data["pending"] = json.loads(json.dumps(target.get("pending", [])))
            self._snapshot()
            self._save()
            return True


class LearningIteration:
    def __init__(self, data_dir: Path, get_llm, get_cfg):
        self.store = LearningStore(data_dir)
        self.rules = RuleStore(data_dir)
        self.get_llm = get_llm
        self.get_cfg = get_cfg

    async def maybe_run(self) -> None:
        cfg = self.get_cfg().learning
        if not cfg.enabled:
            return
        rows = self.store.unprocessed()
        if not rows:
            return
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["reason"]] = counts.get(row["reason"], 0) + 1
        eligible = {reason: count for reason, count in counts.items() if count >= cfg.min_labels}
        if not eligible:
            return
        sample = [r for r in rows if r["reason"] in eligible]
        lines = []
        for r in sample[:40]:
            verdict = "好" if r["verdict"] > 0 else "不好"
            lines.append(
                f"[{r['reason']}] {verdict}｜用户：{r['user'][:120]}｜Bot：{r['reply'][:200]}｜备注：{r['note'][:80]}"
            )
        prompt = (
            "你是一个人格迭代分析器。只根据下面的人工标注，归纳最多 5 条可执行规则。"
            '只输出 JSON 数组，每项：{"category":"tone|length|timing|repeat|logic|fact","text":"规则，不超过60字","evidence":[标注序号]}。'
            "tone/length/timing/repeat 是低风险，只改表达和参与策略；"
            "logic/fact 是高风险，只能在用户确认后生效。不要编造样本里没有的偏好。"
        )
        try:
            raw = await self.get_llm().complete(
                [{"role": "system", "content": prompt}, {"role": "user", "content": "\n".join(lines)}],
                temperature=0.2,
                max_tokens=500,
            )
            match = re.search(r"\[.*\]", raw, re.S)
            data = json.loads(match.group(0)) if match else []
            rules = [item for item in data if isinstance(item, dict)]
        except Exception as exc:
            log.warning("[learn] 生成规则失败：%s", exc)
            return
        if not rules:
            log.warning("[learn] 模型没有产出规则，保留标注等下次启动重试")
            return
        low, high = self.rules.apply(rules, cfg.ttl_days)
        if low == 0 and high == 0:
            log.warning("[learn] 规则均无效，保留标注等下次启动重试")
            return
        self.store.mark_processed([r["feedback_id"] for r in sample[:40]])
        log.info("[learn] 标注 %s 条 → 自动规则 %s，待确认 %s", len(sample[:40]), low, high)
