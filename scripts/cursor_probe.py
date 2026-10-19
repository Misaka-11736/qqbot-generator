"""沿窗口边缘扫描实际光标形状，判断缩放热区有多宽（DPI 感知）。"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    pass

IDC_SIZEWE = 32644
IDC_SIZENS = 32645
IDC_SIZENWSE = 32642
IDC_SIZENESW = 32643

we = user32.LoadCursorW(None, IDC_SIZEWE)
ns = user32.LoadCursorW(None, IDC_SIZENS)
nwse = user32.LoadCursorW(None, IDC_SIZENWSE)
nesw = user32.LoadCursorW(None, IDC_SIZENESW)


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class CURSORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hCursor", wintypes.HANDLE),
        ("ptScreenPos", wintypes.POINT),
    ]


def find_window() -> int:
    result = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if "QQ Bot生成器" in buf.value and user32.IsWindowVisible(hwnd):
                result.append(hwnd)
        return True

    user32.EnumWindows(callback, 0)
    return result[0] if result else 0


def cursor_kind() -> str:
    info = CURSORINFO()
    info.cbSize = ctypes.sizeof(CURSORINFO)
    user32.GetCursorInfo(ctypes.byref(info))
    h = info.hCursor
    if h == we:
        return "WE"
    if h == ns:
        return "NS"
    if h == nwse:
        return "NWSE"
    if h == nesw:
        return "NESW"
    return "-"


def main() -> None:
    hwnd = find_window()
    if not hwnd:
        print("window not found")
        return
    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    print("rect", rect.left, rect.top, rect.right, rect.bottom)
    cy = (rect.top + rect.bottom) // 2
    cx = (rect.left + rect.right) // 2
    print("left:", end=" ")
    for offset in range(0, 16):
        user32.SetCursorPos(rect.left + offset, cy)
        time.sleep(0.05)
        print(f"{offset}:{cursor_kind()}", end=" ")
    print()
    print("right:", end=" ")
    for offset in range(0, 16):
        user32.SetCursorPos(rect.right - offset, cy)
        time.sleep(0.05)
        print(f"{offset}:{cursor_kind()}", end=" ")
    print()
    print("bottom:", end=" ")
    for offset in range(0, 16):
        user32.SetCursorPos(cx, rect.bottom - offset)
        time.sleep(0.05)
        print(f"{offset}:{cursor_kind()}", end=" ")
    print()
    user32.SetCursorPos(cx, cy)


if __name__ == "__main__":
    main()
