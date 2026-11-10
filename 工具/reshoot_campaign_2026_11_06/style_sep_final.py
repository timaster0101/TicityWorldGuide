# -*- coding: utf-8 -*-
"""C134 像素判据终版：在 75 张定标签集上逐特征量分离度，产物落 TSV。

特征 = 真源机检量（fine_variance / sun_blob，同式取自
工具/parallel_batch_2026_11_03/measure_images.py）＋ 9 项自研量。
标签沿用 clip_style.build_items()（与 CLIP 实验同一集合，两次实验可逐张对拍）。
"""
import io
import os
import sys
import importlib.util
import numpy as np
from PIL import Image

ROOT = r"C:\Users\TIMASTER\Documents\Qoder\2026-10-29\c8c10ff8"
SET = os.path.join(ROOT, "钛湖城城市设定集")
sys.path.insert(0, os.path.join(SET, "工具", "parallel_batch_2026_11_03"))
from measure_images import fine_variance, sun_blob  # noqa: E402  真源同式

# 复用 clip_style 的样本集与标签（不重复维护名单）
_p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clip_style.py")
with io.open(_p, encoding="utf-8") as fp:
    _cs_src = fp.read()
_ns = {"__name__": "probe", "os": os, "glob": __import__("glob")}
exec(compile(_cs_src.split("def main()")[0], "clip_style.py", "exec"), _ns)
ITEMS = _ns["build_items"]()

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style_sep_final.tsv")


def boxmean(a, k):
    pad = k // 2
    P = np.pad(a, pad, mode="edge")
    j = np.zeros((P.shape[0] + 1, P.shape[1] + 1))
    j[1:, 1:] = np.cumsum(np.cumsum(P, axis=0), axis=1)
    return (j[k:, k:] - j[:-k, k:] - j[k:, :-k] + j[:-k, :-k]) / float(k * k)


def feats(path):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    rgb = np.asarray(im, dtype=np.float64)
    a = rgb.mean(axis=2)
    gray = im.convert("L")
    out = {"fine_var_full": fine_variance(gray), "sun_blob_px": sun_blob(gray)}
    bh, bw = 16, 16
    nH, nW = h // bh, w // bw
    box = boxmean(a, 5)
    r = a - box[:h, :w]
    rs = r[:nH * bh, :nW * bw]
    gy, gx = np.gradient(box)
    lg = np.abs(gx) + np.abs(gy)
    L = lg[:nH * bh, :nW * bw].reshape(nH, bh, nW, bw).mean(axis=(1, 3))
    sel = L <= np.percentile(L, 25)
    res_blk = rs.reshape(nH, bh, nW, bw).std(axis=(1, 3))
    out["flat_noise"] = float(res_blk[sel].mean())
    out["res_all"] = float(res_blk.mean())

    d1 = np.abs(np.diff(rs, axis=1)).mean()
    d2 = np.abs(rs[:, 2:] - rs[:, :-2]).mean()
    out["ratio12"] = float(d1 / d2) if d2 else float("nan")

    ac1 = ac2 = ac0 = hi = lo = 0.0
    fy = np.fft.fftfreq(bh)[:, None]
    fx = np.fft.rfftfreq(bw)[None, :]
    fr = np.sqrt(fy * fy + fx * fx)
    for y, x in np.argwhere(sel):
        b = rs[y * bh:(y + 1) * bh, x * bw:(x + 1) * bw]
        b = b - b.mean()
        ac0 += float((b * b).sum())
        ac1 += float((b[:, :-1] * b[:, 1:]).sum())
        ac2 += float((b[:, 2:] * b[:, :-2]).sum())
        sp = np.abs(np.fft.rfft2(b)) ** 2
        hi += sp[fr > 0.25].sum()
        lo += sp[fr <= 0.25].sum()
    out["ar1"] = float(ac1 / max(ac0, 1e-9))
    out["ar2"] = float(ac2 / max(ac0, 1e-9))
    out["spectral_hi"] = float(hi / max(lo, 1e-9))

    db = rgb[:, :, 0] - rgb[:, :, 2]
    bd = db - boxmean(db, 5)
    cd = bd[:nH * bh, :nW * bw].reshape(nH, bh, nW, bw).std(axis=(1, 3))
    out["luma_over_chroma"] = out["flat_noise"] / max(float(cd[sel].mean()), 1e-9)

    fine = res_blk * 0 + rs.reshape(nH, bh, nW, bw).std(axis=(1, 3))
    mid = (boxmean(a, 3) - boxmean(a, 9))[:nH * bh, :nW * bw].reshape(nH, bh, nW, bw).std(axis=(1, 3))
    lum = a[:nH * bh, :nW * bw].reshape(nH, bh, nW, bw).mean(axis=(1, 3))
    ok = lum > 8
    fv = np.sort(fine[ok])
    q = max(1, len(fv) // 4)
    out["sharp_spread"] = float(np.mean(fv[-q:]) / max(np.mean(fv[:q]), 1e-9))
    out["fine_vs_mid"] = float(np.mean(fine[ok]) / max(np.mean(mid[ok]), 1e-9))

    b5 = boxmean(a, 5)
    gy5, gx5 = np.gradient(b5)
    lf = np.abs(np.sqrt(gx5 * gx5 + gy5 * gy5))[:nH * bh, :nW * bw].reshape(nH, bh, nW, bw).mean(axis=(1, 3))
    s2 = (lf <= np.percentile(lf, 25)) & ok & (fine > 1e-6) & (lum > 16) & (lum < 239)
    out["noise_slope"] = float(np.polyfit(np.log(lum[s2]), np.log(fine[s2]), 1)[0]) if s2.sum() > 40 else float("nan")

    g = np.sqrt(np.gradient(a)[0] ** 2 + np.gradient(a)[1] ** 2)
    out["edge_w"] = float(np.percentile(g, 99) / max(np.percentile(g, 90), 1e-9))
    out["edge_w2"] = float(np.percentile(g, 90) / max(np.percentile(g, 50), 1e-9))
    return out


KEYS = ["fine_var_full", "sun_blob_px", "flat_noise", "res_all", "ratio12", "ar1", "ar2",
        "spectral_hi", "luma_over_chroma", "sharp_spread", "fine_vs_mid", "noise_slope",
        "edge_w", "edge_w2"]


def sep(pairs):
    vals = sorted([(v, l) for v, l in pairs if v == v])
    best, bthr = 99, None
    for i in range(1, len(vals)):
        if vals[i - 1][0] == vals[i][0]:
            continue
        thr = (vals[i - 1][0] + vals[i][0]) / 2.0
        e = min(sum(1 for v, l in vals if (v > thr) != (l == "PHOTO")),
                sum(1 for v, l in vals if (v > thr) != (l == "PAINT")))
        if e < best:
            best, bthr = e, thr
    return best, len(vals), bthr


def main():
    rows = []
    for lab, name, p in ITEMS:
        d = feats(p)
        d.update(label=lab, name=name, file=os.path.basename(p),
                 core=not name.startswith(("档-", "实验-")))
        rows.append(d)
        print("%-5s %-40s ok" % (lab, name[:40]), flush=True)
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("label\tcore\tname\tfile\t" + "\t".join(KEYS) + "\n")
        for d in rows:
            fh.write("%s\t%d\t%s\t%s\t" % (d["label"], int(d["core"]), d["name"], d["file"])
                     + "\t".join("%.6f" % d[k] if d[k] == d[k] else "nan" for k in KEYS) + "\n")
    print("\n== 单特征最小错分（n=75 全集 / 核心集=剔除三档对照与画风通道实验臂）==")
    res = []
    for k in KEYS:
        a = sep([(d[k], d["label"]) for d in rows])
        b = sep([(d[k], d["label"]) for d in rows if d["core"]])
        res.append((k, a[0], b[0]))
        print("  %-17s 全集 %2d/%d @%.5f | 核心集 %2d/%d" % (k, a[0], a[1], a[2] if a[2] else -1, b[0], b[1]))
    best = min(res, key=lambda x: x[1])
    print("\n最好单特征：%s 全集错分 %d/%d" % (best[0], best[1], len(rows)))
    for k in ("fine_var_full", "sun_blob_px"):
        ph = [d[k] for d in rows if d["label"] == "PHOTO"]
        pa = [d[k] for d in rows if d["label"] == "PAINT"]
        print("  %-14s PHOTO %.6f..%.6f | PAINT %.6f..%.6f 重叠=%s"
              % (k, min(ph), max(ph), min(pa), max(pa),
                 "是" if min(pa) <= max(ph) and min(ph) <= max(pa) else "否"))


main()
