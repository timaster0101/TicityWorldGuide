# -*- coding: utf-8 -*-
"""把 4 张高倍定点放大纸按格拆开单独保存，避免查看器整体降采样后读数失真。只读切片图。"""
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
CROPS = HERE / "sign_gap_crops"

# 与 make_sign_zooms.py 的 BOXES 一致：(框宽, 框高, 倍率) 推出每格像素高度
ZOOMS = {
    "L064": [((838, 858, 1024, 1062), 4), ((300, 930, 560, 1060), 4), ((820, 990, 1024, 1230), 4)],
    "L069": [((0, 540, 330, 800), 4), ((0, 700, 260, 920), 4),
             ((730, 680, 890, 790), 4), ((1230, 590, 1380, 700), 4)],
    "L070": [((0, 690, 420, 900), 3), ((40, 850, 340, 1120), 3), ((380, 690, 720, 900), 3)],
    "L077": [((770, 430, 960, 510), 4), ((180, 690, 620, 810), 3), ((280, 380, 720, 540), 3)],
}

for rid, boxes in ZOOMS.items():
    sheet = Image.open(CROPS / ("%s_定点放大.png" % rid))
    sy = 4
    for i, ((x0, y0, x1, y1), zoom) in enumerate(boxes, 1):
        h = (y1 - y0) * zoom
        panel = sheet.crop((4, sy, sheet.width - 4, sy + h))
        out = CROPS / ("%s_定点_p%d.png" % (rid, i))
        panel.save(out)
        print("%s 第%d格 %dx%d → %s" % (rid, i, panel.width, panel.height, out.name))
        sy += h + 8
    print("   %s 合计消费 %d/%d 高" % (rid, sy - 8, sheet.height))
