"""按钮内小转圈：测试类操作时告诉用户“正在算/已刷新”。"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QMovie
from PySide6.QtWidgets import QLabel, QPushButton

from .. import paths


class Spinner(QLabel):
    def __init__(self, parent=None, size: int = 18):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.movie = QMovie(str(paths.resource("assets", "spinner.gif")))
        self.movie.setScaledSize(QSize(size, size))
        self.setMovie(self.movie)
        self.hide()

    def start(self) -> None:
        self.show()
        self.movie.start()

    def stop(self) -> None:
        self.movie.stop()
        self.hide()


class BusyButton(QPushButton):
    """点击后按钮右侧出现转圈，调用 stop_busy 结束。"""

    def __init__(self, text: str, kind: str = "secondary", parent=None):
        super().__init__(text, parent)
        self.setObjectName(kind)
        self._text = text
        self.spinner = Spinner(self, 16)
        self._fallback = QTimer(self)
        self._fallback.setSingleShot(True)
        self._fallback.timeout.connect(self.stop_busy)
        self._busy = False

    def start_busy(self, label: str = "处理中…") -> None:
        if self._busy:
            return
        self._busy = True
        self.setText(label)
        self.spinner.start()
        self._relayout()
        self._fallback.start(8000)

    def stop_busy(self) -> None:
        if not self._busy:
            return
        self._busy = False
        self._fallback.stop()
        self.spinner.stop()
        self.setText(self._text)
        self._relayout()

    def _relayout(self) -> None:
        if self.spinner.isVisible():
            self.spinner.move(self.width() - 26, (self.height() - 16) // 2)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout()


def mark_refreshed(label: QLabel, text: str, ms: int = 2200) -> None:
    label.setText(f"✓ 已刷新 · {text}")
    QTimer.singleShot(ms, lambda: label.setText(text))
