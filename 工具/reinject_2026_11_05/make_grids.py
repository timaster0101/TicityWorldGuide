# -*- coding: utf-8 -*-
"""把 19 张 C123 新串图拼成两张对照表：整帧缩略网格 与 上半幅（背景天际线所在区）网格。

只读原图，不改名、不裁剪原图、不写任何真源；产物为目视对照用的拼图。
"""
import io
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
VIBE = ROOT / "vibe_images"
OUT = Path(__file__).resolve().parent
CELL_W = 360


def grid(rows, out_path, upper_only, cols=4):
    thumbs = []
    for rid, path in rows:
        im = Image.open(path).convert("RGB")
        if upper_only:
            im = im.crop((0, 0, im.width, im.height // 2))
        scale = CELL_W / im.width
        th = im.resize((CELL_W, max(1, int(im.height * scale))), Image.LANCZOS)
        canvas = Image.new("RGB", (th.width, th.height + 26), (24, 24, 24))
        canvas.paste(th, (0, 26))
        d = ImageDraw.Draw(canvas)
        d.text((6, 5), "%s  %s" % (rid, "upper" if upper_only else "full"), fill=(255, 232, 120))
        thumbs.append(canvas)
    max_h = max(t.height for t in thumbs)
    n = len(thumbs)
    sheet = Image.new("RGB", (cols * CELL_W, ((n + cols - 1) // cols) * max_h), (12, 12, 12))
    for i, t in enumerate(thumbs):
        r, c = divmod(i, cols)
        sheet.paste(t, (c * CELL_W, r * max_h))
    sheet.save(out_path)
    print("%s -> %s (%dx%d)" % (out_path.name, out_path, sheet.width, sheet.height))


def main():
    files = sorted(VIBE.glob("*C123新串*.png"))
    rows = []
    for f in files:
        rid = re.match(r"([A-Z]\d{2,3})-", f.name).group(1)
        rows.append((rid, f))
    grid(rows, OUT / "c123_grid_full.png", False)
    grid(rows, OUT / "c123_grid_upper.png", True)
    print("cells", len(rows))


if __name__ == "__main__":
    main()
