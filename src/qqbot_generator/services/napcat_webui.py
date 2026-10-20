"""NapCat WebUI API 客户端：密码登录、二维码、内置终端。"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from typing import Any


class WebUIError(RuntimeError):
    pass


class NapCatWebUI:
    def __init__(self, base: str = "http://127.0.0.1:6099"):
        self.base = base.rstrip("/")
        self.token = ""

    # ---------- 基础请求 ----------

    def _request(self, path: str, payload: dict | None = None, timeout: float = 8.0) -> Any:
        url = self.base + path
        data = json.dumps(payload or {}).encode("utf-8") if payload is not None else b"{}"
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, data=data, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise WebUIError(f"HTTP {exc.code}: {body[:200]}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise WebUIError(f"连不上 NapCat WebUI：{exc}") from exc
        try:
            data_obj = json.loads(body)
        except json.JSONDecodeError as exc:
            raise WebUIError(f"返回不是 JSON：{body[:120]}") from exc
        if data_obj.get("code") not in (0, None):
            raise WebUIError(str(data_obj.get("message") or data_obj))
        return data_obj.get("data")

    # ---------- 鉴权 ----------

    def login(self, password: str) -> bool:
        digest = hashlib.sha256((password + ".napcat").encode("utf-8")).hexdigest()
        data = self._request("/api/auth/login", {"hash": digest, "totpCode": ""})
        token = ""
        if isinstance(data, dict):
            token = data.get("Credential") or data.get("token") or data.get("accessToken") or ""
        elif data:
            token = str(data)
        if not token:
            raise WebUIError("登录成功但没有拿到凭证")
        self.token = str(token)
        return True

    def check(self) -> bool:
        try:
            self._request("/api/auth/check", {})
            return True
        except WebUIError:
            return False

    # ---------- 登录二维码 ----------

    def qrcode(self) -> str:
        data = self._request("/api/QQLogin/GetQQLoginQrcode", {})
        if isinstance(data, dict):
            return str(data.get("qrcode") or data.get("base64") or "")
        return str(data or "")

    def refresh_qrcode(self) -> str:
        data = self._request("/api/QQLogin/RefreshQRcode", {})
        if isinstance(data, dict):
            return str(data.get("qrcode") or "")
        return str(data or "")

    def login_status(self) -> dict:
        data = self._request("/api/QQLogin/CheckLoginStatus", {})
        return data if isinstance(data, dict) else {}

    def quick_login_list(self) -> list[dict]:
        data = self._request("/api/QQLogin/GetQuickLoginListNew", {})
        return data if isinstance(data, list) else []

    def quick_login(self, uin: str) -> bool:
        self._request("/api/QQLogin/SetQuickLogin", {"uin": str(uin)})
        return True

    def login_info(self) -> dict:
        data = self._request("/api/QQLogin/GetQQLoginInfo", {})
        return data if isinstance(data, dict) else {}

    # ---------- 内置终端 ----------

    def create_terminal(self, cols: int = 100, rows: int = 30) -> str:
        data = self._request("/api/Log/terminal/create", {"cols": cols, "rows": rows})
        if isinstance(data, dict):
            return str(data.get("id") or data.get("sessionId") or "")
        return str(data or "")

    def close_terminal(self, session_id: str) -> None:
        try:
            self._request(f"/api/Log/terminal/{session_id}/close", {})
        except WebUIError:
            pass

    def terminal_url(self, session_id: str) -> str:
        scheme = "wss" if self.base.startswith("https") else "ws"
        host = self.base.split("://", 1)[-1]
        return f"{scheme}://{host}/api/ws/terminal?id={session_id}&token={self.token}"
