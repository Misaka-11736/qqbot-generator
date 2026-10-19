"""角色立绘「小鲸」：加载用户提供的蓝鲸女仆设定图。

资源在 assets/character/：
  character.png  正面立绘（透明背景，720px 高）
  avatar.png     圆形头像
如果资源缺失，退化为一个蓝色圆形 + 字母，保证界面不崩。
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

from ..paths import resource


def _load(name: str) -> QPixmap:
    path = resource("assets", "character", name)
    return QPixmap(str(path))


_CHARACTER: QPixmap | None = None
_AVATAR: QPixmap | None = None


def character_pixmap() -> QPixmap:
    global _CHARACTER
    if _CHARACTER is None:
        _CHARACTER = _load("character.png")
    return _CHARACTER


def avatar_pixmap() -> QPixmap:
    global _AVATAR
    if _AVATAR is None:
        _AVATAR = _load("avatar.png")
    return _AVATAR


class Mascot(QWidget):
    """首页 / 关于页的立绘，带轻微浮动和气泡。"""

    def __init__(self, parent: QWidget | None = None, size: int = 220, animated: bool = True):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self._t = 0.0
        self._bubbles = [
            (random.uniform(0.05, 0.95), random.uniform(0.0, 1.0), random.uniform(2.0, 5.0), random.uniform(0.3, 0.7))
            for _ in range(7)
        ]
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        if animated:
            self._timer.start()

    def _tick(self) -> None:
        self._t += 0.035
        self._bubbles = [(x, (y - speed * 0.004) % 1.05, r, speed) for (x, y, r, speed) in self._bubbles]
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        width, height = self.width(), self.height()

        glow = QRadialGradient(width / 2, height * 0.55, width * 0.52)
        glow.setColorAt(0.0, QColor(111, 161, 242, 60))
        glow.setColorAt(1.0, QColor(111, 161, 242, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(width / 2, height * 0.55), width * 0.52, height * 0.52)

        painter.setBrush(QColor(180, 210, 255, 70))
        for x, y, r, _speed in self._bubbles:
            painter.drawEllipse(QPointF(20 + x * (width - 40), height - y * height), r, r)

        pix = character_pixmap()
        if pix.isNull():
            painter.setBrush(QColor("#4F7FE0"))
            painter.drawEllipse(QRectF(width * 0.15, height * 0.15, width * 0.7, height * 0.7))
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "鲸")
            painter.end()
            return

        float_y = math.sin(self._t) * 4
        target_h = height * 0.96
        target_w = pix.width() * target_h / pix.height()
        if target_w > width * 0.95:
            target_w = width * 0.95
            target_h = pix.height() * target_w / pix.width()
        x = (width - target_w) / 2
        y = (height - target_h) / 2 + float_y
        painter.drawPixmap(QRectF(x, y, target_w, target_h), pix, QRectF(pix.rect()))
        painter.end()


def mascot_pixmap(size: int = 512, animated: bool = False) -> QPixmap:
    pix = character_pixmap()
    if pix.isNull():
        canvas = QPixmap(size, size)
        canvas.fill(Qt.GlobalColor.transparent)
        return canvas
    return pix.scaledToHeight(size, Qt.TransformationMode.SmoothTransformation)


def avatar(size: int = 40) -> QPixmap:
    pix = avatar_pixmap()
    if pix.isNull():
        canvas = QPixmap(size, size)
        canvas.fill(Qt.GlobalColor.transparent)
        return canvas
    return pix.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
