"""模型页：OpenAI 兼容接口配置与连通性测试。"""

from __future__ import annotations

import asyncio
import os
import time

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from qqbot_core.keyvault import get_key, set_key
from qqbot_core.llm import ChatLLM, friendly_error

from ..theme import COLORS
from ..widgets.common import Card, Field, small_button
from .base import BasePage

PRESETS = {
    "DeepSeek": ("deepseek", "https://api.deepseek.com/v1", "deepseek-chat"),
    "通义千问": ("qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    "智谱 GLM": ("zhipu", "https://open.bigmodel.cn/api/paas/v4", "glm-4-flash"),
    "本地 Ollama": ("ollama", "http://127.0.0.1:11434/v1", "qwen2.5:7b"),
}


class _Signals(QObject):
    done = Signal(bool, str)


class _Probe(QRunnable):
    def __init__(self, base_url: str, key: str, model: str, timeout: float):
        super().__init__()
        self.base_url = base_url
        self.key = key
        self.model = model
        self.timeout = timeout
        self.signals = _Signals()

    def run(self) -> None:
        started = time.time()
        try:
            client = ChatLLM(self.base_url, self.key, self.model, timeout=self.timeout, retries=0)
            reply = asyncio.run(
                client.complete(
                    [{"role": "user", "content": "用一句话证明你活着，别超过 20 个字。"}],
                    temperature=0.8,
                    max_tokens=60,
                )
            )
            elapsed = int((time.time() - started) * 1000)
            self.signals.done.emit(True, f"{elapsed} ms · {reply.strip()[:60]}")
        except Exception as exc:
            self.signals.done.emit(False, friendly_error(str(exc)))


class ModelPage(BasePage):
    key = "model"
    title = "模型"
    subtitle = "任何 OpenAI 兼容接口都能接，先测通再保存"

    def build(self) -> None:
        self._build_provider()
        self._build_params()
        self._build_actions()
        self.load()

    def _build_provider(self) -> None:
        card = Card()
        title = QLabel("服务商")
        title.setObjectName("cardTitle")
        card.add(title)
        card.add(_hint("点一下快捷填充，再改成自己的 Key 即可。"))

        chips = QHBoxLayout()
        chips.setSpacing(8)
        for name in PRESETS:
            chip = small_button(name, "chip")
            chip.clicked.connect(lambda _=False, n=name: self._fill_preset(n))
            chips.addWidget(chip)
        chips.addStretch(1)
        card.add_layout(chips)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(14)

        self.provider_combo = QComboBox()
        self.provider_combo.addItem("自动（有 Key 就用真模型）", "auto")
        self.provider_combo.addItem("强制在线模型", "openai")
        self.provider_combo.addItem("强制离线大脑", "mock")
        grid.addWidget(Field("调用方式", self.provider_combo), 0, 0)

        self.model_edit = QLineEdit()
        self.model_edit.setPlaceholderText("deepseek-chat")
        grid.addWidget(Field("模型名", self.model_edit), 0, 1)

        self.base_edit = QLineEdit()
        self.base_edit.setPlaceholderText("https://api.deepseek.com/v1")
        grid.addWidget(Field("接口地址", self.base_edit, "填到 /v1 为止，程序自动补 /chat/completions"), 1, 0, 1, 2)
        card.add_layout(grid)
        self.add(card)

    def _build_params(self) -> None:
        card = Card()
        title = QLabel("密钥与采样")
        title.setObjectName("cardTitle")
        card.add(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(14)

        key_box = QWidget()
        key_layout = QHBoxLayout(key_box)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.setSpacing(8)
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("sk-...")
        self.key_edit.setClearButtonEnabled(True)
        key_layout.addWidget(self.key_edit, 1)
        eye = small_button("显示", "chip")
        eye.setCheckable(True)
        eye.setFixedWidth(64)
        eye.toggled.connect(lambda on: self.key_edit.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        key_layout.addWidget(eye)
        grid.addWidget(Field("API Key", key_box, "只存在本机 config.toml，不会外传"), 0, 0, 1, 2)

        self.env_edit = QLineEdit()
        self.env_edit.setPlaceholderText("QQBOT_API_KEY")
        grid.addWidget(Field("环境变量名", self.env_edit, "Key 也可以放环境变量，程序优先读输入框"), 1, 0)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setSuffix(" 秒")
        grid.addWidget(Field("超时", self.timeout_spin), 1, 1)

        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 1.6)
        self.temp_spin.setSingleStep(0.05)
        self.temp_spin.setDecimals(2)
        grid.addWidget(Field("温度", self.temp_spin, "越高越发散，聊天建议 0.8~1.0"), 2, 0)

        self.tokens_spin = QSpinBox()
        self.tokens_spin.setRange(40, 2000)
        self.tokens_spin.setSuffix(" tokens")
        grid.addWidget(Field("最大生成长度", self.tokens_spin), 2, 1)
        card.add_layout(grid)
        self.add(card)

    def _build_actions(self) -> None:
        footer = QFrame()
        row = QHBoxLayout(footer)
        row.setContentsMargins(30, 12, 30, 14)
        row.setSpacing(12)
        self.test_button = QPushButton("测试连接")
        self.test_button.setObjectName("secondary")
        self.test_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.test_button.clicked.connect(self._test)
        row.addWidget(self.test_button)

        self.result = QLabel("还没测过。填完 Key 点一下，能收到一句话就算通。")
        self.result.setObjectName("hint")
        self.result.setWordWrap(True)
        row.addWidget(self.result, 1)

        save = QPushButton("保存配置")
        save.setObjectName("primary")
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.clicked.connect(self.save)
        row.addWidget(save)
        self.set_footer(footer)

    # ---------- 数据 ----------

    def load(self) -> None:
        cfg = self.ctx.cfg
        index = self.provider_combo.findData(cfg.llm.provider)
        self.provider_combo.setCurrentIndex(max(index, 0))
        self.base_edit.setText(cfg.llm.base_url)
        self.model_edit.setText(cfg.llm.model)
        self.key_edit.setText(cfg.llm.api_key)
        if not cfg.llm.api_key:
            saved = bool(get_key(self.ctx.data_dir, f"llm_{cfg.llm.provider_id}"))
            self.key_edit.setPlaceholderText("已保存，留空不修改" if saved else "粘贴 API Key")
        self.env_edit.setText(cfg.llm.api_key_env)
        self.timeout_spin.setValue(int(cfg.llm.timeout))
        self.temp_spin.setValue(cfg.llm.temperature)
        self.tokens_spin.setValue(cfg.llm.max_tokens)
        if cfg.effective_provider == "mock":
            self.result.setText("当前没有可用 Key，保存后会走离线大脑。")
        else:
            self.result.setText(f"当前：{cfg.llm.model}")

    def _fill_preset(self, name: str) -> None:
        provider_id, base, model = PRESETS[name]
        self.ctx.cfg.llm.provider_id = provider_id
        self.base_edit.setText(base)
        self.model_edit.setText(model)
        self.key_edit.clear()
        saved = bool(get_key(self.ctx.data_dir, f"llm_{provider_id}"))
        self.key_edit.setPlaceholderText("已保存，留空不修改" if saved else "粘贴这家 Provider 的 Key")
        self.ctx.toast(f"已填入 {name}，记得保存")

    def _values(self) -> tuple[str, str, str, str, float]:
        base = self.base_edit.text().strip()
        model = self.model_edit.text().strip()
        key = self.key_edit.text().strip()
        env = self.env_edit.text().strip()
        if not key and env:
            key = os.environ.get(env, "").strip()
        return base, model, key, env, float(self.timeout_spin.value())

    def save(self) -> None:
        base, model, key, env, timeout = self._values()
        if not base or not model:
            self.ctx.toast("接口地址和模型名不能为空")
            return
        cfg = self.ctx.cfg
        cfg.llm.provider = self.provider_combo.currentData()
        cfg.llm.base_url = base
        cfg.llm.model = model
        if key:
            set_key(self.ctx.data_dir, f"llm_{cfg.llm.provider_id}", key)
            cfg.llm.api_key = ""
        cfg.llm.api_key_env = env or "QQBOT_API_KEY"
        cfg.llm.timeout = timeout
        cfg.llm.temperature = round(self.temp_spin.value(), 2)
        cfg.llm.max_tokens = self.tokens_spin.value()
        self.ctx.save_config()
        self.ctx.toast("模型配置已保存，重启机器人后生效")

    def _test(self) -> None:
        base, model, key, _env, timeout = self._values()
        provider = self.provider_combo.currentData()
        if provider == "mock":
            self.result.setText("离线模式不需要测试，直接用模板大脑。")
            return
        if not key:
            key = self.ctx.cfg.resolve_api_key()
        if not key:
            self.result.setText("没有 Key：先填 Key，或把调用方式改成「离线」。")
            return
        self.test_button.setEnabled(False)
        self.result.setText("正在敲模型的门…")
        worker = _Probe(base, key, model, timeout)
        worker.signals.done.connect(self._on_test_done)
        QThreadPool.globalInstance().start(worker)

    def _on_test_done(self, ok: bool, message: str) -> None:
        self.test_button.setEnabled(True)
        if ok:
            self.result.setText(f"连通 · {message}")
            self.result.setStyleSheet(f"color:{COLORS['green']}; font-weight:600;")
        else:
            self.result.setText(f"失败 · {message}")
            self.result.setStyleSheet(f"color:{COLORS['red']};")


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("cardHint")
    label.setWordWrap(True)
    return label
