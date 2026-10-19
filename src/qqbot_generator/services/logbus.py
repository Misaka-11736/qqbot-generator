"""日志跟随：增量读取 logs/bot-YYYYMMDD.log，推给界面。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from .. import paths


class LogBus(QObject):
    line = Signal(str)
    switched = Signal(str)  # 切换到新日志文件时发出文件名

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._path: Path | None = None
        self._pos = 0
        self._buffer = ""
        self._timer = QTimer(self)
        self._timer.setInterval(700)
        self._timer.timeout.connect(self.poll)
        self._timer.start()

    # ---------- 对外 ----------

    def current_file(self) -> Path | None:
        return self._path

    def poll(self) -> None:
        path = self._latest()
        if path is None:
            return
        if path != self._path:
            self._path = path
            try:
                self._pos = path.stat().st_size  # 只跟随新内容，避免把历史日志当成刚发生的事件
            except OSError:
                self._pos = 0
            self._buffer = ""
            self.switched.emit(path.name)
        try:
            size = path.stat().st_size
            if size < self._pos:
                self._pos = 0
            if size == self._pos:
                return
            with path.open("rb") as handle:
                handle.seek(self._pos)
                chunk = handle.read()
                self._pos = handle.tell()
        except OSError:
            return
        text = self._buffer + chunk.decode("utf-8", errors="replace")
        lines = text.split("\n")
        self._buffer = lines.pop() if lines else ""
        for line in lines:
            if line.strip():
                self.line.emit(line)

    def read_all(self) -> list[str]:
        path = self._latest()
        if path is None or not path.is_file():
            return []
        try:
            return path.read_text("utf-8", errors="replace").splitlines()
        except OSError:
            return []

    # ---------- 内部 ----------

    def _latest(self) -> Path | None:
        folder = paths.logs_dir()
        if not folder.is_dir():
            return None
        files = sorted(folder.glob("bot-*.log"))
        return files[-1] if files else None
