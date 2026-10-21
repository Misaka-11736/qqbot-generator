"""左侧导航栏：品牌、分组导航、底部版本与状态。"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import (
    QButtonGroup,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..paths import APP_VERSION
from .icons import icon

NAV_GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ("控制台", [("home", "首页", "home"), ("bot", "机器人", "bot"), ("model", "模型", "model"), ("persona", "人格", "persona"), ("capabilities", "能力", "plug")]),
    ("部署", [("napcat", "NapCat", "plug"), ("chat", "试聊", "chat"), ("logs", "日志", "terminal"), ("diagnostics", "诊断", "check"), ("review", "评审", "check")]),
    ("其他", [("tutorial", "教程", "info"), ("settings", "设置", "gear"), ("about", "关于", "info")]),
]


class Sidebar(QWidget):
    navigate = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(236)
        self._buttons: dict[str, QPushButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)

        for section, items in NAV_GROUPS:
            label = QLabel(section.upper())
            label.setObjectName("navSection")
            layout.addWidget(label)
            for key, text, icon_name in items:
                button = QPushButton(text)
                button.setObjectName("nav")
                button.setCheckable(True)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setIcon(icon(icon_name, "#AEBCD6", 18))
                button.setIconSize(QSize(18, 18))
                button.clicked.connect(lambda _=False, k=key: self.navigate.emit(k))
                self._group.addButton(button)
                self._buttons[key] = button
                layout.addWidget(button)
            layout.addSpacing(10)

        layout.addStretch(1)

        self.status = QLabel("●  服务未启动")
        self.status.setStyleSheet(
            "color:#8EA0C2; font-size:11px; padding:6px 10px; border-radius:9px; background:rgba(255,255,255,0.04);"
        )
        layout.addWidget(self.status)

        version = QLabel(f"v{APP_VERSION} · Win11 初版")
        version.setStyleSheet("color:#5E6F92; font-size:10px; padding-left:4px;")
        layout.addWidget(version)

    def select(self, key: str) -> None:
        button = self._buttons.get(key)
        if button is not None and not button.isChecked():
            button.setChecked(True)

    def set_status(self, text: str, ok: bool = False) -> None:
        color = "#5FD3A6" if ok else "#8EA0C2"
        self.status.setText(f"●  {text}")
        self.status.setStyleSheet(
            f"color:{color}; font-size:11px; padding:6px 10px; border-radius:9px; background:rgba(255,255,255,0.04);"
        )

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        w, h = self.width(), self.height()

        # 底部蓝色光晕
        glow = QLinearGradient(0, h - 150, 0, h)
        glow.setColorAt(0.0, QColor(79, 127, 224, 0))
        glow.setColorAt(1.0, QColor(79, 127, 224, 46))
        painter.setBrush(glow)
        painter.drawRect(0, h - 150, w, 150)
        painter.end()
