"""v3.2 语音：faster-whisper 识别 + Edge-TTS 合成 + ffmpeg 转 AMR。"""

from __future__ import annotations

import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from .media import ffmpeg_path

VOICE_EXT = (".amr", ".silk", ".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac")


def voice_sources(segments: list[dict]) -> list[str]:
    urls = []
    for seg in segments:
        if seg.get("type") != "record":
            continue
        data = seg.get("data") or {}
        value = str(data.get("url") or data.get("file") or data.get("path") or "").strip()
        if value:
            urls.append(value)
    return urls


def _download(url: str, dest: Path) -> Path:
    if url.startswith("file:///"):
        src = Path(urllib.parse.unquote(url[8:]))
        if src.is_file():
            return src
    if not url.startswith(("http://", "https://")):
        path = Path(url)
        if path.is_file():
            return path
        raise OSError("不认识的语音地址")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 QQBot/3.2"})
    with urllib.request.urlopen(req, timeout=30) as resp, dest.open("wb") as out:
        out.write(resp.read(20 * 1024 * 1024))
    return dest


def prepare(url: str, cache: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    return _download(url, cache / f"in-{abs(hash(url)) % 10_000_000}.amr")


def to_wav(src: Path, dest: Path, rate: int = 16000) -> Path:
    ffmpeg = ffmpeg_path()
    if ffmpeg is None:
        raise OSError("缺少 ffmpeg")
    subprocess.run(
        [str(ffmpeg), "-y", "-i", str(src), "-ar", str(rate), "-ac", "1", str(dest)],
        capture_output=True,
        timeout=120,
        check=False,
    )
    if not dest.is_file():
        raise OSError("音频转码失败")
    return dest


_MODEL = None


def transcribe(src: Path, model_size: str = "small") -> str:
    global _MODEL
    from faster_whisper import WhisperModel

    wav = src.with_suffix(".16k.wav")
    to_wav(src, wav)
    if _MODEL is None or getattr(_MODEL, "_qqbot_size", "") != model_size:
        _MODEL = WhisperModel(model_size, device="cpu", compute_type="int8")
        _MODEL._qqbot_size = model_size
    import wave

    import numpy as np

    with wave.open(str(wav), "rb") as fh:
        audio = np.frombuffer(fh.readframes(fh.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    segments, _info = _MODEL.transcribe(audio, language="zh", vad_filter=True)
    return "".join(seg.text for seg in segments).strip()


async def synthesize(text: str, out_dir: Path, voice: str = "zh-CN-XiaoxiaoNeural") -> Path:
    import edge_tts

    out_dir.mkdir(parents=True, exist_ok=True)
    mp3 = out_dir / f"tts-{abs(hash(text)) % 10_000_000}.mp3"
    await edge_tts.Communicate(text[:500], voice).save(str(mp3))
    ffmpeg = ffmpeg_path()
    if ffmpeg is None:
        return mp3
    amr = mp3.with_suffix(".amr")
    subprocess.run(
        [str(ffmpeg), "-y", "-i", str(mp3), "-ar", "8000", "-ac", "1", "-c:a", "libopencore_amrnb", "-b:a", "12.2k", str(amr)],
        capture_output=True,
        timeout=120,
        check=False,
    )
    return amr if amr.is_file() and amr.stat().st_size > 200 else mp3


def wants_voice(text: str) -> bool:
    return bool(
        __import__("re").search(r"(用语音|发条语音|发个语音|语音说|念一下|读一下|说给我听|来段语音)", text or "")
    )


class VoiceError(RuntimeError):
    pass


def _cloud_endpoint(base: str, path: str) -> str:
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    return base + path


def _cloud_error(exc: Exception, action: str) -> VoiceError:
    detail = str(exc)
    if "401" in detail:
        return VoiceError(f"{action} Key 无效或已过期")
    if "402" in detail:
        return VoiceError(f"{action} 账户余额不足")
    if "404" in detail:
        return VoiceError(f"{action} 模型名或接口地址不对")
    if "429" in detail:
        return VoiceError(f"{action} 请求太频繁，稍后再试")
    return VoiceError(f"{action}失败：{detail[:120]}")


def transcribe_cloud(src: Path, base_url: str, key: str, model: str) -> str:
    wav = to_wav(src, src.with_suffix(".16k.wav"))
    boundary = "----qqbot" + str(abs(hash(str(wav))) % 10_000_000)
    parts = []
    for name, value in (("model", model), ("language", "zh")):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"audio.wav\"\r\n"
        "Content-Type: audio/wav\r\n\r\n".encode() + wav.read_bytes() + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        _cloud_endpoint(base_url, "/audio/transcriptions"),
        data=b"".join(parts),
        headers={"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = __import__("json").loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        raise _cloud_error(exc, "云端语音识别") from exc
    return str(data.get("text") or "").strip()


def synthesize_cloud(text: str, out_dir: Path, base_url: str, key: str, model: str, voice: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = __import__("json").dumps(
        {"model": model, "input": text[:500], "voice": voice or "alloy", "response_format": "mp3"},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        _cloud_endpoint(base_url, "/audio/speech"),
        data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            audio = resp.read(20 * 1024 * 1024)
    except Exception as exc:
        raise _cloud_error(exc, "云端语音合成") from exc
    mp3 = out_dir / f"cloud-tts-{abs(hash(text)) % 10_000_000}.mp3"
    mp3.write_bytes(audio)
    ffmpeg = ffmpeg_path()
    if ffmpeg is None:
        return mp3
    amr = mp3.with_suffix(".amr")
    subprocess.run(
        [str(ffmpeg), "-y", "-i", str(mp3), "-ar", "8000", "-ac", "1", "-c:a", "libopencore_amrnb", "-b:a", "12.2k", str(amr)],
        capture_output=True,
        timeout=120,
        check=False,
    )
    return amr if amr.is_file() and amr.stat().st_size > 200 else mp3
