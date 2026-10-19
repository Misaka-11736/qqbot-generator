"""首次启动：选择数据目录（配置、记忆、日志、NapCat 下载都放这里）。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from .. import paths
from ..theme import COLORS


class DataDirDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择数据目录")
        self.setMinimumWidth(560)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(12)

        title = QLabel("把数据放在哪里？")
        title.setStyleSheet(f"color:{COLORS['ink']}; font-size:20px; font-weight:800;")
        layout.addWidget(title)

        desc = QLabel(
            "配置、聊天记忆、日志，以及从界面下载的 NapCat 都会放在这里。\n"
            "选一个空间充足的盘，之后可以在「设置」里再改（会帮你迁移）。"
        )
        desc.setWordWrap(True)
        desc.setObjectName("hint")
        layout.addWidget(desc)

        row = QHBoxLayout()
        self.path_edit = QLineEdit(str(paths.recommended_root()))
        row.addWidget(self.path_edit, 1)
        browse = QPushButton("浏览…")
        browse.setObjectName("secondary")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        layout.addLayout(row)

        tip = QLabel(f"推荐：{paths.recommended_root()}（不在 C 盘，重装系统不丢）")
        tip.setObjectName("hint")
        layout.addWidget(tip)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        use_default = QPushButton("先用默认位置")
        use_default.setObjectName("ghost")
        use_default.clicked.connect(self._use_default)
        buttons.addWidget(use_default)
        ok = QPushButton("就放这里")
        ok.setObjectName("primary")
        ok.clicked.connect(self._accept)
        buttons.addWidget(ok)
        layout.addLayout(buttons)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择数据目录", self.path_edit.text())
        if folder:
            self.path_edit.setText(folder)

    def _use_default(self) -> None:
        paths.set_data_root(paths.bootstrap_dir())
        self.accept()

    def _accept(self) -> None:
        text = self.path_edit.text().strip()
        if not text:
            return
        paths.set_data_root(Path(text))
        self.accept()
