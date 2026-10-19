"""入口：有命令行参数走 CLI，否则打开 GUI。"""

from __future__ import annotations

import sys

from .cli import main as cli_main


def main() -> int:
    code = cli_main(sys.argv[1:])
    if code >= 0:
        return code
    from .app import run_gui

    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
