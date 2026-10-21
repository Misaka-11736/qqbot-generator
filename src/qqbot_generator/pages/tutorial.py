"""教程页：功能说明、控制逻辑、常见问题与内置问答。"""

from __future__ import annotations

import asyncio

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QTextBrowser

from qqbot_core.llm import make_llm

from ..widgets.common import Card, small_button
from .base import BasePage

DOC = """
<h3>它是怎么判断“该不该干活”的</h3>
<p>每条群消息先过四道门：</p>
<ol>
<li><b>是不是在跟它说话</b>：@、回复它、私聊，或者语义上接得住它上一句；</li>
<li><b>是不是明确请求</b>：有“搜/查/找/发/来/画/总结”等动作，而不是“我有一张票”这种陈述；</li>
<li><b>对应能力开没开</b>：图片/搜索关了，就回到普通聊天，不执行任务；</li>
<li><b>能力执行</b>：语义槽位（动作/量词/主体/输出/发送）→ 搜索/下载/发送。</li>
</ol>
<p>普通聊天不会因为出现“张、图、搜”这些字就被劫持。</p>

<h3>Provider 怎么分工</h3>
<p>模型页只配置文字聊天 Provider；能力页负责看图、语音和搜索。聊天 Provider 在能力页只读，避免两边互相覆盖。</p>
<ul>
<li><b>看图</b>：默认跟随聊天 Provider；聊天 Provider 不支持视觉时，可以单独选 Qwen/OpenAI/SiliconFlow/OpenRouter/智谱/Ollama，并填独立 Key；</li>
<li><b>语音识别</b>：本地 faster-whisper，或 OpenAI/Groq/SiliconFlow；</li>
<li><b>语音合成</b>：本地 Edge-TTS，或 OpenAI/Groq/SiliconFlow；</li>
<li><b>搜索</b>：Brave / Tavily / DuckDuckGo，完全独立。</li>
</ul>
<p>所有 Provider Key 都用 DPAPI 加密存 secrets.json，不写进 config.toml。云端语音失败会直接报错，不回退本地。</p>

<h3>能力与触发</h3>
<table border="1" cellspacing="0" cellpadding="6">
<tr><th>能力</th><th>自然说法</th><th>结果</th></tr>
<tr><td>网页搜索</td><td>搜一下 猎鹰队比赛</td><td>2~4 句口语结论，不贴链接</td></tr>
<tr><td>图片任务</td><td>搜张丑猫发来 / 来张猫图</td><td>Brave 图片搜索 → 下载 cache → 发图</td></tr>
<tr><td>识图</td><td>发图并问“这是啥”</td><td>当前视觉 Provider 看图回答</td></tr>
<tr><td>语音</td><td>发语音 / 用语音说晚安</td><td>本地 Whisper/Edge-TTS，或云端 ASR/TTS</td></tr>
<tr><td>总结</td><td>总结最近 300 条</td><td>分段摘要当前会话</td></tr>
<tr><td>缓存</td><td>设置 → 缓存</td><td>查看占用、打开目录、一键清理</td></tr>
</table>

<h3>配置怎么生效</h3>
<p>人格页所有滑杆/开关改动后 350ms 写入 config.toml；机器人每秒检查文件变更并热加载，下一条消息生效。IQ 以当前人格卡为唯一权威，不再读会话里的旧值。新用户默认只开聊天与归档，其他能力在能力页按需开启。</p>

<h3>命令</h3>
<p>群聊只保留 <code>/reset</code>，且只有管理员能执行；其他 <code>/xxx</code> 一律当普通聊天。</p>

<h3>诊断与修复</h3>
<p>启动后会自动跑一次诊断；也可以到「诊断」页点「开始检查」。绿色通过，黄色警告，红色失败。</p>
<ul>
<li>目录缺失、配置旧字段：自动修复；</li>
<li>loadNapCat.js 缺失：点「复制并修复」，会弹 UAC，不会重启 QQ；</li>
<li>NapCat 与 QQ 版本不一致：点「下载匹配版本」，不会自动安装未知版本；</li>
<li>机器人没启动：点「启动机器人」；</li>
<li>Provider/Key 问题：只提示，去模型页或能力页手动改，不自动切换。</li>
</ul>

<h3>常见问题</h3>
<p><b>为什么它不回？</b> 先看「日志」里有没有 <code>[recv]</code>；没有是 OneBot 没连上；有 <code>[intent] chat</code> 是判定为聊天，被语义门槛拦了。</p>
<p><b>为什么图片是空的？</b> 看 <code>[task]</code> 和 <code>[send]</code>；没配 Brave Key 或图片 CDN 被拦都会写原因。</p>
<p><b>为什么 IQ 和界面不一致？</b> 3.6.2 起 IQ 只认当前人格卡；旧版本会话缓存不再覆盖。</p>
"""


class _QAWorker(QThread):
    done = Signal(bool, str)

    def __init__(self, cfg, question: str):
        super().__init__()
        self.cfg = cfg
        self.question = question

    def run(self) -> None:
        try:
            llm, _label = make_llm(self.cfg)
            system = (
                "你是 QQ Bot生成器的使用教程助手。只回答这个 App 的功能、开关、触发方式、日志含义和排错；"
                "不要执行搜索、发图、改配置等任务。回答简洁、中文、分步骤。"
            )
            answer = asyncio.run(
                llm.complete(
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": self.question},
                    ],
                    temperature=0.4,
                    max_tokens=600,
                )
            )
            self.done.emit(True, answer)
        except Exception as exc:
            self.done.emit(False, str(exc))


class TutorialPage(BasePage):
    key = "tutorial"
    title = "教程"
    subtitle = "功能、控制逻辑、生效流程，以及可以直接提问的使用助手"

    def build(self) -> None:
        text = QTextBrowser()
        text.setOpenExternalLinks(True)
        text.setHtml(DOC)
        text.setMinimumHeight(420)
        card = Card()
        card.add(text)
        self.add(card)

        qa = Card()
        title = QLabel("问教程助手")
        title.setObjectName("cardTitle")
        qa.add(title)
        qa.add(QLabel("只回答 App 用法，不会执行搜索、发图或改配置。和聊天共用同一个模型 Key。"))
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("例如：为什么我发“搜张猫”它不回？")
        self.input.returnPressed.connect(self._ask)
        row.addWidget(self.input, 1)
        self.button = small_button("提问", "primary")
        self.button.clicked.connect(self._ask)
        row.addWidget(self.button)
        qa.add_layout(row)
        self.answer = QTextBrowser()
        self.answer.setMinimumHeight(160)
        qa.add(self.answer)
        self.add(qa)

    def _ask(self) -> None:
        question = self.input.text().strip()
        if not question:
            return
        self.button.setEnabled(False)
        self.answer.setText("正在查教程…")
        self._worker = _QAWorker(self.ctx.cfg, question)
        self._worker.done.connect(self._show)
        self._worker.start()

    def _show(self, ok: bool, text: str) -> None:
        self.button.setEnabled(True)
        self.answer.setText(text if ok else f"回答失败：{text}")
