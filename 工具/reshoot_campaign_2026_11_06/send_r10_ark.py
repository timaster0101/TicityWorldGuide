# -*- coding: utf-8 -*-
"""R10 投送执行器：按 send_bodies_r10.json 逐条调方舟标准域 doubao-seedream-5-0-pro。

口径（会话 2026-11-27 实测，见交接清单 §55.66）：
- 端点 POST https://ark.cn-beijing.volces.com/api/v3/images/generations
- 母图参数名是 image（单数、data URL 字符串）；传 images 数组会被静默忽略，
  故必须断言 usage.input_images == 1，否则视为母图臂断了，立即停手。
- watermark=True 会印「AI生成」角标；标准域产物无 caBX/iTXt 容器（verify 的
  container_ok 会判红），因此本脚本只负责出图落盘，不做 verify/backfill。
- 403 就地停手（退额度），不做措辞重试。

用法：
  python -X utf8 工具/reshoot_campaign_2026_11_06/send_r10_ark.py --ids D19 L069 ...
  python -X utf8 工具/reshoot_campaign_2026_11_06/send_r10_ark.py --ingest D18 <已有png>
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEDGER = os.path.join(ROOT, "工具", "reshoot_campaign_2026_11_06", "send_bodies_r10.json")
IMG_DIR = os.path.join(os.path.dirname(ROOT), "vibe_images")
KEY_FILE = os.path.join(os.path.expanduser("~"), ".dsh", "secrets", "ark-api-key.txt")
RUNLOG = os.path.join(ROOT, "数据", "R10方舟投送记录.json")
ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
MODEL = "doubao-seedream-5-0-pro-260628"
UNIT_COST = 0.30
NAME_RE = re.compile(r"^(.+)_(1\d{12})_[0-9a-f]{8}\.png$")

sys.path.insert(0, os.path.join(ROOT, "工具"))
from r4_style_ref import send_body  # noqa: E402  （同仓库工具，非三方依赖）


def load_key() -> str:
    with io.open(KEY_FILE, encoding="utf-8") as fh:
        k = fh.read().strip()
    if not k.startswith("ark-"):
        raise SystemExit("key 形态不对：%r" % k[:8])
    return k


def data_url(path: str) -> str:
    with io.open(path, "rb") as fh:
        raw = fh.read()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def post(payload: dict, key: str, timeout: int = 300) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(ENDPOINT, data=body, method="POST")
    req.add_header("Authorization", "Bearer " + key)
    req.add_header("Content-Type", "application/json")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:600].decode("utf-8", "replace")
        raise SystemExit("HTTP %s 停手：%s" % (exc.code, detail))
    out = json.loads(data.decode("utf-8"))
    out["_seconds"] = round(time.time() - t0, 1)
    return out


def ensure_png(raw: bytes) -> tuple[bytes, str]:
    """方舟 url 通道回的是 jpeg，落盘必须转真 PNG（图集惯例 + verify 的容器判据）。"""
    from PIL import Image

    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return raw, "png"
    with Image.open(io.BytesIO(raw)) as im:
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), "jpeg->png"


def fetch(url: str, timeout: int = 180) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


def existing(send_name: str) -> str | None:
    for name in os.listdir(IMG_DIR):
        m = NAME_RE.match(name)
        if m and m.group(1) == send_name:
            return os.path.join(IMG_DIR, name)
    return None


def load_runlog() -> list:
    path = os.path.join(ROOT, RUNLOG)
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)["rows"]


def save_runlog(rows: list) -> None:
    path = os.path.join(ROOT, RUNLOG)
    doc = {
        "note": "R10 方舟标准域投送记录：每行一次付费调用。unit_cost 为刊例价，实扣以方舟账单为准。",
        "endpoint": ENDPOINT,
        "model": MODEL,
        "unit_cost": UNIT_COST,
        "rows": rows,
    }
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--ingest", nargs=2, metavar=("ID", "PNG"))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    with io.open(LEDGER, encoding="utf-8") as fh:
        ledger = json.load(fh)
    key = load_key()
    rows = load_runlog()

    if args.ingest:
        eid, src = args.ingest
        entry = ledger[eid]
        name = os.path.basename(src)
        m = re.match(r"^(.+?)_?(1\d{12})_[0-9a-f]{8}\.png$", name)
        with io.open(src, "rb") as fh:
            raw = fh.read()
        sha8 = hashlib.sha256(raw).hexdigest()[:8]
        ts = int(m.group(2)) if m else int(os.path.getmtime(src) * 1000)
        dest = os.path.join(IMG_DIR, "%s_%s_%s.png" % (entry["send_name"], ts, sha8))
        with io.open(dest, "wb") as fh:
            fh.write(raw)
        rows.append({"id": eid, "send_name": entry["send_name"], "file": os.path.basename(dest),
                     "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                     "size": entry["size"], "seconds": None, "cost": None, "model": None,
                     "input_images": None, "note": "ingest（探针件归位，成本记在诊断轮）"})
        save_runlog(rows)
        print("INGEST", eid, "->", dest)
        return 0

    ids = list(ledger) if args.all else args.ids
    if not ids:
        raise SystemExit("给 --ids 或 --all")
    spent = 0.0
    for eid in ids:
        entry = ledger[eid]
        prev = existing(entry["send_name"])
        if prev and not args.force:
            print("SKIP", eid, "已有", os.path.basename(prev))
            continue
        mother = os.path.join(ROOT, entry["ref_image"].replace("/", os.sep))
        if not os.path.exists(mother):
            raise SystemExit("母图不在盘：%s" % mother)
        payload = {
            "model": MODEL,
            "prompt": send_body(entry["body"]),
            "image": data_url(mother),
            "size": entry["size"],
            "watermark": False,
            "output_format": "png",
            "response_format": "url",
        }
        print("SEND", eid, entry["size"], "chars=%d" % len(payload["prompt"]), flush=True)
        try:
            out = post(payload, key)
        except SystemExit as exc:
            print("ABORT", eid, exc, flush=True)
            save_runlog(rows)
            return 2
        usage = out.get("usage") or {}
        if usage.get("input_images", 0) != 1:
            print("ABORT", eid, "input_images != 1，母图没生效", usage, flush=True)
            save_runlog(rows)
            return 3
        url = out["data"][0].get("url")
        raw = fetch(url)
        jpeg_sha = hashlib.sha256(raw).hexdigest()
        raw, conv = ensure_png(raw)
        sha8 = hashlib.sha256(raw).hexdigest()[:8]
        ts = int(time.time() * 1000)
        dest = os.path.join(IMG_DIR, "%s_%s_%s.png" % (entry["send_name"], ts, sha8))
        with io.open(dest, "wb") as fh:
            fh.write(raw)
        spent += UNIT_COST
        rows.append({"id": eid, "send_name": entry["send_name"], "file": os.path.basename(dest),
                     "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                     "size": out.get("size") or entry["size"], "seconds": out["_seconds"],
                     "cost": UNIT_COST, "model": out.get("model") or MODEL,
                     "input_images": 1, "note": conv, "sha256_jpeg": jpeg_sha})
        save_runlog(rows)
        print("OK", eid, dest, len(raw), "%.1fs" % out["_seconds"], "累计 %.2f 元" % spent, flush=True)
    print("DONE 累计 %.2f 元" % spent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
