"""把用户提供的角色设定图处理成应用素材：抠背景、裁正面、做头像。"""

from __future__ import annotations

from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SRC = Path(r"C:\Users\孟禹璋\.dsh\attachments\v1\objects\2b\2b23e24092a4be40cedd47b22d8a882592aae6af43a219578d50f1b127802566")
OUT = Path(r"D:\QQ Bot\qqbot-generator\assets\character")


def near_white(pixel: tuple[int, int, int], tol: int = 18) -> bool:
    r, g, b = pixel[:3]
    return r > 255 - tol * 3 and g > 255 - tol * 3 and b > 255 - tol * 3 and max(r, g, b) - min(r, g, b) < 12


def cut_background(image: Image.Image) -> Image.Image:
    image = image.convert("RGBA")
    width, height = image.size
    pixels = image.load()
    visited = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    for x in range(width):
        queue.append((x, 0))
        queue.append((x, height - 1))
    for y in range(height):
        queue.append((0, y))
        queue.append((width - 1, y))

    while queue:
        x, y = queue.popleft()
        if x < 0 or y < 0 or x >= width or y >= height:
            continue
        index = y * width + x
        if visited[index]:
            continue
        visited[index] = 1
        if not near_white(pixels[x, y]):
            continue
        pixels[x, y] = (255, 255, 255, 0)
        queue.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    # 边缘柔化：alpha 轻微模糊后再拉对比
    alpha = image.getchannel("A").filter(ImageFilter.GaussianBlur(1.2))
    image.putalpha(alpha)
    return image


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source = Image.open(SRC).convert("RGB")
    print("source", source.size)

    # 正面视图在左侧约 0~360
    front = source.crop((32, 25, 352, 555))
    front = cut_background(front)
    bbox = front.getbbox()
    print("bbox", bbox)
    if bbox:
        front = front.crop((max(0, bbox[0] - 8), max(0, bbox[1] - 8), min(front.width, bbox[2] + 8), min(front.height, bbox[3] + 8)))

    target_h = 720
    ratio = target_h / front.height
    front = front.resize((int(front.width * ratio), target_h), Image.LANCZOS)
    front.save(OUT / "character.png")
    print("character", front.size)

    # 头像：脸部区域（含眼睛）
    head = front.crop((95, 95, 415, 415)).resize((320, 320), Image.LANCZOS)

    mask = Image.new("L", (320, 320), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, 319, 319), fill=255)

    backdrop = Image.new("RGBA", (320, 320), (0, 0, 0, 0))
    ImageDraw.Draw(backdrop).ellipse((0, 0, 319, 319), fill=(234, 242, 255, 255))
    avatar = Image.alpha_composite(backdrop, Image.composite(head, Image.new("RGBA", (320, 320), (0, 0, 0, 0)), mask))
    avatar.save(OUT / "avatar.png")
    print("avatar", avatar.size)


if __name__ == "__main__":
    main()
