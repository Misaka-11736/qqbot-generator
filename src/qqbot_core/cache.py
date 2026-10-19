"""下载/生成文件的缓存目录：统计与清理。"""

from __future__ import annotations

import shutil
from pathlib import Path


def cache_dir(data_dir: Path) -> Path:
    return Path(data_dir) / "cache"


def stats(data_dir: Path) -> tuple[int, int]:
    root = cache_dir(data_dir)
    if not root.is_dir():
        return 0, 0
    files = 0
    size = 0
    for item in root.rglob("*"):
        if item.is_file():
            files += 1
            try:
                size += item.stat().st_size
            except OSError:
                pass
    return files, size


def clear(data_dir: Path) -> tuple[int, list[str]]:
    root = cache_dir(data_dir)
    if not root.is_dir():
        return 0, []
    removed = 0
    errors: list[str] = []
    for item in list(root.iterdir()):
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            removed += 1
        except OSError as exc:
            errors.append(f"{item.name}: {exc}")
    return removed, errors
