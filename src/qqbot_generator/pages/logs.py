"""日志页：实时跟随 logs/bot-*.log。"""

from __future__ import annotations

import os
from collections import deque

from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QWidget,
)

from .. import paths
from ..widgets.common import small_button
from .base import BasePage


class LogsPage(BasePage):
    key = "logs"
    title = "日志"
    subtitle = "机器人每一句话都记在这里，排错先看它"
    fill = True

    def build(self) -> None:
        self.lines: deque[str] = deque(maxlen=3000)
        self._loaded = False

        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.file_label = QLabel("等待日志…")
        self.file_label.setObjectName("mono")
        row.addWidget(self.file_label)
        row.addStretch(1)
        self.autoscroll = QCheckBox("自动滚动")
        self.autoscroll.setChecked(True)
        row.addWidget(self.autoscroll)
        refresh = small_button("刷新", "ghost")
        refresh.clicked.connect(self.reload)
        row.addWidget(refresh)
        clear = small_button("清空显示", "ghost")
        clear.clicked.connect(self._clear)
        row.addWidget(clear)
        open_dir = small_button("打开目录", "ghost")
        open_dir.clicked.connect(lambda: os.startfile(paths.logs_dir()))
        row.addWidget(open_dir)

        from ..widgets.common import Card

        toolbar = Card(padding=14)
        toolbar.add(bar)
        self.add(toolbar)

        self.view = QPlainTextEdit()
        self.view.setObjectName("logView")
        self.view.setReadOnly(True)
        self.view.setMinimumHeight(430)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.view.setPlaceholderText("还没有日志。回首页点「启动机器人」，这里就会开始滚动。")
        self.add(self.view, 1)
        self.ctx.logbus.line.connect(self._append)
        self.ctx.logbus.switched.connect(lambda name: self.file_label.setText(name))

    def on_show(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        lines = self.ctx.logbus.read_all()
        self.lines.clear()
        self.lines.extend(lines[-3000:])
        self.view.setPlainText("\n".join(self.lines))
        self._loaded = True
        path = self.ctx.logbus.current_file()
        self.file_label.setText(path.name if path else "还没有日志文件")
        self._scroll()

    def _clear(self) -> None:
        self.lines.clear()
        self.view.clear()

    def _append(self, line: str) -> None:
        self.lines.append(line)
        self.view.appendPlainText(line)
        if self.autoscroll.isChecked():
            self._scroll()

    def _scroll(self) -> None:
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())
