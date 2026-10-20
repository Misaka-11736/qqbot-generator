"""核心逻辑单元测试：消息解析、指令、人格、离线大脑、HTTP 协议、配置。"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qqbot_core.commands import parse_command
from qqbot_core.config import Config, load_config, validate
from qqbot_core.llm import ChatLLM, LLMError, MockBrain
from qqbot_core.message import parse_event
from qqbot_core.persona import TIERS, build_system_prompt, style_of, tier_of
from qqbot_core.util import clean_reply, split_text

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def test_message() -> None:
    print("[消息解析]")
    event = {
        "post_type": "message",
        "message_type": "group",
        "group_id": 123,
        "user_id": 456,
        "message_id": 789,
        "self_id": 10000,
        "sender": {"card": "阿伟"},
        "message": [
            {"type": "at", "data": {"qq": "10000"}},
            {"type": "text", "data": {"text": " 帮我写个作业"}},
        ],
    }
    incoming = parse_event(event, 10000)
    check("数组消息能解析", incoming is not None)
    assert incoming is not None
    check("@ 自己能被识别", incoming.at_me)
    check("文本去掉多余空格", incoming.text == "帮我写个作业", incoming.text)
    check("会话键正确", incoming.conversation_key == "group:123")
    check("群目标 id", incoming.target_id == 123)

    cq = {
        "post_type": "message",
        "message_type": "private",
        "user_id": 456,
        "message_id": 790,
        "message": "[CQ:reply,id=555][CQ:at,qq=10000] 在吗[CQ:face,id=14]",
    }
    parsed = parse_event(cq, 10000)
    assert parsed is not None
    check("CQ 码 reply 能解析", parsed.reply_id == 555, str(parsed.reply_id))
    check("CQ 码 at 能识别", parsed.at_me)
    check("表情转占位符", "[表情]" in parsed.text, parsed.text)

    self_msg = parse_event({**event, "user_id": 10000}, 10000)
    assert self_msg is not None
    check("自己发的消息被标记", self_msg.is_self)


def test_commands() -> None:
    print("[指令解析]")
    check("/智商 20", parse_command("/智商 20", ["/"], False) == ("智商", "20"))
    check("。重置", parse_command("。重置", ["/", "。"], False) == ("重置", ""))
    check("普通聊天不是指令", parse_command("你好呀", ["/"], False) is None)
    check("群聊不 @ 时裸指令无效", parse_command("智商", ["/"], False) is None)
    check("私聊裸指令有效", parse_command("智商", ["/"], True) == ("智商", ""))
    check("未知指令忽略", parse_command("/唱歌", ["/"], True) is None)


def test_persona() -> None:
    print("[人格与智商]")
    check("1 是降智档", tier_of(1).key == "dumb")
    check("200 是超频档", tier_of(200).key == "overclock")
    check("100 是机灵档", tier_of(100).key == "smart")
    low_t, _, low_chars = style_of(20)
    high_t, _, high_chars = style_of(190)
    check("低智商温度更高", low_t > high_t)
    check("低智商回复更短", low_chars < high_chars)
    check("档位覆盖 1~200", all(TIERS[i].max_iq + 1 == TIERS[i + 1].min_iq for i in range(len(TIERS) - 1)))
    prompt = build_system_prompt(
        preset_text="你是{bot_name}",
        persona_label="损友",
        bot_name="小鲸鱼",
        iq=20,
        user_name="阿伟",
        is_group=True,
        group_name="相亲相爱一家人",
    )
    check("提示词含人名", "阿伟" in prompt)
    check("提示词含智商", "20/200" in prompt)
    check("提示词含降智设定", "降智模式" in prompt)


def test_llm() -> None:
    print("[离线大脑]")
    brain = MockBrain()

    async def ask(text: str, iq: int) -> str:
        return await brain.complete([{"role": "user", "content": text}], meta={"iq": iq})

    reply = asyncio.run(ask("我在设置里给你智商调低了", 20))
    check("名场面台词", "顺眼" in reply, reply)
    low = asyncio.run(ask("今天上班好累", 15))
    high = asyncio.run(ask("今天上班好累", 190))
    check("不同智商回复不同", low != high, f"{low} / {high}")
    check("回复不为空", bool(low) and bool(high))


class _OpenAIHandler(BaseHTTPRequestHandler):
    fail = False
    seen: dict[str, str] = {}

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        _OpenAIHandler.seen = {
            "path": self.path,
            "auth": self.headers.get("Authorization", ""),
            "model": str(body.get("model", "")),
            "role": str((body.get("messages") or [{}])[0].get("role", "")),
        }
        if _OpenAIHandler.fail:
            payload = b'{"error":{"message":"invalid api key"}}'
            self.send_response(401)
        else:
            payload = json.dumps({"choices": [{"message": {"content": "收到。"}}]}).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args) -> None:
        pass


def test_http_llm() -> None:
    print("[模型接口协议]")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _OpenAIHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    client = ChatLLM(f"http://127.0.0.1:{port}/v1", "test-key", "test-model", timeout=5, retries=0)
    try:
        reply = asyncio.run(client.complete([{"role": "user", "content": "在吗"}]))
        check("能解析标准返回", reply == "收到。", reply)
        check("请求路径正确", _OpenAIHandler.seen.get("path") == "/v1/chat/completions", str(_OpenAIHandler.seen))
        check("带上 Authorization", _OpenAIHandler.seen.get("auth") == "Bearer test-key")
        check("带上模型名", _OpenAIHandler.seen.get("model") == "test-model")
        _OpenAIHandler.fail = True
        failed = False
        try:
            asyncio.run(client.complete([{"role": "user", "content": "在吗"}]))
        except LLMError:
            failed = True
        check("401 会抛 LLMError", failed)
    finally:
        server.shutdown()
        server.server_close()


def test_text() -> None:
    print("[文本处理]")
    check("去引号", clean_reply("“你好呀”") == "你好呀")
    check("去角色前缀", clean_reply("小鲸鱼：在的") == "在的")
    check("去 Markdown", clean_reply("**真的**吗") == "真的吗")
    parts = split_text("第一句话。" * 20, limit=60)
    check("长文本会分段", len(parts) > 1)
    check("分段不丢内容", "".join(parts).replace(" ", "") == ("第一句话。" * 20).replace(" ", ""))


def test_config() -> None:
    print("[配置]")
    cfg = Config()
    check("默认值合法", validate(cfg) == [], str(validate(cfg)))
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.toml"
        path.write_text(cfg.toml_dump(), "utf-8")
        loaded = load_config(path)
        check("写出去还能读回来", loaded.bot_name == cfg.bot_name and loaded.onebot.port == cfg.onebot.port)
        check("data_dir 能往返", str(loaded.data_dir) == str(cfg.data_dir))
    check("provider 可推导", cfg.effective_provider in ("mock", "openai"))


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    print(f"Python {sys.version.split()[0]}")
    test_message()
    test_commands()
    test_persona()
    test_llm()
    test_http_llm()
    test_text()
    test_config()
    print()
    print(f"通过 {PASS} 项，失败 {FAIL} 项")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
