"""API Key 本地加密存储（DPAPI），与 GUI 的 secrets 同格式。"""

from __future__ import annotations

import base64
import ctypes
import json
import sys
from ctypes import wintypes
from pathlib import Path


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes):
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def protect(text: str) -> str:
    if sys.platform != "win32" or not text:
        return ""
    blob_in, _ = _blob(text.encode("utf-8"))
    blob_out = _Blob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        return ""
    try:
        return base64.b64encode(ctypes.string_at(blob_out.pbData, blob_out.cbData)).decode()
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def unprotect(token: str) -> str:
    if sys.platform != "win32" or not token:
        return ""
    try:
        raw = base64.b64decode(token)
    except (ValueError, TypeError):
        return ""
    blob_in, _ = _blob(raw)
    blob_out = _Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        return ""
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData).decode("utf-8", errors="replace")
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def keys_path(data_dir: Path) -> Path:
    return data_dir / "secrets.json"


def load_keys(data_dir: Path) -> dict[str, str]:
    path = keys_path(data_dir)
    try:
        raw = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: unprotect(str(v)) for k, v in raw.items() if isinstance(v, str)}


def get_key(data_dir: Path, name: str) -> str:
    return load_keys(data_dir).get(name, "")


def set_key(data_dir: Path, name: str, value: str) -> None:
    path = keys_path(data_dir)
    try:
        raw = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    if value:
        raw[name] = protect(value)
    else:
        raw.pop(name, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), "utf-8")
