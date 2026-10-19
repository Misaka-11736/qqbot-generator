"""机器人页：身份、连接、聊天行为。"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..theme import COLORS
from ..widgets.common import Card, Field, small_button
from .base import BasePage


def _spin(minimum: int, maximum: int, value: int, suffix: str = "") -> QSpinBox:
    box = QSpinBox()
    box.setRange(minimum, maximum)
    box.setValue(value)
    if suffix:
        box.setSuffix(f" {suffix}")
    return box


class BotPage(BasePage):
    key = "bot"
    title = "机器人"
    subtitle = "名字、管理员和聊天节奏，改完记得保存"

    def build(self) -> None:
        self._build_identity()
        self._build_scope()
        self._build_connection()
        self._build_chat()
        self._build_actions()
        self.load()

    # ---------- 身份 ----------

    def _build_identity(self) -> None:
        card = Card()
        title = QLabel("身份")
        title.setObjectName("cardTitle")
        card.add(title)
        card.add(_hint("机器人叫什么、谁能管它。"))

        row = QGridLayout()
        row.setHorizontalSpacing(16)
        row.setVerticalSpacing(14)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("小鲸")
        row.addWidget(Field("机器人名字", self.name_edit, "会出现在它自称和提示词里"), 0, 0)

        self.admin_edit = QLineEdit()
        self.admin_edit.setPlaceholderText("你自己的 QQ 号，多个用逗号隔开")
        row.addWidget(Field("管理员 QQ", self.admin_edit, "填你本人的号，不是机器人登录的小号"), 0, 1)
        card.add_layout(row)
        self.add(card)

    # ---------- 作用域 ----------

    def _build_scope(self) -> None:
        card = Card()
        title = QLabel("作用域")
        title.setObjectName("cardTitle")
        card.add(title)
        card.add(_hint("决定它在哪些聊天里出现。群号填数字，多个用逗号或空格隔开。"))

        toggles = QHBoxLayout()
        toggles.setSpacing(24)
        self.private_check = QCheckBox("响应私聊")
        self.group_check = QCheckBox("响应群聊")
        toggles.addWidget(self.private_check)
        toggles.addWidget(self.group_check)
        toggles.addStretch(1)
        card.add_layout(toggles)

        row = QGridLayout()
        row.setHorizontalSpacing(16)
        row.setVerticalSpacing(14)
        self.scope_combo = QComboBox()
        self.scope_combo.addItem("所有群", "all")
        self.scope_combo.addItem("仅白名单里的群", "whitelist")
        self.scope_combo.addItem("排除黑名单里的群", "blacklist")
        row.addWidget(Field("群范围", self.scope_combo), 0, 0)
        self.group_edit = QLineEdit()
        self.group_edit.setPlaceholderText("例如：123456789 987654321")
        row.addWidget(Field("群号列表", self.group_edit, "白名单/黑名单生效时才会用到"), 0, 1)
        self.ignore_edit = QLineEdit()
        self.ignore_edit.setPlaceholderText("不想理的 QQ，多个用逗号隔开")
        row.addWidget(Field("忽略的用户", self.ignore_edit), 1, 0, 1, 2)
        card.add_layout(row)
        self.add(card)

    # ---------- 连接 ----------

    def _build_connection(self) -> None:
        card = Card()
        title = QLabel("接入方式")
        title.setObjectName("cardTitle")
        card.add(title)
        card.add(_hint("默认反向：机器人先监听端口，NapCat 主动连过来。"))

        row = QGridLayout()
        row.setHorizontalSpacing(16)
        row.setVerticalSpacing(14)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("反向 WebSocket（推荐）", "reverse")
        self.mode_combo.addItem("正向 WebSocket", "forward")
        row.addWidget(Field("模式", self.mode_combo, "反向：NapCat 连机器人"), 0, 0)

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("127.0.0.1")
        row.addWidget(Field("主机", self.host_edit), 0, 1)

        self.port_spin = _spin(1, 65535, 3002)
        row.addWidget(Field("端口", self.port_spin, "要和 NapCat 里填的一致"), 1, 0)

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("/onebot/v11/ws")
        row.addWidget(Field("路径", self.path_edit), 1, 1)

        self.token_edit = QLineEdit()
        self.token_edit.setPlaceholderText("本机自用可留空")
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        row.addWidget(Field("Token", self.token_edit, "和 NapCat 里的 Token 一致"), 2, 0, 1, 2)
        card.add_layout(row)
        self.add(card)

    # ---------- 聊天 ----------

    def _build_chat(self) -> None:
        card = Card()
        title = QLabel("聊天行为")
        title.setObjectName("cardTitle")
        card.add(title)
        card.add(_hint("控制它多爱说话、记得多少、多久回一次。"))

        row = QGridLayout()
        row.setHorizontalSpacing(16)
        row.setVerticalSpacing(14)

        prob_box = QWidget()
        prob_layout = QHBoxLayout(prob_box)
        prob_layout.setContentsMargins(0, 0, 0, 0)
        from PySide6.QtWidgets import QSlider

        self.prob_slider = QSlider(Qt.Orientation.Horizontal)
        self.prob_slider.setRange(0, 100)
        self.prob_slider.setValue(6)
        self.prob_value = QLabel("6%")
        self.prob_value.setFixedWidth(44)
        self.prob_value.setStyleSheet(f"color:{COLORS['coral_dark']}; font-weight:700;")
        self.prob_slider.valueChanged.connect(lambda v: self.prob_value.setText(f"{v}%"))
        prob_layout.addWidget(self.prob_slider, 1)
        prob_layout.addWidget(self.prob_value)
        row.addWidget(Field("群里主动搭话概率", prob_box, "没被 @ 时插话的几率，0 = 只在被叫时开口"), 0, 0)

        self.cooldown_spin = _spin(0, 3600, 90, "秒")
        row.addWidget(Field("搭话冷却", self.cooldown_spin, "同一群两次主动说话的最小间隔"), 0, 1)

        self.turns_spin = _spin(1, 40, 12, "轮")
        row.addWidget(Field("上下文轮数", self.turns_spin, "带多少轮历史给模型，越大越贵"), 1, 0)

        self.rate_spin = _spin(1, 100, 8, "次/分")
        row.addWidget(Field("每人限流", self.rate_spin), 1, 1)

        self.chars_spin = _spin(60, 2000, 300, "字")
        row.addWidget(Field("单条最长", self.chars_spin, "超过会拆段或截断"), 2, 0)

        toggles = QWidget()
        toggle_layout = QVBoxLayout(toggles)
        toggle_layout.setContentsMargins(0, 0, 0, 0)
        toggle_layout.setSpacing(8)
        self.delay_check = QCheckBox("模拟打字延迟")
        self.quote_check = QCheckBox("回复时引用原消息")
        toggle_layout.addWidget(self.delay_check)
        toggle_layout.addWidget(self.quote_check)
        row.addWidget(Field("小动作", toggles), 2, 1)
        card.add_layout(row)
        self.add(card)

    # ---------- 底部 ----------

    def _build_actions(self) -> None:
        bar = QFrame()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(30, 10, 30, 14)
        layout.setSpacing(10)
        hint = QLabel("改完点保存；正在运行时可以顺手重启。")
        hint.setObjectName("hint")
        layout.addWidget(hint)
        layout.addStretch(1)

        revert = small_button("撤销修改", "ghost")
        revert.clicked.connect(self.load)
        layout.addWidget(revert)

        save = QPushButton("保存配置")
        save.setObjectName("primary")
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.clicked.connect(self.save)
        layout.addWidget(save)

        self.restart_button = QPushButton("保存并重启")
        self.restart_button.setObjectName("secondary")
        self.restart_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.restart_button.clicked.connect(self.save_and_restart)
        layout.addWidget(self.restart_button)
        self.set_footer(bar)

    # ---------- 数据 ----------

    def load(self) -> None:
        cfg = self.ctx.cfg
        self.name_edit.setText(cfg.bot_name)
        self.admin_edit.setText("、".join(str(q) for q in cfg.admin_qq))
        index = self.mode_combo.findData(cfg.onebot.mode)
        self.mode_combo.setCurrentIndex(max(index, 0))
        self.host_edit.setText(cfg.onebot.host)
        self.port_spin.setValue(cfg.onebot.port)
        self.path_edit.setText(cfg.onebot.path)
        self.token_edit.setText(cfg.onebot.access_token)
        self.prob_slider.setValue(round(cfg.chat.group_chat_probability * 100))
        self.cooldown_spin.setValue(round(cfg.chat.group_cooldown))
        self.turns_spin.setValue(cfg.chat.context_turns)
        self.rate_spin.setValue(cfg.chat.rate_limit_per_minute)
        self.chars_spin.setValue(cfg.chat.max_reply_chars)
        self.delay_check.setChecked(cfg.chat.reply_delay)
        self.quote_check.setChecked(cfg.chat.quote_reply)
        self.private_check.setChecked(cfg.chat.enable_private)
        self.group_check.setChecked(cfg.chat.enable_group)
        idx = self.scope_combo.findData(cfg.chat.group_scope)
        self.scope_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.group_edit.setText("、".join(str(x) for x in cfg.chat.group_list))
        self.ignore_edit.setText("、".join(str(x) for x in cfg.chat.ignore_qq))
        self.restart_button.setVisible(self.ctx.process.running)

    def _collect(self) -> bool:
        cfg = self.ctx.cfg
        name = self.name_edit.text().strip()
        if not name:
            self.ctx.toast("机器人名字不能为空")
            return False
        admins = [int(x) for x in re.findall(r"\d{5,12}", self.admin_edit.text())]
        cfg.bot_name = name
        cfg.admin_qq = admins
        cfg.onebot.mode = self.mode_combo.currentData()
        cfg.onebot.host = self.host_edit.text().strip() or "127.0.0.1"
        cfg.onebot.port = self.port_spin.value()
        cfg.onebot.path = self.path_edit.text().strip() or "/onebot/v11/ws"
        cfg.onebot.access_token = self.token_edit.text()
        cfg.chat.group_chat_probability = self.prob_slider.value() / 100.0
        cfg.chat.group_cooldown = float(self.cooldown_spin.value())
        cfg.chat.context_turns = self.turns_spin.value()
        cfg.chat.rate_limit_per_minute = self.rate_spin.value()
        cfg.chat.max_reply_chars = self.chars_spin.value()
        cfg.chat.reply_delay = self.delay_check.isChecked()
        cfg.chat.quote_reply = self.quote_check.isChecked()
        cfg.chat.enable_private = self.private_check.isChecked()
        cfg.chat.enable_group = self.group_check.isChecked()
        cfg.chat.group_scope = self.scope_combo.currentData()
        cfg.chat.group_list = [int(x) for x in re.findall(r"\d{5,12}", self.group_edit.text())]
        cfg.chat.ignore_qq = [int(x) for x in re.findall(r"\d{5,12}", self.ignore_edit.text())]
        return True

    def save(self) -> bool:
        if not self._collect():
            return False
        self.ctx.save_config()
        self.ctx.toast("已保存，重启机器人后生效")
        self.restart_button.setVisible(self.ctx.process.running)
        return True

    def save_and_restart(self) -> None:
        if not self.save():
            return
        if not self.ctx.process.running:
            self.ctx.process.start()
            return
        self.ctx.process.stop()
        QTimer.singleShot(1800, self.ctx.process.start)
        self.ctx.toast("正在重启机器人…")


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("cardHint")
    label.setWordWrap(True)
    return label
