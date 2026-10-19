"""无边框窗口的自定义标题栏：品牌、拖动、最小化/最大化/关闭。"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ..paths import APP_TITLE, APP_VERSION
from ..theme import COLORS
from .mascot import avatar


class WindowButton(QPushButton):
    def __init__(self, kind: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(46, 40)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setStyleSheet("QPushButton{background:transparent;border:none;}")
        self.setToolTip({"min": "最小化", "max": "最大化", "close": "关闭"}.get(kind, ""))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        hover = self.underMouse()
        if hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#E25C6A") if self.kind == "close" else QColor(255, 255, 255, 26))
            painter.drawRect(self.rect())
        pen = QPen(QColor("#E8EEFB"))
        pen.setWidthF(1.2)
        painter.setPen(pen)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        if self.kind == "min":
            painter.drawLine(QPoint(int(cx - 7), int(cy)), QPoint(int(cx + 7), int(cy)))
        elif self.kind == "max":
            painter.drawRect(QRectF(cx - 6, cy - 6, 12, 12))
        else:
            painter.drawLine(QPoint(int(cx - 6), int(cy - 6)), QPoint(int(cx + 6), int(cy + 6)))
            painter.drawLine(QPoint(int(cx + 6), int(cy - 6)), QPoint(int(cx - 6), int(cy + 6)))
        painter.end()

    def enterEvent(self, event) -> None:
        self.update()

    def leaveEvent(self, event) -> None:
        self.update()


class TitleBar(QWidget):
    def __init__(self, window: QWidget):
        super().__init__(window)
        self._window = window
        self.setFixedHeight(40)
        self.setObjectName("titlebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"QWidget#titlebar{{background:{COLORS['sidebar']};}}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 0, 0)
        layout.setSpacing(10)

        logo = QLabel()
        logo.setPixmap(avatar(22))
        logo.setFixedSize(22, 22)
        layout.addWidget(logo)

        title = QLabel(APP_TITLE)
        title.setStyleSheet("color:#FFFFFF; font-size:13px; font-weight:700;")
        layout.addWidget(title)

        version = QLabel(f"v{APP_VERSION}")
        version.setStyleSheet("color:#6F84AD; font-size:11px;")
        layout.addWidget(version)
        layout.addStretch(1)

        minimize = WindowButton("min")
        minimize.clicked.connect(self._window.showMinimized)
        layout.addWidget(minimize)
        self.max_button = WindowButton("max")
        self.max_button.clicked.connect(self.toggle_max)
        layout.addWidget(self.max_button)
        close = WindowButton("close")
        close.clicked.connect(self._window.close)
        layout.addWidget(close)

    def toggle_max(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle is not None:
                handle.startSystemMove()
            event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        self.toggle_max()
        event.accept()
