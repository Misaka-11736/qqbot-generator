"""通用小工具：日志、文本切分、限流、原子 JSON 存储。"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

_LOG_CONFIGURED = False


def ensure_utf8_stdout() -> None:
    """Windows 控制台默认 GBK，直接 print emoji 会炸；这里强制 UTF-8 且不抛异常。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def setup_logging(level: str = "INFO", log_dir: Path | None = None, tag: str = "bot") -> logging.Logger:
    """控制台 + 文件双通道日志，文件按天切分并自动清理。"""
    global _LOG_CONFIGURED
    logger = logging.getLogger("qqbot")
    if _LOG_CONFIGURED:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")

    # PyInstaller windowed 模式下 sys.stdout 可能是 None，此时只写文件
    if sys.stdout is not None:
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(fmt)
        logger.addHandler(stream)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"{tag}-{time.strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    _LOG_CONFIGURED = True
    return logger


def trim_old_logs(log_dir: Path, keep_days: int = 14) -> None:
    if keep_days <= 0 or not log_dir.is_dir():
        return
    cutoff = time.time() - keep_days * 86400
    for item in log_dir.glob("*.log*"):
        try:
            if item.stat().st_mtime < cutoff:
                item.unlink()
        except OSError:
            pass


def clean_reply(text: str) -> str:
    """把模型输出洗成适合 QQ 的一句话/几句话。"""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").strip()

    # 去掉整体包裹的引号
    if len(text) >= 2 and text[0] in "“\"'「『" and text[-1] in "”\"'」』":
        text = text[1:-1].strip()

    # 去掉角色名前缀，如 “小鲸鱼：”
    text = re.sub(r"^\s*(?:小鲸鱼|助手|Bot|bot|AI|我)\s*[：:]\s*", "", text)

    # Markdown 痕迹
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"`{1,3}([^`]*)`{1,3}", r"\1", text)
    text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)

    # 括号里的动作描写：（笑）（沉默）
    text = re.sub(r"[（(](?:笑|微笑|沉默|认真|思考|歪头|点头|叹气|摆手)[^）)]{0,8}[）)]", "", text)

    # 压缩空行
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_text(text: str, limit: int = 300, max_parts: int = 3) -> list[str]:
    """按句子边界把长回复切成几段，避免刷屏。"""
    text = text.strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    parts: list[str] = []
    rest = text
    while rest and len(parts) < max_parts:
        if len(rest) <= limit:
            parts.append(rest)
            rest = ""
            break
        window = rest[:limit]
        cut = max(window.rfind(mark) for mark in ("。", "！", "？", "\n", "…", "；", "，"))
        if cut < limit // 3:
            cut = limit
        else:
            cut += 1
        parts.append(rest[:cut].strip())
        rest = rest[cut:].strip()

    if rest:
        # 超出的部分并进最后一段，避免丢内容；再长就截断并留省略号
        merged = parts[-1] + rest
        if len(merged) > limit + 50:
            parts[-1] = merged[: limit + 50] + "……"
        else:
            parts[-1] = merged
    return [p for p in parts if p]


class RateLimiter:
    """滑动窗口限流：每个 key 每 window 秒最多 times 次。"""

    def __init__(self, times: int, window: float = 60.0):
        self.times = max(1, times)
        self.window = window
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits.setdefault(key, deque())
            while bucket and now - bucket[0] > self.window:
                bucket.popleft()
            if len(bucket) >= self.times:
                return False
            bucket.append(now)
            return True


class JsonStore:
    """极简 JSON 持久化：写临时文件再替换，避免半截文件。"""

    def __init__(self, path: Path, default: dict[str, Any] | None = None):
        self.path = path
        self._lock = threading.Lock()
        self.data: dict[str, Any] = default or {}
        self.load()

    def load(self) -> None:
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text("utf-8"))
            if isinstance(raw, dict):
                self.data = raw
        except (OSError, json.JSONDecodeError):
            # 文件损坏时备份，避免直接覆盖
            try:
                self.path.replace(self.path.with_suffix(".corrupt.json"))
            except OSError:
                pass

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), "utf-8")
            os.replace(tmp, self.path)


def pretty_seconds(seconds: float) -> str:
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds}秒"
    if seconds < 3600:
        return f"{seconds // 60}分{seconds % 60}秒"
    return f"{seconds // 3600}小时{(seconds % 3600) // 60}分"
