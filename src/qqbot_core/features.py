"""v3 能力开关与表达风格配置。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FeatureConfig:
    """每个能力独立开关；Key 不放这里，存 secrets.json。"""

    archive: bool = True  # 归档所有消息
    summarize: bool = True  # 允许 /总结
    search: bool = True  # 允许 /搜
    download: bool = True  # 允许 /下载
    gen_image: bool = True  # 允许 /做图
    gen_file: bool = True  # 允许 /做文件
    classify: bool = True  # 群聊内容分类
    vision: bool = False  # v3.1
    voice_in: bool = False  # v3.2
    voice_out: bool = False  # v3.2

    search_daily_limit: int = 50
    download_max_mb: int = 20
    summary_max: int = 1000
    archive_days: int = 30

    # 表达风格
    tone: int = 50  # 0=毒舌 100=温柔
    verbosity: int = 40  # 0=很短 100=很详细
    emoji: int = 50  # 0=不用表情 100=很多
    catchphrase: str = ""
    reply_format: str = "text"  # text / image / voice（image/voice 后续版本）


STYLE_LABELS = {
    "tone": ((0, 30), "毒舌", (70, 100), "温柔"),
    "verbosity": ((0, 30), "很短", (70, 100), "很详细"),
    "emoji": ((0, 15), "几乎不用", (70, 100), "很多"),
}


def style_prompt(features: FeatureConfig) -> str:
    """把滑块转成给模型的自然语言约束。"""
    parts: list[str] = []
    tone = features.tone
    if tone <= 30:
        parts.append("说话偏毒舌、爱挑刺，但别侮辱人")
    elif tone >= 70:
        parts.append("说话偏温柔、会照顾对方情绪")
    verbosity = features.verbosity
    if verbosity <= 30:
        parts.append("回复尽量短，一到两句就结束")
    elif verbosity >= 70:
        parts.append("可以多说几句，把意思讲清楚，但别写成小作文")
    emoji = features.emoji
    if emoji <= 15:
        parts.append("少用或不用 emoji")
    elif emoji >= 70:
        parts.append("可以自然地多用一点 emoji")
    phrase = features.catchphrase.strip()
    if phrase:
        parts.append(f"偶尔可以带一句口头禅「{phrase}」，不要每句都带")
    if features.reply_format == "text":
        parts.append("用纯文字回复")
    return "；".join(parts)
