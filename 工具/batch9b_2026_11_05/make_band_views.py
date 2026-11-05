# -*- coding: utf-8 -*-
"""地面层整幅带视图：先看牌面在不在（原尺），再按需放大。只读原图、不改原图。"""
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "sign_gap_crops"
IDS = ["L064", "L068", "L069", "L070", "L077", "L088"]


def image_of(rid):
    d = json.loads((ROOT / "数据" / "开图清单.json").read_text(encoding="utf-8"))["items"]
    for it in d:
        if it["id"] == rid and it["image_file"]:
            f = it["image_file"]
            return (f[0] if isinstance(f, list) else f), it["name"]
    raise KeyError(rid)


for rid in IDS:
    rel, name = image_of(rid)
    im = Image.open(ROOT / rel).convert("RGB")
    w, h = im.width, im.height
    band = im.crop((0, int(h * 0.50), w, h))
    p1 = OUT / ("%s_地面带原尺.png" % rid)
    band.save(p1)
    strip = im.crop((0, int(h * 0.76), w, h))
    strip = strip.resize((strip.width * 2, strip.height * 2), Image.LANCZOS)
    mid = strip.width // 2
    for tag, box in (("左", (0, 0, mid, strip.height)), ("右", (mid, 0, strip.width, strip.height))):
        p = OUT / ("%s_近地面2x%s.png" % (rid, tag))
        strip.crop(box).save(p)
    print("%s｜%s｜带=%s｜近地面2x两格=%s" % (rid, name, band.size, (strip.width // 2, strip.height)))
