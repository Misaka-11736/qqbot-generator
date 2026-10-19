"""NapCat 相关：探测安装、写入 OneBot 配置、隐藏启动、下载解压、打开 WebUI。"""

from __future__ import annotations

import ctypes
import json
import os
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

from .. import paths

DEFAULT_WEBUI_TOKEN = "qqbot-local-2026"
DEFAULT_WEBUI_PORT = 6099
RELEASE_VERSION = "v4.18.38"
DOWNLOAD_URL = f"https://github.com/NapNeko/NapCatQQ/releases/download/{RELEASE_VERSION}/NapCat.Shell.zip"


def is_install(folder: Path) -> bool:
    return (folder / "launcher.bat").is_file() or (folder / "napcat.bat").is_file()


def launch_script(folder: Path) -> Path | None:
    for name in ("launcher.bat", "launcher-win10.bat", "napcat.bat"):
        candidate = folder / name
        if candidate.is_file():
            return candidate
    return None


def find_candidates(extra: list[str] | None = None) -> list[Path]:
    found: list[Path] = []
    guesses = [Path(p) for p in (extra or []) if p]
    guesses += [
        paths.data_dir() / "napcat",
        paths.app_dir() / "NapCat" / "app",
        Path(r"D:\QQ Bot\NapCat\app"),
    ]
    for root in (paths.app_dir(), paths.data_dir()):
        for pattern in ("NapCat*Shell*", "NapCat.*.Shell", "NapCat*/app"):
            try:
                guesses.extend(p for p in root.glob(pattern) if p.is_dir())
            except OSError:
                pass

    seen: set[str] = set()
    for item in guesses:
        try:
            key = str(item.resolve()).lower()
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        if is_install(item):
            found.append(item)
    return found


def _client_entry(clients: list, url: str, token: str) -> dict:
    entry = next((c for c in clients if isinstance(c, dict) and c.get("name") == "qqbot"), None)
    if entry is None:
        entry = next((c for c in clients if isinstance(c, dict) and "127.0.0.1" in str(c.get("url", ""))), None)
    if entry is None:
        entry = {}
        clients.append(entry)
    entry.update(
        {
            "name": "qqbot",
            "enable": True,
            "url": url,
            "messagePostFormat": "array",
            "reportSelfMessage": False,
            "reconnectInterval": 5000,
            "token": token,
            "debug": False,
            "heartInterval": 30000,
        }
    )
    return entry


def configure(folder: Path, port: int, ws_path: str, token: str = "") -> tuple[Path, list[Path]]:
    """写入默认配置和所有账号配置，返回 (默认文件, 实际更新的文件列表)。"""
    config_dir = folder / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    url = f"ws://127.0.0.1:{port}{ws_path}"

    targets = [config_dir / "onebot11.json"]
    targets += sorted(config_dir.glob("onebot11_*.json"))

    updated: list[Path] = []
    for target in targets:
        data: dict = {}
        if target.is_file():
            try:
                data = json.loads(target.read_text("utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
        network = data.setdefault("network", {})
        clients = network.setdefault("websocketClients", [])
        if not isinstance(clients, list):
            clients = []
            network["websocketClients"] = clients
        _client_entry(clients, url, token)
        network.setdefault("httpServers", [])
        network.setdefault("httpClients", [])
        network.setdefault("websocketServers", [])
        data.setdefault("musicSignUrl", "")
        data.setdefault("enableLocalFile2Url", False)
        data.setdefault("parseMultMsg", False)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")
        updated.append(target)

    webui = {"host": "127.0.0.1", "port": DEFAULT_WEBUI_PORT, "token": DEFAULT_WEBUI_TOKEN, "loginRate": 3}
    (config_dir / "webui.json").write_text(json.dumps(webui, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return config_dir / "onebot11.json", updated


def read_client_urls(folder: Path) -> list[tuple[Path, str]]:
    """读取所有 onebot 配置里的 WS 客户端地址。"""
    config_dir = folder / "config"
    result: list[tuple[Path, str]] = []
    for target in sorted(config_dir.glob("onebot11*.json")):
        try:
            data = json.loads(target.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for client in (data.get("network") or {}).get("websocketClients") or []:
            url = client.get("url") if isinstance(client, dict) else None
            if url:
                result.append((target, str(url)))
    return result


def _hidden_script(folder: Path, log: Path) -> Path:
    script = paths.data_dir() / "launch_napcat_hidden.cmd"
    entry = "napcat.bat" if (folder / "napcat.bat").is_file() else "launcher.bat"
    script.write_text(
        "@echo off\r\nchcp 65001 >nul\r\n"
        f'cd /d "{folder}"\r\n'
        f'call "{entry}" > "{log}" 2>&1\r\n',
        "utf-8",
    )
    return script


def launch_hidden(folder: Path) -> tuple[bool, str]:
    """管理员权限、无控制台窗口启动 NapCat，输出重定向到 napcat_console.log。"""
    script = launch_script(folder)
    if script is None:
        return False, "这个目录里没有 launcher.bat / napcat.bat"
    if os.name != "nt":
        return False, "只支持 Windows"

    log = paths.data_dir() / "napcat_console.log"
    cmd_file = _hidden_script(folder, log)
    params = f'/c ""{cmd_file}""'
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", params, str(folder), 0)
    if result <= 32:
        if result == 5:
            return False, "你取消了管理员授权"
        return False, f"启动失败（ShellExecute 返回 {result}）"
    return True, "正在隐藏启动 NapCat，同意 UAC 后等 5~10 秒"


def launch(folder: Path) -> tuple[bool, str]:
    """旧的可见窗口启动，作为兜底。"""
    script = launch_script(folder)
    if script is None:
        return False, "这个目录里没有 launcher.bat / napcat.bat"
    result = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", "cmd.exe", f'/c ""{script}" & pause"', str(folder), 1
    )
    if result <= 32:
        return False, "用户取消了管理员授权" if result == 5 else f"启动失败（{result}）"
    return True, "已请求管理员权限"


def open_webui(token: str = DEFAULT_WEBUI_TOKEN) -> None:
    import webbrowser

    webbrowser.open(f"http://127.0.0.1:{DEFAULT_WEBUI_PORT}/webui/?token={token}")


def download(url: str, dest: Path, progress: Callable[[int, int], None] | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "QQBotGenerator/2.1"})
    with urllib.request.urlopen(req, timeout=60) as resp, dest.open("wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    return dest


def extract(zip_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(dest)
    if is_install(dest):
        return dest
    for item in dest.iterdir():
        if item.is_dir() and is_install(item):
            return item
    return dest
