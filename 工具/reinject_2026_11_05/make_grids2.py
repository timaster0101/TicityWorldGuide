# -*- coding: utf-8 -*-
"""按幅面分组重拼 19 张 C123 新串图的整帧对照表（横幅单列大图、竖幅四列）。只读原图。"""
import re
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
VIBE = ROOT / "vibe_images"
OUT = Path(__file__).resolve().parent


def rows_by_orient():
    out = []
    for f in sorted(VIBE.glob("*C123新串*.png")):
        rid = re.match(r"([A-Z]\d{2,3})-", f.name).group(1)
        with Image.open(f) as im:
            out.append((rid, f, "横幅" if im.width > im.height else "竖幅"))
    return out


def cell(rid, path, w, tag=""):
    im = Image.open(path).convert("RGB")
    scale = w / im.width
    th = im.resize((w, max(1, int(im.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGB", (th.width, th.height + 24), (24, 24, 24))
    canvas.paste(th, (0, 24))
    ImageDraw.Draw(canvas).text((6, 5), "%s %s" % (rid, tag), fill=(255, 232, 120))
    return canvas


def main():
    data = rows_by_orient()
    ban = [d for d in data if d[2] == "横幅"]
    por = [d for d in data if d[2] == "竖幅"]
    print("横幅", len(ban), "竖幅", len(por))

    cells = [cell(r, p, 880, "横幅整帧") for r, p, _ in ban]
    h = sum(c.height for c in cells)
    sheet = Image.new("RGB", (880, h), (12, 12, 12))
    y = 0
    for c in cells:
        sheet.paste(c, (0, y))
        y += c.height
    sheet.save(OUT / "c123_banners_full.png")
    print("c123_banners_full.png", sheet.size)

    cols = 4
    cw = 380
    cells = [cell(r, p, cw, "竖幅整帧") for r, p, _ in por]
    rh = max(c.height for c in cells)
    sheet = Image.new("RGB", (cols * cw, ((len(cells) + cols - 1) // cols) * rh), (12, 12, 12))
    for i, c in enumerate(cells):
        r, cc = divmod(i, cols)
        sheet.paste(c, (cc * cw, r * rh))
    sheet.save(OUT / "c123_portraits_full.png")
    print("c123_portraits_full.png", sheet.size)


if __name__ == "__main__":
    main()
