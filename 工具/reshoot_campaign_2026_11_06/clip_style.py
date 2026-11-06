# -*- coding: utf-8 -*-
"""CLIP 零样本画风判据实验: 照片/CG渲染 档 vs 数字绘画 档.
输出每图: 各类模板相似度 + 类均值 softmax 概率; 再按组级标签量分离度.
"""
import os, sys, glob, json
import numpy as np
from PIL import Image
import torch
from transformers import CLIPModel, CLIPProcessor

ROOT = r"C:\Users\TIMASTER\Documents\Qoder\2026-10-29\c8c10ff8"
SET = os.path.join(ROOT, "钛湖城城市设定集")
V = os.path.join(ROOT, "vibe_images")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clip_style_scores.tsv")
M = os.environ.get("CLIP_MODEL_DIR", os.path.join(ROOT, "_scratch_reshoot", "clip-model"))  # 权重 605247071 字节不入库

PHOTO_T = [
    "a photograph",
    "a photo taken with a camera",
    "a photorealistic architectural visualization render",
    "a clean 3D CGI rendering of a building",
]
PAINT_T = [
    "a semi-realistic digital painting",
    "a hand-painted illustration",
    "a painting with soft blended brush transitions",
    "an illustration rather than a snapshot",
]


def build_items():
    it = []
    for p in sorted(glob.glob(os.path.join(SET, "backup", "vibe_images", "*C123新串*.png"))):
        it.append(("PHOTO", "C123-" + os.path.basename(p)[:34], p))
    for p in sorted(glob.glob(os.path.join(V, "*C133冻结重投*.png"))):
        it.append(("PHOTO", "C133-" + os.path.basename(p)[:30], p))
    it.append(("PHOTO", "半写实E0-基线纯写实", os.path.join(SET, "backup", "数据", "视觉控制资产", "E1半写实厚涂", "E0-基线纯写实.png")))
    for p in sorted(glob.glob(os.path.join(SET, "数据", "视觉控制资产", "E1定档-20261103", "*.png"))):
        it.append(("PAINT", "E1-" + os.path.basename(p)[:30], p))
    for p in sorted(glob.glob(os.path.join(SET, "数据", "视觉控制资产", "画风诊断-媒介强度三档-2026-11-04", "*.png"))):
        it.append(("PAINT", "档-" + os.path.basename(p)[:24], p))
    for p in [os.path.join(V, "D03-东湖金融片区-画风通道实验-v01_1793974245358_a45b2ea5.png"),
              os.path.join(V, "D03-东湖金融片区-画风通道实验-v02_1793974408154_794acdb9.png")]:
        it.append(("PAINT", "实验-" + os.path.basename(p)[:26], p))
    it.append(("PAINT", "半写实E1-定稿", os.path.join(SET, "backup", "数据", "视觉控制资产", "E1半写实厚涂", "E1-定稿半写实厚涂.png")))
    return [x for x in it if os.path.exists(x[2])]


def sep(labels, scores):
    pairs = sorted(zip(scores, labels))
    best = 99; bthr = None
    for i in range(1, len(pairs)):
        if pairs[i - 1][0] == pairs[i][0]:
            continue
        thr = (pairs[i - 1][0] + pairs[i][0]) / 2.0
        e = min(sum(1 for s, l in pairs if (s > thr) != (l == "PHOTO")),
                sum(1 for s, l in pairs if (s > thr) != (l == "PAINT")))
        if e < best:
            best, bthr = e, thr
    return best, bthr


def main():
    items = build_items()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print("loading clip on", dev, flush=True)
    model = CLIPModel.from_pretrained(M).to(dev).eval()
    proc = CLIPProcessor.from_pretrained(M)
    texts = PHOTO_T + PAINT_T
    with torch.no_grad():
        tx = proc(text=texts, return_tensors="pt", padding=True).to(dev)
        temb = model.get_text_features(**tx)["pooler_output"]
        temb = temb / temb.norm(dim=-1, keepdim=True)
    ph = temb[:len(PHOTO_T)].mean(0); ph = ph / ph.norm()
    pa = temb[len(PHOTO_T):].mean(0); pa = pa / pa.norm()
    rows = []
    for lab, name, p in items:
        im = Image.open(p).convert("RGB")
        with torch.no_grad():
            f = proc(images=im, return_tensors="pt").to(dev)
            e = model.get_image_features(**f)["pooler_output"]
            e = e / e.norm(dim=-1, keepdim=True)
            sims = (e @ temb.T)[0].cpu().numpy()
        sp = float(e[0] @ ph); spa = float(e[0] @ pa)
        logit = 100.0 * np.array([sp, spa])
        pr = np.exp(logit - logit.max()); pr /= pr.sum()
        rows.append((lab, name, os.path.basename(p), float(sims.max()), sp, spa, float(pr[0])))
        print("%-5s %-38s photo=%.4f paint=%.4f P(photo)=%.4f" % (lab, name, sp, spa, pr[0]), flush=True)
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("label\tname\tfile\tmax_sim\tphoto\tpaint\tp_photo\n")
        for r in rows:
            f.write("\t".join([r[0], r[1], r[2]] + ["%.6f" % x for x in r[3:]]) + "\n")
    print("\n== 分离度 (P(photo) 作分界) ==")
    labs = [r[0] for r in rows]; sc = np.array([r[6] for r in rows])
    b, t = sep(labs, sc)
    print("最小错分=%d/%d @thr=%.4f" % (b, len(rows), t))
    for key, idx in (("max_sim", 3), ("photo", 4), ("paint", 5)):
        bb, tt = sep(labs, np.array([r[idx] for r in rows]))
        print("%-8s 最小错分=%d/%d @thr=%.4f" % (key, bb, len(rows), tt))
    # 按分数排序打印错分名单
    order = np.argsort(-sc)
    print("\n== 按 P(photo) 降序 ==")
    for i in order:
        print("  P(photo)=%.4f %-5s %s" % (sc[i], labs[i], rows[i][1]))


import io
main()
