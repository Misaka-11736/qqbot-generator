"""运行路径：支持把数据目录放到任意盘（指针文件留在 %LOCALAPPDATA%）。"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

APP_NAME = "QQBotGenerator"
APP_TITLE = "QQ Bot生成器"
APP_VERSION = "3.1.0"
APP_TAGLINE = "一只住在你 QQ 里的蓝鲸女仆"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def resource_dir() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", app_dir()))
    return Path(__file__).resolve().parents[2]


def resource(*parts: str) -> Path:
    return resource_dir().joinpath(*parts)


def _local_appdata() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base)


def bootstrap_dir() -> Path:
    """固定在 C 盘的小目录，只放 location.json。"""
    return _local_appdata() / APP_NAME


def location_file() -> Path:
    return bootstrap_dir() / "location.json"


def _env_override() -> Path | None:
    value = os.environ.get("QQBOT_DATA_DIR", "").strip()
    return Path(value).expanduser() if value else None


def data_dir() -> Path:
    override = _env_override()
    if override is not None:
        return override
    pointer = location_file()
    try:
        raw = json.loads(pointer.read_text("utf-8"))
        root = str(raw.get("root", "")).strip()
        if root:
            return Path(root)
    except (OSError, json.JSONDecodeError):
        pass
    return bootstrap_dir()


def config_path() -> Path:
    return data_dir() / "config.toml"


def logs_dir() -> Path:
    return data_dir() / "logs"


def prompts_dir() -> Path:
    return data_dir() / "prompts"


def downloads_dir() -> Path:
    return data_dir() / "downloads"


def ensure_dirs() -> None:
    for path in (bootstrap_dir(), data_dir(), logs_dir(), prompts_dir(), downloads_dir()):
        path.mkdir(parents=True, exist_ok=True)


def needs_location_setup() -> bool:
    """全新安装且没选过目录：需要弹一次选择框。"""
    if _env_override() is not None:
        return False
    if location_file().is_file():
        return False
    return not config_path().is_file()


def recommended_root() -> Path:
    for drive in ("D:", "E:"):
        if Path(drive + "\\").exists():
            return Path(drive + "\\QQBotData")
    return Path.home() / "QQBotData"


def set_data_root(root: Path) -> None:
    bootstrap_dir().mkdir(parents=True, exist_ok=True)
    location_file().write_text(json.dumps({"root": str(root)}, ensure_ascii=False, indent=2), "utf-8")
    root.mkdir(parents=True, exist_ok=True)
    ensure_dirs()


ITEMS = ["config.toml", "ui.json", "memory.json", "chat_memory.json", "prompts", "logs", "downloads", "napcat"]


def migrate_data(new_root: Path) -> tuple[bool, str]:
    """把当前数据目录整体复制到新位置，再切换指针。"""
    old = data_dir()
    try:
        new_root = new_root.expanduser().resolve()
        old = old.resolve()
    except OSError as exc:
        return False, f"路径无效：{exc}"
    if new_root == old:
        return True, "目录没有变化"
    if old in new_root.parents or new_root in old.parents:
        return False, "新目录不能是旧目录的上级或子目录"

    try:
        new_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"无法创建目录：{exc}"

    copied = 0
    for name in ITEMS:
        src = old / name
        if not src.exists():
            continue
        dst = new_root / name
        try:
            if src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            copied += 1
        except OSError as exc:
            return False, f"复制 {name} 失败：{exc}"

    ui = new_root / "ui.json"
    if ui.is_file():
        try:
            data = json.loads(ui.read_text("utf-8"))
            for key, value in list(data.items()):
                if isinstance(value, str) and value.lower().startswith(str(old).lower()):
                    data[key] = str(new_root) + value[len(str(old)):]
            ui.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        except (OSError, json.JSONDecodeError):
            pass

    set_data_root(new_root)
    return True, f"已迁移 {copied} 项到 {new_root}"
