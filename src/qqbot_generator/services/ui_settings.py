"""界面侧的小设置（NapCat 路径、窗口偏好等），和机器人配置分开存。"""

from __future__ import annotations

from pathlib import Path

from qqbot_core.util import JsonStore

from .. import paths


class UiSettings:
    def __init__(self) -> None:
        self.store = JsonStore(paths.data_dir() / "ui.json", {})

    def get(self, key: str, default: str = "") -> str:
        value = self.store.data.get(key, default)
        return value if isinstance(value, str) else default

    def set(self, key: str, value: str) -> None:
        self.store.data[key] = value
        self.store.save()

    def get_path(self, key: str) -> Path | None:
        value = self.get(key)
        return Path(value) if value else None
