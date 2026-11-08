# -*- coding: utf-8 -*-
"""印章素材漂移闸门：版本化素材的可见章面外接框必须与落点判据假设的 SEAL_VIS 一致。

§55.25 偏差②的收口：落点闸门 verify_card_faces.py 第 7 条的 SEAL_VIS 是交叉源硬编码
（不读 720 素材，素材缺失不造成假红），代价是素材若被改（viewBox／环径／字位）落点闸门
不会自动发现。本闸门把入仓素材 数据/运行时资产/印章-已获得-酒红.png 的非透明墨迹外接框
占比逐边对回 SEAL_VIS，容差 TOL；超出即判红，逼使改素材的人同步落点口径。

只读盘上真素材、按像素现算，不信任任何登记件、不按 mtime 猜。--root 指向副本目录即可
对夹具跑违例负测，不触碰被守护仓库。
"""
import argparse
import os
import sys
from PIL import Image

import card_geometry as v

ASSET_REL = os.path.join("数据", "运行时资产", "印章-已获得-酒红.png")
# 720 画布上 0.01≈7.2px；当前素材实测最大偏差 0.0018≈1.3px，留约 5.5 倍抖动余量，
# 环径/字位级改动会移动边缘数十像素，远超此容差。
TOL = 0.01


def measure(path):
    with Image.open(path) as im:
        im = im.convert("RGBA")
        w, h = im.size
        bbox = im.getchannel("A").getbbox()
    if bbox is None:
        return None
    l, t, r, b = bbox
    return (l / w, t / h, r / w, b / h), (w, h), bbox


def check(root):
    p = os.path.join(root, ASSET_REL)
    if not os.path.exists(p):
        return ["缺少印章素材 " + ASSET_REL]
    m = measure(p)
    if m is None:
        return ["印章素材全透明，无可见章面：" + ASSET_REL]
    frac, size, bbox = m
    fails = []
    for i, nm in enumerate(("x0", "y0", "x1", "y1")):
        if abs(frac[i] - v.SEAL_VIS[i]) > TOL:
            fails.append("印章素材可见章面 %s=%.4f 偏离 SEAL_VIS %.4f 超容差 %.3f（bbox %s size %s）"
                         % (nm, frac[i], v.SEAL_VIS[i], TOL, bbox, size))
    return fails


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    args = ap.parse_args()
    p = os.path.join(args.root, ASSET_REL)
    if os.path.exists(p):
        m = measure(p)
        if m:
            frac, size, bbox = m
            print("印章素材 %s size %s bbox %s 可见占比 %s"
                  % (ASSET_REL, size, bbox, tuple(round(x, 4) for x in frac)))
            print("对 SEAL_VIS %s 逐边偏差 %s 容差 %.3f"
                  % (v.SEAL_VIS, tuple(round(abs(frac[i] - v.SEAL_VIS[i]), 4) for i in range(4)), TOL))
    fails = check(args.root)
    for f in fails:
        print("✗ " + f)
    print("印章素材漂移闸门：%s（违例 %d 条）" % ("通过" if not fails else "未通过", len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())