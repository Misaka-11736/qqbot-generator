"""检查 GitHub 最新 Release，提示用户更新。"""

from __future__ import annotations

import json
import re
import urllib.request

from PySide6.QtCore import QThread, Signal

API = "https://api.github.com/repos/Misaka-11736/qqbot-generator/releases/latest"


def _tuple(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", version)[:3])


class UpdateChecker(QThread):
    result = Signal(str, str, str)  # status(new/latest/error), tag, url

    def __init__(self, current: str):
        super().__init__()
        self.current = current

    def run(self) -> None:
        try:
            req = urllib.request.Request(API, headers={"User-Agent": "qqbot-generator-updater"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            tag = str(data.get("tag_name") or "").strip()
            url = str(data.get("html_url") or "")
            if not tag:
                self.result.emit("error", "", "")
                return
            self.result.emit("new" if _tuple(tag) > _tuple(self.current) else "latest", tag, url)
        except Exception:
            self.result.emit("error", "", "")
