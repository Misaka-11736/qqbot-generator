"""开机自启：写 HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run。"""

from __future__ import annotations

import sys

APP_KEY = "QQBotGenerator"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --autostart'
    return f'"{sys.executable}" -m qqbot_generator --autostart'


def is_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_KEY)
            return bool(value)
    except OSError:
        return False


def set_enabled(enabled: bool) -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "只支持 Windows"
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, APP_KEY, 0, winreg.REG_SZ, _command())
                return True, "已加入开机自启"
            try:
                winreg.DeleteValue(key, APP_KEY)
            except FileNotFoundError:
                pass
            return True, "已取消开机自启"
    except OSError as exc:
        return False, f"写注册表失败：{exc}"
