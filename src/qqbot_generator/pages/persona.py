"""人格页：人设编辑 + 智商调节 + 离线/在线试一句。"""

from __future__ import annotations

import asyncio

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from qqbot_core.llm import ChatLLM, MockBrain
from qqbot_core.persona import (
    PRESETS,
    build_system_prompt,
    load_preset,
    tier_of,
)

from .. import paths
from ..theme import COLORS
from ..widgets.common import Card, WheelSlider, small_button
from ..widgets.mascot import avatar
from .base import BasePage

DESCRIPTIONS = {
    "snark": "嘴硬心软，阴阳怪气但不脏",
    "soft": "温柔慢热，会接住情绪",
    "nerd": "学霸拆台，爱举例讲原理",
}


class _Signals(QObject):
    done = Signal(bool, str)


class _Preview(QRunnable):
    def __init__(self, cfg, preset_text: str, iq: int, text: str):
        super().__init__()
        self.cfg = cfg
        self.preset_text = preset_text
        self.iq = iq
        self.text = text
        self.signals = _Signals()

    def run(self) -> None:
        system = build_system_prompt(
            preset_text=self.preset_text,
            persona_label=PRESETS.get(self.cfg.persona.preset, "人格"),
            bot_name=self.cfg.bot_name,
            iq=self.iq,
            user_name="你",
            is_group=False,
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": f"你：{self.text}"}]
        try:
            if self.cfg.effective_provider == "mock":
                reply = asyncio.run(MockBrain().complete(messages, meta={"iq": self.iq}))
                self.signals.done.emit(True, "离线预览 · " + reply)
                return
            key = self.cfg.resolve_api_key()
            client = ChatLLM(self.cfg.llm.base_url, key, self.cfg.llm.model, timeout=self.cfg.llm.timeout, retries=0)
            reply = asyncio.run(client.complete(messages, temperature=self.cfg.llm.temperature, max_tokens=200, meta={"iq": self.iq}))
            self.signals.done.emit(True, reply.strip())
        except Exception as exc:
            self.signals.done.emit(False, str(exc)[:200])


class PersonaPage(BasePage):
    key = "persona"
    title = "人格"
    subtitle = "写它怎么说话，再用智商旋钮调它的态度"

    def build(self) -> None:
        self.current = self.ctx.cfg.persona.preset
        self._build_top()
        self._build_editor()
        self._build_address()
        self._build_style()
        self._build_chat()
        self._build_preview()
        self.load()

    # ---------- 上半部分 ----------

    def _build_top(self) -> None:
        row = QHBoxLayout()
        row.setSpacing(16)

        pick = Card()
        title = QLabel("三套人格")
        title.setObjectName("cardTitle")
        pick.add(title)
        self.preset_group = QButtonGroup(self)
        self.preset_buttons: dict[str, QPushButton] = {}
        self.slot_by_preset = {str(s.get("preset")): s for s in self.ctx.cfg.persona.slots}
        for key, name in PRESETS.items():
            slot = self.slot_by_preset.get(key, {})
            label = f"{str(slot.get('id', '')).upper()} · {slot.get('name', name)}"
            button = QPushButton(f"{label}\n{DESCRIPTIONS.get(key, '')} · IQ {slot.get('iq', 100)}")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(58)
            button.setStyleSheet(
                "QPushButton{text-align:left; padding:10px 14px; border-radius:12px; border:1px solid #F2E6D9;"
                "background:#FFFFFF; color:#232A38; font-size:13px;}"
                "QPushButton:hover{border-color:#4F7FE0;}"
                "QPushButton:checked{background:#E1EBFF; border:1px solid #4F7FE0; color:#355FC4; font-weight:700;}"
            )
            button.clicked.connect(lambda _=False, k=key: self._select(k))
            self.preset_group.addButton(button)
            self.preset_buttons[key] = button
            pick.add(button)
        pick.add(_hint("每套人格独立保存提示词、智商和风格；点卡切换。"))
        pick.add_stretch(1)
        row.addWidget(pick, 1)

        iq_card = Card()
        header = QHBoxLayout()
        head = QLabel("智商")
        head.setObjectName("cardTitle")
        header.addWidget(head)
        header.addStretch(1)
        self.iq_badge = QLabel("机灵")
        self.iq_badge.setStyleSheet(
            f"color:{COLORS['coral_dark']}; background:{COLORS['coral_soft']}; border-radius:10px; padding:3px 10px; font-weight:700;"
        )
        header.addWidget(self.iq_badge)
        iq_card.add_layout(header)

        self.iq_value = QLabel("100")
        self.iq_value.setStyleSheet(f"color:{COLORS['ink']}; font-size:34px; font-weight:800;")
        iq_card.add(self.iq_value)

        self.iq_bar = QLabel("100/200 · 机灵")
        self.iq_bar.setObjectName("mono")
        iq_card.add(self.iq_bar)

        self.iq_slider = WheelSlider(Qt.Orientation.Horizontal)
        self.iq_slider.setRange(1, 200)
        self.iq_slider.setValue(100)
        self.iq_slider.valueChanged.connect(self._on_iq)
        iq_card.add(self.iq_slider)

        self.iq_hint = QLabel("")
        self.iq_hint.setObjectName("hint")
        self.iq_hint.setWordWrap(True)
        iq_card.add(self.iq_hint)
        iq_card.add_stretch(1)
        row.addWidget(iq_card, 1)

        wrapper = QWidget()
        wrapper.setLayout(row)
        self.add(wrapper)

    # ---------- 编辑器 ----------

    def _build_editor(self) -> None:
        card = Card()
        header = QHBoxLayout()
        title = QLabel("人格设定")
        title.setObjectName("cardTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.file_hint = QLabel("")
        self.file_hint.setObjectName("hint")
        header.addWidget(self.file_hint)
        card.add_layout(header)
        card.add(_hint("支持 {bot_name} 占位符。保存后新消息立即生效，不用重启。"))

        self.editor = QPlainTextEdit()
        self.editor.setObjectName("editor")
        self.editor.setMinimumHeight(260)
        card.add(self.editor)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        reset = small_button("恢复默认", "ghost")
        reset.clicked.connect(self._reset_prompt)
        actions.addWidget(reset)
        actions.addStretch(1)
        save = QPushButton("保存人格")
        save.setObjectName("primary")
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.clicked.connect(self.save)
        actions.addWidget(save)
        card.add_layout(actions)
        self.add(card)

    # ---------- 试一句 ----------

    def _build_address(self) -> None:
        card = Card()
        title = QLabel("对话识别")
        title.setObjectName("cardTitle")
        card.add(title)
        card.add(_hint("判断群里的话是不是在跟它说：被 @/回复、叫它名字、接着它上一句说，才算对话。"))
        self.address_check = QCheckBox("只参与跟自己有关的对话")
        self.address_check.setChecked(self.ctx.cfg.chat.address_awareness)
        card.add(self.address_check)
        row = QGridLayout()
        row.setHorizontalSpacing(16)
        self.join_slider = WheelSlider(Qt.Orientation.Horizontal)
        self.join_slider.setRange(0, 100)
        self.join_slider.setValue(self.ctx.cfg.chat.address_threshold)
        self.join_label = QLabel("")
        self.join_label.setObjectName("hint")
        row.addWidget(QLabel("参与无关对话门槛"), 0, 0)
        row.addWidget(self.join_slider, 0, 1)
        row.addWidget(self.join_label, 0, 2)
        self.freq_slider = WheelSlider(Qt.Orientation.Horizontal)
        self.freq_slider.setRange(0, 100)
        self.freq_slider.setValue(int(self.ctx.cfg.chat.group_chat_probability * 100))
        self.freq_label = QLabel("")
        self.freq_label.setObjectName("hint")
        row.addWidget(QLabel("群聊主动搭话概率"), 1, 0)
        row.addWidget(self.freq_slider, 1, 1)
        row.addWidget(self.freq_label, 1, 2)
        card.add_layout(row)
        self.join_slider.valueChanged.connect(lambda v: self.join_label.setText(f"{v}（越高越少插话）"))
        self.freq_slider.valueChanged.connect(lambda v: self.freq_label.setText(f"{v}%"))
        self.join_label.setText(f"{self.join_slider.value()}（越高越少插话）")
        self.freq_label.setText(f"{self.freq_slider.value()}%")
        self.add(card)

    def _build_style(self) -> None:
        card = Card()
        title = QLabel("表达风格")
        title.setObjectName("cardTitle")
        card.add(title)
        card.add(_hint("这套风格属于当前人格卡，切换人格会一起切换。"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        self.tone_slider = WheelSlider(Qt.Orientation.Horizontal)
        self.tone_slider.setRange(0, 100)
        self.verbosity_slider = WheelSlider(Qt.Orientation.Horizontal)
        self.verbosity_slider.setRange(0, 100)
        self.emoji_slider = WheelSlider(Qt.Orientation.Horizontal)
        self.emoji_slider.setRange(0, 100)
        grid.addWidget(QLabel("毒舌 ←→ 温柔"), 0, 0); grid.addWidget(self.tone_slider, 0, 1)
        grid.addWidget(QLabel("简短 ←→ 详细"), 0, 2); grid.addWidget(self.verbosity_slider, 0, 3)
        grid.addWidget(QLabel("少用表情 ←→ 多用"), 1, 0); grid.addWidget(self.emoji_slider, 1, 1)
        self.phrase_edit = QLineEdit()
        self.phrase_edit.setPlaceholderText("口头禅，可留空")
        grid.addWidget(QLabel("口头禅"), 1, 2); grid.addWidget(self.phrase_edit, 1, 3)
        self.format_combo = QComboBox()
        for label, value in (("自动（按语义）", "auto"), ("总是文字", "text"), ("总是图片", "image"), ("总是语音", "voice")):
            self.format_combo.addItem(label, value)
        grid.addWidget(QLabel("回复形式"), 2, 0); grid.addWidget(self.format_combo, 2, 1)
        self.image_thr = WheelSlider(Qt.Orientation.Horizontal); self.image_thr.setRange(0, 100)
        self.voice_thr = WheelSlider(Qt.Orientation.Horizontal); self.voice_thr.setRange(0, 100)
        self.search_thr = WheelSlider(Qt.Orientation.Horizontal); self.search_thr.setRange(0, 100)
        grid.addWidget(QLabel("图片门槛"), 2, 2); grid.addWidget(self.image_thr, 2, 3)
        grid.addWidget(QLabel("语音门槛"), 3, 0); grid.addWidget(self.voice_thr, 3, 1)
        grid.addWidget(QLabel("搜索门槛"), 3, 2); grid.addWidget(self.search_thr, 3, 3)
        card.add_layout(grid)
        self.add(card)

    def _build_chat(self) -> None:
        card = Card()
        title = QLabel("聊天行为")
        title.setObjectName("cardTitle")
        card.add(title)
        card.add(_hint("控制它多爱说话、记得多少、多久回一次。"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        self.prob_slider = WheelSlider(Qt.Orientation.Horizontal); self.prob_slider.setRange(0, 100)
        self.prob_label = QLabel("6%")
        grid.addWidget(QLabel("群里主动搭话概率"), 0, 0); grid.addWidget(self.prob_slider, 0, 1); grid.addWidget(self.prob_label, 0, 2)
        self.cooldown_spin = QSpinBox(); self.cooldown_spin.setRange(0, 3600); self.cooldown_spin.setSuffix(" 秒")
        grid.addWidget(QLabel("搭话冷却"), 0, 3); grid.addWidget(self.cooldown_spin, 0, 4)
        self.turns_spin = QSpinBox(); self.turns_spin.setRange(1, 40); self.turns_spin.setSuffix(" 轮")
        grid.addWidget(QLabel("上下文轮数"), 1, 0); grid.addWidget(self.turns_spin, 1, 1)
        self.rate_spin = QSpinBox(); self.rate_spin.setRange(1, 100); self.rate_spin.setSuffix(" 次/分")
        grid.addWidget(QLabel("每人限流"), 1, 3); grid.addWidget(self.rate_spin, 1, 4)
        self.chars_spin = QSpinBox(); self.chars_spin.setRange(60, 2000); self.chars_spin.setSuffix(" 字")
        grid.addWidget(QLabel("单条最长"), 2, 0); grid.addWidget(self.chars_spin, 2, 1)
        self.delay_check = QCheckBox("模拟打字延迟")
        self.quote_check = QCheckBox("回复时引用原消息")
        grid.addWidget(self.delay_check, 2, 3); grid.addWidget(self.quote_check, 2, 4)
        card.add_layout(grid)
        self.add(card)
        self.prob_slider.valueChanged.connect(self.freq_slider.setValue)
        self.freq_slider.valueChanged.connect(self.prob_slider.setValue)

    def _build_preview(self) -> None:
        card = Card(soft=True)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.input = QLineEdit()
        self.input.setPlaceholderText("输入一句，看看它现在怎么回")
        self.input.setText("在吗")
        self.input.returnPressed.connect(self._preview)
        row.addWidget(self.input, 1)
        button = QPushButton("试一句")
        button.setObjectName("secondary")
        button.clicked.connect(self._preview)
        row.addWidget(button)
        card.add_layout(row)

        bubble_row = QHBoxLayout()
        bubble_row.setSpacing(10)
        face = QLabel()
        face.setPixmap(avatar(36))
        face.setFixedSize(36, 36)
        bubble_row.addWidget(face, 0, Qt.AlignmentFlag.AlignTop)
        self.preview = QLabel("预览会走当前模型；没配 Key 时用离线大脑，只演示语气。")
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet(
            "background:#FFFFFF; border:1px solid #F2E6D9; border-radius:12px; padding:10px 14px; color:#232A38;"
        )
        bubble_row.addWidget(self.preview, 1)
        card.add_layout(bubble_row)
        self.add(card)

    # ---------- 数据 ----------

    def on_show(self) -> None:
        self.load_iq()

    def load(self) -> None:
        self._select(self.ctx.cfg.persona.preset, load_text=False)
        self.address_check.setChecked(self.ctx.cfg.chat.address_awareness)
        self.join_slider.setValue(self.ctx.cfg.chat.address_threshold)
        self.freq_slider.setValue(int(self.ctx.cfg.chat.group_chat_probability * 100))
        f = self.ctx.cfg.features
        self.tone_slider.setValue(f.tone); self.verbosity_slider.setValue(f.verbosity); self.emoji_slider.setValue(f.emoji)
        self.phrase_edit.setText(f.catchphrase)
        idx = self.format_combo.findData(f.reply_format); self.format_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.image_thr.setValue(f.image_threshold); self.voice_thr.setValue(f.voice_threshold); self.search_thr.setValue(f.search_threshold)
        c = self.ctx.cfg.chat
        self.prob_slider.setValue(int(c.group_chat_probability * 100)); self.prob_label.setText(f"{int(c.group_chat_probability * 100)}%")
        self.prob_slider.valueChanged.connect(lambda v: self.prob_label.setText(f"{v}%"))
        self.cooldown_spin.setValue(int(c.group_cooldown)); self.turns_spin.setValue(c.context_turns)
        self.rate_spin.setValue(c.rate_limit_per_minute); self.chars_spin.setValue(c.max_reply_chars)
        self.delay_check.setChecked(c.reply_delay); self.quote_check.setChecked(c.quote_reply)
        self.iq_slider.setValue(self.ctx.cfg.persona.default_iq)
        self._select(self.ctx.cfg.persona.preset, load_text=True)
        self.load_iq()

    def load_iq(self) -> None:
        self.iq_slider.setValue(int(self.ctx.cfg.persona.default_iq))
        self._on_iq(self.iq_slider.value())

    def _slot(self) -> dict:
        for slot in self.ctx.cfg.persona.slots:
            if slot.get("preset") == self.current:
                return slot
        return self.ctx.cfg.persona.slots[0]

    def _select(self, key: str, load_text: bool = True) -> None:
        self.current = key
        self.preset_buttons[key].setChecked(True)
        slot = self._slot()
        self.iq_slider.setValue(int(slot.get("iq", 100)))
        if hasattr(self, "tone_slider"):
            self.tone_slider.setValue(int(slot.get("tone", 50)))
            self.verbosity_slider.setValue(int(slot.get("verbosity", 50)))
            self.emoji_slider.setValue(int(slot.get("emoji", 50)))
            self.phrase_edit.setText(str(slot.get("catchphrase", "")))
            idx = self.format_combo.findData(str(slot.get("reply_format", "auto")))
            self.format_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.join_slider.setValue(int(slot.get("address_threshold", 50)))
        if load_text:
            self.editor.setPlainText(load_preset(key))
            self.file_hint.setText(f"{key}.md")

    def _on_iq(self, value: int) -> None:
        tier = tier_of(value)
        self.iq_value.setText(str(value))
        self.iq_badge.setText(tier.label)
        self.iq_bar.setText(f"{value}/200 · {tier.label}")
        self.iq_hint.setText(tier.style)
        self.ctx.cfg.persona.default_iq = value
        self._slot()["iq"] = value

    def save(self) -> None:
        text = self.editor.toPlainText().strip()
        if not text:
            self.ctx.toast("人格内容不能为空")
            return
        paths.prompts_dir().mkdir(parents=True, exist_ok=True)
        (paths.prompts_dir() / f"{self.current}.md").write_text(text, "utf-8")
        self.ctx.cfg.persona.preset = self.current
        self.ctx.cfg.persona.default_iq = self.iq_slider.value()
        slot = self._slot()
        slot["iq"] = self.iq_slider.value()
        slot["preset"] = self.current
        slot["tone"] = self.tone_slider.value()
        slot["verbosity"] = self.verbosity_slider.value()
        slot["emoji"] = self.emoji_slider.value()
        slot["catchphrase"] = self.phrase_edit.text().strip()
        slot["reply_format"] = self.format_combo.currentData()
        slot["address_threshold"] = self.join_slider.value()
        self.ctx.cfg.chat.address_awareness = self.address_check.isChecked()
        self.ctx.cfg.chat.address_threshold = self.join_slider.value()
        self.ctx.cfg.chat.group_chat_probability = self.prob_slider.value() / 100
        f = self.ctx.cfg.features
        f.tone = self.tone_slider.value(); f.verbosity = self.verbosity_slider.value(); f.emoji = self.emoji_slider.value()
        f.catchphrase = self.phrase_edit.text().strip()
        f.reply_format = self.format_combo.currentData()
        f.image_threshold = self.image_thr.value(); f.voice_threshold = self.voice_thr.value(); f.search_threshold = self.search_thr.value()
        c = self.ctx.cfg.chat
        c.group_cooldown = self.cooldown_spin.value(); c.context_turns = self.turns_spin.value()
        c.rate_limit_per_minute = self.rate_spin.value(); c.max_reply_chars = self.chars_spin.value()
        c.reply_delay = self.delay_check.isChecked(); c.quote_reply = self.quote_check.isChecked()
        self.ctx.save_config()
        self.ctx.toast("人格已保存，新消息立即生效")

    def _reset_prompt(self) -> None:
        text = self.ctx.config_service.reset_prompt(self.current)
        self.editor.setPlainText(text)
        self.ctx.toast("已恢复默认内容（记得再点保存）")

    def _preview(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.preview.setText("小鲸鱼正在想…")
        worker = _Preview(self.ctx.cfg, self.editor.toPlainText(), self.iq_slider.value(), text)
        worker.signals.done.connect(self._on_preview)
        QThreadPool.globalInstance().start(worker)

    def _on_preview(self, ok: bool, text: str) -> None:
        self.preview.setText(text if ok else f"调用失败：{text}")
        self.preview.setStyleSheet(
            "background:#FFFFFF; border:1px solid #F2E6D9; border-radius:12px; padding:10px 14px;"
            + (f"color:{COLORS['text']};" if ok else f"color:{COLORS['red']};")
        )


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("cardHint")
    label.setWordWrap(True)
    return label
