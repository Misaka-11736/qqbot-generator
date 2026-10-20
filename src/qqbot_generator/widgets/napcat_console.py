"""NapCat 内置控制台：密码登录、二维码、终端、状态。"""

from __future__ import annotations

import base64
import re
from io import BytesIO

import qrcode
import socket

from PySide6.QtCore import QThread, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWebSockets import QWebSocket
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..context import AppContext
from ..services import napcat, secrets
from ..services.napcat_webui import NapCatWebUI, WebUIError
from ..services.ui_settings import UiSettings
from ..theme import COLORS
from ..widgets.common import Card, small_button
from ..widgets.loading import BusyButton, mark_refreshed

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")


class _LoginWorker(QThread):
    done = Signal(object, str, str)

    def __init__(self, candidates: list[str]):
        super().__init__()
        self.candidates = candidates

    def run(self) -> None:
        try:
            with socket.create_connection(("127.0.0.1", 6099), timeout=1.2):
                pass
        except OSError:
            self.done.emit(None, "", "连不上 127.0.0.1:6099：NapCat WebUI 没启动")
            return
        last = ""
        for candidate in self.candidates:
            client = NapCatWebUI()
            try:
                client.login(candidate)
                self.done.emit(client, candidate, "")
                return
            except WebUIError as exc:
                last = str(exc)
        self.done.emit(None, "", last or "登录失败")


class NapCatConsole(Card):
    def __init__(self, ctx: AppContext):
        super().__init__(padding=18)
        self.ctx = ctx
        self.ui = UiSettings()
        self.client = NapCatWebUI()
        self.ws: QWebSocket | None = None
        self.session_id = ""
        self._qr_tick = 0

        header = QHBoxLayout()
        title = QLabel("内置控制台")
        title.setObjectName("cardTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.state = QLabel("未连接")
        self.state.setStyleSheet(f"color:{COLORS['muted']}; font-size:12px;")
        header.addWidget(self.state)
        self.add_layout(header)
        self.add(_hint("用 NapCat WebUI 的密码登录，终端和二维码都在这里，不用开浏览器。"))

        auth = QHBoxLayout()
        auth.setSpacing(8)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("WebUI Token / 密码（通常在 webui.json，不是 QQ 密码）")
        saved = secrets.unprotect(self.ui.get("napcat_webui_pwd"))
        if saved:
            self.password.setText(saved)
        auth.addWidget(self.password, 1)
        self.connect_button = BusyButton("连接", "primary")
        self.connect_button.clicked.connect(self._connect)
        auth.addWidget(self.connect_button)
        self.add_layout(auth)

        self.tabs = QHBoxLayout()
        self.tabs.setSpacing(6)
        self.tab_buttons: list[QPushButton] = []
        for index, name in enumerate(("终端", "扫码登录")):
            button = small_button(name, "chip")
            button.setCheckable(True)
            button.clicked.connect(lambda _=False, i=index: self._show_tab(i))
            self.tab_buttons.append(button)
            self.tabs.addWidget(button)
        self.tabs.addStretch(1)
        self.add_layout(self.tabs)

        self.stack = QStackedWidget()
        self.stack.setMinimumHeight(260)
        self.stack.addWidget(self._build_terminal())
        self.stack.addWidget(self._build_qr())
        self.add(self.stack)
        self._show_tab(0)

        self.timer = QTimer(self)
        self.timer.setInterval(2500)
        self.timer.timeout.connect(self._poll)
        self.ctx.signals.config_changed.connect(self._show_tab)

    # ---------- 界面 ----------

    def _build_terminal(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.term = QPlainTextEdit()
        self.term.setObjectName("logView")
        self.term.setReadOnly(True)
        self.term.setMinimumHeight(210)
        self.term.setPlaceholderText("连接后这里会出现 NapCat 的终端输出。")
        layout.addWidget(self.term, 1)
        row = QHBoxLayout()
        self.command = QLineEdit()
        self.command.setPlaceholderText("输入命令，回车发送（例如 help）")
        self.command.returnPressed.connect(self._send_command)
        row.addWidget(self.command, 1)
        send = small_button("发送", "secondary")
        send.clicked.connect(self._send_command)
        row.addWidget(send)
        layout.addLayout(row)
        return page

    def _build_qr(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(16)
        self.qr = QLabel("连接后显示二维码")
        self.qr.setFixedSize(200, 200)
        self.qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr.setStyleSheet(f"background:{COLORS['cream2']}; border-radius:12px; color:{COLORS['muted']};")
        row.addWidget(self.qr)
        side = QVBoxLayout()
        side.setSpacing(8)
        self.login_state = QLabel("等待连接 WebUI")
        self.login_state.setWordWrap(True)
        self.login_state.setObjectName("hint")
        side.addWidget(self.login_state)
        refresh = small_button("刷新二维码", "secondary")
        refresh.clicked.connect(self._refresh_qr)
        side.addWidget(refresh)
        side.addStretch(1)
        row.addLayout(side, 1)
        layout.addLayout(row)
        layout.addWidget(_hint("二维码来自 NapCat 自身的登录接口；也可以直接扫 QQ 窗口里的码。"))
        return page

    # ---------- 动作 ----------

    def _show_tab(self, index: int = 0) -> None:
        if not isinstance(index, int):
            index = 0
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.tab_buttons):
            button.setChecked(i == index)
        if index == 1:
            self._refresh_qr()

    def _connect(self) -> None:
        password = self.password.text().strip()
        candidates = [password] if password else []
        try:
            folder = napcat.find_candidates()[0]
            token = napcat.read_webui_token(folder)
            if token and token not in candidates:
                candidates.append(token)
        except (IndexError, OSError):
            pass
        if not candidates:
            self._set_state("先填 WebUI Token", "warn")
            return
        self.connect_button.start_busy("连接中…")
        self._set_state("正在连接 127.0.0.1:6099…", "info")
        self._login_worker = _LoginWorker(candidates)
        self._login_worker.done.connect(lambda client, used, err: self._on_login(client, used, err, password))
        self._login_worker.start()

    def _on_login(self, client, used: str, error: str, password: str) -> None:
        self.connect_button.stop_busy()
        if client is None:
            self._set_state(f"连接失败：{error}", "error")
            self.login_state.setText(
                "检查：NapCat 是否在运行、6099 是否被占用；这里填 webui.json 的 token（默认 qqbot-local-2026），不是 QQ 密码。"
            )
            self.ctx.toast(f"NapCat 连接失败：{error}")
            return
        self.client = client
        self.ui.set("napcat_webui_pwd", secrets.protect(used))
        self._set_state("已连接 · 登录成功", "ok")
        mark_refreshed(self.state, "已连接 · 登录成功")
        if password and used != password:
            self.ctx.toast("已自动使用 webui.json 里的 Token 登录")
        self.password.clear()
        self._auto_quick_login()

    def _auto_quick_login(self) -> None:
        try:
            status = self.client.login_status()
        except WebUIError:
            status = {}
        if status.get("isLogin"):
            self._finish_login("已登录")
            return
        try:
            accounts = self.client.quick_login_list()
        except WebUIError:
            accounts = []
        if not accounts:
            self._set_state("没有可快速登录的账号，请扫码", "warn")
            self._refresh_qr()
            return
        account = accounts[0]
        uin = str(account.get("uin") or "")
        nick = str(account.get("nickName") or uin)
        if not uin:
            self._refresh_qr()
            return
        try:
            self.client.quick_login(uin)
        except WebUIError as exc:
            self._set_state(f"快速登录失败：{exc}", "warn")
            self._refresh_qr()
            return
        self._set_state(f"正在快速登录 {nick}…", "info")
        self._quick_ticks = 0
        self._quick_timer = QTimer(self)
        self._quick_timer.setInterval(1500)
        self._quick_timer.timeout.connect(lambda: self._poll_quick_login(nick))
        self._quick_timer.start()

    def _poll_quick_login(self, nick: str) -> None:
        self._quick_ticks += 1
        try:
            status = self.client.login_status()
        except WebUIError:
            status = {}
        if status.get("isLogin"):
            self._quick_timer.stop()
            self._finish_login(f"已快速登录 {nick}")
            return
        if status.get("loginError"):
            self._quick_timer.stop()
            self._set_state(f"快速登录失败：{status['loginError']}", "warn")
            self._refresh_qr()
            return
        if self._quick_ticks >= 20:
            self._quick_timer.stop()
            self._set_state("快速登录超时，请扫码", "warn")
            self._refresh_qr()

    def _finish_login(self, message: str) -> None:
        self._set_state(message, "ok")
        mark_refreshed(self.state, message)
        self._open_terminal()
        self.timer.start()
        self._poll()

    def _open_terminal(self) -> None:
        try:
            self.session_id = self.client.create_terminal()
        except WebUIError as exc:
            self.term.appendPlainText(f"创建终端失败：{exc}")
            return
        self.ws = QWebSocket()
        self.ws.textMessageReceived.connect(self._on_term)
        self.ws.connected.connect(lambda: self.term.appendPlainText("· 已连接 NapCat 终端"))
        self.ws.disconnected.connect(lambda: self.term.appendPlainText("· 终端连接已断开"))
        self.ws.errorOccurred.connect(lambda _e: self.term.appendPlainText("· 终端连接出错"))
        self.ws.open(QUrl(self.client.terminal_url(self.session_id)))

    def _on_term(self, text: str) -> None:
        self.term.appendPlainText(ANSI.sub("", text).replace("\r", ""))

    def _send_command(self) -> None:
        text = self.command.text()
        if not text or self.ws is None:
            return
        self.command.clear()
        self.ws.sendTextMessage(text + "\r")

    def _refresh_qr(self) -> None:
        if not self.client.token:
            self.qr.setText("先在上方连接")
            return
        try:
            status = self.client.login_status()
        except WebUIError:
            status = {}
        if status.get("isLogin"):
            self._show_logged_in()
            return
        url = str(status.get("qrcodeurl") or "")
        if url:
            self._render_qr(url)
            self.login_state.setText("等待扫码…（二维码每 15 秒自动刷新）")
            return
        try:
            data = self.client.qrcode() or self.client.refresh_qrcode()
        except WebUIError as exc:
            if "Logined" in str(exc):
                self._show_logged_in()
            else:
                self.qr.setText(f"获取失败\n{exc}")
            return
        pix = self._pixmap(data)
        if pix is None:
            self.qr.setText("二维码为空\n可能已经登录")
            return
        self.qr.setPixmap(pix.scaled(196, 196, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def _render_qr(self, text: str) -> None:
        image = qrcode.make(text)
        buf = BytesIO()
        image.save(buf, format="PNG")
        pix = QPixmap()
        if pix.loadFromData(buf.getvalue()):
            self.qr.setPixmap(pix.scaled(196, 196, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.qr.setText("二维码生成失败")

    def _show_logged_in(self) -> None:
        name = ""
        uin = ""
        try:
            info = self.client.login_info()
            name = str(info.get("nick") or info.get("nickName") or "")
            uin = str(info.get("uin") or info.get("user_id") or "")
        except WebUIError:
            pass
        label = f"{name}（{uin}）" if uin else "当前账号"
        self.qr.setPixmap(QPixmap())
        self.qr.setText(f"已登录\n{label}\n\n无需扫码")
        self.login_state.setText(f"NapCat 已登录 {label}；要换号，请退出 QQ 后重启 NapCat，再回来扫码。")

    @staticmethod
    def _pixmap(data: str) -> QPixmap | None:
        if not data:
            return None
        raw = data.split(",", 1)[-1] if data.startswith("data:") else data
        try:
            blob = base64.b64decode(raw)
        except (ValueError, TypeError):
            return None
        pix = QPixmap()
        return pix if pix.loadFromData(blob) else None

    def _poll(self) -> None:
        if not self.client.token:
            return
        try:
            status = self.client.login_status()
            info = self.client.login_info()
        except WebUIError:
            return
        uin = str(info.get("uin") or info.get("user_id") or status.get("uin") or "")
        nick = str(info.get("nick") or info.get("nickName") or "")
        if uin:
            self.login_state.setText(f"已登录：{nick or uin}（{uin}）")
            self._set_state("已连接 · 已登录", "ok")
        else:
            self.login_state.setText("等待扫码…（二维码每 15 秒自动刷新）")
            self._qr_tick += 1
            if self._qr_tick % 6 == 0 and self.stack.currentIndex() == 1:
                self._refresh_qr()

    def _set_state(self, text: str, kind: str) -> None:
        colors = {"ok": COLORS["green"], "warn": "#A9721E", "error": COLORS["red"], "info": COLORS["coral_dark"]}
        self.state.setText(text)
        self.state.setStyleSheet(f"color:{colors.get(kind, COLORS['muted'])}; font-size:12px; font-weight:600;")


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("cardHint")
    label.setWordWrap(True)
    return label
