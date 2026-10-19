"""插件内核：扫描 plugins/<name>/plugin.json，加载 main.py 的 handle(ctx)。"""

from __future__ import annotations

import importlib.util
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger("qqbot.plugins")


@dataclass
class PluginInfo:
    name: str
    version: str
    description: str
    author: str
    path: Path
    enabled: bool = True
    error: str = ""


class PluginContext:
    def __init__(self, api: PluginAPI, incoming: Any, text: str):
        self.api = api
        self.incoming = incoming
        self.text = text

    async def reply(self, text: str) -> None:
        await self.api.engine._deliver(self.incoming, text)

    async def image(self, path: str, caption: str = "") -> None:
        await self.api.engine._send_media(self.incoming, "image", path, caption)

    async def voice(self, path: str) -> None:
        await self.api.engine._send_voice(self.incoming, path)

    async def search(self, query: str) -> str:
        return await self.api.engine._search(query)


class PluginAPI:
    def __init__(self, engine, info: PluginInfo):
        self.engine = engine
        self.info = info

    @property
    def config(self) -> dict:
        path = self.info.path / "config.json"
        try:
            return json.loads(path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def save_config(self, data: dict) -> None:
        (self.info.path / "config.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


class PluginManager:
    def __init__(self, engine):
        self.engine = engine
        self.items: list[PluginInfo] = []
        self.handlers: dict[str, Callable[..., Awaitable[Any]]] = {}
        self._loaded = False

    def roots(self) -> list[Path]:
        roots = [Path(__file__).resolve().parents[2] / "plugins"]
        data = getattr(self.engine.cfg, "data_dir", None)
        if data:
            roots.append(Path(data) / "plugins")
        return [r for r in roots if r.is_dir()]

    def discover(self) -> list[PluginInfo]:
        found: dict[str, PluginInfo] = {}
        for root in self.roots():
            for manifest in sorted(root.glob("*/plugin.json")):
                try:
                    data = json.loads(manifest.read_text("utf-8-sig"))
                except (OSError, json.JSONDecodeError) as exc:
                    log.warning("插件清单坏了：%s（%s）", manifest, exc)
                    continue
                name = str(data.get("name") or manifest.parent.name)
                found[name] = PluginInfo(
                    name=name,
                    version=str(data.get("version") or "0"),
                    description=str(data.get("description") or ""),
                    author=str(data.get("author") or ""),
                    path=manifest.parent,
                )
        return list(found.values())

    def load(self) -> list[PluginInfo]:
        self.items = self.discover()
        enabled_map = self._enabled_map()
        for info in self.items:
            info.enabled = enabled_map.get(info.name, True)
            if not info.enabled:
                continue
            try:
                module_path = info.path / "main.py"
                if not module_path.is_file():
                    raise FileNotFoundError("缺少 main.py")
                spec = importlib.util.spec_from_file_location(f"qqbot_plugin_{info.name}", module_path)
                module = importlib.util.module_from_spec(spec)
                assert spec.loader is not None
                spec.loader.exec_module(module)
                handler = getattr(module, "handle", None)
                if handler is None:
                    raise AttributeError("main.py 里没有 handle(ctx)")
                self.handlers[info.name] = handler
                log.info("插件已加载：%s v%s", info.name, info.version)
            except Exception as exc:
                info.error = str(exc)
                log.warning("插件加载失败：%s（%s）", info.name, exc)
        self._loaded = True
        return self.items

    async def dispatch(self, incoming, text: str) -> bool:
        if not self._loaded:
            self.load()
        for info in self.items:
            handler = self.handlers.get(info.name)
            if not info.enabled or handler is None:
                continue
            try:
                ctx = PluginContext(PluginAPI(self.engine, info), incoming, text)
                if await handler(ctx):
                    return True
            except Exception as exc:
                log.warning("插件 %s 处理失败：%s", info.name, exc)
        return False

    def _enabled_map(self) -> dict[str, bool]:
        path = Path(self.engine.cfg.data_dir) / "plugins.json"
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {str(k): bool(v) for k, v in data.items()}

    def set_enabled(self, name: str, enabled: bool) -> None:
        path = Path(self.engine.cfg.data_dir) / "plugins.json"
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        data[name] = enabled
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
