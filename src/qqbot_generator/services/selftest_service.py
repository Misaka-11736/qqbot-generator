"""内置自检：不连 QQ、不花钱，检查安装是否健康。"""

from __future__ import annotations

import asyncio
import socket

from qqbot_core.config import load_config, validate
from qqbot_core.llm import MockBrain
from qqbot_core.message import parse_event
from qqbot_core.persona import PRESETS, build_system_prompt, load_preset, tier_of

from .. import paths
from . import napcat


def check_data_dir() -> tuple[bool, str]:
    try:
        probe = paths.data_dir() / ".write_test"
        probe.write_text("ok", "utf-8")
        probe.unlink()
        return True, str(paths.data_dir())
    except OSError as exc:
        return False, f"不可写：{exc}"


def check_config() -> tuple[bool, str]:
    path = paths.config_path()
    if not path.is_file():
        return False, "config.toml 不存在"
    try:
        cfg = load_config(path)
    except Exception as exc:
        return False, f"解析失败：{exc}"
    errors = validate(cfg)
    if errors:
        return False, "；".join(errors)
    return True, f"{cfg.bot_name} · {cfg.llm.model} · 端口 {cfg.onebot.port}"


def check_prompts() -> tuple[bool, str]:
    missing = [name for name in PRESETS if not load_preset(name).strip()]
    if missing:
        return False, "缺少人格：" + "、".join(missing)
    return True, f"{len(PRESETS)} 份人格就绪"


def check_prompt_build() -> tuple[bool, str]:
    prompt = build_system_prompt(
        preset_text=load_preset("snark"),
        persona_label=PRESETS["snark"],
        bot_name="小鲸鱼",
        iq=20,
        user_name="测试",
        is_group=False,
    )
    ok = "降智模式" in prompt and "小鲸鱼" in prompt and len(prompt) > 100
    return ok, f"{len(prompt)} 字" if ok else "提示词构建异常"


def check_message_parse() -> tuple[bool, str]:
    event = {
        "post_type": "message",
        "message_type": "group",
        "group_id": 1,
        "user_id": 2,
        "message_id": 3,
        "self_id": 10000,
        "sender": {"card": "测试"},
        "message": [{"type": "at", "data": {"qq": "10000"}}, {"type": "text", "data": {"text": " 你好"}}],
    }
    incoming = parse_event(event, 10000)
    ok = bool(incoming and incoming.at_me and incoming.text == "你好" and incoming.conversation_key == "group:1")
    return ok, incoming.conversation_key if incoming else "解析失败"


def check_mock_brain() -> tuple[bool, str]:
    brain = MockBrain()

    async def ask() -> str:
        return await brain.complete(
            [{"role": "user", "content": "我在设置里给你智商调低了"}], meta={"iq": 20}
        )

    try:
        reply = asyncio.run(ask())
    except Exception as exc:
        return False, f"离线大脑异常：{exc}"
    ok = "顺眼" in reply
    return ok, reply


def check_iq_tiers() -> tuple[bool, str]:
    labels = [tier_of(iq).label for iq in (1, 45, 80, 120, 160, 200)]
    ok = len(set(labels)) == 6
    return ok, " / ".join(labels)


def check_port(port: int) -> tuple[bool, str]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True, f"{port} 可用"
        except OSError:
            return False, f"{port} 被占用"


def check_napcat() -> tuple[bool, str]:
    found = napcat.find_candidates()
    if not found:
        return False, "没找到 NapCat，去「NapCat」页安装或选择目录"
    return True, str(found[0])


def run_all(port: int = 3002) -> list[dict[str, object]]:
    checks = [
        ("数据目录", check_data_dir),
        ("配置文件", check_config),
        ("人格文件", check_prompts),
        ("提示词构建", check_prompt_build),
        ("消息解析", check_message_parse),
        ("智商档位", check_iq_tiers),
        ("离线大脑", check_mock_brain),
        ("监听端口", lambda: check_port(port)),
        ("NapCat", check_napcat),
    ]
    results: list[dict[str, object]] = []
    for name, func in checks:
        try:
            ok, detail = func()
        except Exception as exc:
            ok, detail = False, f"异常：{exc}"
        results.append({"name": name, "ok": ok, "detail": detail})
    return results
