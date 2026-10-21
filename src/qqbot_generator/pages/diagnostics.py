"""诊断页：检查环境、QQ/NapCat、端口、Provider 和日志，并提供可执行修复。"""

from __future__ import annotations

import webbrowser

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget

from ..services import napcat
from ..services.diagnostics import FAIL, OK, WARN, Check, Diagnostics
from ..theme import COLORS
from ..widgets.common import Card, small_button
from ..widgets.loading import BusyButton
from .base import BasePage


class DiagnosticsPage(BasePage):
    key = "diagnostics"
    title = "诊断"
    subtitle = "自动检查环境、QQ、NapCat、端口和 Provider；能安全修的给按钮"

    def build(self) -> None:
        self.diag = Diagnostics(self.ctx)
        card = Card()
        head = QHBoxLayout()
        title = QLabel("一键诊断")
        title.setObjectName("cardTitle")
        head.addWidget(title)
        head.addStretch(1)
        self.check_button = BusyButton("开始检查", "primary")
        self.check_button.clicked.connect(lambda: self.run_checks())
        head.addWidget(self.check_button)
        card.add_layout(head)
        self.summary = QLabel("还没检查。建议每次启动机器人前点一下。")
        self.summary.setObjectName("cardHint")
        self.summary.setWordWrap(True)
        card.add(self.summary)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(8)
        card.add_layout(self.rows)
        self.add(card)

    def run_checks(self, quiet: bool = False) -> None:
        self.check_button.start_busy("检查中…")
        QTimer.singleShot(120, lambda: self._finish(quiet))

    def _finish(self, quiet: bool) -> None:
        while self.rows.count():
            item = self.rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        checks = self.diag.run()
        fails = sum(1 for c in checks if c.status == FAIL)
        warns = sum(1 for c in checks if c.status == WARN)
        for check in checks:
            self._add_row(check)
        self.check_button.stop_busy()
        self.summary.setText(
            f"通过 {sum(1 for c in checks if c.status == OK)} 项，警告 {warns} 项，失败 {fails} 项。"
            + (" 绿色项不用管，黄色/红色项按右侧按钮处理。" if fails or warns else " 当前环境正常。")
        )
        if quiet and (fails or warns):
            self.ctx.toast(f"诊断发现 {fails} 个失败、{warns} 个警告，去「诊断」页看看")

    def _add_row(self, check: Check) -> None:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        color = {OK: COLORS["green"], WARN: COLORS["yellow"], FAIL: COLORS["red"]}.get(check.status, COLORS["muted"])
        badge = QLabel({"ok": "通过", "warn": "警告", "fail": "失败"}.get(check.status, check.status))
        badge.setStyleSheet(f"color:{color}; font-weight:600; min-width:36px;")
        layout.addWidget(badge)
        text = QLabel(f"<b>{check.title}</b>　{check.detail}")
        text.setWordWrap(True)
        text.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(text, 1)
        if check.action:
            button = small_button(check.action_label or "修复", "secondary")
            button.clicked.connect(lambda _=False, c=check: self._action(c))
            layout.addWidget(button)
        self.rows.addWidget(row)

    def _action(self, check: Check) -> None:
        action = check.action
        if action == "copy_loader":
            folder = self.diag.folder()
            if folder is None:
                self.ctx.toast("没找到 NapCat 目录")
                return
            if QMessageBox.question(
                self,
                "复制 loadNapCat.js",
                "这会弹一次 UAC，把 loadNapCat.js 复制到 QQ 版本目录。\n不会重启 QQ；复制后需要你手动重启 NapCat。继续？",
            ) != QMessageBox.StandardButton.Yes:
                return
            ok, message = napcat.install_loader(folder)
            self.ctx.toast(message)
            if ok:
                self.run_checks()
            return
        if action == "create_dirs":
            self.diag.auto_fix_safe()
            self.run_checks()
            return
        if action == "start_bot":
            self.ctx.process.start()
            QTimer.singleShot(1800, self.run_checks)
            return
        if action == "restart_bot":
            if self.ctx.process.running:
                self.ctx.process.stop()
            QTimer.singleShot(1200, self.ctx.process.start)
            QTimer.singleShot(2500, self.run_checks)
            return
        if action == "open_download":
            webbrowser.open("https://github.com/NapNeko/NapCatQQ/releases")
            return
        pages = {
            "open_napcat": "napcat",
            "open_model": "model",
            "open_capabilities": "capabilities",
            "open_logs": "logs",
        }
        if action in pages:
            self.ctx.open_page(pages[action])
