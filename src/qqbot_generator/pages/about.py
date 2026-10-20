"""关于页：版本、链接、致谢与免责声明。"""

from __future__ import annotations

import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout

from .. import paths
from ..theme import COLORS
from ..widgets.common import Card, small_button
from ..widgets.mascot import Mascot
from .base import BasePage

LINKS = [
    ("NapCat 文档", "https://napneko.github.io/"),
    ("NapCat 仓库", "https://github.com/NapNeko/NapCatQQ"),
    ("OneBot 11 协议", "https://github.com/botuniverse/onebot-11"),
    ("DeepSeek 开放平台", "https://platform.deepseek.com/"),
    ("Qt for Python", "https://doc.qt.io/qtforpython/"),
]


class AboutPage(BasePage):
    key = "about"
    title = "关于"
    subtitle = "一只蓝鲸女仆的自我介绍"

    def build(self) -> None:
        self._build_hero()
        self._build_links()
        self._build_credits()

    def _build_hero(self) -> None:
        card = Card(soft=True)
        card.setMaximumHeight(280)
        row = QHBoxLayout()
        row.setSpacing(22)
        row.addWidget(Mascot(size=190, animated=True), 0, Qt.AlignmentFlag.AlignVCenter)

        text = QVBoxLayout()
        text.setSpacing(6)
        text.addStretch(1)
        name = QLabel("QQ Bot生成器")
        name.setObjectName("heroTitle")
        name.setStyleSheet("font-size:30px;")
        text.addWidget(name)
        version = QLabel(f"v{paths.APP_VERSION} · Windows 11 初版 · 开源 MIT")
        version.setObjectName("hint")
        text.addWidget(version)
        desc = QLabel(
            "把小号 QQ 变成你的 AI 搭子：有人格、有记忆、能被你调智商。\n"
            "住在界面里的蓝鲸女仆叫「小鲸鱼」，界面配色参考她的海军蓝与蕾丝白。"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color:{COLORS['ink2']}; font-size:13px; line-height:160%;")
        text.addWidget(desc)
        text.addStretch(1)
        row.addLayout(text, 1)
        card.add_layout(row)
        self.add(card)

    def _build_links(self) -> None:
        card = Card()
        title = QLabel("相关链接")
        title.setObjectName("cardTitle")
        card.add(title)
        grid = QGridLayout()
        grid.setSpacing(8)
        for index, (name, url) in enumerate(LINKS):
            button = small_button(f"{name} ↗", "secondary")
            button.clicked.connect(lambda _=False, u=url: webbrowser.open(u))
            grid.addWidget(button, index // 3, index % 3)
        card.add_layout(grid)
        self.add(card)

    def _build_credits(self) -> None:
        card = Card()
        title = QLabel("致谢与免责")
        title.setObjectName("cardTitle")
        card.add(title)
        body = QLabel(
            "· 协议接入：NapCatQQ（github.com/NapNeko/NapCatQQ，MIT）与 OneBot 11 标准。\n"
            "· 界面：PySide6（LGPL）；角色立绘由项目作者提供，不随 MIT 授权。\n"
            "· 模型：任何 OpenAI 兼容接口，默认示例为 DeepSeek。\n\n"
            "本工具仅用于学习与个人娱乐。使用第三方协议登录 QQ 违反腾讯用户协议，"
            "存在被限制或封号的风险，请使用小号并自行承担后果；请勿用于骚扰、诈骗或任何违法用途。"
        )
        body.setWordWrap(True)
        body.setStyleSheet(f"color:{COLORS['ink2']}; font-size:12px; line-height:170%;")
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card.add(body)

        row = QHBoxLayout()
        open_data = small_button("打开数据目录", "ghost")
        open_data.clicked.connect(self.ctx.config_service.open_data_dir)
        row.addWidget(open_data)
        row.addStretch(1)
        card.add_layout(row)
        self.add(card)
