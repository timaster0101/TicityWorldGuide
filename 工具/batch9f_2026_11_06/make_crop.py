# -*- coding: utf-8 -*-
"""第9批 f 轮（12 条第五投 v02）按 id 裁出原图局部并放大，供人工目视复核。

用法：python -X utf8 工具/batch9f_2026_11_06/make_crop.py <id> <x0> <y0> <x1> <y1> <倍数> [名字]
坐标按 0—1 比例给（相对原图宽高），产物写 crops/<id>_<名字>.png，只读原图、不改原图。
只看本轮时间戳带内的 v02 产物：9c／9e 轮也投过同名档，带外的历史文件一律不作本轮产物。
"""
import re
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VIBE = ROOT / "vibe_images"
OUT = HERE / "crops"
OUT.mkdir(exist_ok=True)

rid, x0, y0, x1, y1, scale = sys.argv[1:7]
name = sys.argv[7] if len(sys.argv) > 7 else "局部"
x0, y0, x1, y1, scale = float(x0), float(y0), float(x1), float(y1), float(scale)

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
crop = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.LANCZOS)
p = OUT / ("%s_%s.png" % (rid, name))
crop.save(p)
print(p, cands[-1].name, box, "->", crop.size)
