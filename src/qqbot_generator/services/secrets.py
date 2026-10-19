"""Windows DPAPI 加解密，用来保存 NapCat WebUI 密码。"""

from __future__ import annotations

import base64
import ctypes
import sys
from ctypes import wintypes


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> tuple[_Blob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def protect(text: str) -> str:
    if sys.platform != "win32" or not text:
        return ""
    raw = text.encode("utf-8")
    blob_in, _keep = _blob(raw)
    blob_out = _Blob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        return ""
    try:
        data = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        return base64.b64encode(data).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)


def unprotect(token: str) -> str:
    if sys.platform != "win32" or not token:
        return ""
    try:
        raw = base64.b64decode(token)
    except (ValueError, TypeError):
        return ""
    blob_in, _keep = _blob(raw)
    blob_out = _Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        return ""
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData).decode("utf-8", errors="replace")
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)
