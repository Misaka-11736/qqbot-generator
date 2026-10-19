"""主窗口：无边框标题栏 + 侧栏 + 顶栏状态 + 页面栈 + 托盘。"""

from __future__ import annotations

import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from . import paths
from .context import AppContext
from .pages import PAGES
from .pages.base import BasePage
from .services.config_service import ConfigService
from .services.logbus import LogBus
from .services.process_manager import ProcessManager
from .theme import app_font, qss
from .widgets.common import StatusPill, Toast
from .widgets.mascot import mascot_pixmap
from .widgets.sidebar import Sidebar
from .widgets.titlebar import TitleBar


class _ResizeHandle(QWidget):
    def __init__(self, window, edge, cursor):
        super().__init__(window)
        self._window = window
        self._edge = edge
        self.setCursor(cursor)
        self.setStyleSheet("background: transparent;")
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

    def mousePressEvent(self, event) -> None:
        handle = self._window.windowHandle()
        if handle is not None:
            handle.startSystemResize(self._edge)
        event.accept()


class _HitTestFilter(QAbstractNativeEventFilter):
    """屏蔽 Qt/系统自带的无边框缩放热区，缩放交给 4px 手柄处理。"""

    def nativeEventFilter(self, event_type, message):
        try:
            if bytes(event_type) != b"windows_generic_MSG":
                return False, 0
            from ctypes import wintypes

            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0084:  # WM_NCHITTEST
                return True, 1  # HTCLIENT
        except Exception:
            pass
        return False, 0


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(paths.APP_TITLE)
        self.setWindowIcon(QIcon(mascot_pixmap(256)))
        self.resize(1240, 820)
        self.setMinimumSize(1080, 700)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        self.pages: dict[str, BasePage] = {}
        self._napcat_connected = False
        self._account = ""
        self._dwm_done = False

        root = QWidget()
        root.setObjectName("root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.titlebar = TitleBar(self)
        outer.addWidget(self.titlebar)

        body = QWidget()
        body.setObjectName("content")
        layout = QHBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar()
        self.sidebar.navigate.connect(self.show_page)
        layout.addWidget(self.sidebar)

        right = QFrame()
        right.setObjectName("content")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._build_header())
        self.stack = QStackedWidget()
        right_layout.addWidget(self.stack, 1)
        layout.addWidget(right, 1)
        outer.addWidget(body, 1)
        self.setCentralWidget(root)

        self._build_pages()
        self.toast = Toast(root)
        self._install_resize_borders()

        ctx.signals.toast.connect(self.toast.show_message)
        ctx.signals.config_changed.connect(self.refresh_status)
        ctx.process.changed.connect(self._on_process_changed)
        ctx.process.message.connect(self.toast.show_message)
        ctx.logbus.line.connect(self._on_log_line)

        self._build_tray()
        self._hit_filter = _HitTestFilter(self)
        QApplication.instance().installNativeEventFilter(self._hit_filter)
        self.show_page("home")
        QTimer.singleShot(300, self.refresh_status)

    # ---------- 无边框缩放 ----------

    def _install_resize_borders(self) -> None:
        from PySide6.QtCore import Qt as _Qt

        self._borders: list[tuple[QWidget, _Qt.Edge]] = []
        edges = {
            "l": _Qt.Edge.LeftEdge,
            "r": _Qt.Edge.RightEdge,
            "t": _Qt.Edge.TopEdge,
            "b": _Qt.Edge.BottomEdge,
            "tl": _Qt.Edge.LeftEdge | _Qt.Edge.TopEdge,
            "tr": _Qt.Edge.RightEdge | _Qt.Edge.TopEdge,
            "bl": _Qt.Edge.LeftEdge | _Qt.Edge.BottomEdge,
            "br": _Qt.Edge.RightEdge | _Qt.Edge.BottomEdge,
        }
        cursors = {
            "l": _Qt.CursorShape.SizeHorCursor,
            "r": _Qt.CursorShape.SizeHorCursor,
            "t": _Qt.CursorShape.SizeVerCursor,
            "b": _Qt.CursorShape.SizeVerCursor,
            "tl": _Qt.CursorShape.SizeFDiagCursor,
            "br": _Qt.CursorShape.SizeFDiagCursor,
            "tr": _Qt.CursorShape.SizeBDiagCursor,
            "bl": _Qt.CursorShape.SizeBDiagCursor,
        }
        for key, edge in edges.items():
            widget = _ResizeHandle(self, edge, cursors[key])
            self._borders.append((widget, edge))
        self._layout_borders()

    def _layout_borders(self) -> None:
        border = 4
        w, h = self.width(), self.height()
        boxes = {
            "l": (0, border, border, h - border * 2),
            "r": (w - border, border, border, h - border * 2),
            "t": (border, 0, w - border * 2, border),
            "b": (border, h - border, w - border * 2, border),
            "tl": (0, 0, border, border),
            "tr": (w - border, 0, border, border),
            "bl": (0, h - border, border, border),
            "br": (w - border, h - border, border, border),
        }
        order = ["l", "r", "t", "b", "tl", "tr", "bl", "br"]
        for (widget, _edge), key in zip(self._borders, order, strict=False):
            x, y, bw, bh = boxes[key]
            widget.setGeometry(x, y, bw, bh)
            widget.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_borders"):
            self._layout_borders()

    # ---------- 顶栏 ----------

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("header")
        header.setFixedHeight(84)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(30, 14, 30, 4)
        layout.setSpacing(12)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        self.title_label = QLabel("首页")
        self.title_label.setObjectName("pageTitle")
        self.subtitle_label = QLabel("")
        self.subtitle_label.setObjectName("pageSub")
        text_box.addWidget(self.title_label)
        text_box.addWidget(self.subtitle_label)
        layout.addLayout(text_box)
        layout.addStretch(1)

        self.bot_pill = StatusPill("未启动", "idle")
        self.model_pill = StatusPill("离线", "warn")
        self.napcat_pill = StatusPill("未连接", "idle")
        for pill in (self.bot_pill, self.model_pill, self.napcat_pill):
            layout.addWidget(pill)

        self.quick_button = QPushButton("启动")
        self.quick_button.setObjectName("primary")
        self.quick_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.quick_button.setFixedWidth(96)
        self.quick_button.clicked.connect(self._toggle_bot)
        layout.addWidget(self.quick_button)
        return header

    # ---------- 页面 ----------

    def _build_pages(self) -> None:
        for cls in PAGES:
            page = cls(self.ctx)
            self.pages[page.key] = page
            self.stack.addWidget(page)

    def show_page(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        self.title_label.setText(page.title)
        self.subtitle_label.setText(page.subtitle)
        self.sidebar.select(key)
        page.on_show()
        self.refresh_status()

    # ---------- 状态 ----------

    def refresh_status(self) -> None:
        proc = self.ctx.process
        if proc.status == "running":
            self.bot_pill.set_status("ok", "机器人运行中")
            self.quick_button.setText("停止")
        elif proc.status in ("starting", "stopping"):
            self.bot_pill.set_status("warn", "启动中" if proc.status == "starting" else "停止中")
            self.quick_button.setText("停止" if proc.status == "starting" else "…")
        else:
            self.bot_pill.set_status("idle", "未启动")
            self.quick_button.setText("启动")
        self.quick_button.setEnabled(proc.status not in ("starting", "stopping"))

        cfg = self.ctx.cfg
        if cfg.effective_provider == "mock":
            self.model_pill.set_status("warn", "离线模型")
        else:
            self.model_pill.set_status("ok", cfg.llm.model)

        if self._napcat_connected:
            self.napcat_pill.set_status("ok", f"NapCat 已连{(' · ' + self._account) if self._account else ''}")
        else:
            self.napcat_pill.set_status("idle", "NapCat 未连接")

        if proc.status == "running" and self._napcat_connected:
            self.sidebar.set_status(f"小鲸在线{(' · ' + self._account) if self._account else ''}", ok=True)
        elif proc.status == "running":
            self.sidebar.set_status("机器人已启动，等 NapCat", ok=True)
        else:
            self.sidebar.set_status("服务未启动", ok=False)

    def _on_process_changed(self) -> None:
        if not self.ctx.process.running:
            self._napcat_connected = False
            self._account = ""
        self.refresh_status()
        page = self.stack.currentWidget()
        if isinstance(page, BasePage):
            page.on_show()

    def _on_log_line(self, line: str) -> None:
        if "NapCat 已接入" in line:
            self._napcat_connected = True
        elif "NapCat 连接断开" in line:
            self._napcat_connected = False
            self._account = ""
        elif "登录账号：" in line:
            self._account = line.split("登录账号：", 1)[-1].strip()
        else:
            return
        self.refresh_status()
        page = self.stack.currentWidget()
        if isinstance(page, BasePage):
            page.on_show()

    # ---------- 动作 ----------

    def _toggle_bot(self) -> None:
        if self.ctx.process.running:
            self.ctx.process.stop()
        else:
            self.ctx.process.start()
        self.refresh_status()

    # ---------- 无边框窗口 ----------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._dwm_done:
            self._dwm_done = True
            QTimer.singleShot(60, self._apply_dwm)

    def _apply_dwm(self) -> None:
        if sys.platform != "win32":
            return
        try:
            import ctypes

            hwnd = int(self.winId())
            corner = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))

        except Exception:
            pass

    def nativeEvent(self, event_type, message):
        if sys.platform == "win32" and bytes(event_type) == b"windows_generic_MSG":
            try:
                import ctypes
                from ctypes import wintypes

                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0084:  # WM_NCHITTEST
                    x = ctypes.c_short(msg.lParam & 0xFFFF).value
                    y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                    pos = self.mapFromGlobal(QPoint(x, y))
                    border = 6
                    left = pos.x() <= border
                    right = pos.x() >= self.width() - border
                    top = pos.y() <= border
                    bottom = pos.y() >= self.height() - border
                    hit = 0
                    if top and left:
                        hit = 13
                    elif top and right:
                        hit = 14
                    elif bottom and left:
                        hit = 16
                    elif bottom and right:
                        hit = 17
                    elif left:
                        hit = 10
                    elif right:
                        hit = 11
                    elif top:
                        hit = 12
                    elif bottom:
                        hit = 15
                    if hit:
                        return True, hit
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

    # ---------- 托盘 ----------

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(QIcon(mascot_pixmap(64)), self)
        self.tray.setToolTip(paths.APP_TITLE)
        menu = QMenu()
        show = QAction("显示主界面", self)
        show.triggered.connect(self._restore)
        start = QAction("启动机器人", self)
        start.triggered.connect(lambda: self.ctx.process.start())
        stop = QAction("停止机器人", self)
        stop.triggered.connect(lambda: self.ctx.process.stop())
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self._quit)
        menu.addAction(show)
        menu.addSeparator()
        menu.addAction(start)
        menu.addAction(stop)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self._restore() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None
        )
        self.tray.show()

    def _restore(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit(self) -> None:
        self.ctx.process.shutdown()
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event) -> None:
        if self.ctx.process.running:
            box = QMessageBox(self)
            box.setWindowTitle("机器人还在运行")
            box.setText("要把小鲸留在后台，还是连机器人一起关掉？")
            minimize = box.addButton("最小化到托盘", QMessageBox.ButtonRole.AcceptRole)
            quit_button = box.addButton("退出并停止", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is minimize:
                self.hide()
                self.tray.showMessage(
                    paths.APP_TITLE,
                    "小鲸还在后台待命，双击托盘图标回来。",
                    QSystemTrayIcon.MessageIcon.Information,
                    2500,
                )
                event.ignore()
                return
            if box.clickedButton() is quit_button:
                self._quit()
                return
            event.ignore()
            return
        self.tray.hide()
        event.accept()


def build_context() -> AppContext:
    config_service = ConfigService()
    process = ProcessManager(
        config_path=lambda: config_service.path,
        get_port=lambda: config_service.cfg.onebot.port,
    )
    logbus = LogBus()
    return AppContext(config_service=config_service, process=process, logbus=logbus)


def run_gui() -> int:
    app = QApplication(sys.argv[:1])
    app.setApplicationName(paths.APP_TITLE)
    app.setApplicationVersion(paths.APP_VERSION)
    app.setWindowIcon(QIcon(mascot_pixmap(256)))
    app.setStyle("Fusion")
    app.setFont(app_font(10))
    app.setStyleSheet(qss())
    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.Window, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#F7F4EC"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#22262E"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#22262E"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#FFFFFF"))
    app.setPalette(palette)

    if paths.needs_location_setup():
        from .widgets.data_dialog import DataDirDialog

        DataDirDialog().exec()

    ctx = build_context()
    window = MainWindow(ctx)
    ctx.navigate = window.show_page
    window.show()

    if "--autostart" in sys.argv:
        window.hide()
        window.tray.showMessage(
            paths.APP_TITLE, "小鲸在托盘里待命，双击图标打开。", QSystemTrayIcon.MessageIcon.Information, 2500
        )
    return app.exec()

