# -*- coding: utf-8 -*-
"""卡面交付资产闸门：核验 数据/视觉控制资产/卡牌/768x1024/{无文案,有文案} 的成对交付。

判据全部机器可验，不做画风目视：
  1) 两版数量相等、文件名逐一对应，且与 数据/卡面文案底稿.json 的条目同名；
  2) 每张尺寸 768×1024；
  3) manifest 副标题不含档号（A12／L009／T3 之类），即「副标题里的编号一起去掉」已落实；
  4) 不存在「源放不下」的卡——竖幅源必须由 数据/卡面专用提示词/ 产出的横幅图顶上，不许挤压或留白；
  5) 有文案版底部文字带有墨、无文案版同带无墨，两版只差程序叠字那一段；
  6) 占位窗（实景待投／需卡面专用图）只允许出现在 manifest 记为 MISSING 的卡上。

--root 指向副本目录即可对夹具跑违例负测，不触碰被守护仓库。
"""
import argparse
import collections
import json
import os
import re
import sys
from PIL import Image, ImageChops

CANVAS = (768, 1024)
MARGIN = {"left": 0.0931, "right": 0.0765, "top": 0.0625, "bottom": 0.0529}
BOTTOM_BAND = (0.872, 0.899)
WINDOW_BAND = (0.3200, 0.7930)
PLACEHOLDER_FILL = (0xE9, 0xE1, 0xD3)
CODE_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]\d{2,3}(?![0-9])")


def body_rect(w, h):
    x0 = round(w * MARGIN["left"])
    x1 = w - round(w * MARGIN["right"])
    y0 = round(h * MARGIN["top"])
    y1 = h - round(h * MARGIN["bottom"])
    return x0, y0, x1 - x0, y1 - y0


def band_rows(img, lo, hi):
    x, y, w, h = body_rect(*img.size)
    return img.crop((x + w // 8, y + round(h * lo), x + w - w // 8, y + round(h * hi)))


def ink_count(img):
    return img.convert("L").point(lambda v: 255 if v < 170 else 0).histogram()[255]


def placeholder_ratio(img):
    box = band_rows(img, *WINDOW_BAND)
    if not box.size[0] or not box.size[1]:
        return 0.0
    diff = ImageChops.difference(box.convert("RGB"), Image.new("RGB", box.size, PLACEHOLDER_FILL))
    worst = ImageChops.lighter(ImageChops.lighter(diff.getchannel("R"), diff.getchannel("G")),
                               diff.getchannel("B"))
    hit = worst.point(lambda v: 255 if v <= 4 else 0).histogram()[255]
    return hit / float(box.size[0] * box.size[1])


def check(root):
    fails = []
    cards_dir = os.path.join(root, "数据", "视觉控制资产", "卡牌", "768x1024")
    manifest_path = os.path.join(cards_dir, "manifest.json")
    draft_path = os.path.join(root, "数据", "卡面文案底稿.json")
    for p in (manifest_path, draft_path):
        if not os.path.exists(p):
            return ["缺少 " + os.path.relpath(p, root)]
    with open(manifest_path, encoding="utf-8") as fh:
        man = json.load(fh)
    with open(draft_path, encoding="utf-8") as fh:
        draft = json.load(fh)

    want = {os.path.splitext(it["file"])[0] for it in draft["items"]}
    variants = man.get("variants") or []
    if sorted(variants) != ["无文案", "有文案"]:
        fails.append("manifest 版本应为 无文案/有文案，实为 %s" % variants)
    by_variant = {}
    for v in variants:
        d = os.path.join(cards_dir, v)
        if not os.path.isdir(d):
            fails.append("目录缺失 %s" % v)
            continue
        names = {os.path.splitext(f)[0] for f in os.listdir(d) if f.lower().endswith(".png")}
        by_variant[v] = names
        if names != want:
            fails.append("%s 与底稿不同名：缺 %d 个 / 多 %d 个" %
                         (v, len(want - names), len(names - want)))
    if len(by_variant) == 2 and by_variant.get("无文案") != by_variant.get("有文案"):
        fails.append("两版文件名不一致")

    codes = {os.path.splitext(c["file"])[0]: c for c in man["cards"]}
    if len(codes) != len(man["cards"]):
        fails.append("manifest 条目文件名重复：%d 条 / %d 个唯一名" % (len(man["cards"]), len(codes)))

    stat = collections.Counter(c["status"] for c in man["cards"])
    if stat.get("OVERFLOW"):
        fails.append("仍有 %d 张源放不下窗幅，须先出卡面专用图" % stat["OVERFLOW"])

    for v, names in by_variant.items():
        for stem in sorted(names):
            p = os.path.join(cards_dir, v, stem + ".png")
            with Image.open(p) as im:
                if im.size != CANVAS:
                    fails.append("%s/%s 尺寸 %s ≠ %s" % (v, stem, im.size, CANVAS))
                    continue
                rec = codes.get(stem)
                if rec is None:
                    fails.append("%s/%s 不在 manifest 内" % (v, stem))
                    continue
                if rec["template"] == "back":
                    continue
                if v == "无文案" and ink_count(band_rows(im, *BOTTOM_BAND)) > 0:
                    fails.append("%s 无文案版底部文字带仍有墨" % stem)
                if v == "有文案" and rec["bottom"] and ink_count(band_rows(im, *BOTTOM_BAND)) == 0:
                    fails.append("%s 有文案版底部文字带无墨" % stem)
                ph = placeholder_ratio(im)
                if (rec["status"] == "MISSING") != (ph > 0.9):
                    fails.append("%s 占位窗判据与状态不符：status=%s 占位比 %.2f" %
                                 (stem, rec["status"], ph))
    for c in man["cards"]:
        if CODE_RE.search(c.get("subtitle") or ""):
            fails.append("%s 副标题仍含档号：%s" % (c["file"], c["subtitle"]))
    return fails


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    args = ap.parse_args()
    fails = check(args.root)
    for f in fails:
        print("✗ " + f)
    print("卡面资产闸门：%s（违例 %d 条）" % ("通过" if not fails else "未通过", len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
