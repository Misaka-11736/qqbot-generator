"""页面基类：统一的标题、滚动区和生命周期。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from ..context import AppContext


class BasePage(QWidget):
    key = ""
    title = ""
    subtitle = ""
    fill = False  # True 表示页面里有一个需要撑满的控件（聊天区、日志区）

    def __init__(self, ctx: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.ctx = ctx
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.outer = outer

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.scroll.viewport().setAutoFillBackground(False)

        content = QWidget()
        content.setObjectName("pageBody")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(30, 6, 30, 30)
        self.body.setSpacing(18)
        self.scroll.setWidget(content)
        outer.addWidget(self.scroll)

        self.build()
        if not self.fill:
            self.body.addStretch(1)

    def build(self) -> None: ...

    def on_show(self) -> None:
        """每次切换到该页时调用，用于刷新状态。"""

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self.body.addWidget(widget, stretch)
        return widget

    def add_stretch(self) -> None:
        self.body.addStretch(1)

    def set_footer(self, widget: QWidget) -> None:
        """把操作条固定在滚动区下方，永远看得见。"""
        widget.setObjectName("footer")
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.outer.addWidget(widget)
