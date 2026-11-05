# -*- coding: utf-8 -*-
"""按源图像素坐标画网格的切片器：给「屋面细杆算不算记号」这类判读提供可量的数，不靠目测印象。

用法：python -X utf8 工具/batch9f_2026_11_06/grid_crop.py <id> <x0> <y0> <x1> <y1> <倍数> <网格步长px> [名字]
坐标按 0—1 比例给；网格线按源图像素步长画，标签写源图 y 坐标；产物写 crops/<id>_网格_<名字>.png，只读原图。

为什么要网格：C125 只写「桅杆／细针天线即判废」，上一轮 L067 的读数又留了一句
「发丝状直细丝、无横档无格构、高度远小于塔身十二分之一」的待观察口径。两档的分界必须有可复量的数，
否则同一根杆这一轮判废、下一轮判待观察，判废率就成了评审人的手气。
"""
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VIBE = ROOT / "vibe_images"
OUT = HERE / "crops"
OUT.mkdir(exist_ok=True)

rid, x0, y0, x1, y1, scale, step = sys.argv[1:8]
name = sys.argv[8] if len(sys.argv) > 8 else "局部"
x0, y0, x1, y1, scale, step = (float(x0), float(y0), float(x1), float(y1), float(scale), int(step))

FLOOR = 1793901894424  # 本轮探针落盘 ts；§32.6：按时间戳带取本轮产物，同名档历史文件不算
cands = sorted(
    (p for p in VIBE.glob("%s-*C123新串-v02*.png" % rid)
     if re.search(r"_(\d{13})_", p.name)
     and int(re.search(r"_(\d{13})_", p.name).group(1)) >= FLOOR),
    key=lambda p: int(re.search(r"_(\d{13})_", p.name).group(1)),
)
assert len(cands) == 1, (rid, "带内应恰 1 张本轮产物", [p.name for p in cands])
im = Image.open(cands[-1]).convert("RGB")
w, h = im.size
box = (int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))
crop = im.crop(box)
big = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.LANCZOS)
d = ImageDraw.Draw(big)
for sy in range(box[1], box[3], step):
    y = int((sy - box[1]) * scale)
    d.line((0, y, big.width, y), fill=(0, 255, 255), width=1)
    d.text((2, max(0, y - 11)), str(sy), fill=(0, 255, 255))
for sy in range(box[0], box[2], step):
    x = int((sy - box[0]) * scale)
    d.line((x, 0, x, big.height), fill=(255, 0, 255), width=1)
    d.text((max(0, x + 2), 2), str(sy), fill=(255, 0, 255))
p = OUT / ("%s_网格_%s.png" % (rid, name))
big.save(p)
print(p, cands[-1].name, box, "step=%d" % step, "->", big.size)
