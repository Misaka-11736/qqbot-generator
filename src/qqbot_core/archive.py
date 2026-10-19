"""SQLite 消息归档：给总结、分类、统计用。"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER,
    conversation TEXT NOT NULL,
    group_id INTEGER DEFAULT 0,
    user_id INTEGER,
    name TEXT,
    text TEXT,
    segments TEXT,
    created_at REAL,
    tags TEXT
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation, id);
CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation TEXT,
    count INTEGER,
    text TEXT,
    created_at REAL
);
"""

CATEGORIES = {
    "技术": ["代码", "报错", "程序", "服务器", "接口", "python", "bug", "部署", "数据库", "前端", "后端"],
    "游戏": ["游戏", "开黑", "steam", "原神", "王者", "lol", "副本", "抽卡"],
    "学习": ["作业", "考试", "论文", "复习", "上课", "老师", "题", "考研"],
    "工作": ["上班", "加班", "项目", "老板", "会议", "工资", "面试", "简历"],
    "生活": ["吃饭", "睡觉", "天气", "快递", "外卖", "房租", "猫", "狗"],
    "情绪": ["烦", "累", "开心", "难受", "崩溃", "生气", "焦虑", "笑死"],
    "资源": ["链接", "下载", "分享", "网盘", "文件", "教程", "视频"],
}


def classify_text(text: str) -> list[str]:
    low = text.lower()
    hits = [name for name, words in CATEGORIES.items() if any(w in low for w in words)]
    return hits[:3]


class Archive:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        self.db.commit()

    def add(self, incoming, tags: list[str] | None = None) -> int:
        cur = self.db.execute(
            "INSERT INTO messages(message_id,conversation,group_id,user_id,name,text,segments,created_at,tags)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (
                incoming.message_id,
                incoming.conversation_key,
                incoming.group_id,
                incoming.user_id,
                incoming.sender_name,
                incoming.text[:4000],
                json.dumps(incoming.segments, ensure_ascii=False)[:8000],
                time.time(),
                "、".join(tags or []),
            ),
        )
        self.db.commit()
        return int(cur.lastrowid or 0)

    def recent(self, conversation: str, limit: int = 1000) -> list[dict]:
        rows = self.db.execute(
            "SELECT name,text,created_at,tags FROM messages WHERE conversation=? ORDER BY id DESC LIMIT ?",
            (conversation, max(1, min(limit, 2000))),
        ).fetchall()
        return [
            {"name": r[0] or "?", "text": r[1] or "", "ts": r[2], "tags": r[3] or ""}
            for r in reversed(rows)
        ]

    def conversations(self) -> list[tuple[str, int]]:
        rows = self.db.execute(
            "SELECT conversation, COUNT(*) FROM messages GROUP BY conversation ORDER BY COUNT(*) DESC LIMIT 50"
        ).fetchall()
        return [(str(r[0]), int(r[1])) for r in rows]

    def count(self) -> int:
        return int(self.db.execute("SELECT COUNT(*) FROM messages").fetchone()[0])

    def top_tags(self, limit: int = 8) -> list[tuple[str, int]]:
        counter: dict[str, int] = {}
        for (tags,) in self.db.execute("SELECT tags FROM messages WHERE tags<>''"):
            for tag in str(tags).split("、"):
                if tag:
                    counter[tag] = counter.get(tag, 0) + 1
        return sorted(counter.items(), key=lambda kv: kv[1], reverse=True)[:limit]

    def save_summary(self, conversation: str, count: int, text: str) -> None:
        self.db.execute(
            "INSERT INTO summaries(conversation,count,text,created_at) VALUES(?,?,?,?)",
            (conversation, count, text, time.time()),
        )
        self.db.commit()

    def prune(self, days: int) -> int:
        cutoff = time.time() - max(1, days) * 86400
        cur = self.db.execute("DELETE FROM messages WHERE created_at < ?", (cutoff,))
        self.db.commit()
        return cur.rowcount

    def close(self) -> None:
        self.db.close()
