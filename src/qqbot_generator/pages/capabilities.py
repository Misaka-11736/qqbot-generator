"""能力控制台：开关、API Key、限额、风格和归档统计。"""

from __future__ import annotations

from PySide6.QtCore import Qt
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

from ..widgets.common import Card, Field, small_button
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
        ]
        for index, (name, label) in enumerate(items):
            box = QCheckBox(label)
            box.setChecked(bool(getattr(f, name)))
            self.checks[name] = box
            grid.addWidget(box, index // 4, index % 4)
        for index, (name, label) in enumerate(
            [("vision", "图片理解（v3.1）"), ("voice_in", "语音识别（v3.2）"), ("voice_out", "语音合成（v3.2）")]
        ):
            box = QCheckBox(label)
            box.setEnabled(False)
            box.setChecked(bool(getattr(f, name)))
            self.checks[name] = box
            grid.addWidget(box, 2, index)
        switch.add_layout(grid)
        self.add(switch)

        keys = Card()
        title = QLabel("API Key")
        title.setObjectName("cardTitle")
        keys.add(title)
        keys.add(_hint("Brave 用于搜索；百炼 Qwen-VL 用于 v3.1 看图。Key 不会写进 config.toml。"))
        row = QGridLayout()
        row.setHorizontalSpacing(16)
        row.setVerticalSpacing(12)
        self.brave_edit = QLineEdit()
        self.brave_edit.setEchoMode(QLineEdit.EchoMode.Password)
        brave_saved = bool(get_key(self.ctx.data_dir, "brave"))
        self.brave_edit.setPlaceholderText("已保存，留空则不修改" if brave_saved else "粘贴 Brave API Key")
        row.addWidget(Field("Brave Search Key", self.brave_edit), 0, 0)
        self.qwen_edit = QLineEdit()
        self.qwen_edit.setEchoMode(QLineEdit.EchoMode.Password)
        qwen_saved = bool(get_key(self.ctx.data_dir, "qwen"))
        self.qwen_edit.setPlaceholderText("已保存，留空则不修改" if qwen_saved else "粘贴百炼 API Key（v3.1 用）")
        row.addWidget(Field("百炼 Qwen Key", self.qwen_edit), 0, 1)
        self.model_combo = QComboBox()
        self.model_combo.addItems(["qwen-vl-max", "qwen-vl-plus"])
        row.addWidget(Field("视觉模型", self.model_combo), 1, 0)
        self.search_limit = QSpinBox()
        self.search_limit.setRange(1, 500)
        self.search_limit.setValue(f.search_daily_limit)
        row.addWidget(Field("搜索每日上限", self.search_limit), 1, 1)
        self.download_limit = QSpinBox()
        self.download_limit.setRange(1, 200)
        self.download_limit.setValue(f.download_max_mb)
        self.download_limit.setSuffix(" MB")
        row.addWidget(Field("单文件下载上限", self.download_limit), 2, 0)
        self.summary_limit = QSpinBox()
        self.summary_limit.setRange(50, 1000)
        self.summary_limit.setValue(f.summary_max)
        self.summary_limit.setSingleStep(50)
        row.addWidget(Field("总结最多条数", self.summary_limit), 2, 1)
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
        self.format_combo.addItem("纯文字", "text")
        self.format_combo.addItem("图片（v3.1）", "image")
        self.format_combo.addItem("语音（v3.2）", "voice")
        idx = self.format_combo.findData(f.reply_format)
        self.format_combo.setCurrentIndex(idx if idx >= 0 else 0)
        grid.addWidget(Field("回复形式", self.format_combo), 2, 0)
        style.add_layout(grid)
        self.add(style)

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

    def _save(self) -> None:
        f = self.ctx.cfg.features
        for name, box in self.checks.items():
            setattr(f, name, box.isChecked())
        f.search_daily_limit = self.search_limit.value()
        f.download_max_mb = self.download_limit.value()
        f.summary_max = self.summary_limit.value()
        f.tone = self.tone_slider.value()
        f.verbosity = self.verbosity_slider.value()
        f.emoji = self.emoji_slider.value()
        f.catchphrase = self.phrase_edit.text().strip()
        f.reply_format = self.format_combo.currentData()
        f.auto_search = self.auto_check.isChecked()
        f.auto_search_interval = self.auto_interval.value()
        f.auto_search_target = self.auto_target.text().strip()
        f.auto_search_topics = self.auto_topics.text().strip()
        if self.brave_edit.text().strip():
            set_key(self.ctx.data_dir, "brave", self.brave_edit.text().strip())
            self.brave_edit.clear()
            self.brave_edit.setPlaceholderText("已保存，留空则不修改")
        if self.qwen_edit.text().strip():
            set_key(self.ctx.data_dir, "qwen", self.qwen_edit.text().strip())
            self.qwen_edit.clear()
            self.qwen_edit.setPlaceholderText("已保存，留空则不修改")
        self.ctx.save_config()
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
