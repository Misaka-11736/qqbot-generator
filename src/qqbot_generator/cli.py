"""非 GUI 入口：跑机器人内核、自检、离屏截图，供 GUI 子进程与打包脚本使用。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from qqbot_core.config import load_config
from qqbot_core.engine import Engine
from qqbot_core.llm import LLMError, make_llm
from qqbot_core.memory import Memory
from qqbot_core.onebot import OneBotLink
from qqbot_core.persona import set_prompts_dir
from qqbot_core.util import ensure_utf8_stdout, setup_logging, trim_old_logs

from . import paths


def run_bot(config_path: str) -> int:
    ensure_utf8_stdout()
    cfg = load_config(config_path)
    set_prompts_dir(paths.prompts_dir())
    log_dir = Path(cfg.log.dir) if Path(cfg.log.dir).is_absolute() else paths.logs_dir()
    setup_logging(cfg.log.level, log_dir, tag="bot")
    trim_old_logs(log_dir, cfg.log.keep_days)

    try:
        llm, label = make_llm(cfg)
    except LLMError as exc:
        setup_logging(cfg.log.level, log_dir, tag="bot").error("模型初始化失败：%s，改用离线大脑", exc)
        from qqbot_core.llm import MockBrain

        llm, label = MockBrain(), "离线兜底大脑"

    memory = Memory(Path(cfg.data_dir) / "memory.json", cfg.persona.default_iq, cfg.chat.context_turns)
    if memory.prune(days=30):
        memory.save()
    engine = Engine(cfg, memory, llm, label)
    link = OneBotLink(cfg.onebot, engine.handle_event, engine.on_ready)
    engine.link = link

    async def main() -> None:
        try:
            await link.start()
        finally:
            await link.stop()
            memory.save()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        return 0
    except OSError as exc:
        setup_logging(cfg.log.level, log_dir, tag="bot").error("启动失败：%s", exc)
        return 2
    except Exception as exc:
        import traceback

        setup_logging(cfg.log.level, log_dir, tag="bot").error("异常退出：%s\n%s", exc, traceback.format_exc())
        return 1
    return 0


def run_selftest(out: str) -> int:
    from .services import selftest_service
    from .services.config_service import ConfigService

    paths.ensure_dirs()
    ConfigService()  # 确保 config.toml 和人格文件已生成
    results = selftest_service.run_all()
    Path(out).write_text(json.dumps(results, ensure_ascii=False, indent=2), "utf-8")
    ok = all(item["ok"] for item in results)
    return 0 if ok else 1


def run_screenshot(outdir: str, width: int = 1280, height: int = 860) -> int:
    import os
    import tempfile

    os.environ.pop("QT_QPA_PLATFORM", None)
    os.environ.setdefault("QQBOT_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="qqbot-shot-"))))

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from .app import MainWindow, build_context
    from .theme import app_font, qss

    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    app.setFont(app_font(10))
    app.setStyleSheet(qss())
    ctx = build_context()
    window = MainWindow(ctx)
    ctx.navigate = window.show_page
    # 不真正显示在屏幕上，但走 windows 平台插件，才能用系统字体
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.resize(width, height)
    window.show()

    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    for key in list(window.pages):
        window.show_page(key)
        for _ in range(3):
            app.processEvents()
        window.grab().save(str(out / f"{key}.png"))
    app.quit()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qqbot-generator", add_help=True)
    parser.add_argument("--run-bot", action="store_true", help="以机器人内核模式运行（不开 GUI）")
    parser.add_argument("--config", default="", help="config.toml 路径")
    parser.add_argument("--selftest", default="", help="跑自检并把结果写到指定 JSON")
    parser.add_argument("--screenshot", default="", help="离屏渲染各页面到指定目录")
    parser.add_argument("--size", default="1280x860")
    args, _unknown = parser.parse_known_args(argv)

    if args.run_bot:
        return run_bot(args.config or str(paths.config_path()))
    if args.selftest:
        return run_selftest(args.selftest)
    if args.screenshot:
        width, _, height = args.size.partition("x")
        return run_screenshot(args.screenshot, int(width or 1280), int(height or 860))
    return -1


if __name__ == "__main__":
    raise SystemExit(main())
