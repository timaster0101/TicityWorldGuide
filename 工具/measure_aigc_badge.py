# -*- coding: utf-8 -*-
"""全量实测 80 张卡面源图右下角 AIGC 台标的上沿，给 SEAL_BADGE_BAND 一个全量下界依据。

此前 35 px 只是 4/80 OCR 样本的上界（D01 这种两行大标曾被漏读）。本工具改用
源图空间裁右下角 12%×10%、6× 放大、tesseract chi_sim psm 6（chi_sim+eng 混排会把这枚低对比小标读空，实测），
逐张取「AI／生成／TC260／元数据／标识」词框的最小 y 作为台标上沿，再换算到卡面空间
（贴入格由 build_card_faces.window_box 给出，与合成器实际贴法一致）。

读数落 数据/台标带实测.json：逐张 source 上沿、卡面上沿、距实景下沿、是否检出。
未检出的卡不猜高度，只记 detected=False；判据取值另由人工按检出最大值定。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

from PIL import Image, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import build_card_faces as bcf

TESS = r"C:\Program Files\Tesseract-OCR\tesseract.EXE"
TOKEN = re.compile(r"AI|生成|TC260|元|数据|标|识", re.I)


def badge_top_source(path):
    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
    crop = im.crop((int(w * 0.88), int(h * 0.90), w, h)).convert("L")
    crop = crop.resize((crop.width * 6, crop.height * 6), Image.LANCZOS)
    with tempfile.TemporaryDirectory() as td:
        png = os.path.join(td, "c.png")
        crop.save(png)
        p = subprocess.run([TESS, png, "stdout", "-l", "chi_sim", "--psm", "6", "tsv"],
                           capture_output=True, text=True)
    tops, words = [], []
    for line in p.stdout.splitlines()[1:]:
        f = line.split("\t")
        if len(f) < 12 or f[0] != "5":  # tesseract TSV 词级是 level 5，不是 12
            continue
        txt = f[11].strip()
        if not txt or not TOKEN.search(txt):
            continue
        conf = float(f[10])
        if conf < 20:
            continue
        y = int(f[7]) / 6.0 + h * 0.90
        tops.append(y)
        words.append((txt, round(conf, 1), round(y, 1)))
    return (min(tops) if tops else None), words, (w, h)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(ROOT, "数据", "台标带实测.json"))
    ap.add_argument("--full-bleed", action="store_true",
                    help="路线 B（C148）满幅主图：源即整卡，卡面空间按 1:1 换算，不走已退役的实景窗映射")
    args = ap.parse_args()
    with open(os.path.join(ROOT, "数据", "视觉控制资产", "卡牌", "768x1024", "manifest.json"), encoding="utf-8") as fp:
        man = json.load(fp)
    body = bcf.body_rect()
    rows = []
    for c in man["cards"]:
        if c["status"] != "OK":
            continue
        src = c["source"]
        top, words, size = badge_top_source(src)
        if args.full_bleed:
            box = [0, 0, 768, 1024]
        else:
            box = list(bcf.window_box(body, size))
        scale = box[2] / float(size[0])
        photo_bottom = box[1] + box[3]
        top_card = None if top is None else box[1] + top * scale
        rows.append({"code": c["code"], "file": c["file"], "src_size": list(size),
                     "detected": top is not None, "words": words,
                     "badge_top_src": None if top is None else round(top, 1),
                     "badge_top_card": None if top_card is None else round(top_card, 1),
                     "dist_above_photo_bottom": None if top_card is None else round(photo_bottom - top_card, 1)})
    det = [r for r in rows if r["detected"]]
    summary = {"统计面": "manifest status=OK 的 %d 张源图，逐张全量、非抽样；换算路线＝%s" % (
        len(rows), "满幅 1:1（C148 路线 B，源即整卡）" if args.full_bleed else "实景窗映射（烤 PNG 时代）"),
               "检出": len(det), "未检出": len(rows) - len(det),
               "距实景下沿_max": max((r["dist_above_photo_bottom"] for r in det), default=None),
               "距实景下沿_min": min((r["dist_above_photo_bottom"] for r in det), default=None),
               "rows": rows}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, ensure_ascii=False))
    for r in sorted(det, key=lambda r: -r["dist_above_photo_bottom"])[:8]:
        print("  %-6s 距底 %5.1f  词 %s" % (r["code"], r["dist_above_photo_bottom"], r["words"]))
    if not det:
        print("✗ 全量 0 检出：检测器退化或预处理失效，本读数不作判据依据")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())