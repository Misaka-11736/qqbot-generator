"""Qwen-VL 识图：下载 QQ 图片 → base64 → OpenAI 兼容视觉接口。"""

from __future__ import annotations

import base64
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

VISION_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
VISION_PROMPT = (
    "客观描述这张图的内容，不要猜测发送者身份，不要使用“对方/用户”等第三人称，不要直接组织成聊天回复。"
    "直接说结论，不要列点、不要标题、不要贴链接、不要说“这张图片显示/根据图片”；"
    "看不清就直说看不清，不要编。"
)


def image_sources(segments: list[dict]) -> list[str]:
    urls: list[str] = []
    for seg in segments:
        if seg.get("type") not in ("image", "mface"):
            continue
        data = seg.get("data") or {}
        for key in ("url", "file", "path"):
            value = str(data.get(key) or "").strip()
            if value:
                urls.append(value)
                break
    return urls


def _fetch(url: str, dest: Path, max_mb: int = 10) -> Path:
    if url.startswith("file:///"):
        src = Path(urllib.parse.unquote(url[8:]))
        if src.is_file():
            return src
    if url.startswith("base64://"):
        raw = base64.b64decode(url[9:])
        dest.write_bytes(raw)
        return dest
    if not url.startswith(("http://", "https://")):
        path = Path(url)
        if path.is_file():
            return path
        raise OSError("不认识的图片地址")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 QQBot/3.0"})
    with urllib.request.urlopen(req, timeout=20) as resp, dest.open("wb") as out:
        done = 0
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            done += len(chunk)
            if done > max_mb * 1024 * 1024:
                dest.unlink(missing_ok=True)
                raise OSError("图片太大")
            out.write(chunk)
    return dest


def _data_uri(path: Path) -> str:
    with Image.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail((1400, 1400))
        from io import BytesIO

        buf = BytesIO()
        img.save(buf, format="JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def look_at_image(url: str, key: str, model: str, question: str, cache: Path, base: str = VISION_BASE) -> str:
    if not key:
        return "还没配百炼 Key，去「能力」页填一下。"
    cache.mkdir(parents=True, exist_ok=True)
    raw = cache / f"vision-{abs(hash(url)) % 10_000_000}.img"
    try:
        path = _fetch(url, raw)
        uri = _data_uri(path)
    except Exception as exc:
        return f"图我这边没加载出来（{exc}）"
    ask = question.strip() or "看看这张图，告诉我是什么"
    payload = {
        "model": model or "qwen-vl-max",
        "messages": [
            {"role": "system", "content": VISION_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"问题：{ask}"},
                    {"type": "image_url", "image_url": {"url": uri}},
                ],
            },
        ],
        "temperature": 0.6,
        "max_tokens": 300,
    }
    endpoint = base if base.rstrip("/").endswith("chat/completions") else base.rstrip("/") + "/chat/completions"
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:200]
        if exc.code in (403, 404) and model != "qwen3-vl-plus":
            return look_at_image(url, key, "qwen3-vl-plus", question, cache)
        return f"识图接口报错（HTTP {exc.code}）：{body}"
    except OSError as exc:
        return f"识图失败：{exc}"
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return "识图没返回内容。"
    text = re.sub(r"https?://\S+", "", str(text))
    text = re.sub(r"\n{2,}", "\n", text).strip()
    return text[:500]


def looks_like_image_question(text: str) -> bool:
    if not text:
        return False
    return bool(
        re.search(
            r"(这是啥|这是什么|什么图|哪张|哪个|谁|什么游戏|什么动漫|什么角色|表情|截图|视频|文件|附件|这段|讲啥|什么内容|图里|这张|这图|看看|识别|认一下|你看|干嘛的|什么意思)",
            text,
        )
    )


def look_at_frames(frames: list[Path], key: str, model: str, question: str, extra: str = "", base: str = VISION_BASE) -> str:
    if not key:
        return "还没配百炼 Key，去「能力」页填一下。"
    if not frames:
        return "没拿到能看的画面。"
    content: list[dict] = [{"type": "text", "text": f"问题：{question or '看看这些内容'}" + (f"\n文件内容：{extra[:3000]}" if extra else "")}]
    for frame in frames[:3]:
        try:
            content.append({"type": "image_url", "image_url": {"url": _data_uri(frame)}})
        except Exception:
            continue
    if len(content) == 1:
        return "画面打不开。"
    payload = {
        "model": model or "qwen3-vl-plus",
        "messages": [
            {
                "role": "system",
                "content": "客观描述这张图片/表情/GIF/视频截图/文件的内容：画面、文字、界面元素和可见动作。"
                "不要猜测发送者身份，不要使用“对方/用户/提问者”等第三人称，不要直接组织成聊天回复；"
                "如果看不清或不确定就明确写“不确定”。只输出事实摘要。",
            },
            {"role": "user", "content": content},
        ],
        "temperature": 0.6,
        "max_tokens": 300,
    }
    endpoint = base if base.rstrip("/").endswith("chat/completions") else base.rstrip("/") + "/chat/completions"
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:200]
        if exc.code in (403, 404) and model != "qwen3-vl-plus":
            return look_at_frames(frames, key, "qwen3-vl-plus", question, extra)
        return f"识图接口报错（HTTP {exc.code}）：{body}"
    except OSError as exc:
        return f"识图失败：{exc}"
    try:
        text = str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError):
        return "识图没返回内容。"
    text = re.sub(r"https?://\S+", "", text)
    return re.sub(r"\n{2,}", "\n", text).strip()[:500]


def caption_frames(frames: list[Path], key: str, model: str, base: str = VISION_BASE) -> str:
    if not key or not frames:
        return ""
    content: list[dict] = [{"type": "text", "text": "用不超过 10 个字概括这张图的主体/商品/角色，只输出关键词，不要解释。"}]
    for frame in frames[:1]:
        try:
            content.append({"type": "image_url", "image_url": {"url": _data_uri(frame)}})
        except Exception:
            continue
    if len(content) == 1:
        return ""
    payload = {
        "model": model or "qwen3-vl-plus",
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.2,
        "max_tokens": 40,
    }
    endpoint = base if base.rstrip("/").endswith("chat/completions") else base.rstrip("/") + "/chat/completions"
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        return str(data["choices"][0]["message"]["content"]).strip().splitlines()[0][:40]
    except Exception:
        return ""
