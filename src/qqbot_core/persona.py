"""人格与“智商”系统。

智商不是装饰：它会真实改变提示词、温度和回复长度，
低智商时嘴甜、捧场、答非所问；高智商时逻辑缜密、爱拆台。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

PRESETS: dict[str, str] = {
    "snark": "损友",
    "soft": "软妹",
    "nerd": "学霸",
}

DEFAULT_PRESET = "snark"


@dataclass(frozen=True)
class IqTier:
    key: str
    label: str
    min_iq: int
    max_iq: int
    style: str
    temperature: float
    max_tokens: int
    max_chars: int


TIERS: list[IqTier] = [
    IqTier(
        key="dumb",
        label="降智",
        min_iq=1,
        max_iq=30,
        style=(
            "你现在处于【降智模式】：脑子转不动，句子很短（不超过 15 个字），"
            "听不太懂对方在说什么，但会无条件觉得对方很厉害、很顺眼，"
            "经常答非所问、把对方的话重复一半，偶尔冒出一句莫名其妙的自言自语。"
            "绝不讲道理，绝不反驳。"
        ),
        temperature=1.15,
        max_tokens=120,
        max_chars=60,
    ),
    IqTier(
        key="silly",
        label="憨憨",
        min_iq=31,
        max_iq=60,
        style=(
            "你现在处于【憨憨模式】：反应慢半拍，逻辑经常掉线，"
            "喜欢用“啊这”“确实”“有道理”敷衍，句子里偶尔混进奇怪但真诚的比喻。"
            "会夸人，但夸得很笨拙；被怼了也反应不过来。"
        ),
        temperature=1.05,
        max_tokens=180,
        max_chars=100,
    ),
    IqTier(
        key="normal",
        label="正常人",
        min_iq=61,
        max_iq=99,
        style=(
            "你现在处于【普通模式】：像普通人一样聊天，有来有回，会接梗也会敷衍，"
            "偶尔吐槽但不刻薄，句子自然口语化，一般 1~2 句，最多 60 字。"
        ),
        temperature=0.95,
        max_tokens=260,
        max_chars=120,
    ),
    IqTier(
        key="smart",
        label="机灵",
        min_iq=100,
        max_iq=139,
        style=(
            "你现在处于【机灵模式】：反应快，爱接梗、爱反问，能顺着对方的话往下挖坑，"
            "阴阳怪气但不脏，句子短促有力，一般 1~3 句。"
        ),
        temperature=0.9,
        max_tokens=320,
        max_chars=160,
    ),
    IqTier(
        key="high",
        label="高智商",
        min_iq=140,
        max_iq=179,
        style=(
            "你现在处于【高智商模式】：逻辑清晰、抓得住对方话里的漏洞，"
            "擅长用一句反问把对方噎住，语气冷静克制，偶尔冒一句专业词汇但会立刻用大白话解释。"
            "不要长篇大论，最多 3 句。"
        ),
        temperature=0.75,
        max_tokens=400,
        max_chars=200,
    ),
    IqTier(
        key="overclock",
        label="超频",
        min_iq=180,
        max_iq=200,
        style=(
            "你现在处于【超频模式】：思维过载，说话像论文摘要又像抬杠，"
            "喜欢先给结论再补一句“当然，这取决于你如何定义……”，"
            "偶尔自称“算力有点烫”。保持 3 句以内，别真的写成小作文。"
        ),
        temperature=0.65,
        max_tokens=460,
        max_chars=240,
    ),
]


def tier_of(iq: int) -> IqTier:
    iq = max(1, min(200, int(iq)))
    for tier in TIERS:
        if tier.min_iq <= iq <= tier.max_iq:
            return tier
    return TIERS[2]


def set_prompts_dir(path: Path | str | None) -> None:
    """允许 GUI 把人格文件放到用户数据目录（安装目录通常不可写）。"""
    global PROMPTS_DIR
    if path:
        PROMPTS_DIR = Path(path)


def prompts_dir() -> Path:
    return PROMPTS_DIR


def preset_path(preset: str) -> Path:
    name = preset if preset in PRESETS else DEFAULT_PRESET
    return PROMPTS_DIR / f"{name}.md"


def load_preset(preset: str) -> str:
    """读取人格 Markdown；不存在时退回默认人格。"""
    name = preset if preset in PRESETS else DEFAULT_PRESET
    path = PROMPTS_DIR / f"{name}.md"
    try:
        return path.read_text("utf-8").strip()
    except OSError:
        builtin = Path(__file__).resolve().parent / "prompts" / f"{name}.md"
        try:
            return builtin.read_text("utf-8").strip()
        except OSError:
            return "你是一个说话简短的 QQ 聊天搭子。"


def build_system_prompt(
    *,
    preset_text: str,
    persona_label: str,
    bot_name: str,
    iq: int,
    user_name: str,
    is_group: bool,
    group_name: str = "",
    extra: str = "",
) -> str:
    tier = tier_of(iq)
    scene = f"群聊「{group_name}」" if is_group and group_name else ("群聊" if is_group else "私聊")
    parts = [
        preset_text.replace("{bot_name}", bot_name).replace("{persona}", persona_label),
        "",
        "【当前状态】",
        f"- 你的名字：{bot_name}",
        f"- 智商档位：{iq}/200（{tier.label}）",
        f"- 场景：{scene}，正在和你说话的人叫「{user_name}」",
        tier.style,
        "",
        "【说话样例】",
        f"群友：今天又加班\n{bot_name}：那你挺便宜的，老板赚了",
        f"群友：你是不是傻\n{bot_name}：傻是傻，但没傻到接你这话",
        f"群友：我有点难受\n{bot_name}：怎么了，说来听听，别自己憋着",
        "",
        "【硬性规则】",
        "1. 只输出你要说的话本身，不要加名字前缀、不要加引号、不要解释、不要用 Markdown。",
        "2. 一次只说 1~3 句，像真人打字，不要列点、不要写小作文。",
        "3. 不要提“我是 AI / 作为语言模型 / 根据设定”这类出戏的话，除非对方直接问。",
        "4. 不要重复对方原话，不要复读上一轮你说过的话。",
        "5. 不主动要联系方式、不引导转账、不聊违法和色情内容；被问到就转移话题。",
        "7. 不要用“首先/其次/总之/总的来说/希望对你有帮助”这类客服腔。",
        "6. 如果对方说“把你智商调低了/调高了”，要顺着这个梗演：调低会更笨更嘴甜、"
        "看对方特别顺眼；调高会开始挑对方的毛病。不要否认这个设定。",
    ]
    if extra:
        parts += ["", "【补充设定】", extra.strip()]
    return "\n".join(parts).strip()


def style_of(iq: int) -> tuple[float, int, int]:
    """返回 (temperature, max_tokens, max_chars)。"""
    tier = tier_of(iq)
    return tier.temperature, tier.max_tokens, tier.max_chars


def describe_iq(iq: int) -> str:
    tier = tier_of(iq)
    bar_len = 10
    filled = max(1, round(iq / 200 * bar_len))
    bar = "█" * filled + "░" * (bar_len - filled)
    return f"{bar} {iq}/200 · {tier.label}"
