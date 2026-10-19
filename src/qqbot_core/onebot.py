"""OneBot 11 连接层（对接 NapCat）。

两种接法：
  reverse —— 本程序监听 port，NapCat 反过来连它（推荐：机器人先启动，NapCat 随时重启都能自动接上）
  forward —— 本程序主动连 NapCat 的 WebSocket 服务端（NapCat 里配“WS 服务端”）

协议采用 OneBot 11：事件是 JSON 推送，调用 API 是 {"action":..., "params":..., "echo":...}。
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
from collections.abc import Awaitable, Callable
from typing import Any

from websockets.exceptions import ConnectionClosed, InvalidStatus, WebSocketException

try:  # websockets >= 14 的新 asyncio 接口
    from websockets.asyncio.client import connect as ws_connect
    from websockets.asyncio.server import ServerConnection
    from websockets.asyncio.server import serve as ws_serve
except ImportError:  # 旧版本兼容
    from websockets.client import connect as ws_connect  # type: ignore
    from websockets.server import serve as ws_serve  # type: ignore

    ServerConnection = Any  # type: ignore

from .config import OneBotConfig

log = logging.getLogger("qqbot")

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


class OneBotError(RuntimeError):
    pass


class NotConnected(OneBotError):
    pass


class OneBotLink:
    def __init__(self, cfg: OneBotConfig, on_event: EventHandler, on_ready: Callable[[], Awaitable[None]] | None = None):
        self.cfg = cfg
        self.on_event = on_event
        self.on_ready = on_ready
        self.self_id: int = int(cfg.self_id or 0)
        self.nickname: str = ""
        self._ws: Any = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._counter = 0
        self._tasks: set[asyncio.Task[Any]] = set()
        self._stop = asyncio.Event()
        self._server: Any = None

    # ---------------- 生命周期 ----------------

    async def start(self) -> None:
        if self.cfg.mode == "reverse":
            await self._run_server()
        else:
            await self._run_client()

    async def stop(self) -> None:
        self._stop.set()
        if self._server is not None:
            self._server.close()
            try:
                await asyncio.wait_for(self._server.wait_closed(), 5)
            except Exception:
                pass
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass

    @property
    def connected(self) -> bool:
        return self._ws is not None

    # ---------------- 服务端模式 ----------------

    async def _run_server(self) -> None:
        host, port = self.cfg.host, self.cfg.port
        log.info("OneBot 反向接入已启动：ws://%s:%s%s（等待 NapCat 连接）", host, port, self.cfg.path)
        try:
            async with ws_serve(self._handle_conn, host, port, ping_interval=25, ping_timeout=25, max_size=None):
                await self._stop.wait()
        except OSError as exc:
            log.error("端口 %s 监听失败：%s（换个 onebot.port，或先关掉占用它的程序）", port, exc)
            raise

    async def _handle_conn(self, ws: ServerConnection) -> None:
        if not self._authorized(ws):
            await ws.close(1008, "invalid token")
            log.warning("拒绝了一个未通过鉴权的连接：%s", getattr(ws, "remote_address", "?"))
            return
        old, self._ws = self._ws, ws
        if old is not None and old is not ws:
            try:
                await old.close(1000, "replaced by new connection")
            except Exception:
                pass
        log.info("NapCat 已接入：%s", getattr(ws, "remote_address", "?"))
        # 先开始读消息，再去问登录信息，避免“等响应时没人读 socket”的死锁
        ready_task = asyncio.create_task(self._ready())
        self._tasks.add(ready_task)
        ready_task.add_done_callback(self._tasks.discard)
        try:
            async for raw in ws:
                await self._dispatch(raw)
        except ConnectionClosed:
            pass
        finally:
            if self._ws is ws:
                self._ws = None
            log.warning("NapCat 连接断开")

    def _authorized(self, ws: ServerConnection) -> bool:
        token = self.cfg.access_token.strip()
        if not token:
            return True
        try:
            request = ws.request
            headers = request.headers
            auth = headers.get("Authorization", "")
            if auth.lower().startswith("bearer ") and auth[7:].strip() == token:
                return True
            query = urllib.parse.parse_qs(urllib.parse.urlparse(request.path).query)
            if query.get("access_token", [""])[0] == token:
                return True
        except Exception:
            return False
        return False

    # ---------------- 客户端模式 ----------------

    async def _run_client(self) -> None:
        url = f"ws://{self.cfg.host}:{self.cfg.port}{self.cfg.path}"
        headers = {}
        if self.cfg.access_token:
            headers["Authorization"] = f"Bearer {self.cfg.access_token}"
        log.info("OneBot 正向连接：%s", url)
        while not self._stop.is_set():
            try:
                async with ws_connect(url, additional_headers=headers, max_size=None) as ws:
                    self._ws = ws
                    log.info("已连上 NapCat：%s", url)
                    ready_task = asyncio.create_task(self._ready())
                    self._tasks.add(ready_task)
                    ready_task.add_done_callback(self._tasks.discard)
                    async for raw in ws:
                        await self._dispatch(raw)
            except InvalidStatus as exc:
                log.error("握手被拒绝（HTTP %s），多半是 access_token 不对", exc.response.status_code)
            except (OSError, WebSocketException) as exc:
                log.warning("连接 NapCat 失败：%s（%.0f 秒后重试）", exc, self.cfg.reconnect_interval)
            except ConnectionClosed:
                log.warning("与 NapCat 的连接断开（%.0f 秒后重试）", self.cfg.reconnect_interval)
            finally:
                self._ws = None
            if self._stop.is_set():
                break
            await asyncio.sleep(max(1.0, self.cfg.reconnect_interval))

    # ---------------- 收发 ----------------

    async def _ready(self) -> None:
        if self.on_ready is not None:
            try:
                await self.on_ready()
            except Exception as exc:
                log.warning("连接就绪回调失败：%s", exc)

    async def _dispatch(self, raw: str | bytes) -> None:
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            log.debug("收到非 JSON 数据：%r", raw[:120])
            return
        if not isinstance(data, dict):
            return

        echo = data.get("echo")
        if echo is not None and echo in self._pending:
            fut = self._pending[echo]
            if not fut.done():
                fut.set_result(data)
            return

        post_type = data.get("post_type")
        if post_type == "meta_event":
            if data.get("meta_event_type") == "lifecycle":
                log.info("NapCat 生命周期事件：%s", data.get("sub_type"))
            return
        if post_type is None:
            return

        task = asyncio.create_task(self.on_event(data))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def call(self, action: str, params: dict[str, Any] | None = None, timeout: float = 20.0) -> Any:
        ws = self._ws
        if ws is None:
            raise NotConnected("还没有和 NapCat 建立连接")
        self._counter += 1
        echo = f"qqbot-{self._counter}"
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[echo] = fut
        payload = {"action": action, "params": params or {}, "echo": echo}
        try:
            await ws.send(json.dumps(payload, ensure_ascii=False))
            resp = await asyncio.wait_for(fut, timeout)
        except TimeoutError as exc:
            raise OneBotError(f"调用 {action} 超时") from exc
        finally:
            self._pending.pop(echo, None)

        retcode = resp.get("retcode")
        if resp.get("status") == "failed" or retcode not in (0, 1, None):
            raise OneBotError(f"{action} 失败：{resp.get('message') or resp.get('wording') or resp}")
        return resp.get("data")

    async def get_login_info(self) -> tuple[int, str]:
        data = await self.call("get_login_info", timeout=10)
        if isinstance(data, dict):
            self.self_id = int(data.get("user_id") or 0)
            self.nickname = str(data.get("nickname") or "")
        return self.self_id, self.nickname

    async def send_text(
        self,
        target_type: str,
        target_id: int,
        text: str,
        reply_to: int | None = None,
    ) -> Any:
        message: list[dict[str, Any]] = []
        if reply_to:
            message.append({"type": "reply", "data": {"id": str(reply_to)}})
        message.append({"type": "text", "data": {"text": text}})
        action = "send_group_msg" if target_type == "group" else "send_private_msg"
        key = "group_id" if target_type == "group" else "user_id"
        return await self.call(action, {key: target_id, "message": message})
