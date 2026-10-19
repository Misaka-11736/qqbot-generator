"""配置加载：读取项目根目录的 config.toml，缺省值内置，缺项自动补全。"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .features import FeatureConfig

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class OneBotConfig:
    """OneBot 11 (NapCat) 连接参数。"""

    mode: str = "reverse"  # reverse=本程序开 WS 服务端，等 NapCat 连过来；forward=本程序去连 NapCat 的 WS
    host: str = "127.0.0.1"
    port: int = 3002
    path: str = "/onebot/v11/ws"
    access_token: str = ""
    self_id: int = 0  # 0 表示连接后自动读取
    reconnect_interval: float = 5.0


@dataclass
class LLMConfig:
    """OpenAI 兼容接口参数（DeepSeek / 通义 / 智谱 / Ollama…都行）。"""

    provider: str = "auto"  # auto=有 key 就用 openai，否则用 mock；也可强制 openai / mock
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    api_key: str = ""
    api_key_env: str = "QQBOT_API_KEY"
    temperature: float = 0.95
    max_tokens: int = 320
    timeout: float = 60.0
    retries: int = 1


@dataclass
class ChatConfig:
    """聊天行为。"""

    prefixes: list[str] = field(default_factory=lambda: ["/", "。", "!"])
    group_chat_probability: float = 0.06  # 群里不 @ 时的搭话概率
    group_cooldown: float = 90.0  # 同一群两次主动搭话的最小间隔（秒）
    context_turns: int = 12  # 带多少轮历史给模型
    reply_delay: bool = True  # 模拟真人打字延迟
    quote_reply: bool = True  # 回复时引用触发消息
    max_reply_chars: int = 300
    split_long_reply: bool = True
    rate_limit_per_minute: int = 8  # 每人每分钟最多触发次数
    ignore_qq: list[int] = field(default_factory=list)
    enable_private: bool = True  # 私聊是否响应
    enable_group: bool = True  # 群聊是否响应
    group_scope: str = "all"  # all / whitelist / blacklist
    group_list: list[int] = field(default_factory=list)


@dataclass
class PersonaConfig:
    """人格与智商。"""

    preset: str = "snark"  # 默认人格，见 bot/prompts/
    default_iq: int = 100
    allow_everyone_set_iq: bool = True  # 群里是否允许非管理员调智商


@dataclass
class LogConfig:
    level: str = "INFO"
    dir: str = "logs"
    keep_days: int = 14


@dataclass
class Config:
    bot_name: str = "小鲸"
    admin_qq: list[int] = field(default_factory=list)
    onebot: OneBotConfig = field(default_factory=OneBotConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    chat: ChatConfig = field(default_factory=ChatConfig)
    persona: PersonaConfig = field(default_factory=PersonaConfig)
    log: LogConfig = field(default_factory=LogConfig)
    features: FeatureConfig = field(default_factory=FeatureConfig)
    data_dir: Path = PROJECT_ROOT / "data"
    source: Path | None = None

    # ---------- 派生属性 ----------

    @property
    def effective_provider(self) -> str:
        if self.llm.provider in ("mock", "openai"):
            return self.llm.provider
        return "openai" if self.resolve_api_key() else "mock"

    def resolve_api_key(self) -> str:
        if self.llm.api_key.strip():
            return self.llm.api_key.strip()
        if self.llm.api_key_env:
            return os.environ.get(self.llm.api_key_env, "").strip()
        return ""

    def toml_dump(self) -> str:
        """把当前配置渲染成 TOML 文本（给 --dump-config / 测试用）。"""
        lines = [
            f"data_dir = {_q(str(self.data_dir))}",
            f"bot_name = {_q(self.bot_name)}",
            f"admin_qq = [{', '.join(str(q) for q in self.admin_qq)}]",
            "",
            "[onebot]",
            f"mode = {_q(self.onebot.mode)}",
            f"host = {_q(self.onebot.host)}",
            f"port = {self.onebot.port}",
            f"path = {_q(self.onebot.path)}",
            f"access_token = {_q(self.onebot.access_token)}",
            f"self_id = {self.onebot.self_id}",
            f"reconnect_interval = {self.onebot.reconnect_interval}",
            "",
            "[llm]",
            f"provider = {_q(self.llm.provider)}",
            f"base_url = {_q(self.llm.base_url)}",
            f"model = {_q(self.llm.model)}",
            f"api_key = {_q(self.llm.api_key)}",
            f"api_key_env = {_q(self.llm.api_key_env)}",
            f"temperature = {self.llm.temperature}",
            f"max_tokens = {self.llm.max_tokens}",
            f"timeout = {self.llm.timeout}",
            f"retries = {self.llm.retries}",
            "",
            "[chat]",
            f"prefixes = [{', '.join(_q(p) for p in self.chat.prefixes)}]",
            f"group_chat_probability = {self.chat.group_chat_probability}",
            f"group_cooldown = {self.chat.group_cooldown}",
            f"context_turns = {self.chat.context_turns}",
            f"reply_delay = {str(self.chat.reply_delay).lower()}",
            f"quote_reply = {str(self.chat.quote_reply).lower()}",
            f"max_reply_chars = {self.chat.max_reply_chars}",
            f"split_long_reply = {str(self.chat.split_long_reply).lower()}",
            f"rate_limit_per_minute = {self.chat.rate_limit_per_minute}",
            f"ignore_qq = [{', '.join(str(q) for q in self.chat.ignore_qq)}]",
            f"enable_private = {str(self.chat.enable_private).lower()}",
            f"enable_group = {str(self.chat.enable_group).lower()}",
            f"group_scope = {_q(self.chat.group_scope)}",
            f"group_list = [{', '.join(str(q) for q in self.chat.group_list)}]",
            "",
            "[features]",
            f"archive = {str(self.features.archive).lower()}",
            f"summarize = {str(self.features.summarize).lower()}",
            f"search = {str(self.features.search).lower()}",
            f"download = {str(self.features.download).lower()}",
            f"gen_image = {str(self.features.gen_image).lower()}",
            f"gen_file = {str(self.features.gen_file).lower()}",
            f"classify = {str(self.features.classify).lower()}",
            f"vision = {str(self.features.vision).lower()}",
            f"voice_in = {str(self.features.voice_in).lower()}",
            f"voice_out = {str(self.features.voice_out).lower()}",
            f"search_daily_limit = {self.features.search_daily_limit}",
            f"download_max_mb = {self.features.download_max_mb}",
            f"summary_max = {self.features.summary_max}",
            f"archive_days = {self.features.archive_days}",
            f"tone = {self.features.tone}",
            f"verbosity = {self.features.verbosity}",
            f"emoji = {self.features.emoji}",
            f"catchphrase = {_q(self.features.catchphrase)}",
            f"reply_format = {_q(self.features.reply_format)}",
            "",
            "[persona]",
            f"preset = {_q(self.persona.preset)}",
            f"default_iq = {self.persona.default_iq}",
            f"allow_everyone_set_iq = {str(self.persona.allow_everyone_set_iq).lower()}",
            "",
            "[log]",
            f"level = {_q(self.log.level)}",
            f"dir = {_q(self.log.dir)}",
            f"keep_days = {self.log.keep_days}",
        ]
        return "\n".join(lines) + "\n"


def _q(value: str) -> str:
    """TOML 基本字符串转义。"""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _pick(section: dict[str, Any], key: str, current: Any) -> Any:
    """从 TOML 段里取一个值，类型不符时回退默认值。"""
    if key not in section:
        return current
    value = section[key]
    if isinstance(current, bool):
        return bool(value)
    if isinstance(current, int) and not isinstance(current, bool):
        try:
            return int(value)
        except (TypeError, ValueError):
            return current
    if isinstance(current, float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return current
    if isinstance(current, list):
        return list(value) if isinstance(value, list) else current
    return value


def load_config(path: str | Path | None = None) -> Config:
    """读取 config.toml；文件不存在时返回全默认配置。"""
    cfg = Config()
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path))
    else:
        env_path = os.environ.get("QQBOT_CONFIG", "").strip()
        if env_path:
            candidates.append(Path(env_path))
        candidates.append(PROJECT_ROOT / "config.toml")
        candidates.append(Path.cwd() / "config.toml")

    for cand in candidates:
        if cand.is_file():
            raw = tomllib.loads(cand.read_text("utf-8"))
            cfg.source = cand
            _apply(cfg, raw)
            break
    return cfg


def _apply(cfg: Config, raw: dict[str, Any]) -> None:
    cfg.bot_name = _pick(raw, "bot_name", cfg.bot_name)
    cfg.admin_qq = [int(x) for x in _pick(raw, "admin_qq", cfg.admin_qq)]

    ob = raw.get("onebot", {})
    cfg.onebot.mode = _pick(ob, "mode", cfg.onebot.mode)
    cfg.onebot.host = _pick(ob, "host", cfg.onebot.host)
    cfg.onebot.port = _pick(ob, "port", cfg.onebot.port)
    cfg.onebot.path = _pick(ob, "path", cfg.onebot.path)
    cfg.onebot.access_token = _pick(ob, "access_token", cfg.onebot.access_token)
    cfg.onebot.self_id = _pick(ob, "self_id", cfg.onebot.self_id)
    cfg.onebot.reconnect_interval = _pick(ob, "reconnect_interval", cfg.onebot.reconnect_interval)

    llm = raw.get("llm", {})
    cfg.llm.provider = _pick(llm, "provider", cfg.llm.provider)
    cfg.llm.base_url = _pick(llm, "base_url", cfg.llm.base_url)
    cfg.llm.model = _pick(llm, "model", cfg.llm.model)
    cfg.llm.api_key = _pick(llm, "api_key", cfg.llm.api_key)
    cfg.llm.api_key_env = _pick(llm, "api_key_env", cfg.llm.api_key_env)
    cfg.llm.temperature = _pick(llm, "temperature", cfg.llm.temperature)
    cfg.llm.max_tokens = _pick(llm, "max_tokens", cfg.llm.max_tokens)
    cfg.llm.timeout = _pick(llm, "timeout", cfg.llm.timeout)
    cfg.llm.retries = _pick(llm, "retries", cfg.llm.retries)

    chat = raw.get("chat", {})
    cfg.chat.prefixes = [str(p) for p in _pick(chat, "prefixes", cfg.chat.prefixes)]
    cfg.chat.group_chat_probability = _pick(chat, "group_chat_probability", cfg.chat.group_chat_probability)
    cfg.chat.group_cooldown = _pick(chat, "group_cooldown", cfg.chat.group_cooldown)
    cfg.chat.context_turns = _pick(chat, "context_turns", cfg.chat.context_turns)
    cfg.chat.reply_delay = _pick(chat, "reply_delay", cfg.chat.reply_delay)
    cfg.chat.quote_reply = _pick(chat, "quote_reply", cfg.chat.quote_reply)
    cfg.chat.max_reply_chars = _pick(chat, "max_reply_chars", cfg.chat.max_reply_chars)
    cfg.chat.split_long_reply = _pick(chat, "split_long_reply", cfg.chat.split_long_reply)
    cfg.chat.rate_limit_per_minute = _pick(chat, "rate_limit_per_minute", cfg.chat.rate_limit_per_minute)
    cfg.chat.ignore_qq = [int(x) for x in _pick(chat, "ignore_qq", cfg.chat.ignore_qq)]
    cfg.chat.enable_private = _pick(chat, "enable_private", cfg.chat.enable_private)
    cfg.chat.enable_group = _pick(chat, "enable_group", cfg.chat.enable_group)
    cfg.chat.group_scope = _pick(chat, "group_scope", cfg.chat.group_scope)
    cfg.chat.group_list = [int(x) for x in _pick(chat, "group_list", cfg.chat.group_list)]

    feat = raw.get("features", {})
    for name in ("archive", "summarize", "search", "download", "gen_image", "gen_file", "classify", "vision", "voice_in", "voice_out"):
        setattr(cfg.features, name, bool(_pick(feat, name, getattr(cfg.features, name))))
    for name in ("search_daily_limit", "download_max_mb", "summary_max", "archive_days", "tone", "verbosity", "emoji"):
        setattr(cfg.features, name, int(_pick(feat, name, getattr(cfg.features, name))))
    cfg.features.catchphrase = str(_pick(feat, "catchphrase", cfg.features.catchphrase))
    cfg.features.reply_format = str(_pick(feat, "reply_format", cfg.features.reply_format))

    persona = raw.get("persona", {})
    cfg.persona.preset = _pick(persona, "preset", cfg.persona.preset)
    cfg.persona.default_iq = _pick(persona, "default_iq", cfg.persona.default_iq)
    cfg.persona.allow_everyone_set_iq = _pick(persona, "allow_everyone_set_iq", cfg.persona.allow_everyone_set_iq)

    log = raw.get("log", {})
    cfg.log.level = _pick(log, "level", cfg.log.level)
    cfg.log.dir = _pick(log, "dir", cfg.log.dir)

    data_dir = raw.get("data_dir")
    if isinstance(data_dir, str) and data_dir.strip():
        cfg.data_dir = PROJECT_ROOT / data_dir.strip()


def validate(cfg: Config) -> list[str]:
    """返回严重错误列表（为空表示可以启动）。"""
    errors: list[str] = []
    if cfg.onebot.mode not in ("reverse", "forward"):
        errors.append(f"onebot.mode 只能是 reverse 或 forward，当前为 {cfg.onebot.mode!r}")
    if not (1 <= cfg.onebot.port <= 65535):
        errors.append(f"onebot.port 非法：{cfg.onebot.port}")
    if not (0.0 <= cfg.chat.group_chat_probability <= 1.0):
        errors.append("chat.group_chat_probability 必须在 0~1 之间")
    if not (1 <= cfg.persona.default_iq <= 200):
        errors.append("persona.default_iq 必须在 1~200 之间")
    if cfg.llm.provider not in ("auto", "openai", "mock"):
        errors.append("llm.provider 只能是 auto / openai / mock")
    return errors
