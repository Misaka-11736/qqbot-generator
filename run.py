"""PyInstaller 入口：把包当成普通脚本启动。"""

from qqbot_generator.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
