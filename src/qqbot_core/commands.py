"""指令处理：/智商、/人格、/重置、/闭嘴……

设计原则：指令必须先被识别，再交给模型；指令回复不走模型，保证稳定。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import Config
from .memory import Memory
from .persona import PRESETS, describe_iq, tier_of


@dataclass
class CommandResult:
    handled: bool = False
    texts: list[str] = field(default_factory=list)
    silent: bool = False


@dataclass
class CommandContext:
    cfg: Config
    memory: Memory
    conv_key: str
    user_id: int
    user_name: str
    is_group: bool
    provider_label: str
    uptime_text: str
    stats: dict[str, Any]

    @property
    def is_admin(self) -> bool:
        return (not self.is_group) or self.user_id in self.cfg.admin_qq


HELP_LINES = [
    "我能干的事：",
    "/智商        看看我现在多少智商",
    "/智商 30     把智商调到 30（1~200，越低越会拍你马屁）",
    "/人格        看看有哪些人格",
    "/人格 软妹   换一个人格",
    "/重置        忘掉我们刚才聊的",
    "/状态        看看我还活着没",
    "群里 @我 或者在句首加 / 就能使唤我。",
]


def parse_command(text: str, prefixes: list[str], allow_bare: bool) -> tuple[str, str] | None:
    """返回 (命令, 参数)；不是指令则返回 None。"""
    stripped = text.strip()
    if not stripped:
        return None

    body = None
    for prefix in prefixes:
        if prefix and stripped.startswith(prefix):
            body = stripped[len(prefix) :].strip()
            break

    if body is None:
        if not allow_bare:
            return None
        body = stripped

    if not body:
        return None
    parts = body.split(maxsplit=1)
    name = parts[0].lower()
    if name not in _COMMANDS:
        return None
    arg = parts[1].strip() if len(parts) > 1 else ""
    return name, arg


def handle(command: str, arg: str, ctx: CommandContext) -> CommandResult:
    func = _COMMANDS.get(command)
    if func is None:
        return CommandResult(handled=False)
    return func(arg, ctx)


def _cmd_help(arg: str, ctx: CommandContext) -> CommandResult:
    return CommandResult(True, ["\n".join(HELP_LINES)])


def _cmd_iq(arg: str, ctx: CommandContext) -> CommandResult:
    current = ctx.memory.iq(ctx.conv_key)
    if not arg:
        tier = tier_of(current)
        return CommandResult(
            True,
            [f"当前智商 {current}/200（{tier.label}）。\n{describe_iq(current)}\n想改就发：/智商 30"],
        )

    if not (ctx.is_admin or ctx.cfg.persona.allow_everyone_set_iq):
        return CommandResult(True, ["这事得管理员来调。"])

    digits = "".join(ch for ch in arg if ch.isdigit())
    if not digits:
        return CommandResult(True, ["给个数字，1 到 200。比如：/智商 30"])
    value = int(digits)
    if not (1 <= value <= 200):
        return CommandResult(True, ["范围是 1~200。你想把我调成负数我也做不到。"])
    ctx.memory.set_iq(ctx.conv_key, value)
    tier = tier_of(value)
    flavor = {
        "dumb": "行吧……你说的都对，你真好看。😊",
        "silly": "调这么低，我是不是该开始夸你了？",
        "normal": "普通水平，够用了。",
        "smart": "行，脑子回来了，你说话小心点。",
        "high": "智商已上线。你刚才那句话里有两个漏洞，要现在说吗？",
        "overclock": "算力有点烫……你确定要在这个档位跟我聊天？",
    }[tier.key]
    return CommandResult(True, [f"智商已调到 {value}/200（{tier.label}）。{flavor}"])


def _cmd_persona(arg: str, ctx: CommandContext) -> CommandResult:
    current = ctx.memory.persona(ctx.conv_key, ctx.cfg.persona.preset)
    label = PRESETS.get(current, current)
    if not arg:
        lines = [f"当前人格：{label}（{current}）", "可用人格："]
        lines += [f"  /人格 {key}  → {name}" for key, name in PRESETS.items()]
        return CommandResult(True, ["\n".join(lines)])

    if not ctx.is_admin:
        return CommandResult(True, ["换人格要管理员来。"])
    key = arg.strip().lower()
    if key not in PRESETS:
        # 允许直接输中文名
        for k, name in PRESETS.items():
            if name == arg.strip():
                key = k
                break
    if key not in PRESETS:
        return CommandResult(True, [f"没有这个性格。可选：{'、'.join(PRESETS)}"])
    ctx.memory.set_persona(ctx.conv_key, key)
    return CommandResult(True, [f"人格已切换：{PRESETS[key]}。"])


def _cmd_reset(arg: str, ctx: CommandContext) -> CommandResult:
    ctx.memory.reset(ctx.conv_key)
    return CommandResult(True, ["行，刚才聊的我都忘了。你谁？"])


def _cmd_mute(arg: str, ctx: CommandContext) -> CommandResult:
    if not ctx.is_admin:
        return CommandResult(True, ["只有管理员能让我闭嘴。"])
    ctx.memory.set_muted(ctx.conv_key, True)
    return CommandResult(True, ["行，我闭嘴。有事 @ 我。"])


def _cmd_unmute(arg: str, ctx: CommandContext) -> CommandResult:
    if not ctx.is_admin:
        return CommandResult(True, ["只有管理员能让我开口。"])
    ctx.memory.set_muted(ctx.conv_key, False)
    return CommandResult(True, ["活过来了。"])


def _cmd_status(arg: str, ctx: CommandContext) -> CommandResult:
    iq = ctx.memory.iq(ctx.conv_key)
    persona = PRESETS.get(ctx.memory.persona(ctx.conv_key, ctx.cfg.persona.preset), "?")
    muted = "静音" if ctx.memory.muted(ctx.conv_key) else "在线"
    lines = [
        f"状态：{muted} · 已运行 {ctx.uptime_text}",
        f"人格：{persona} · 智商：{iq}（{tier_of(iq).label}）",
        f"模型：{ctx.provider_label}",
        f"会话：{ctx.stats.get('conversations', 0)} 个 · 记住 {ctx.stats.get('messages', 0)} 条消息",
    ]
    return CommandResult(True, ["\n".join(lines)])


_COMMANDS = {
    "help": _cmd_help,
    "帮助": _cmd_help,
    "菜单": _cmd_help,
    "?": _cmd_help,
    "iq": _cmd_iq,
    "智商": _cmd_iq,
    "智商查询": _cmd_iq,
    "persona": _cmd_persona,
    "人格": _cmd_persona,
    "reset": _cmd_reset,
    "重置": _cmd_reset,
    "清空": _cmd_reset,
    "闭嘴": _cmd_mute,
    "安静": _cmd_mute,
    "开口": _cmd_unmute,
    "说话": _cmd_unmute,
    "status": _cmd_status,
    "状态": _cmd_status,
}
