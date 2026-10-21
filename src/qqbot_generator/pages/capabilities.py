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
    subtitle = "按能力绑定 Provider；Key 加密存储，日志自动打码"

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
        switch.add(_hint("关掉后不会再执行对应任务；归档关掉后总结和分类都不可用。"))
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
        self._build_provider_cards()

        keys = Card()
        title = QLabel("API Key")
        title.setObjectName("cardTitle")
        keys.add(title)
        keys.add(_hint("搜索 Key 在这里；看图/语音的独立 Key 在上方各自卡片。Key 加密保存，不写进 config.toml。"))
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
                "私聊不用 @。群里只保留管理员 /reset，其他斜杠按普通聊天。"
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

    def _build_provider_cards(self) -> None:
        f = self.ctx.cfg.features
        chat = Card()
        title = QLabel("聊天 Provider")
        title.setObjectName("cardTitle")
        chat.add(title)
        self.chat_provider_hint = QLabel("")
        self.chat_provider_hint.setObjectName("cardHint")
        self.chat_provider_hint.setWordWrap(True)
        chat.add(self.chat_provider_hint)
        self.add(chat)

        vision = Card()
        title = QLabel("看图 Provider")
        title.setObjectName("cardTitle")
        vision.add(title)
        vision.add(_hint("默认跟随聊天 Provider；聊天 Provider 不支持视觉时，可单独指定并填它的 Key。"))
        vrow = QGridLayout()
        vrow.setHorizontalSpacing(16)
        vrow.setVerticalSpacing(10)
        self.vision_combo = QComboBox()
        self.vision_combo.addItem("跟随聊天 Provider", "")
        for item in provider_choices():
            if "vision" in item.capabilities:
                self.vision_combo.addItem(item.name, item.id)
        idx = self.vision_combo.findData(f.vision_provider)
        self.vision_combo.setCurrentIndex(idx if idx >= 0 else 0)
        vrow.addWidget(Field("视觉 Provider", self.vision_combo), 0, 0)
        self.vision_key = QLineEdit()
        self.vision_key.setEchoMode(QLineEdit.EchoMode.Password)
        vrow.addWidget(Field("独立 Key（跟随聊天时不用填）", self.vision_key), 0, 1)
        vision.add_layout(vrow)
        self.vision_hint = QLabel("")
        self.vision_hint.setObjectName("cardHint")
        self.vision_hint.setWordWrap(True)
        vision.add(self.vision_hint)
        self.add(vision)

        voice = Card()
        title = QLabel("语音 Provider")
        title.setObjectName("cardTitle")
        voice.add(title)
        voice.add(_hint("本地 Whisper/Edge-TTS 不消耗 Token；云端走 OpenAI 兼容的 /audio/transcriptions 和 /audio/speech。"))
        vgrid = QGridLayout()
        vgrid.setHorizontalSpacing(16)
        vgrid.setVerticalSpacing(10)
        self.asr_combo = QComboBox()
        self.asr_combo.addItem("本地 faster-whisper", "local")
        for item in provider_choices():
            if "asr" in item.capabilities:
                self.asr_combo.addItem(item.name, item.id)
        idx = self.asr_combo.findData(f.asr_provider)
        self.asr_combo.setCurrentIndex(idx if idx >= 0 else 0)
        vgrid.addWidget(Field("语音识别", self.asr_combo), 0, 0)
        self.voice_combo = QComboBox()
        self.voice_combo.addItems(["small", "base", "tiny"])
        idx_voice = self.voice_combo.findText(f.voice_model)
        if idx_voice >= 0:
            self.voice_combo.setCurrentIndex(idx_voice)
        vgrid.addWidget(Field("本地 Whisper 模型", self.voice_combo), 0, 1)
        self.asr_model = QLineEdit(f.asr_model)
        self.asr_model.setPlaceholderText("云端 ASR 模型，留空用 Provider 默认")
        vgrid.addWidget(Field("云端 ASR 模型", self.asr_model), 1, 0)
        self.asr_key = QLineEdit()
        self.asr_key.setEchoMode(QLineEdit.EchoMode.Password)
        vgrid.addWidget(Field("ASR Key（本地不用填）", self.asr_key), 1, 1)

        self.tts_combo = QComboBox()
        self.tts_combo.addItem("本地 Edge-TTS", "edge")
        for item in provider_choices():
            if "tts" in item.capabilities:
                self.tts_combo.addItem(item.name, item.id)
        idx = self.tts_combo.findData(f.tts_provider)
        self.tts_combo.setCurrentIndex(idx if idx >= 0 else 0)
        vgrid.addWidget(Field("语音合成", self.tts_combo), 2, 0)
        self.voice_name = QLineEdit(f.voice_name)
        vgrid.addWidget(Field("Edge-TTS 音色", self.voice_name), 2, 1)
        self.tts_model = QLineEdit(f.tts_model)
        self.tts_model.setPlaceholderText("云端 TTS 模型，留空用 Provider 默认")
        vgrid.addWidget(Field("云端 TTS 模型", self.tts_model), 3, 0)
        self.tts_voice = QLineEdit(f.tts_voice)
        self.tts_voice.setPlaceholderText("云端 TTS 音色，如 alloy / Fritz-PlayAI")
        vgrid.addWidget(Field("云端 TTS 音色", self.tts_voice), 3, 1)
        self.tts_key = QLineEdit()
        self.tts_key.setEchoMode(QLineEdit.EchoMode.Password)
        vgrid.addWidget(Field("TTS Key（Edge 不用填）", self.tts_key), 4, 0)
        voice.add_layout(vgrid)
        self.voice_hint = QLabel("")
        self.voice_hint.setObjectName("cardHint")
        self.voice_hint.setWordWrap(True)
        voice.add(self.voice_hint)
        self.add(voice)

        self.vision_combo.currentIndexChanged.connect(self._refresh_capability_providers)
        self.asr_combo.currentIndexChanged.connect(self._refresh_capability_providers)
        self.tts_combo.currentIndexChanged.connect(self._refresh_capability_providers)
        self._refresh_capability_providers()

    def _refresh_capability_providers(self) -> None:
        chat_provider = get_provider(self.ctx.cfg.llm.provider_id)
        if self.chat_provider_hint is not None:
            self.chat_provider_hint.setText(
                f"当前聊天：{chat_provider.name if chat_provider else self.ctx.cfg.llm.provider_id} / "
                f"{self.ctx.cfg.llm.model}。聊天 Provider 在「模型」页修改，这里只读。"
            )
        vision_id = self.vision_combo.currentData() or self.ctx.cfg.llm.provider_id
        vision_ok = get_provider(vision_id) and "vision" in get_provider(vision_id).capabilities
        self.vision_key.setEnabled(bool(self.vision_combo.currentData()))
        if self.vision_combo.currentData():
            vkey = get_key(self.ctx.data_dir, f"cap_vision_{vision_id}")
            self.vision_key.setPlaceholderText("已保存，留空不修改" if vkey else "粘贴这家视觉 Provider 的 Key")
        self.checks["vision"].setEnabled(bool(vision_ok))
        self.checks["vision"].setText("图片/视频/文件" if vision_ok else "图片/视频/文件（不支持）")
        if not vision_ok:
            self.checks["vision"].setChecked(False)
        self.vision_hint.setText(
            ("跟随聊天：" if not self.vision_combo.currentData() else "独立 Provider：")
            + (get_provider(vision_id).name if get_provider(vision_id) else vision_id)
            + ("，支持视觉。" if vision_ok else "，不支持视觉，请换一个。")
            + (" 需要填独立 Key。" if self.vision_combo.currentData() and not get_key(self.ctx.data_dir, f"cap_vision_{vision_id}") else "")
        )

        asr_id = self.asr_combo.currentData()
        self.voice_combo.setEnabled(asr_id == "local")
        self.asr_model.setEnabled(asr_id != "local")
        self.asr_key.setEnabled(asr_id != "local")
        if asr_id != "local":
            akey = get_key(self.ctx.data_dir, f"cap_asr_{asr_id}")
            self.asr_key.setPlaceholderText("已保存，留空不修改" if akey else "粘贴 ASR Key")
        tts_id = self.tts_combo.currentData()
        self.voice_name.setEnabled(tts_id == "edge")
        self.tts_model.setEnabled(tts_id != "edge")
        self.tts_voice.setEnabled(tts_id != "edge")
        self.tts_key.setEnabled(tts_id != "edge")
        if tts_id != "edge":
            tkey = get_key(self.ctx.data_dir, f"cap_tts_{tts_id}")
            self.tts_key.setPlaceholderText("已保存，留空不修改" if tkey else "粘贴 TTS Key")
        self.voice_hint.setText("语音识别/合成失败会直接报错，不会偷偷回退本地。")

    def on_show(self) -> None:
        self._refresh_capability_providers()
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
        vision_id = self.vision_combo.currentData()
        f.vision_provider = vision_id
        if vision_id:
            provider = get_provider(vision_id)
            if provider and "vision" in provider.capabilities:
                f.vision_model = provider.vision_model
                key = self.vision_key.text().strip()
                if key:
                    set_key(self.ctx.data_dir, f"cap_vision_{vision_id}", key)
                    self.vision_key.clear()
            else:
                f.vision = False
                self.checks["vision"].setChecked(False)

        f.asr_provider = self.asr_combo.currentData()
        f.asr_model = self.asr_model.text().strip()
        if f.asr_provider != "local":
            key = self.asr_key.text().strip()
            if key:
                set_key(self.ctx.data_dir, f"cap_asr_{f.asr_provider}", key)
                self.asr_key.clear()
        f.tts_provider = self.tts_combo.currentData()
        f.tts_model = self.tts_model.text().strip()
        f.tts_voice = self.tts_voice.text().strip()
        if f.tts_provider != "edge":
            key = self.tts_key.text().strip()
            if key:
                set_key(self.ctx.data_dir, f"cap_tts_{f.tts_provider}", key)
                self.tts_key.clear()
        f.voice_model = self.voice_combo.currentText()
        f.voice_name = self.voice_name.text().strip() or "zh-CN-XiaoxiaoNeural"

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
