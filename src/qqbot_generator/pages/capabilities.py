"""能力控制台：开关、API Key、限额、风格和归档统计。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSlider,
    QSpinBox,
    QWidget,
)

from qqbot_core.archive import Archive
from qqbot_core.keyvault import get_key, set_key
from qqbot_core.providers import choices as provider_choices
from qqbot_core.providers import get as get_provider

from ..widgets.common import Card, Field, small_button
from ..widgets.loading import BusyButton, mark_refreshed
from .base import BasePage


class CapabilitiesPage(BasePage):
    key = "capabilities"
    title = "能力"
    subtitle = "每个能力独立开关；Key 只存在本机，日志自动打码"

    def build(self) -> None:
        self.archive = Archive(self.ctx.data_dir / "archive.db") if self.ctx.cfg.features.archive else None
        f = self.ctx.cfg.features

        stats = Card()
        head = QHBoxLayout()
        title = QLabel("运行概览")
        title.setObjectName("cardTitle")
        head.addWidget(title)
        head.addStretch(1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("hint")
        head.addWidget(self.count_label)
        stats.add_layout(head)
        self.tags_label = QLabel("")
        self.tags_label.setObjectName("hint")
        self.tags_label.setWordWrap(True)
        stats.add(self.tags_label)
        self.conv_label = QLabel("")
        self.conv_label.setObjectName("hint")
        self.conv_label.setWordWrap(True)
        stats.add(self.conv_label)
        self.add(stats)

        switch = Card()
        title = QLabel("能力开关")
        title.setObjectName("cardTitle")
        switch.add(title)
        switch.add(_hint("关掉后对应指令不再响应；归档关掉后 /总结 和分类都不可用。"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(10)
        self.checks: dict[str, QCheckBox] = {}
        items = [
            ("archive", "消息归档"),
            ("summarize", "群聊总结"),
            ("search", "联网搜索"),
            ("download", "文件下载"),
            ("gen_image", "生成图片"),
            ("gen_file", "生成文件"),
            ("classify", "内容分类"),
            ("vision", "图片/视频/文件"),
            ("voice_in", "语音识别"),
            ("voice_out", "语音合成"),
        ]
        for index, (name, label) in enumerate(items):
            box = QCheckBox(label)
            box.setChecked(bool(getattr(f, name)))
            self.checks[name] = box
            grid.addWidget(box, index // 4, index % 4)
        # v3.2 语音开关已并入上方网格
        switch.add_layout(grid)
        self.add(switch)
        self._build_provider_card()

        keys = Card()
        title = QLabel("API Key")
        title.setObjectName("cardTitle")
        keys.add(title)
        keys.add(_hint("Brave 用于搜索；Provider Key 在上方「API Provider」卡片填写。Key 不会写进 config.toml。"))
        row = QGridLayout()
        row.setHorizontalSpacing(16)
        row.setVerticalSpacing(12)
        self.brave_edit = QLineEdit()
        self.brave_edit.setEchoMode(QLineEdit.EchoMode.Password)
        brave_saved = bool(get_key(self.ctx.data_dir, "brave"))
        self.brave_edit.setPlaceholderText("已保存，留空则不修改" if brave_saved else "粘贴 Brave API Key")
        self.search_combo = QComboBox()
        self.search_combo.addItem("Brave（推荐）", "brave")
        self.search_combo.addItem("Tavily", "tavily")
        self.search_combo.addItem("DuckDuckGo（免费无 Key）", "duckduckgo")
        idx_search = self.search_combo.findData(f.search_provider)
        self.search_combo.setCurrentIndex(idx_search if idx_search >= 0 else 0)
        row.addWidget(Field("搜索提供商", self.search_combo), 0, 0)
        row.addWidget(Field("Brave Search Key", self.brave_edit), 0, 1)
        self.tavily_edit = QLineEdit()
        self.tavily_edit.setEchoMode(QLineEdit.EchoMode.Password)
        tavily_saved = bool(get_key(self.ctx.data_dir, "tavily"))
        self.tavily_edit.setPlaceholderText("已保存，留空则不修改" if tavily_saved else "Tavily API Key（可选）")
        row.addWidget(Field("Tavily Key", self.tavily_edit), 1, 0)
        self.voice_combo = QComboBox()
        self.voice_combo.addItems(["small", "base", "tiny"])
        idx_voice = self.voice_combo.findText(f.voice_model)
        if idx_voice >= 0:
            self.voice_combo.setCurrentIndex(idx_voice)
        self.search_limit = QSpinBox()
        self.search_limit.setRange(1, 500)
        self.search_limit.setValue(f.search_daily_limit)
        row.addWidget(Field("搜索每日上限", self.search_limit), 1, 1)
        self.download_limit = QSpinBox()
        self.download_limit.setRange(1, 200)
        self.download_limit.setValue(f.download_max_mb)
        self.download_limit.setSuffix(" MB")
        row.addWidget(Field("单文件下载上限", self.download_limit), 3, 0)
        self.summary_limit = QSpinBox()
        self.summary_limit.setRange(50, 1000)
        self.summary_limit.setValue(f.summary_max)
        self.summary_limit.setSingleStep(50)
        row.addWidget(Field("总结最多条数", self.summary_limit), 3, 1)
        self.voice_name = QLineEdit(f.voice_name)
        row.addWidget(Field("Edge-TTS 音色", self.voice_name), 2, 0)
        row.addWidget(Field("Whisper 模型", self.voice_combo), 2, 1)
        keys.add_layout(row)
        self.add(keys)

        auto = Card()
        title = QLabel("自动搜索")
        title.setObjectName("cardTitle")
        auto.add(title)
        auto.add(_hint("闲着的时候自己搜点东西发到指定会话。默认关闭；目标留空就用最活跃的会话。"))
        self.auto_check = QCheckBox("启用自动搜索")
        self.auto_check.setChecked(bool(f.auto_search))
        auto.add(self.auto_check)
        auto_row = QGridLayout()
        auto_row.setHorizontalSpacing(16)
        auto_row.setVerticalSpacing(12)
        self.auto_interval = QSpinBox()
        self.auto_interval.setRange(5, 720)
        self.auto_interval.setSuffix(" 分钟")
        self.auto_interval.setValue(int(f.auto_search_interval))
        auto_row.addWidget(Field("间隔", self.auto_interval), 0, 0)
        self.auto_target = QLineEdit(f.auto_search_target)
        self.auto_target.setPlaceholderText("group:123456 / private:654321，留空=最活跃会话")
        auto_row.addWidget(Field("发到哪个会话", self.auto_target), 0, 1)
        self.auto_topics = QLineEdit(f.auto_search_topics)
        self.auto_topics.setPlaceholderText("自定义话题，逗号分隔；留空则从最近聊天里找")
        auto_row.addWidget(Field("话题", self.auto_topics), 1, 0, 1, 2)
        auto.add_layout(auto_row)
        self.add(auto)

        self.checks["auto_search"] = self.auto_check

        style = Card()
        title = QLabel("表达风格")
        title.setObjectName("cardTitle")
        style.add(title)
        style.add(_hint("滑块会拼进人格提示词，立刻影响下一句回复。"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)
        self.tone_slider = _slider(f.tone)
        self.verbosity_slider = _slider(f.verbosity)
        self.emoji_slider = _slider(f.emoji)
        grid.addWidget(Field("毒舌 ←→ 温柔", self.tone_slider), 0, 0)
        grid.addWidget(Field("简短 ←→ 详细", self.verbosity_slider), 0, 1)
        grid.addWidget(Field("少用表情 ←→ 多用", self.emoji_slider), 1, 0)
        self.phrase_edit = QLineEdit(f.catchphrase)
        self.phrase_edit.setPlaceholderText("口头禅，可留空")
        grid.addWidget(Field("口头禅", self.phrase_edit), 1, 1)
        self.format_combo = QComboBox()
        self.format_combo.addItem("自动（按语义）", "auto")
        self.format_combo.addItem("总是文字", "text")
        self.format_combo.addItem("总是图片", "image")
        self.format_combo.addItem("总是语音", "voice")
        idx = self.format_combo.findData(f.reply_format)
        self.format_combo.setCurrentIndex(idx if idx >= 0 else 0)
        grid.addWidget(Field("回复形式", self.format_combo), 2, 0)
        self.image_thr = _slider(f.image_threshold)
        self.voice_thr = _slider(f.voice_threshold)
        grid.addWidget(Field("图片判定门槛（低=更容易发图）", self.image_thr), 3, 0)
        grid.addWidget(Field("语音判定门槛（低=更容易语音）", self.voice_thr), 3, 1)
        self.search_thr = _slider(f.search_threshold)
        grid.addWidget(Field("搜索判定门槛（低=更容易搜索）", self.search_thr), 4, 0)
        style.add_layout(grid)
        test_row = QHBoxLayout()
        self.test_edit = QLineEdit()
        self.test_edit.setPlaceholderText("输入一句话，预览会怎么回：例如 发张猫图 / 叫妈妈")
        test_row.addWidget(self.test_edit, 1)
        self.test_button = BusyButton("测试判定", "secondary")
        self.test_button.clicked.connect(self._preview_modality)
        test_row.addWidget(self.test_button)
        style.add_layout(test_row)
        self.test_result = QLabel("当前会：—")
        self.test_result.setObjectName("hint")
        style.add(self.test_result)
        self.add(style)
        style.hide()  # 已迁移到人格页

        use = Card()
        title = QLabel("怎么用")
        title.setObjectName("cardTitle")
        use.add(title)
        use.add(
            _hint(
                "直接说人话就行：@它 说「搜一下 今天的新闻」「总结最近 200 条」「下载 https://…」；"
                "私聊不用 @，也不用加 /。斜杠指令仍然保留。"
            )
        )
        self.add(use)

        footer = QWidget()
        row = QHBoxLayout(footer)
        row.setContentsMargins(30, 10, 30, 12)
        row.addStretch(1)
        save = small_button("保存能力配置", "primary")
        save.clicked.connect(self._save)
        row.addWidget(save)
        self.set_footer(footer)

    def _build_provider_card(self) -> None:
        card = Card()
        title = QLabel("API Provider")
        title.setObjectName("cardTitle")
        card.add(title)
        card.add(_hint("聊天和看图由同一家 Provider 提供；语音、搜索是独立能力，不受 Provider 限制。"))
        row = QGridLayout()
        row.setHorizontalSpacing(16)
        row.setVerticalSpacing(10)
        self.provider_combo = QComboBox()
        for item in provider_choices():
            self.provider_combo.addItem(item.name, item.id)
        idx = self.provider_combo.findData(self.ctx.cfg.llm.provider_id)
        self.provider_combo.setCurrentIndex(idx if idx >= 0 else 0)
        row.addWidget(Field("提供商", self.provider_combo), 0, 0)
        self.provider_key = QLineEdit()
        self.provider_key.setEchoMode(QLineEdit.EchoMode.Password)
        saved = bool(get_key(self.ctx.data_dir, f"llm_{self.ctx.cfg.llm.provider_id}"))
        self.provider_key.setPlaceholderText("已保存，留空不修改" if saved else "粘贴这家 Provider 的 API Key")
        row.addWidget(Field("API Key", self.provider_key), 0, 1)
        self.provider_hint = QLabel("")
        self.provider_hint.setObjectName("cardHint")
        self.provider_hint.setWordWrap(True)
        card.add_layout(row)
        card.add(self.provider_hint)
        self.add(card)
        self.provider_combo.currentIndexChanged.connect(self._refresh_provider_ui)
        self._refresh_provider_ui()

    def _refresh_provider_ui(self) -> None:
        provider = get_provider(self.provider_combo.currentData())
        if provider is None:
            return
        caps = "、".join({"chat": "聊天", "vision": "看图"}.get(c, c) for c in provider.capabilities)
        self.provider_hint.setText(f"{provider.note}\n支持：{caps}　Key：{provider.key_url}")
        saved = bool(get_key(self.ctx.data_dir, f"llm_{provider.id}") or (provider.id == "qwen" and get_key(self.ctx.data_dir, "qwen")))
        self.provider_key.clear()
        self.provider_key.setPlaceholderText("已保存，留空不修改" if saved else "粘贴这家 Provider 的 API Key")
        if "vision" in self.checks:
            ok = "vision" in provider.capabilities
            self.checks["vision"].setEnabled(ok)
            self.checks["vision"].setText("图片/视频/文件" if ok else "图片/视频/文件（Provider 不支持）")
            if not ok:
                self.checks["vision"].setChecked(False)

    def on_show(self) -> None:
        if not self.archive:
            self.count_label.setText("归档未开启")
            return
        try:
            total = self.archive.count()
            tags = self.archive.top_tags(6)
            convs = self.archive.conversations()[:3]
        except Exception:
            return
        self.count_label.setText(f"已归档 {total} 条")
        self.tags_label.setText("分类：" + ("、".join(f"{k}({v})" for k, v in tags) or "暂无"))
        self.conv_label.setText("活跃会话：" + ("；".join(f"{k} {v} 条" for k, v in convs) or "暂无"))

    def _preview_modality(self) -> None:
        if not self.test_edit.text().strip():
            self.test_result.setText("先输入一句话")
            return
        self.test_button.start_busy("判定中…")
        QTimer.singleShot(450, self._finish_preview)

    def _finish_preview(self) -> None:
        from qqbot_core.modality import choose_modality

        text = self.test_edit.text().strip()
        mode = choose_modality(text, self.voice_thr.value(), self.image_thr.value())
        from qqbot_core.modality import search_query

        if search_query(text, self.search_thr.value()):
            mode = "search"
        label = {"text": "文字", "image": "图片", "voice": "语音", "file": "文件", "search": "搜索"}.get(mode, mode)
        self.test_button.stop_busy()
        mark_refreshed(self.test_result, f"当前会：{label}")

    def _save(self) -> None:
        f = self.ctx.cfg.features
        provider = get_provider(self.provider_combo.currentData())
        if provider is not None:
            old_provider = self.ctx.cfg.llm.provider_id
            old_key = self.ctx.cfg.llm.api_key
            self.ctx.cfg.llm.provider_id = provider.id
            self.ctx.cfg.llm.base_url = provider.base_url
            self.ctx.cfg.llm.model = provider.chat_model
            self.ctx.cfg.llm.api_key = old_key if provider.id == old_provider else ""
            if provider.vision_model:
                f.vision_model = provider.vision_model
            if "vision" not in provider.capabilities:
                f.vision = False
                self.checks["vision"].setChecked(False)
            key = self.provider_key.text().strip()
            if key:
                set_key(self.ctx.data_dir, f"llm_{provider.id}", key)
                self.ctx.cfg.llm.api_key = ""
                self.provider_key.clear()
                self.provider_key.setPlaceholderText("已保存，留空不修改")
        for name, box in self.checks.items():
            setattr(f, name, box.isChecked())
        f.search_daily_limit = self.search_limit.value()
        f.download_max_mb = self.download_limit.value()
        f.summary_max = self.summary_limit.value()
        # 表达风格已迁移到人格页保存
        f.voice_model = self.voice_combo.currentText()
        f.voice_name = self.voice_name.text().strip() or "zh-CN-XiaoxiaoNeural"
        f.auto_search = self.auto_check.isChecked()
        f.auto_search_interval = self.auto_interval.value()
        f.auto_search_target = self.auto_target.text().strip()
        f.auto_search_topics = self.auto_topics.text().strip()
        f.search_provider = self.search_combo.currentData()
        if self.tavily_edit.text().strip():
            set_key(self.ctx.data_dir, "tavily", self.tavily_edit.text().strip())
            self.tavily_edit.clear()
            self.tavily_edit.setPlaceholderText("已保存，留空则不修改")
        if self.brave_edit.text().strip():
            set_key(self.ctx.data_dir, "brave", self.brave_edit.text().strip())
            self.brave_edit.clear()
            self.brave_edit.setPlaceholderText("已保存，留空则不修改")
        self.ctx.save_config()
        if self.ctx.process.running:
            self.ctx.process.stop()
            QTimer.singleShot(1500, self.ctx.process.start)
            self.ctx.toast("已保存，正在重启机器人…")
        else:
            self.ctx.toast("能力配置已保存")
        self.on_show()


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("cardHint")
    label.setWordWrap(True)
    return label


def _slider(value: int) -> QSlider:
    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(0, 100)
    slider.setValue(int(value))
    return slider
