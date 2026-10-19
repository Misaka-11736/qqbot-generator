"""生成界面用的小图标资源（纯 Pillow，构建时跑一次）。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


def chevron(name: str, up: bool) -> None:
    scale = 8
    size = 12 * scale
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (124, 135, 156, 255)
    width = 2 * scale
    if up:
        points = [(2 * scale, 8 * scale), (6 * scale, 4 * scale), (10 * scale, 8 * scale)]
    else:
        points = [(2 * scale, 4 * scale), (6 * scale, 8 * scale), (10 * scale, 4 * scale)]
    draw.line(points, fill=color, width=width, joint="curve")
    img.resize((12, 12), Image.LANCZOS).save(ASSETS / name)


def check() -> None:
    scale = 8
    size = 14 * scale
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (255, 255, 255, 255)
    width = 2 * scale
    draw.line([(3 * scale, 7 * scale), (6 * scale, 10 * scale), (11 * scale, 4 * scale)], fill=color, width=width, joint="curve")
    img.resize((14, 14), Image.LANCZOS).save(ASSETS / "check.png")


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    chevron("chevron_down.png", up=False)
    chevron("chevron_up.png", up=True)
    check()
    print("assets written to", ASSETS)


if __name__ == "__main__":
    main()
