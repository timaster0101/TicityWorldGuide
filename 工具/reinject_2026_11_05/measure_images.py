# -*- coding: utf-8 -*-
"""C118 新串批次 49 张新图＋放量前探针 1 张的逐张 PIL 测量打表（只读，不写任何真源）。

读数口径：
- 尺寸／字节／sha256／模式：文件与像素体检。
- 容器（C97 侧）：PNG 私有块 caBX 处数、iTXt 是否含 TC260:AIGC。C136 订正：二者不再按出图通道分别成立——同为文本生图，本轮格实测 caBX=0／iTXt=1、母图实测 caBX=1／iTXt=0，占格只要求至少其一在位。
- 细尺度方差：灰度图减去 5x5 均值模糊后的残差方差（像素归一到 0—1），与
  数据/生成输入记录/画风诊断-媒介强度分档-2026-11-04.txt 的「整图细尺度方差」同式，
  C134 降级：该量只作读数、不作判据。2026-11-06 在 75 张定标签集（照片侧 45／绘画侧 30，读数见 工具/reshoot_campaign_2026_11_06/style_sep_final.tsv）实测：整图细尺度方差低于地板 0.000414 者为照片侧 0/45、绘画侧 0/30——地板对本集合零分离力；14 项像素特征里最好的一枚错分 11/75（edge_w2：照片侧误判 4／绘画侧误判 7，绘画侧 7 张全部是 E1 定档·E1 重出·画风通道实验·半写实 E1 定稿，即把已定档正典读成照片侧）；CLIP ViT-B/32 零样本在剔除媒介连续档臂的 58 张核心集上最好错分 6/58，错分同样集中在正典侧。故「数值越高越油画」不成立为判废依据，地板仅保留为读数参照。另取中央 1/3 窗口作近景读数。
- 四角亮度：四角 64x64 灰度均值（TL／TR／BL／BR）与全图 p99 峰值。
- 日面检出：上半区亮度 >=250 的连通块最大面积。C134 降级：>=1500 px 只是读数分档线，不单独构成判据（同集实测照片侧 3/45、绘画侧 5/30 超限，方向与「照片才有强光源盘」的预期相反）；日盘在框内与否按清单 camera_facing_deg／sun_relative_deg 的取景分支逐张人工核。
- 横缝候选：逐行均值的行际差分峰所在行段。
"""
import hashlib
import io
import json
import os
import re
import struct
import sys
import tempfile
import zlib
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
VIBE = ROOT / "vibe_images"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "c118_measure.json"

MANIFEST = json.loads((ROOT / "数据/开图清单.json").read_text(encoding="utf-8"))
ITEMS = {it["id"]: it for it in MANIFEST["items"]}


def png_chunks(path):
    cabx = 0
    itxt = 0
    aigc = False
    tc260 = False
    with open(path, "rb") as fh:
        if fh.read(8) != b"\x89PNG\r\n\x1a\n":
            return None
        while True:
            head = fh.read(8)
            if len(head) < 8:
                break
            length, ctype = struct.unpack(">I4s", head)
            body = fh.read(length)
            fh.read(4)
            if ctype == b"caBX":
                cabx += 1
            elif ctype == b"iTXt":
                itxt += 1
                text = body.decode("utf-8", "replace")
                if "TC260" in text:
                    tc260 = True
                if "AIGC" in text or "trainedAlgorithmicMedia" in text:
                    aigc = True
            if len(body) < length:
                break
    return {"cabx": cabx, "itxt": itxt, "tc260": tc260, "aigc": aigc}


def fine_variance(gray):
    import numpy as np

    a = np.asarray(gray, dtype=np.float32) / 255.0
    H, W = a.shape
    k = 5
    pad = 2
    p = np.pad(a, pad, mode="edge")
    j = np.zeros((p.shape[0] + 1, p.shape[1] + 1), dtype=np.float64)
    j[1:, 1:] = np.cumsum(np.cumsum(p, axis=0), axis=1)
    box = (j[k:, k:] - j[:-k, k:] - j[k:, :-k] + j[:-k, :-k]) / float(k * k)
    resid = a - box[:H, :W]
    return float(resid.var())


def sun_blob(gray):
    import numpy as np

    a = np.asarray(gray, dtype=np.uint8)
    top = a[: a.shape[0] // 2, :]
    mask = (top >= 250).astype(np.uint8)
    if not mask.any():
        return 0
    # 4x 降采样后做 4-邻接连通块，面积按 16 倍还原，供「疑似日面圆盘／强光源」读数（C134 起只作记录）
    H, W = mask.shape
    bh, bw = H // 4, W // 4
    small = mask[: bh * 4, : bw * 4].reshape(bh, 4, bw, 4).sum(axis=(1, 3)) > 0
    best = 0
    seen = np.zeros_like(small, dtype=bool)
    for sy in range(bh):
        for sx in range(bw):
            if not small[sy, sx] or seen[sy, sx]:
                continue
            stack = [(sy, sx)]
            seen[sy, sx] = True
            size = 0
            while stack:
                y, x = stack.pop()
                size += 1
                for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if 0 <= ny < bh and 0 <= nx < bw and small[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            best = max(best, size)
    return int(best * 16)


def row_seam_peaks(gray):
    import numpy as np

    a = np.asarray(gray, dtype=np.float32)
    rm = a.mean(axis=1)
    d = np.abs(np.diff(rm))
    order = np.argsort(d)[::-1][:6]
    return sorted(int(o) for o in order)


def measure(path):
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    img = Image.open(io.BytesIO(raw))
    img.load()
    gray = img.convert("L")
    w, h = gray.size
    px = gray.load()
    c = 64

    def patch_mean(xs, ys):
        tot = 0
        n = 0
        for y in range(ys, min(ys + c, h)):
            for x in range(xs, min(xs + c, w)):
                tot += px[x, y]
                n += 1
        return round(tot / max(n, 1), 1)

    corners = {
        "TL": patch_mean(0, 0),
        "TR": patch_mean(max(w - c, 0), 0),
        "BL": patch_mean(0, max(h - c, 0)),
        "BR": patch_mean(max(w - c, 0), max(h - c, 0)),
    }
    import numpy as np

    ga = np.asarray(gray, dtype=np.uint8)
    p99 = float(np.percentile(ga, 99))
    full_var = fine_variance(gray)
    cx, cy = w // 3, h // 3
    center = gray.crop((cx, cy, min(cx + w // 3, w), min(cy + h // 3, h)))
    mid_var = fine_variance(center)
    return {
        "file": path.name,
        "bytes": len(raw),
        "sha256_12": sha[:12],
        "dims": "%dx%d" % (w, h),
        "mode": img.mode,
        "container": png_chunks(path),
        "corners": corners,
        "p99_lum": round(p99, 1),
        "fine_var_full": round(full_var, 6),
        "fine_var_center": round(mid_var, 6),
        "sun_blob_px": sun_blob(gray),
        "row_seam_peaks": row_seam_peaks(gray),
    }


def main():
    files = sorted(VIBE.glob("*C123新串*.png"))
    rows = []
    for f in files:
        m = re.match(r"([A-Z]\d{2,3})-", f.name)
        ident = m.group(1) if m else ("PROBE" if "probe" in f.name else "?")
        rec = measure(f)
        rec["id"] = ident
        it = ITEMS.get(ident)
        if it:
            rec["entry_name"] = it["name"]
            rec["entry_type"] = it["type"]
            rec["expected_size"] = it["size"]
            rec["size_match"] = rec["dims"] == it["size"]
            rec["status_now"] = it["status"]
            rec["image_file_now"] = it["image_file"]
            rec["camera_facing_deg"] = it["camera_facing_deg"]
            rec["sun_relative_deg"] = it["sun_relative_deg"]
            rec["aspect"] = it["aspect"]
            rec["lock"] = (it.get("review_note") or "")[:0]
        rows.append(rec)
        print("%-6s %-12s %s %9d caBX=%d iTXt=%d fvar=%.6f cvar=%.6f sun=%d match=%s"
              % (rec["id"], rec["sha256_12"], rec["dims"], rec["bytes"],
                 rec["container"]["cabx"], rec["container"]["itxt"],
                 rec["fine_var_full"], rec["fine_var_center"], rec["sun_blob_px"],
                 rec.get("size_match", "-")), flush=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("count", len(rows), "->", OUT)


if __name__ == "__main__":
    main()
