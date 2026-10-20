"""首页：吉祥物 + 一键启动 + 状态总览 + 快速入口。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..services import napcat
from ..theme import COLORS, shadow
from ..widgets.common import Card, ClickableCard, StatusPill, muted, small_button
from ..widgets.icons import icon
from ..widgets.mascot import Mascot
from .base import BasePage


class StatusCard(ClickableCard):
    def __init__(self, title: str, icon_name: str, page: str, parent: QWidget | None = None):
        super().__init__(parent, padding=18)
        self.page = page
        header = QHBoxLayout()
        header.setSpacing(8)
        badge = QLabel()
        badge.setPixmap(icon(icon_name, COLORS["ink2"], 18).pixmap(18, 18))
        header.addWidget(badge)
        name = QLabel(title)
        name.setStyleSheet(f"color:{COLORS['muted']}; font-size:12px; font-weight:600;")
        header.addWidget(name)
        header.addStretch(1)
        self.pill = StatusPill("未启动", "idle")
        header.addWidget(self.pill)
        self.add_layout(header)

        self.value = QLabel("—")
        self.value.setStyleSheet(f"color:{COLORS['ink']}; font-size:20px; font-weight:800;")
        self.add(self.value)
        self.hint = QLabel("")
        self.hint.setObjectName("hint")
        self.hint.setWordWrap(True)
        self.add(self.hint)

    def set_state(self, kind: str, text: str, value: str, hint: str) -> None:
        self.pill.set_status(kind, text)
        self.value.setText(value)
        self.hint.setText(hint)


class HomePage(BasePage):
    key = "home"
    title = "首页"
    subtitle = "所有开关都在这一页，剩下的交给小鲸鱼"

    def build(self) -> None:
        self._build_hero()
        self._build_status()
        self._build_columns()
        self._build_logs()

    # ---------- Hero ----------

    def _build_hero(self) -> None:
        hero = Card(padding=0)
        hero.setObjectName("heroCard")
        hero.setMinimumHeight(300)
        shadow(hero, radius=36, alpha=44, dy=12)
        layout = QHBoxLayout()
        layout.setContentsMargins(34, 26, 14, 16)
        layout.setSpacing(6)

        left = QVBoxLayout()
        left.setSpacing(10)

        tag = QLabel("WIN11 · 本地运行 · 数据不出门")
        tag.setStyleSheet(
            "color:#D9E6FF; background:rgba(255,255,255,0.12);"
            "border:1px solid rgba(255,255,255,0.20);"
            "border-radius:10px; padding:4px 10px; font-size:11px; font-weight:700;"
        )
        tag.setFixedHeight(24)
        tag.setMaximumWidth(280)
        tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(tag, 0, Qt.AlignmentFlag.AlignLeft)

        headline = QLabel("把 QQ 变成\n你的 AI 搭子")
        headline.setObjectName("heroTitleOnDark")
        headline.setStyleSheet("font-size:33px; font-weight:800; line-height:120%;")
        left.addWidget(headline)

        sub = QLabel("一只住在你 QQ 里的蓝鲸女仆：会怼人、会撒娇、能被你调智商。\n扫码登录小号即可开聊，不用公网 IP。")
        sub.setObjectName("heroSubOnDark")
        sub.setWordWrap(True)
        left.addWidget(sub)
        left.addSpacing(4)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.start_button = QPushButton("启动机器人")
        self.start_button.setObjectName("onDark")
        self.start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_button.setIcon(icon("play", COLORS["coral_dark"], 16))
        self.start_button.clicked.connect(self._toggle_bot)
        buttons.addWidget(self.start_button)

        chat_button = small_button("先试聊一句", "onDarkGhost", icon("chat", "#E6EFFF", 16))
        chat_button.clicked.connect(lambda: self.ctx.open_page("chat"))
        buttons.addWidget(chat_button)
        buttons.addStretch(1)
        left.addLayout(buttons)
        left.addStretch(1)

        layout.addLayout(left, 1)

        self.mascot = Mascot(size=320, animated=True)
        layout.addWidget(self.mascot, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        hero.add_layout(layout)

        self.add(hero)

    # ---------- 状态 ----------

    def _build_status(self) -> None:
        row = QHBoxLayout()
        row.setSpacing(16)
        self.bot_card = StatusCard("机器人", "bot", "bot")
        self.model_card = StatusCard("模型", "model", "model")
        self.napcat_card = StatusCard("NapCat", "plug", "napcat")
        for card in (self.bot_card, self.model_card, self.napcat_card):
            card.clicked.connect(lambda c=card: self.ctx.open_page(c.page))
            row.addWidget(card, 1)
        wrapper = QWidget()
        wrapper.setLayout(row)
        self.add(wrapper)

    # ---------- 两列 ----------

    def _build_columns(self) -> None:
        row = QHBoxLayout()
        row.setSpacing(16)

        quick = Card()
        title = QLabel("快速入口")
        title.setObjectName("cardTitle")
        quick.add(title)
        quick.add(muted("第一次用，按顺序点一遍就行。"))
        actions = QGridLayout()
        actions.setSpacing(8)
        entries = [
            ("配置 NapCat 连接", "plug", self._configure_napcat),
            ("打开 NapCat 网页", "external", self._open_webui),
            ("跑一次自检", "check", self._run_selftest),
            ("打开数据目录", "folder", self._open_data),
        ]
        for index, (text, icon_name, handler) in enumerate(entries):
            button = small_button(text, "secondary", icon(icon_name, COLORS["ink2"], 16))
            button.clicked.connect(handler)
            actions.addWidget(button, index // 2, index % 2)
        quick.add_layout(actions)
        quick.add_stretch(1)
        row.addWidget(quick, 1)

        steps = Card()
        title2 = QLabel("三步开聊")
        title2.setObjectName("cardTitle")
        steps.add(title2)
        lines = [
            ("1", "填好模型 Key", "模型页粘贴 API Key，或先用离线大脑"),
            ("2", "启动 NapCat", "NapCat 页 → 启动，扫码登录小号"),
            ("3", "@ 你的小号", "群里 @ 它，或者直接私聊"),
        ]
        for index, headline, hint in lines:
            line = QHBoxLayout()
            line.setSpacing(10)
            badge = QLabel(index)
            badge.setFixedSize(24, 24)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(
                f"background:{COLORS['coral_soft']}; color:{COLORS['coral_dark']};"
                "border-radius:12px; font-weight:800; font-size:12px;"
            )
            line.addWidget(badge)
            text = QVBoxLayout()
            text.setSpacing(1)
            head = QLabel(headline)
            head.setStyleSheet(f"color:{COLORS['ink']}; font-weight:700; font-size:13px;")
            text.addWidget(head)
            text.addWidget(muted(hint))
            line.addLayout(text, 1)
            steps.add_layout(line)
        steps.add_stretch(1)
        row.addWidget(steps, 1)

        wrapper = QWidget()
        wrapper.setLayout(row)
        self.add(wrapper)

    # ---------- 日志 ----------

    def _build_logs(self) -> None:
        card = Card()
        header = QHBoxLayout()
        title = QLabel("最近日志")
        title.setObjectName("cardTitle")
        header.addWidget(title)
        header.addStretch(1)
        more = small_button("查看全部", "ghost")
        more.clicked.connect(lambda: self.ctx.open_page("logs"))
        header.addWidget(more)
        card.add_layout(header)

        self.log_preview = QLabel("还没有日志，启动机器人后这里会滚动。")
        self.log_preview.setObjectName("mono")
        self.log_preview.setWordWrap(True)
        self.log_preview.setMinimumHeight(96)
        self.log_preview.setStyleSheet(
            f"background:{COLORS['sidebar']}; color:#C9D6EF; border-radius:12px; padding:12px;"
            'font-family:"Cascadia Mono","Consolas",monospace; font-size:11px;'
        )
        card.add(self.log_preview)
        self.add(card)

    # ---------- 刷新 ----------

    def on_show(self) -> None:
        ctx = self.ctx
        proc = ctx.process

        if proc.status == "running":
            self.start_button.setText("停止机器人")
            self.start_button.setIcon(icon("stop", "#FFFFFF", 16))
            self.bot_card.set_state("ok", "运行中", f"PID {proc.pid}", f"已运行 {proc.uptime}，端口 {ctx.cfg.onebot.port}")
        elif proc.status == "starting":
            self.start_button.setText("启动中…")
            self.bot_card.set_state("warn", "启动中", "—", "正在等端口就绪")
        elif proc.status == "stopping":
            self.start_button.setText("停止中…")
            self.bot_card.set_state("warn", "停止中", "—", "")
        else:
            self.start_button.setText("启动机器人")
            self.start_button.setIcon(icon("play", "#FFFFFF", 16))
            self.bot_card.set_state("idle", "未启动", "—", f"监听 127.0.0.1:{ctx.cfg.onebot.port}")
        self.start_button.setEnabled(proc.status not in ("starting", "stopping"))

        cfg = ctx.cfg
        if cfg.effective_provider == "mock":
            self.model_card.set_state("warn", "离线", "Mock", "没配 Key，先用模板大脑顶着")
        else:
            self.model_card.set_state("ok", "已配置", cfg.llm.model, cfg.llm.base_url.replace("https://", ""))
        found = napcat.find_candidates()
        if found:
            self.napcat_card.set_state("ok", "已找到", "就绪", str(found[0]))
        else:
            self.napcat_card.set_state("warn", "未安装", "缺失", "去 NapCat 页装一个")

        lines = ctx.logbus.read_all()[-6:]
        self.log_preview.setText("\n".join(lines) if lines else "还没有日志，启动机器人后这里会滚动。")

    # ---------- 动作 ----------

    def _toggle_bot(self) -> None:
        if self.ctx.process.running:
            self.ctx.process.stop()
        else:
            if self.ctx.process.start():
                self.ctx.toast("小鲸鱼出发了，去 NapCat 页扫码吧")
        self.on_show()

    def _configure_napcat(self) -> None:
        found = napcat.find_candidates()
        if not found:
            self.ctx.open_page("napcat")
            return
        cfg = self.ctx.cfg
        try:
            target = napcat.configure(found[0], cfg.onebot.port, cfg.onebot.path, cfg.onebot.access_token)
        except OSError as exc:
            self.ctx.toast(f"写入失败：{exc}")
            return
        self.ctx.toast("NapCat 连接已配置，重启 NapCat 生效")
        self.ctx.open_page("napcat")
        _ = target

    def _open_webui(self) -> None:
        napcat.open_webui()

    def _run_selftest(self) -> None:
        self.ctx.open_page("settings")

    def _open_data(self) -> None:
        self.ctx.config_service.open_data_dir()
