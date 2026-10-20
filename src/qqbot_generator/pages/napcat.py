"""NapCat 页：定位安装、写连接配置、启动、下载。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from ..services import napcat
from ..services.ui_settings import UiSettings
from ..theme import COLORS
from ..widgets.common import Card, small_button
from ..widgets.napcat_console import NapCatConsole
from .base import BasePage


class _Signals(QObject):
    progress = Signal(int, int)
    done = Signal(bool, str, str)  # ok, message, folder


class _Downloader(QRunnable):
    def __init__(self, dest_root: Path):
        super().__init__()
        self.dest_root = dest_root
        self.signals = _Signals()

    def run(self) -> None:
        try:
            zip_path = self.dest_root / "NapCat.Shell.zip"
            self.signals.progress.emit(0, 0)
            napcat.download(napcat.DOWNLOAD_URL, zip_path, lambda done, total: self.signals.progress.emit(done, total))
            folder = napcat.extract(zip_path, self.dest_root)
            self.signals.done.emit(True, "下载并解压完成", str(folder))
        except Exception as exc:
            self.signals.done.emit(False, f"下载失败：{exc}", "")


class NapCatPage(BasePage):
    key = "napcat"
    title = "NapCat"
    subtitle = "QQ 和机器人的中间人：登录、转发消息、维持连接"

    def build(self) -> None:
        self.ui = UiSettings()
        self._build_status()
        self._build_actions()
        self._build_steps()
        self.console = NapCatConsole(self.ctx)
        self.add(self.console)
        self.on_show()

    def _build_status(self) -> None:
        card = Card()
        header = QHBoxLayout()
        title = QLabel("安装位置")
        title.setObjectName("cardTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.status = QLabel("未检测")
        self.status.setStyleSheet(f"color:{COLORS['muted']};")
        header.addWidget(self.status)
        card.add_layout(header)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(r"例如 D:\QQ Bot\NapCat\app")
        row.addWidget(self.path_edit, 1)
        detect = small_button("自动检测", "secondary")
        detect.clicked.connect(self._detect)
        row.addWidget(detect)
        browse = small_button("浏览…", "secondary")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        card.add_layout(row)
        card.add(_hint("目录里要有 launcher.bat（Shell 版）或 napcat.bat（一键版）。"))
        self.add(card)

    def _build_actions(self) -> None:
        card = Card()
        title = QLabel("操作")
        title.setObjectName("cardTitle")
        card.add(title)

        row = QHBoxLayout()
        row.setSpacing(10)
        primary = QPushButton("配置连接")
        primary.setObjectName("primary")
        primary.setCursor(Qt.CursorShape.PointingHandCursor)
        primary.clicked.connect(self._configure)
        row.addWidget(primary)

        launch = QPushButton("启动 NapCat")
        launch.setObjectName("secondary")
        launch.setCursor(Qt.CursorShape.PointingHandCursor)
        launch.clicked.connect(self._launch)
        row.addWidget(launch)

        visible = QPushButton("显示窗口启动")
        visible.setObjectName("ghost")
        visible.clicked.connect(self._launch_visible)
        row.addWidget(visible)

        webui = QPushButton("打开 WebUI")
        webui.setObjectName("secondary")
        webui.setCursor(Qt.CursorShape.PointingHandCursor)
        webui.clicked.connect(lambda: napcat.open_webui())
        row.addWidget(webui)
        row.addStretch(1)
        card.add_layout(row)

        download_row = QHBoxLayout()
        download_row.setSpacing(10)
        self.download_button = QPushButton("下载 NapCat（约 36 MB）")
        self.download_button.setObjectName("secondary")
        self.download_button.setFixedWidth(240)
        self.download_button.clicked.connect(self._download)
        download_row.addWidget(self.download_button)
        download_row.addStretch(1)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(True)
        self.progress.setFixedHeight(10)
        download_row.addWidget(self.progress, 1)
        card.add_layout(download_row)
        card.add(_hint("下载的是 NapCat v4.18.38 Shell 包，解压到数据目录，不碰你现有的 QQ。"))

        self.detail = QLabel("")
        self.detail.setObjectName("hint")
        self.detail.setWordWrap(True)
        card.add(self.detail)
        self.add(card)

    def _build_steps(self) -> None:
        card = Card(soft=True)
        title = QLabel("第一次用，按这个顺序")
        title.setObjectName("cardTitle")
        card.add(title)
        steps = [
            ("配置连接", "把 OneBot 地址写进 NapCat 的 config，指向本机器人"),
            ("启动 NapCat", "会请求管理员权限，然后拉起 QQ"),
            ("扫码登录", "用登录着小号的手机扫码；WebUI 地址在本机 6099 端口"),
            ("回到首页启动", "机器人日志出现「NapCat 已接入」就通了"),
        ]
        for index, (head, hint) in enumerate(steps, 1):
            row = QHBoxLayout()
            row.setSpacing(10)
            badge = QLabel(str(index))
            badge.setFixedSize(22, 22)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(
                f"background:#FFFFFF; color:{COLORS['coral_dark']}; border-radius:11px; font-weight:800; font-size:11px;"
            )
            row.addWidget(badge)
            text = QVBoxLayout()
            text.setSpacing(0)
            head_label = QLabel(head)
            head_label.setStyleSheet(f"color:{COLORS['ink']}; font-weight:700;")
            text.addWidget(head_label)
            hint_label = QLabel(hint)
            hint_label.setObjectName("hint")
            hint_label.setWordWrap(True)
            text.addWidget(hint_label)
            row.addLayout(text, 1)
            card.add_layout(row)
        self.add(card)

    # ---------- 状态 ----------

    def on_show(self) -> None:
        if not self.path_edit.text().strip():
            saved = self.ui.get("napcat_dir")
            found = napcat.find_candidates([saved])
            if found:
                self.path_edit.setText(str(found[0]))
        self.console.autofill()
        self._refresh()

    def _refresh(self) -> None:
        path = Path(self.path_edit.text().strip()) if self.path_edit.text().strip() else None
        if path and napcat.is_install(path):
            self.status.setText("已找到")
            self.status.setStyleSheet(f"color:{COLORS['green']}; font-weight:600;")
            port = self.ctx.cfg.onebot.port
            urls = napcat.read_client_urls(path)
            bad = [u for _f, u in urls if f":{port}/" not in u]
            if bad:
                self.detail.setText(
                    f"⚠ 端口不一致：机器人 {port}，NapCat 有 {len(bad)} 份配置指向 {bad[0]}；点「配置连接」一键修正"
                )
                self.detail.setStyleSheet(f"color:{COLORS['red']}; font-weight:600;")
            else:
                self.detail.setText(f"将写入：{path / 'config' / 'onebot11.json'}")
                self.detail.setStyleSheet("")
        else:
            self.status.setText("未检测到")
            self.status.setStyleSheet(f"color:{COLORS['muted']};")
            self.detail.setText("还没选目录。点「自动检测」，或者下载一个。")

    # ---------- 动作 ----------

    def _detect(self) -> None:
        found = napcat.find_candidates([self.ui.get("napcat_dir")])
        if not found:
            self.ctx.toast("没找到 NapCat，先下载或手动选目录")
            return
        self.path_edit.setText(str(found[0]))
        self.ui.set("napcat_dir", str(found[0]))
        self._refresh()
        self.ctx.toast(f"已找到：{found[0].name}")

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择 NapCat 目录（含 launcher.bat）")
        if not folder:
            return
        self.path_edit.setText(folder)
        if napcat.is_install(Path(folder)):
            self.ui.set("napcat_dir", folder)
            self.ctx.toast("目录已保存")
        else:
            self.ctx.toast("这个目录里没有 launcher.bat，仍可以用，但启动可能失败")
        self._refresh()

    def _folder(self) -> Path | None:
        text = self.path_edit.text().strip()
        if not text:
            self.ctx.toast("先选 NapCat 目录")
            return None
        folder = Path(text)
        if not napcat.is_install(folder):
            self.ctx.toast("目录里没有 launcher.bat / napcat.bat")
            return None
        self.ui.set("napcat_dir", str(folder))
        return folder

    def _configure(self) -> None:
        folder = self._folder()
        if folder is None:
            return
        cfg = self.ctx.cfg
        try:
            _target, updated = napcat.configure(folder, cfg.onebot.port, cfg.onebot.path, cfg.onebot.access_token)
        except OSError as exc:
            self.ctx.toast(f"写入失败：{exc}")
            return
        self.ctx.toast(f"已更新 {len(updated)} 份配置，重启 NapCat 生效")
        self.detail.setText("已写入：" + "、".join(p.name for p in updated))
        self._refresh()

    def _preflight(self, folder) -> bool:
        ok, message = napcat.check_environment(folder)
        if ok:
            return True
        from PySide6.QtWidgets import QMessageBox

        box = QMessageBox(self)
        box.setWindowTitle("无法启动 NapCat")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText("NapCat 注入文件检查未通过")
        box.setInformativeText(message)
        download = box.addButton("打开 NapCat 下载页", QMessageBox.ButtonRole.ActionRole)
        force = box.addButton("仍然启动", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is download:
            import webbrowser

            webbrowser.open("https://github.com/NapNeko/NapCatQQ/releases")
            return False
        return box.clickedButton() is force

    def _launch(self) -> None:
        folder = self._folder()
        if folder is None:
            return
        if not self._preflight(folder):
            return
        ok, message = napcat.launch_hidden(folder)
        self.ctx.toast(message)
        if ok:
            self.detail.setText("已隐藏启动，去「内置控制台」登录或扫码")

    def _launch_visible(self) -> None:
        folder = self._folder()
        if folder is None:
            return
        if not self._preflight(folder):
            return
        _ok, message = napcat.launch(folder)
        self.ctx.toast(message)

    def _download(self) -> None:
        self.download_button.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        worker = _Downloader(self.ctx.data_dir / "napcat")
        worker.signals.progress.connect(self._on_progress)
        worker.signals.done.connect(self._on_downloaded)
        QThreadPool.globalInstance().start(worker)
        self.detail.setText("正在下载，别关窗口…")

    def _on_progress(self, done: int, total: int) -> None:
        if total <= 0:
            self.progress.setRange(0, 0)
            return
        self.progress.setRange(0, 100)
        self.progress.setValue(int(done / total * 100))

    def _on_downloaded(self, ok: bool, message: str, folder: str) -> None:
        self.download_button.setEnabled(True)
        self.progress.setVisible(False)
        if not ok:
            self.detail.setText(message)
            self.ctx.toast(message)
            return
        self.path_edit.setText(folder)
        self.ui.set("napcat_dir", folder)
        self._refresh()
        cfg = self.ctx.cfg
        try:
            napcat.configure(Path(folder), cfg.onebot.port, cfg.onebot.path, cfg.onebot.access_token)
            self.detail.setText(f"下载完成并已配置：{folder}")
        except OSError:
            self.detail.setText(f"下载完成：{folder}")
        self.ctx.toast("NapCat 装好了，点「启动 NapCat」")


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("cardHint")
    label.setWordWrap(True)
    return label
