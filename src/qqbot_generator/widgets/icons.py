"""手绘线性图标：不依赖字体/图片，保证任何机器上都能显示。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from ..theme import COLORS


def _pen(color: str, width: float = 1.8) -> QPen:
    pen = QPen(QColor(color))
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def draw_icon(painter: QPainter, name: str, color: str = COLORS["ink"], size: float = 24.0) -> None:
    """在 24x24 逻辑坐标里画图标，painter 已经缩放到目标尺寸。"""
    painter.setPen(_pen(color))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    p = painter

    if name == "home":
        p.drawPolyline([QPointF(4, 11), QPointF(12, 4), QPointF(20, 11)])
        p.drawRoundedRect(QRectF(6, 10, 12, 10), 2, 2)
        p.drawLine(QPointF(10, 20), QPointF(10, 15))
        p.drawLine(QPointF(14, 20), QPointF(14, 15))
    elif name == "bot":
        p.drawRoundedRect(QRectF(4, 8, 16, 12), 4, 4)
        p.drawLine(QPointF(12, 8), QPointF(12, 4))
        p.drawEllipse(QPointF(12, 3.2), 1.1, 1.1)
        p.setBrush(QColor(color))
        p.drawEllipse(QPointF(9, 13.5), 1.2, 1.2)
        p.drawEllipse(QPointF(15, 13.5), 1.2, 1.2)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(9, 14.5, 6, 4), 200 * 16, 140 * 16)
    elif name == "model":
        p.drawRoundedRect(QRectF(7, 7, 10, 10), 2, 2)
        for x in (9, 15):
            p.drawLine(QPointF(x, 7), QPointF(x, 4))
            p.drawLine(QPointF(x, 17), QPointF(x, 20))
        for y in (9, 15):
            p.drawLine(QPointF(7, y), QPointF(4, y))
            p.drawLine(QPointF(17, y), QPointF(20, y))
    elif name == "persona":
        p.drawEllipse(QRectF(4, 4, 16, 16))
        p.setBrush(QColor(color))
        p.drawEllipse(QPointF(9, 10), 1.0, 1.0)
        p.drawEllipse(QPointF(15, 10), 1.0, 1.0)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(8, 11, 8, 6), 200 * 16, 140 * 16)
    elif name == "plug":
        p.drawRoundedRect(QRectF(9, 10, 6, 7), 2, 2)
        p.drawLine(QPointF(10, 10), QPointF(10, 6))
        p.drawLine(QPointF(14, 10), QPointF(14, 6))
        p.drawLine(QPointF(12, 17), QPointF(12, 21))
    elif name == "chat":
        path = QPainterPath()
        path.addRoundedRect(QRectF(3, 4, 18, 13), 5, 5)
        p.drawPath(path)
        p.drawPolyline([QPointF(8, 17), QPointF(7, 21), QPointF(12, 17)])
        p.drawLine(QPointF(8, 10.5), QPointF(16, 10.5))
    elif name == "terminal":
        p.drawRoundedRect(QRectF(3, 4, 18, 16), 3, 3)
        p.drawPolyline([QPointF(7, 9), QPointF(10, 12), QPointF(7, 15)])
        p.drawLine(QPointF(12.5, 16), QPointF(17, 16))
    elif name == "info":
        p.drawEllipse(QRectF(4, 4, 16, 16))
        p.setBrush(QColor(color))
        p.drawEllipse(QPointF(12, 8), 1.0, 1.0)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(12, 11), QPointF(12, 17))
    elif name == "gear":
        p.drawEllipse(QRectF(8, 8, 8, 8))
        import math

        for i in range(8):
            ang = math.radians(i * 45)
            x1, y1 = 12 + 7 * math.cos(ang), 12 + 7 * math.sin(ang)
            x2, y2 = 12 + 9.4 * math.cos(ang), 12 + 9.4 * math.sin(ang)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    elif name == "play":
        p.setBrush(QColor(color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon([QPointF(8, 5), QPointF(19, 12), QPointF(8, 19)])
    elif name == "stop":
        p.setBrush(QColor(color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(7, 7, 10, 10), 2, 2)
    elif name == "refresh":
        p.drawArc(QRectF(5, 5, 14, 14), 40 * 16, 280 * 16)
        p.drawPolyline([QPointF(16, 3), QPointF(19.5, 7), QPointF(14.5, 8)])
    elif name == "folder":
        p.drawPolyline([QPointF(3, 18), QPointF(3, 6), QPointF(9, 6), QPointF(11, 9), QPointF(21, 9)])
        p.drawLine(QPointF(21, 9), QPointF(21, 18))
        p.drawLine(QPointF(3, 18), QPointF(21, 18))
    elif name == "download":
        p.drawLine(QPointF(12, 4), QPointF(12, 15))
        p.drawPolyline([QPointF(7, 10), QPointF(12, 15), QPointF(17, 10)])
        p.drawPolyline([QPointF(4, 17), QPointF(4, 20), QPointF(20, 20), QPointF(20, 17)])
    elif name == "external":
        p.drawRoundedRect(QRectF(4, 6, 12, 12), 2, 2)
        p.drawLine(QPointF(13, 11), QPointF(20, 4))
        p.drawPolyline([QPointF(15, 4), QPointF(20, 4), QPointF(20, 9)])
    elif name == "copy":
        p.drawRoundedRect(QRectF(8, 8, 11, 11), 2, 2)
        p.drawPolyline([QPointF(16, 8), QPointF(16, 5), QPointF(5, 5), QPointF(5, 16), QPointF(8, 16)])
    elif name == "trash":
        p.drawLine(QPointF(4, 7), QPointF(20, 7))
        p.drawPolyline([QPointF(9, 7), QPointF(9, 4), QPointF(15, 4), QPointF(15, 7)])
        p.drawPolyline([QPointF(6, 7), QPointF(7, 20), QPointF(17, 20), QPointF(18, 7)])
    elif name == "check":
        p.drawPolyline([QPointF(5, 12), QPointF(10, 17), QPointF(19, 6)])
    elif name == "close":
        p.drawLine(QPointF(6, 6), QPointF(18, 18))
        p.drawLine(QPointF(18, 6), QPointF(6, 18))
    elif name == "fish":
        path = QPainterPath()
        path.moveTo(4, 12)
        path.cubicTo(8, 4, 18, 4, 21, 12)
        path.cubicTo(18, 20, 8, 20, 4, 12)
        p.drawPath(path)
        p.drawPolyline([QPointF(4, 12), QPointF(1.5, 8), QPointF(1.5, 16), QPointF(4, 12)])
        p.setBrush(QColor(color))
        p.drawEllipse(QPointF(16, 10), 1.1, 1.1)
    else:
        p.drawEllipse(QRectF(5, 5, 14, 14))


def icon(name: str, color: str = COLORS["ink"], size: int = 20) -> QIcon:
    scale = 2
    pix = QPixmap(size * scale, size * scale)
    pix.setDevicePixelRatio(scale)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale(size / 24.0, size / 24.0)
    draw_icon(painter, name, color, 24.0)
    painter.end()
    return QIcon(pix)


class IconLabel:
    """给需要直接画图标的自定义控件用。"""

    @staticmethod
    def paint(painter: QPainter, name: str, rect: QRectF, color: str = COLORS["ink"]) -> None:
        painter.save()
        painter.translate(rect.topLeft())
        side = min(rect.width(), rect.height())
        painter.scale(side / 24.0, side / 24.0)
        draw_icon(painter, name, color, 24.0)
        painter.restore()
