"""试聊页：不登录 QQ，直接和机器人对线。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..services.chat_session import ChatSession
from ..theme import COLORS
from ..widgets.common import Card, small_button
from ..widgets.mascot import avatar
from .base import BasePage


class Bubble(QWidget):
    def __init__(self, text: str, mine: bool, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        body = QFrame()
        body.setObjectName("bubbleMine" if mine else "bubbleBot")
        body.setMaximumWidth(560)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(14, 9, 14, 10)
        body_layout.setSpacing(2)
        name = QLabel("你" if mine else "小鲸鱼")
        name.setObjectName("bubbleNameMine" if mine else "bubbleName")
        body_layout.addWidget(name)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName("bubbleTextMine" if mine else "bubbleText")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body_layout.addWidget(label)

        # 让气泡宽度跟着文字走，短句不会被挤成一条竖线
        from PySide6.QtGui import QFontMetrics

        metrics = QFontMetrics(label.font())
        longest = max((metrics.horizontalAdvance(line) for line in text.splitlines()), default=0)
        body.setFixedWidth(min(540, max(210, longest + 34)))

        if mine:
            layout.addStretch(1)
            layout.addWidget(body)
        else:
            face = QLabel()
            face.setPixmap(avatar(34))
            face.setFixedSize(34, 34)
            layout.addWidget(face, 0, Qt.AlignmentFlag.AlignTop)
            layout.addWidget(body)
            layout.addStretch(1)


class ChatPage(BasePage):
    key = "chat"
    title = "试聊"
    subtitle = "不用登录 QQ，先在这里把它聊服"
    fill = True

    def build(self) -> None:
        self.session: ChatSession | None = None
        self._build_header()
        self._build_messages()
        self._build_input()
        self.ctx.signals.config_changed.connect(self._rebuild)

    def _build_header(self) -> None:
        card = Card(soft=True, padding=14)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.model_label = QLabel("未加载")
        self.model_label.setObjectName("hint")
        row.addWidget(self.model_label)
        self.iq_label = QLabel("")
        self.iq_label.setStyleSheet(
            f"color:{COLORS['coral_dark']}; background:{COLORS['coral_soft']}; border-radius:10px;"
            "padding:3px 10px; font-size:11px; font-weight:700;"
        )
        row.addWidget(self.iq_label)
        row.addStretch(1)
        tip = QLabel("直接聊天即可；群里只保留管理员 /reset")
        tip.setObjectName("hint")
        row.addWidget(tip)
        reset = small_button("清空对话", "secondary")
        reset.clicked.connect(self._reset)
        row.addWidget(reset)
        card.add_layout(row)
        self.add(card)

    def _build_messages(self) -> None:
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setMinimumHeight(380)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self.container = QWidget()
        self.container.setStyleSheet("background:transparent;")
        self.messages = QVBoxLayout(self.container)
        self.messages.setContentsMargins(4, 4, 12, 4)
        self.messages.setSpacing(12)
        self.messages.addStretch(1)
        self.scroll.setWidget(self.container)
        self.add(self.scroll, 1)
        self._typing: QLabel | None = None

    def _build_input(self) -> None:
        card = Card(padding=12)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.input = QLineEdit()
        self.input.setPlaceholderText("说点什么…（Enter 发送）")
        self.input.returnPressed.connect(self._send)
        row.addWidget(self.input, 1)
        self.send_button = QPushButton("发送")
        self.send_button.setObjectName("primary")
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.clicked.connect(self._send)
        row.addWidget(self.send_button)
        card.add_layout(row)
        self.add(card)

    # ---------- 生命周期 ----------

    def on_show(self) -> None:
        self._ensure_session()
        self._refresh_labels()

    def _ensure_session(self) -> None:
        if self.session is None:
            self.session = ChatSession(self.ctx.cfg)
            self.session.replied.connect(self._on_reply)
            self.session.failed.connect(lambda text: self._on_reply(f"（出错：{text}）"))
            self._render_history()

    def _rebuild(self) -> None:
        if self.session is not None:
            self.session.close()
            self.session = None
        self._clear()
        self._ensure_session()
        self._refresh_labels()

    def _refresh_labels(self) -> None:
        if self.session is None:
            return
        self.model_label.setText(f"当前模型：{self.session.provider_label}")
        iq = self.session.iq()
        self.iq_label.setText(f"智商 {iq}/200")

    # ---------- 消息 ----------

    def _render_history(self) -> None:
        self._clear()
        self._add("你好，我是小鲸鱼。调低我的智商，我会觉得你顺眼很多。😊", mine=False)
        if self.session is None:
            return
        for item in self.session.history()[-8:]:
            role = item.get("role")
            text = item.get("text", "")
            if text:
                self._add(text, mine=(role == "user"))

    def _add(self, text: str, mine: bool) -> None:
        bubble = Bubble(text, mine)
        self.messages.insertWidget(self.messages.count() - 1, bubble)
        QTimer.singleShot(30, self._scroll_bottom)

    def _scroll_bottom(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _clear(self) -> None:
        while self.messages.count() > 1:
            item = self.messages.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _reset(self) -> None:
        if self.session is not None:
            self.session.reset()
        self._clear()
        self._add("行，刚才聊的我都忘了。你谁？", mine=False)
        self._refresh_labels()

    def _send(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self._ensure_session()
        self.input.clear()
        self._add(text, mine=True)
        if self.session is None:
            return
        self._show_typing()
        self.session.send(text)

    def _show_typing(self) -> None:
        self._hide_typing()
        self._typing = QLabel("小鲸鱼正在想…")
        self._typing.setStyleSheet(f"color:{COLORS['muted']}; font-size:12px; padding-left:46px;")
        self.messages.insertWidget(self.messages.count() - 1, self._typing)
        self.send_button.setEnabled(False)
        QTimer.singleShot(30, self._scroll_bottom)

    def _hide_typing(self) -> None:
        if self._typing is not None:
            self._typing.deleteLater()
            self._typing = None
        self.send_button.setEnabled(True)

    def _on_reply(self, text: str) -> None:
        self._hide_typing()
        self._add(text, mine=False)
        self._refresh_labels()
