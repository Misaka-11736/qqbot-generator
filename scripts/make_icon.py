"""生成应用图标：海军蓝圆角底 + 角色头像。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from qqbot_generator.widgets.mascot import avatar_pixmap  # noqa: E402


def build(size: int = 512) -> QPixmap:
    canvas = QPixmap(size, size)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, QColor("#1B2C55"))
    gradient.setColorAt(1.0, QColor("#3F6BD8"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(10, 10, size - 20, size - 20), size * 0.22, size * 0.22)

    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(255, 255, 255, 46), size * 0.012))
    painter.drawRoundedRect(QRectF(22, 22, size - 44, size - 44), size * 0.19, size * 0.19)

    art = avatar_pixmap()
    if not art.isNull():
        target = size * 0.74
        x = (size - target) / 2
        y = (size - target) / 2
        painter.drawPixmap(QRectF(x, y, target, target), art, QRectF(art.rect()))
    painter.end()
    return canvas


def main() -> None:
    app = QApplication(sys.argv[:1])
    assets = ROOT / "assets"
    pix = build(512)
    pix.save(str(assets / "icon.png"))

    from PIL import Image

    image = Image.open(assets / "icon.png").convert("RGBA")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    image.save(assets / "icon.ico", sizes=sizes)
    image.resize((256, 256), Image.LANCZOS).save(assets / "icon-256.png")
    print("icon written")
    app.quit()


if __name__ == "__main__":
    main()
