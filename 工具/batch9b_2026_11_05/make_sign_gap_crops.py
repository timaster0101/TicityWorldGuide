# -*- coding: utf-8 -*-
"""6 条招牌读数缺口的目视切片（团块法）。
牌面特征：饱和度或亮度明显高于周边、横向长宽比 1.4—6、面积 400—9000 像素。只读原图、不改原图。"""
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "sign_gap_crops"
OUT.mkdir(parents=True, exist_ok=True)
IDS = ["L064", "L068", "L069", "L070", "L077", "L088"]
ZOOM = 4


def image_of(rid):
    d = json.loads((ROOT / "数据" / "开图清单.json").read_text(encoding="utf-8"))["items"]
    for it in d:
        if it["id"] == rid and it["image_file"]:
            f = it["image_file"]
            return (f[0] if isinstance(f, list) else f), it["name"]
    raise KeyError(rid)


def blobs(arr, band_top):
    """返回街面带内的牌面候选团块（bbox + 分数）。"""
    h, w, _ = arr.shape
    mx = arr.max(axis=2).astype(np.int16)
    mn = arr.min(axis=2).astype(np.int16)
    sat = mx - mn
    lum = arr.mean(axis=2)
    mask = np.zeros((h, w), dtype=bool)
    mask[band_top:, :] = (sat[band_top:, :] > 68) | (lum[band_top:, :] > 236) | (lum[band_top:, :] < 34)
    mask = ndimage.binary_closing(mask, structure=np.ones((3, 3)))
    lab, n = ndimage.label(mask)
    out = []
    for sl in ndimage.find_objects(lab):
        if sl is None:
            continue
        y, x = sl
        bh, bw = y.stop - y.start, x.stop - x.start
        area = int((lab[y, x] > 0).sum())
        if not (400 <= bw * bh <= 9000):
            continue
        ratio = bw / max(1, bh)
        if not (1.4 <= ratio <= 6.0):
            continue
        fill = area / float(bw * bh)
        if fill < 0.35:
            continue
        score = float(sat[y, x].mean()) * 0.6 + float(lum[y, x].mean()) * 0.4
        out.append({"box": (int(x.start), int(y.start), int(x.stop), int(y.stop)),
                    "score": round(score, 1), "ratio": round(ratio, 2), "fill": round(fill, 2)})
    out.sort(key=lambda b: -b["score"])
    kept = []
    for b in out:
        cx = (b["box"][0] + b["box"][2]) / 2.0
        cy = (b["box"][1] + b["box"][3]) / 2.0
        if any(abs(cx - (k["box"][0] + k["box"][2]) / 2.0) < 90 and abs(cy - (k["box"][1] + k["box"][3]) / 2.0) < 60
               for k in kept):
            continue
        kept.append(b)
    return kept[:4], mask


def main():
    for rid in IDS:
        rel, name = image_of(rid)
        im = Image.open(ROOT / rel).convert("RGB")
        arr = np.asarray(im)
        band_top = int(im.height * 0.45)
        found, mask = blobs(arr, band_top)
        cov = float(mask.sum()) / float((im.height - band_top) * im.width)
        print("%s｜%s｜%dx%d｜街面带=%d..%d｜候选=%d｜带内高对比像素占比=%.3f"
              % (rid, name, im.width, im.height, band_top, im.height, len(found), cov))
        for b in found:
            print("   box=%s 宽高比=%.2f 填充=%.2f 分数=%.1f" % (b["box"], b["ratio"], b["fill"], b["score"]))
        if not found:
            continue
        pad = 16
        panels = []
        for b in found:
            x0, y0, x1, y1 = b["box"]
            crop = im.crop((max(0, x0 - pad), max(0, y0 - pad),
                             min(im.width, x1 + pad), min(im.height, y1 + pad)))
            crop = crop.resize((crop.width * ZOOM, crop.height * ZOOM), Image.LANCZOS)
            panels.append(crop)
        pw = max(p.width for p in panels)
        sheet = Image.new("RGB", (pw + 8, sum(p.height for p in panels) + 8 * len(panels)), (20, 20, 20))
        sy = 4
        for p in panels:
            sheet.paste(p, (4, sy))
            sy += p.height + 8
        out = OUT / ("%s_牌面候选.png" % rid)
        sheet.save(out)
        print("   → %s（%d 格，%dx%d）" % (out.relative_to(ROOT), len(panels), sheet.width, sheet.height))


if __name__ == "__main__":
    main()
