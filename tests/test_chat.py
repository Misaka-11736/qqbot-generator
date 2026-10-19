"""试聊会话冒烟测试：不打开界面，验证 ChatSession 能收到回复。"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["QQBOT_DATA_DIR"] = tempfile.mkdtemp(prefix="qqbot-chat-")

from PySide6.QtCore import QCoreApplication

from qqbot_core.config import Config
from qqbot_generator import paths
from qqbot_generator.services.chat_session import ChatSession


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    paths.ensure_dirs()
    app = QCoreApplication(sys.argv[:1])
    cfg = Config()
    cfg.persona.default_iq = 20
    session = ChatSession(cfg)
    replies: list[str] = []
    session.replied.connect(replies.append)
    session.send("我在设置里给你智商调低了")

    deadline = time.time() + 10
    while not replies and time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)

    print("回复：", replies[0] if replies else "（超时）")
    print("智商：", session.iq())
    session.close()
    ok = bool(replies) and "顺眼" in replies[0] and session.iq() == 20
    print("结果：", "通过" if ok else "失败")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
