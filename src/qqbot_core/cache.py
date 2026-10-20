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


def cleanup(data_dir: Path, keep_days: int = 7, max_mb: int = 500) -> tuple[int, int]:
    root = cache_dir(data_dir)
    if not root.is_dir():
        return 0, 0
    removed = 0
    now = __import__("time").time()
    cutoff = now - max(1, keep_days) * 86400
    files: list[tuple[float, int, Path]] = []
    for item in root.rglob("*"):
        if not item.is_file():
            continue
        try:
            stat = item.stat()
        except OSError:
            continue
        if stat.st_mtime < cutoff:
            try:
                item.unlink()
                removed += 1
                continue
            except OSError:
                pass
        files.append((stat.st_mtime, stat.st_size, item))
    total = sum(size for _, size, _ in files)
    if total > max_mb * 1024 * 1024:
        for _, size, item in sorted(files):
            if total <= max_mb * 1024 * 1024:
                break
            try:
                item.unlink()
                total -= size
                removed += 1
            except OSError:
                pass
    return removed, total
