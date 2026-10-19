"""设置页：自检、数据目录、导入导出、开机自启。"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import paths
from ..services import autostart, selftest_service
from ..theme import COLORS
from ..widgets.common import Card, small_button
from .base import BasePage


class SettingsPage(BasePage):
    key = "settings"
    title = "设置"
    subtitle = "自检、数据、开机自启，都在这里"

    def build(self) -> None:
        self._build_selftest()
        self._build_data()
        self._build_startup()
        self._build_danger()

    # ---------- 自检 ----------

    def _build_selftest(self) -> None:
        card = Card()
        header = QHBoxLayout()
        title = QLabel("环境自检")
        title.setObjectName("cardTitle")
        header.addWidget(title)
        self.summary = QLabel("还没跑过")
        self.summary.setObjectName("hint")
        header.addWidget(self.summary)
        header.addStretch(1)
        run = QPushButton("跑一次")
        run.setObjectName("primary")
        run.setCursor(Qt.CursorShape.PointingHandCursor)
        run.clicked.connect(self._run_checks)
        header.addWidget(run)
        card.add_layout(header)

        self.checks_box = QVBoxLayout()
        self.checks_box.setSpacing(6)
        card.add_layout(self.checks_box)
        self._run_checks()
        self.add(card)

    def _run_checks(self) -> None:
        while self.checks_box.count():
            item = self.checks_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        results = selftest_service.run_all(self.ctx.cfg.onebot.port)
        ok_count = sum(1 for item in results if item["ok"])
        self.summary.setText(f"{ok_count}/{len(results)} 通过")
        self.summary.setStyleSheet(
            f"color:{COLORS['green'] if ok_count == len(results) else COLORS['red']}; font-weight:700;"
        )
        for item in results:
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(2, 2, 2, 2)
            layout.setSpacing(10)
            dot = QLabel("✓" if item["ok"] else "✕")
            dot.setFixedWidth(18)
            dot.setStyleSheet(
                f"color:{COLORS['green'] if item['ok'] else COLORS['red']}; font-weight:800; font-size:14px;"
            )
            layout.addWidget(dot)
            name = QLabel(str(item["name"]))
            name.setFixedWidth(92)
            name.setStyleSheet(f"color:{COLORS['ink2']}; font-weight:600;")
            layout.addWidget(name)
            detail = QLabel(str(item["detail"]))
            detail.setObjectName("hint")
            detail.setWordWrap(True)
            detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(detail, 1)
            self.checks_box.addWidget(row)

    # ---------- 数据 ----------

    def _build_data(self) -> None:
        card = Card()
        title = QLabel("数据与配置")
        title.setObjectName("cardTitle")
        card.add(title)

        path_label = QLabel(str(paths.data_dir()))
        path_label.setObjectName("mono")
        path_label.setWordWrap(True)
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card.add(path_label)

        row = QHBoxLayout()
        row.setSpacing(8)
        open_dir = small_button("打开目录", "secondary")
        open_dir.clicked.connect(lambda: os.startfile(paths.data_dir()))
        row.addWidget(open_dir)
        export = small_button("导出配置", "secondary")
        export.clicked.connect(self._export)
        row.addWidget(export)
        move_dir = small_button("更改数据目录", "secondary")
        move_dir.clicked.connect(self._move_data)
        row.addWidget(move_dir)
        import_button = small_button("导入配置", "secondary")
        import_button.clicked.connect(self._import)
        row.addWidget(import_button)
        clear_memory = small_button("清空聊天记忆", "secondary")
        clear_memory.clicked.connect(self._clear_memory)
        row.addWidget(clear_memory)
        row.addStretch(1)
        card.add_layout(row)
        card.add(_hint("config.toml 里存着 API Key，导出的文件别发给别人。"))
        self.add(card)

    def _export(self) -> None:
        target, _ = QFileDialog.getSaveFileName(self, "导出配置", str(paths.data_dir() / "config.toml"), "TOML (*.toml)")
        if not target:
            return
        try:
            shutil.copyfile(paths.config_path(), target)
            self.ctx.toast("配置已导出")
        except OSError as exc:
            self.ctx.toast(f"导出失败：{exc}")

    def _import(self) -> None:
        source, _ = QFileDialog.getOpenFileName(self, "导入配置", str(paths.data_dir()), "TOML (*.toml)")
        if not source:
            return
        try:
            shutil.copyfile(source, paths.config_path())
        except OSError as exc:
            self.ctx.toast(f"导入失败：{exc}")
            return
        self.ctx.reload_config()
        self.ctx.toast("配置已导入，重启机器人后生效")

    def _move_data(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        from .. import paths

        folder = QFileDialog.getExistingDirectory(self, "选择新的数据目录", str(paths.data_dir().parent))
        if not folder:
            return
        box = QMessageBox(self)
        box.setWindowTitle("迁移数据目录")
        box.setText(f"把配置、记忆、日志和已下载的 NapCat 复制到：\n{folder}\n\n迁移完成后需要重启软件。")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        ok, message = paths.migrate_data(Path(folder))
        self.ctx.toast(message)
        if not ok:
            return
        restart = QMessageBox(self)
        restart.setWindowTitle("迁移完成")
        restart.setText("数据已迁移，是否立即重启软件？")
        restart.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if restart.exec() == QMessageBox.StandardButton.Yes:
            self.ctx.process.shutdown()
            QProcess.startDetached(sys.executable, sys.argv[1:])
            QApplication.quit()

    def _clear_memory(self) -> None:
        removed = 0
        for name in ("memory.json", "chat_memory.json"):
            path = paths.data_dir() / name
            if path.is_file():
                path.unlink()
                removed += 1
        self.ctx.toast(f"清掉 {removed} 个记忆文件" if removed else "本来就没有记忆文件")

    # ---------- 自启 ----------

    def _build_startup(self) -> None:
        card = Card()
        title = QLabel("启动")
        title.setObjectName("cardTitle")
        card.add(title)
        self.autostart_check = QCheckBox("开机自动打开 QQ Bot生成器（只启动界面，不会自动登录 QQ）")
        self.autostart_check.setChecked(autostart.is_enabled())
        self.autostart_check.toggled.connect(self._toggle_autostart)
        card.add(self.autostart_check)
        self.add(card)

    def _toggle_autostart(self, enabled: bool) -> None:
        ok, message = autostart.set_enabled(enabled)
        self.ctx.toast(message)
        if not ok:
            self.autostart_check.blockSignals(True)
            self.autostart_check.setChecked(not enabled)
            self.autostart_check.blockSignals(False)

    # ---------- 危险区 ----------

    def _build_danger(self) -> None:
        card = Card(soft=True)
        title = QLabel("危险操作")
        title.setObjectName("cardTitle")
        card.add(title)
        row = QHBoxLayout()
        reset = QPushButton("恢复默认配置")
        reset.setObjectName("danger")
        reset.setFixedWidth(150)
        reset.setCursor(Qt.CursorShape.PointingHandCursor)
        reset.clicked.connect(self._reset_config)
        row.addWidget(reset)
        hint = _hint("会删掉 config.toml 并重建默认配置，Key 和自定义都会丢。")
        hint.setWordWrap(True)
        row.addWidget(hint, 1)
        card.add_layout(row)
        self.add(card)

    def _reset_config(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("恢复默认配置")
        box.setText("会删除当前 config.toml 并生成默认配置，确定？")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        try:
            paths.config_path().unlink(missing_ok=True)
        except OSError as exc:
            self.ctx.toast(f"删除失败：{exc}")
            return
        self.ctx.reload_config()
        self.ctx.toast("已恢复默认配置，重启机器人后生效")


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("cardHint")
    label.setWordWrap(True)
    return label
