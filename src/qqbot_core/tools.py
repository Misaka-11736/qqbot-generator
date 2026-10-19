"""v3 工具：Brave 搜索、网页正文、沙箱下载、生成图片/文件。"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

UA = "QQBotGenerator/3.0 (+local)"
MAX_PAGE = 20000


class ToolError(RuntimeError):
    pass


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            text = data.strip()
            if text:
                self.parts.append(text)


def _public_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ToolError("只支持 http/https 链接")
    host = parsed.hostname
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise ToolError(f"域名解析失败：{exc}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ToolError("不允许访问内网地址")
    return urllib.parse.urlunparse(parsed)


def _get(url: str, timeout: float = 15.0, limit: int = MAX_PAGE) -> tuple[bytes, str]:
    req = urllib.request.Request(_public_url(url), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        ctype = resp.headers.get("Content-Type", "")
        data = resp.read(limit)
    return data, ctype


def brave_search(key: str, query: str, count: int = 5) -> list[dict]:
    if not key:
        raise ToolError("还没填 Brave API Key")
    url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode(
        {"q": query, "count": max(1, min(count, 8)), "text_decorations": "false"}
    )
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "X-Subscription-Token": key, "User-Agent": UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        raise ToolError(f"Brave 返回 HTTP {exc.code}") from exc
    except OSError as exc:
        raise ToolError(f"搜索失败：{exc}") from exc
    results = []
    for item in (data.get("web") or {}).get("results") or []:
        results.append(
            {
                "title": re.sub(r"<[^>]+>", "", item.get("title") or ""),
                "url": item.get("url") or "",
                "description": re.sub(r"<[^>]+>", "", item.get("description") or ""),
            }
        )
    return results


def fetch_text(url: str, limit: int = 6000) -> str:
    data, ctype = _get(url, limit=MAX_PAGE)
    if "html" in ctype or data[:200].lstrip().startswith(b"<"):
        parser = _TextParser()
        parser.feed(data.decode("utf-8", errors="replace"))
        text = "\n".join(parser.parts)
    else:
        text = data.decode("utf-8", errors="replace")
    return re.sub(r"\n{3,}", "\n\n", text)[:limit]


def download(url: str, dest_dir: Path, max_mb: int = 20) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_url = _public_url(url)
    req = urllib.request.Request(safe_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        length = int(resp.headers.get("Content-Length") or 0)
        if length and length > max_mb * 1024 * 1024:
            raise ToolError(f"文件超过 {max_mb} MB")
        name = Path(urllib.parse.unquote(urllib.parse.urlparse(safe_url).path)).name or "download.bin"
        name = re.sub(r"[^\w.\-]+", "_", name)[:80]
        target = dest_dir / name
        done = 0
        with target.open("wb") as out:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                done += len(chunk)
                if done > max_mb * 1024 * 1024:
                    target.unlink(missing_ok=True)
                    raise ToolError(f"文件超过 {max_mb} MB")
                out.write(chunk)
    return target


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("msyh.ttc", "msyhbd.ttc", "simhei.ttf"):
        path = Path(r"C:\Windows\Fonts") / name
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _wrap(draw, text: str, font, width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        current = ""
        for char in paragraph:
            if draw.textlength(current + char, font=font) > width:
                lines.append(current)
                current = char
            else:
                current += char
        if current:
            lines.append(current)
    return lines or [""]


def make_card(text: str, out_dir: Path, title: str = "小鲸卡片") -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    width = 900
    pad = 48
    font_title = _font(40)
    font_body = _font(28)
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    lines = _wrap(probe, text.strip()[:600] or "（空）", font_body, width - pad * 2)
    height = pad * 2 + 70 + len(lines) * 42
    img = Image.new("RGB", (width, max(360, height)), "#F7F4EC")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, width, 150], fill="#1B2A4A")
    draw.text((pad, 44), title, font=font_title, fill="#F7F4EC")
    y = 190
    for line in lines[:18]:
        draw.text((pad, y), line, font=font_body, fill="#22262E")
        y += 42
    path = out_dir / f"card-{int(__import__('time').time())}.png"
    img.save(path)
    return path


def make_file(name: str, content: str, out_dir: Path) -> Path:
    safe = re.sub(r"[^\w\u4e00-\u9fff.\-]+", "_", name).strip("._") or "note"
    suffix = Path(safe).suffix.lower() or ".txt"
    if suffix not in (".txt", ".md", ".csv", ".json"):
        suffix = ".txt"
    if not Path(safe).suffix:
        safe += suffix
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / safe
    path.write_text(content[:20000], "utf-8")
    return path
