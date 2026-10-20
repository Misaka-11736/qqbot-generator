"""端到端自测：用假的 NapCat 陪机器人演一遍，不需要登录 QQ。

覆盖两种接入方式：
  forward —— 假 NapCat 当 WebSocket 服务端，机器人连过来
  reverse —— 假 NapCat 当 WebSocket 客户端，连机器人的监听端口（默认模式）

流程：起假 NapCat → 用临时配置拉起机器人子进程 → 发私聊/指令/群 @ 消息 → 断言回复。

用法：python tools/e2e_test.py [--mode forward|reverse|both]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from websockets.asyncio.client import connect as ws_connect
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from qqbot_core.util import ensure_utf8_stdout

BOT_QQ = 10000
USER_QQ = 10001
GROUP_ID = 654321
WS_PATH = "/onebot/v11/ws"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def message_event(text: str, *, group: bool, message_id: int, at_bot: bool = False, user_id: int = USER_QQ) -> dict[str, Any]:
    segments: list[dict[str, Any]] = []
    if at_bot:
        segments.append({"type": "at", "data": {"qq": str(BOT_QQ)}})
    segments.append({"type": "text", "data": {"text": text}})
    event: dict[str, Any] = {
        "post_type": "message",
        "message_type": "group" if group else "private",
        "message_id": message_id,
        "user_id": user_id,
        "self_id": BOT_QQ,
        "time": int(time.time()),
        "sender": {"nickname": "测试用户", "card": "测试用户"},
        "message": segments,
        "raw_message": text,
    }
    if group:
        event["group_id"] = GROUP_ID
    return event


class FakeNapCat:
    """假 NapCat 的公共逻辑：处理机器人发来的 API 调用，记录回复。"""

    def __init__(self) -> None:
        self.ready = asyncio.Event()
        self.replies: list[dict[str, Any]] = []
        self.ws: Any = None
        self._counter = 0
        self._reply_event = asyncio.Event()

    async def _process(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return
        action = data.get("action")
        echo = data.get("echo")
        params = data.get("params") or {}
        if action == "get_login_info":
            self.ready.set()
            await self._respond(echo, {"user_id": BOT_QQ, "nickname": "小鲸鱼"})
        elif action in ("send_private_msg", "send_group_msg", "send_msg"):
            self._counter += 1
            self.replies.append(
                {
                    "action": action,
                    "text": self._extract_text(params.get("message")),
                    "group_id": params.get("group_id"),
                    "user_id": params.get("user_id"),
                }
            )
            self._reply_event.set()
            await self._respond(echo, {"message_id": 9000 + self._counter})
        else:
            await self._respond(echo, {})

    async def _respond(self, echo: Any, data: dict[str, Any]) -> None:
        if self.ws is None:
            return
        await self.ws.send(json.dumps({"status": "ok", "retcode": 0, "data": data, "echo": echo}, ensure_ascii=False))

    @staticmethod
    def _extract_text(message: Any) -> str:
        if isinstance(message, str):
            return message
        if isinstance(message, list):
            return "".join(str(seg.get("data", {}).get("text", "")) for seg in message if seg.get("type") == "text")
        return ""

    async def push(self, event: dict[str, Any]) -> None:
        if self.ws is None:
            raise RuntimeError("机器人还没连上来")
        await self.ws.send(json.dumps(event, ensure_ascii=False))

    async def wait_replies(self, count: int, timeout: float = 15.0) -> list[dict[str, Any]]:
        deadline = time.monotonic() + timeout
        while len(self.replies) < count and time.monotonic() < deadline:
            self._reply_event.clear()
            try:
                await asyncio.wait_for(self._reply_event.wait(), 0.3)
            except TimeoutError:
                pass
        return self.replies


class FakeNapCatServer(FakeNapCat):
    """forward 模式：假 NapCat 监听端口，机器人连进来。"""

    def __init__(self, port: int):
        super().__init__()
        self.port = port
        self._server: Any = None

    async def start(self) -> None:
        self._server = await serve(self._handler, "127.0.0.1", self.port, max_size=None)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            try:
                await asyncio.wait_for(self._server.wait_closed(), 3)
            except Exception:
                pass

    async def _handler(self, ws) -> None:
        self.ws = ws
        try:
            async for raw in ws:
                await self._process(raw)
        except (ConnectionClosed, ConnectionResetError, OSError):
            pass
        finally:
            self.ws = None


class FakeNapCatClient(FakeNapCat):
    """reverse 模式：假 NapCat 连机器人的监听端口。"""

    def __init__(self, port: int):
        super().__init__()
        self.port = port
        self._cm: Any = None

    async def connect(self, timeout: float = 25.0) -> None:
        url = f"ws://127.0.0.1:{self.port}{WS_PATH}"
        deadline = time.monotonic() + timeout
        last: Exception | None = None
        while time.monotonic() < deadline:
            try:
                self._cm = ws_connect(url, max_size=None)
                self.ws = await self._cm.__aenter__()
                return
            except (OSError, ConnectionClosed, ConnectionResetError) as exc:
                last = exc
                await asyncio.sleep(0.4)
        raise RuntimeError(f"连不上机器人 {url}: {last}")

    async def stop(self) -> None:
        if self._cm is not None:
            try:
                await self._cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._cm = None
            self.ws = None

    async def loop(self) -> None:
        try:
            async for raw in self.ws:
                await self._process(raw)
        except (ConnectionClosed, ConnectionResetError, OSError):
            pass


def write_config(path: Path, port: int, mode: str, data_dir: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'''bot_name = "小鲸鱼"
admin_qq = [10001]
data_dir = "{data_dir.as_posix()}"

[onebot]
mode = "{mode}"
host = "127.0.0.1"
port = {port}
path = "{WS_PATH}"
access_token = ""
self_id = 0
reconnect_interval = 2.0

[llm]
provider = "mock"

[chat]
prefixes = ["/"]
group_chat_probability = 0.0
group_cooldown = 1.0
context_turns = 8
reply_delay = false
quote_reply = false
max_reply_chars = 300
rate_limit_per_minute = 50

[persona]
preset = "snark"
default_iq = 100
allow_everyone_set_iq = true

[log]
level = "INFO"
dir = "logs"
keep_days = 7
''',
        "utf-8",
    )


STEPS = [
    ("私聊", "在吗", dict(group=False), ""),
    ("私聊", "/reset", dict(group=False), "已重置"),
    ("私聊", "我在设置里给你智商调低了", dict(group=False), "顺眼"),
    ("群聊@", "你好", dict(group=True, at_bot=True), ""),
    ("群聊指令", "/reset", dict(group=True, at_bot=True), "已重置"),
]


async def run_case(mode: str) -> tuple[bool, list[tuple[str, str, str]]]:
    port = free_port()
    work = ROOT / "build" / "e2e"
    work.mkdir(parents=True, exist_ok=True)
    config_path = work / f"config-{mode}.toml"
    memory_path = work / "memory.json"
    if memory_path.exists():
        memory_path.unlink()
    write_config(config_path, port, mode, work)

    napcat: FakeNapCat
    if mode == "forward":
        server = FakeNapCatServer(port)
        await server.start()
        napcat = server
    else:
        client = FakeNapCatClient(port)
        napcat = client

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["QQBOT_DATA_DIR"] = str(work)
    log_path = work / f"bot-{mode}.log"
    log_file = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "qqbot_generator", "--run-bot", "--config", str(config_path)],
        cwd=str(ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        env=env,
    )

    transcript: list[tuple[str, str, str]] = []
    ok = True
    try:
        await asyncio.sleep(1.2 if mode == "forward" else 1.0)
        if mode == "reverse":
            assert isinstance(napcat, FakeNapCatClient)
            await napcat.connect()
            _reader = asyncio.create_task(napcat.loop())  # noqa: RUF006
        try:
            await asyncio.wait_for(napcat.ready.wait(), 20)
        except TimeoutError:
            return False, [("!", "机器人没有发来 get_login_info", "查看 " + str(log_path))]

        await asyncio.sleep(0.4)
        for index, (label, text, kwargs, expect) in enumerate(STEPS, 1):
            before = len(napcat.replies)
            await napcat.push(message_event(text, message_id=1000 + index, **kwargs))
            replies = await napcat.wait_replies(before + 1, timeout=15)
            new = replies[before:]
            if not new:
                transcript.append((label, text, "（没有回复）"))
                ok = False
                continue
            answer = " / ".join(item["text"] for item in new)
            transcript.append((label, text, answer))
            if expect and expect not in answer:
                ok = False
                transcript.append(("  !", f"期望包含“{expect}”", answer))
        await asyncio.sleep(0.3)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_file.close()
        if isinstance(napcat, FakeNapCatServer):
            await napcat.stop()
        else:
            await napcat.stop()
    return ok, transcript


async def run(modes: list[str]) -> int:
    all_ok = True
    for mode in modes:
        ok, transcript = await run_case(mode)
        all_ok = all_ok and ok
        title = "forward（机器人连 NapCat）" if mode == "forward" else "reverse（NapCat 连机器人）"
        print()
        print("=" * 78)
        print(f"端到端自测 · {title}")
        print("=" * 78)
        for label, sent, got in transcript:
            if label == "  !":
                print(f"[FAIL] 期望：{sent}")
                print(f"       实际：{got}")
            else:
                print(f"[{label}] 你：{sent}")
                print(f"       小鲸鱼：{got}")
        print("-" * 78)
        print("结果：", "通过 ✅" if ok else "失败 ❌")
    print()
    print("总结果：", "全部通过 ✅" if all_ok else "有失败项 ❌")
    return 0 if all_ok else 2


def main() -> int:
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["forward", "reverse", "both"], default="both")
    args = parser.parse_args()
    modes = ["forward", "reverse"] if args.mode == "both" else [args.mode]
    try:
        return asyncio.run(run(modes))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
