"""媒体解析：GIF 抽帧、MP4 抽帧、文本文件读取。"""

from __future__ import annotations

import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

TEXT_EXT = {".txt", ".md", ".json", ".csv", ".log", ".py", ".js", ".html", ".xml", ".yml", ".yaml", ".ini", ".toml"}


def ffmpeg_path() -> Path | None:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    for candidate in (base / "assets" / "bin" / "ffmpeg.exe", base / "ffmpeg.exe", Path("ffmpeg.exe")):
        if candidate.is_file():
            return candidate
    return None


def media_sources(segments: list[dict]) -> list[dict]:
    items: list[dict] = []
    for seg in segments:
        kind = str(seg.get("type") or "")
        if kind not in ("image", "mface", "video", "file"):
            continue
        data = seg.get("data") or {}
        url = str(data.get("url") or data.get("file") or data.get("path") or "").strip()
        if not url:
            continue
        items.append({"kind": kind, "url": url, "name": str(data.get("name") or data.get("file") or "")})
    return items


def _download(url: str, dest: Path, max_mb: int = 40) -> Path:
    if url.startswith("file:///"):
        src = Path(urllib.parse.unquote(url[8:]))
        if src.is_file():
            return src
    if not url.startswith(("http://", "https://")):
        path = Path(url)
        if path.is_file():
            return path
        raise OSError("不认识的媒体地址")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 QQBot/3.1"})
    with urllib.request.urlopen(req, timeout=30) as resp, dest.open("wb") as out:
        done = 0
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            done += len(chunk)
            if done > max_mb * 1024 * 1024:
                dest.unlink(missing_ok=True)
                raise OSError("媒体文件太大")
            out.write(chunk)
    return dest


def extract_frames(item: dict, cache: Path, limit: int = 3) -> tuple[list[Path], str]:
    cache.mkdir(parents=True, exist_ok=True)
    suffix = Path(item["name"]).suffix or ".bin"
    raw = cache / f"m-{abs(hash(item['url'])) % 10_000_000}{suffix}"
    try:
        path = _download(item["url"], raw)
    except Exception as exc:
        return [], f"下载失败：{exc}"
    if item["kind"] in ("image", "mface"):
        try:
            with Image.open(path) as img:
                frames: list[Path] = []
                if getattr(img, "is_animated", False):
                    for index in range(min(limit, img.n_frames)):
                        img.seek(index)
                        frame = path.with_name(f"{path.stem}-{index}.jpg")
                        img.convert("RGB").save(frame, "JPEG", quality=88)
                        frames.append(frame)
                    return frames, ""
                return [path], ""
        except Exception as exc:
            return [], f"图片打不开：{exc}"
    ffmpeg = ffmpeg_path()
    if ffmpeg is None:
        return [], "没找到 ffmpeg，视频看不了"
    pattern = cache / f"{path.stem}-%02d.jpg"
    try:
        subprocess.run(
            [str(ffmpeg), "-y", "-i", str(path), "-vf", "fps=1/2,scale=1280:-2", "-frames:v", str(limit), str(pattern)],
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [], f"视频抽帧失败：{exc}"
    frames = sorted(cache.glob(f"{path.stem}-*.jpg"))[:limit]
    return frames, "" if frames else "视频里没抽到画面"


def read_text_attachment(item: dict, cache: Path, max_kb: int = 128) -> str:
    suffix = Path(item["name"]).suffix.lower()
    if suffix and suffix not in TEXT_EXT:
        return ""
    cache.mkdir(parents=True, exist_ok=True)
    raw = cache / f"t-{abs(hash(item['url'])) % 10_000_000}{suffix or '.txt'}"
    try:
        path = _download(item["url"], raw, max_mb=2)
        data = path.read_bytes()[: max_kb * 1024]
    except Exception as exc:
        return f"（文件下载失败：{exc}）"
    for encoding in ("utf-8", "gbk", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")
