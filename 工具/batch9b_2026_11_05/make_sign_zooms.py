# -*- coding: utf-8 -*-
"""6 条缺口的定点放大纸：按人工在带视图上读出的牌面位置开框，4x／3x 上采样后逐张目视。只读原图。"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
VIBE = ROOT / "vibe_images"
OUT = Path(__file__).resolve().parent / "sign_gap_crops"

BOXES = {
    "L064": [("灯杆竖幅旗帜", (838, 858, 1024, 1062), 4), ("玻璃厅入口上沿", (300, 930, 560, 1060), 4),
             ("摊车棚与灯箱", (820, 990, 1024, 1230), 4)],
    "L068": [("底商白底横牌", (918, 1000, 998, 1048), 4), ("门口暖黄灯箱排", (918, 1040, 998, 1082), 4)],
    "L069": [("红牌与摊棚", (0, 540, 330, 800), 4), ("菜单灯箱", (0, 700, 260, 920), 4),
             ("施工告示牌", (730, 680, 890, 790), 4), ("右侧候选牌面", (1230, 590, 1380, 700), 4)],
    "L070": [("入口雨棚上沿", (0, 690, 420, 900), 3), ("大堂门侧", (40, 850, 340, 1120), 3),
             ("沿街退线", (380, 690, 720, 900), 3)],
    "L077": [("玻璃房上沿横带", (770, 430, 960, 510), 4), ("左侧广场棚架", (180, 690, 620, 810), 3),
             ("入口门楣", (280, 380, 720, 540), 3)],
    "L088": [("老城底商牌面群", (1140, 720, 1536, 1024), 3), ("大巴车身记号", (760, 620, 1100, 760), 3)],
}


def find(rid):
    hits = sorted(VIBE.glob("%s-*-C123新串-v01_*.png" % rid))
    assert len(hits) == 1, (rid, hits)
    return hits[0]


for rid, boxes in BOXES.items():
    im = Image.open(find(rid)).convert("RGB")
    panels = []
    for label, (x0, y0, x1, y1), zoom in boxes:
        crop = im.crop((x0, y0, x1, y1))
        crop = crop.resize((crop.width * zoom, crop.height * zoom), Image.LANCZOS)
        panels.append((label, (x0, y0, x1, y1), zoom, crop))
        print("%s｜%s｜框=%s｜%dx放大→%s" % (rid, label, (x0, y0, x1, y1), zoom, crop.size))
    pw = max(p[3].width for p in panels)
    sheet = Image.new("RGB", (pw + 8, sum(p[3].height for p in panels) + 8 * len(panels)), (20, 20, 20))
    sy = 4
    for _, _, _, crop in panels:
        sheet.paste(crop, (4, sy))
        sy += crop.height + 8
    out = OUT / ("%s_定点放大.png" % rid)
    sheet.save(out)
    print("   → %s（%d 格，%dx%d）" % (out.relative_to(ROOT), len(panels), sheet.width, sheet.height))
