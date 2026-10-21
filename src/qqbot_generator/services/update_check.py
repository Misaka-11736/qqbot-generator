"""检查 GitHub 最新 Release，提示用户更新。"""

from __future__ import annotations

import json
import re
import urllib.request

from PySide6.QtCore import QThread, Signal

API = "https://api.github.com/repos/Misaka-11736/qqbot-generator/releases?per_page=10"
ATOM = "https://github.com/Misaka-11736/qqbot-generator/releases.atom"


def _tuple(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", version)[:3])


class UpdateChecker(QThread):
    result = Signal(str, str, str)  # status(new/latest/error), tag, url

    def __init__(self, current: str):
        super().__init__()
        self.current = current

    def _atom(self) -> tuple[str, str] | None:
        import xml.etree.ElementTree as ET

        req = urllib.request.Request(ATOM, headers={"User-Agent": "qqbot-generator-updater"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            root = ET.fromstring(resp.read())
        ns = {"a": "http://www.w3.org/2005/Atom"}
        tag = ""
        url = ""
        for entry in root.findall("a:entry", ns):
            title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
            link = entry.find("a:link", ns)
            href = link.get("href", "") if link is not None else ""
            if title and _tuple(title):
                tag, url = title, href
                break
        return (tag, url) if tag else None

    def run(self) -> None:
        try:
            found = self._atom()
            if found is None:
                req = urllib.request.Request(API, headers={"User-Agent": "qqbot-generator-updater"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8", errors="replace"))
                releases = data if isinstance(data, list) else [data]
                best = None
                for item in releases:
                    if not isinstance(item, dict) or item.get("draft") or item.get("prerelease"):
                        continue
                    t = str(item.get("tag_name") or "").strip()
                    if not t or not _tuple(t):
                        continue
                    if best is None or _tuple(t) > _tuple(str(best.get("tag_name") or "")):
                        best = item
                if best is None:
                    self.result.emit("error", "", "")
                    return
                found = (str(best.get("tag_name") or "").strip(), str(best.get("html_url") or ""))
            tag, url = found
            self.result.emit("new" if _tuple(tag) > _tuple(self.current) else "latest", tag, url)
        except Exception:
            self.result.emit("error", "", "")
