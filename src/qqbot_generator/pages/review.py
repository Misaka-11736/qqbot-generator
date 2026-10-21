"""评审页：人工标注 Bot 回复，确认/回滚自动迭代规则。"""

from __future__ import annotations

import time

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QSpinBox, QVBoxLayout, QWidget

from qqbot_core.learning import REASONS, LearningStore, RuleStore

from ..widgets.common import Card, Field, RoundedComboBox, small_button
from .base import BasePage


class ReviewPage(BasePage):
    key = "review"
    title = "评审"
    subtitle = "人工标注 Bot 回复；自动迭代只根据你的标注生成规则"

    def build(self) -> None:
        self.store = LearningStore(self.ctx.data_dir)
        self.rules = RuleStore(self.ctx.data_dir)
        self.replies = []
        self.index = 0

        card = Card()
        title = QLabel("标注回复")
        title.setObjectName("cardTitle")
        card.add(title)
        card.add(self._hint("好/不好 + 原因；同类原因至少 5 条才会生成规则。标注是自动迭代的唯一学习信号。"))
        self.selector = RoundedComboBox()
        self.selector.currentIndexChanged.connect(self._select)
        card.add(Field("最近的 Bot 回复", self.selector))
        self.context = QLabel("")
        self.context.setObjectName("cardHint")
        self.context.setWordWrap(True)
        card.add(self.context)
        self.reply_view = QLabel("")
        self.reply_view.setWordWrap(True)
        self.reply_view.setStyleSheet("background:#F7F9FC;border:1px solid #DDE5F2;border-radius:10px;padding:12px;")
        card.add(self.reply_view)
        row = QHBoxLayout()
        self.reason = RoundedComboBox()
        for key, label in REASONS.items():
            self.reason.addItem(label, key)
        row.addWidget(Field("原因", self.reason), 1)
        self.note = QLineEdit()
        self.note.setPlaceholderText("可选：一句备注，例如“太长”“接错梗”")
        row.addWidget(Field("备注", self.note), 2)
        card.add_layout(row)
        buttons = QHBoxLayout()
        good = small_button("标为好", "primary")
        good.clicked.connect(lambda: self._mark(1))
        bad = small_button("标为不好", "secondary")
        bad.clicked.connect(lambda: self._mark(-1))
        buttons.addWidget(good)
        buttons.addWidget(bad)
        buttons.addStretch(1)
        self.progress = QLabel("")
        self.progress.setObjectName("cardHint")
        buttons.addWidget(self.progress)
        card.add_layout(buttons)
        self.add(card)

        pending = Card()
        title = QLabel("待确认规则（高风险）")
        title.setObjectName("cardTitle")
        pending.add(title)
        pending.add(self._hint("人格核心、逻辑、事实类规则不会自动生效；确认后进入人格层。"))
        self.pending_box = QVBoxLayout()
        self.pending_box.setSpacing(6)
        pending.add_layout(self.pending_box)
        self.add(pending)

        active = Card()
        title = QLabel("当前生效的适应规则")
        title.setObjectName("cardTitle")
        active.add(title)
        active.add(self._hint("低风险规则已自动生效，带保留期；可在这里回滚。"))
        self.active_box = QVBoxLayout()
        self.active_box.setSpacing(6)
        active.add_layout(self.active_box)
        self.add(active)

        config = Card()
        title = QLabel("迭代设置")
        title.setObjectName("cardTitle")
        config.add(title)
        row = QHBoxLayout()
        self.enabled = small_button("启用自动迭代", "secondary")
        self.enabled.setCheckable(True)
        self.enabled.setChecked(bool(self.ctx.cfg.learning.enabled))
        self.enabled.clicked.connect(self._save_settings)
        row.addWidget(self.enabled)
        self.min_labels = QSpinBox()
        self.min_labels.setRange(1, 50)
        self.min_labels.setValue(int(self.ctx.cfg.learning.min_labels))
        row.addWidget(Field("同类最少标注数", self.min_labels))
        self.ttl = QSpinBox()
        self.ttl.setRange(1, 90)
        self.ttl.setValue(int(self.ctx.cfg.learning.ttl_days))
        self.ttl.setSuffix(" 天")
        row.addWidget(Field("规则保留", self.ttl))
        config.add_layout(row)
        self.add(config)

    def _hint(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("cardHint")
        label.setWordWrap(True)
        return label

    def on_show(self) -> None:
        self.replies = self.store.recent(100)
        current = self.selector.currentData()
        self.selector.blockSignals(True)
        self.selector.clear()
        self.selector.addItem("选择一条 Bot 回复", 0)
        for row in self.replies:
            mark = "已标" if row["verdict"] is not None else "未标"
            text = f"[{mark}] #{row['id']} {row['reply'][:46].replace(chr(10), ' ')}"
            self.selector.addItem(text, row["id"])
        idx = self.selector.findData(current)
        self.selector.setCurrentIndex(max(0, idx))
        self.selector.blockSignals(False)
        self._refresh_rules()
        stats = self.store.stats()
        self.progress.setText(f"回复 {stats['replies']} · 标注 {stats['labels']} · 待分析 {stats['pending']}")
        self._select()

    def _current(self):
        rid = self.selector.currentData()
        return next((r for r in self.replies if r["id"] == rid), None)

    def _select(self) -> None:
        row = self._current()
        if row is None:
            self.context.setText("")
            self.reply_view.setText("")
            return
        when = time.strftime("%m-%d %H:%M", time.localtime(row["ts"] or 0))
        self.context.setText(f"{row['conv']} · {when} · 用户：{row['user'][:160]}")
        self.reply_view.setText(row["reply"])
        if row["reason"]:
            idx = self.reason.findData(row["reason"])
            self.reason.setCurrentIndex(max(0, idx))
        self.note.setText(row["note"])

    def _mark(self, verdict: int) -> None:
        row = self._current()
        if row is None:
            self.ctx.toast("先选一条回复")
            return
        self.store.add_feedback(row["id"], verdict, self.reason.currentData(), self.note.text())
        self.ctx.toast("标注已保存")
        self.on_show()

    def _refresh_rules(self) -> None:
        while self.pending_box.count():
            item = self.pending_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        while self.active_box.count():
            item = self.active_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for rule in self.rules.pending():
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(f"<b>{rule.get('category')}</b>　{rule.get('text')}")
            label.setWordWrap(True)
            layout.addWidget(label, 1)
            rid = rule.get("id")
            ok = small_button("确认", "primary")
            ok.clicked.connect(lambda _=False, rid=rid: (self.rules.approve(rid), self.on_show()))
            no = small_button("拒绝", "secondary")
            no.clicked.connect(lambda _=False, rid=rid: (self.rules.reject(rid), self.on_show()))
            layout.addWidget(ok)
            layout.addWidget(no)
            self.pending_box.addWidget(row)
        for rule in self.rules.active():
            expires = time.strftime("%m-%d %H:%M", time.localtime(float(rule.get("expires") or 0)))
            label = QLabel(f"{rule.get('text')}　（{rule.get('category')}，至 {expires}）")
            label.setWordWrap(True)
            self.active_box.addWidget(label)
        version = int(self.rules.data.get("version") or 0)
        if version:
            back = small_button("回滚到上一版", "secondary")
            back.clicked.connect(lambda: self._rollback(version - 1))
            self.active_box.addWidget(back)

    def _rollback(self, version: int) -> None:
        if self.rules.rollback(version):
            self.ctx.toast(f"已回滚到版本 {version}")
            self.on_show()
        else:
            self.ctx.toast("没有这个版本")

    def _save_settings(self) -> None:
        self.ctx.cfg.learning.enabled = self.enabled.isChecked()
        self.ctx.cfg.learning.min_labels = self.min_labels.value()
        self.ctx.cfg.learning.ttl_days = self.ttl.value()
        self.ctx.save_config()
        self.ctx.toast("迭代设置已保存")
