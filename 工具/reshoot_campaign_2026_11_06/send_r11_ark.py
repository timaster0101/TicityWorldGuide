# -*- coding: utf-8 -*-
"""R11 投送执行器：按 send_bodies_r11.json 把 140 条早期图按 E1 基线重出一版。

与 send_r10_ark.py 的差别：
- 台账换 send_bodies_r11.json，记录换 数据/R11方舟投送记录.json；
- 并发 3 路（顺序跑完 140 条约 4.3 小时，3 路约 1.5 小时）；并发下写台账加锁；
- 429／5xx 退避重试（10s → 30s → 60s），403 就地全停（额度问题，不换措辞重试）；
- 已存在同发名文件即 SKIP（幂等），中断后重跑不会重复花钱。

用户口径（2026-11-27）：图出完就行，不检查缺陷；出图只进 vibe_images，占格与状态由
backfill 另跑。
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
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CAMPAIGN = os.path.join(ROOT, "工具", "reshoot_campaign_2026_11_06")
LEDGER = os.path.join(CAMPAIGN, "send_bodies_r11.json")
IMG_DIR = os.path.join(os.path.dirname(ROOT), "vibe_images")
KEY_FILE = os.path.join(os.path.expanduser("~"), ".dsh", "secrets", "ark-api-key.txt")
RUNLOG = os.path.join(ROOT, "数据", "R11方舟投送记录.json")
ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
MODEL = "doubao-seedream-5-0-pro-260628"
UNIT_COST = 0.30
BACKOFF = (10, 30, 60)
NAME_RE = re.compile(r"^(.+)_(1\d{12})_[0-9a-f]{8}\.png$")

# 轮次配置：R11＝140 条早期图按 E1 基线重出；R12＝7 条待复验片区按今天的串补出。
ROUNDS = {
    "R11": {"ledger": "send_bodies_r11.json", "runlog": "数据/R11方舟投送记录.json",
            "note": "R11 方舟标准域投送记录：把在册首格为四向基准照/C138 母图的 140 条按 E1 基线重出。"},
    "R12": {"ledger": "send_bodies_r12.json", "runlog": "数据/R12方舟投送记录.json",
            "note": "R12 方舟标准域投送记录：7 条待复验片区按今天的串补出（收口用）。"},
}

sys.path.insert(0, os.path.join(ROOT, "工具"))
from r4_style_ref import send_body  # noqa: E402

LOCK = threading.Lock()
STOP = threading.Event()
ROWS: list = []
LEDGER_PATH = LEDGER
RUNLOG_PATH = RUNLOG
NOTE_TEXT = ROUNDS["R11"]["note"]


def load_key() -> str:
    with io.open(KEY_FILE, encoding="utf-8") as fh:
        k = fh.read().strip()
    if not k.startswith("ark-"):
        raise SystemExit("key 形态不对")
    return k


def data_url(path: str) -> str:
    with io.open(path, "rb") as fh:
        raw = fh.read()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def post(payload: dict, key: str, timeout: int = 300) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last = None
    for attempt, wait in enumerate((0,) + BACKOFF):
        if wait:
            time.sleep(wait)
        req = urllib.request.Request(ENDPOINT, data=body, method="POST")
        req.add_header("Authorization", "Bearer " + key)
        req.add_header("Content-Type", "application/json")
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                out = json.loads(resp.read().decode("utf-8"))
            out["_seconds"] = round(time.time() - t0, 1)
            return out
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:600].decode("utf-8", "replace")
            last = "HTTP %s %s" % (exc.code, detail)
            if exc.code == 403:
                raise SystemExit(last)
            if exc.code in (429, 500, 502, 503, 504) and attempt < len(BACKOFF):
                print("RETRY", attempt + 1, last[:120], flush=True)
                continue
            raise SystemExit(last)
        except (urllib.error.URLError, TimeoutError) as exc:
            last = "网络错误 %s" % exc
            if attempt < len(BACKOFF):
                print("RETRY", attempt + 1, last[:120], flush=True)
                continue
            raise SystemExit(last)
    raise SystemExit(last or "未知失败")


def ensure_png(raw: bytes) -> tuple[bytes, str]:
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


def existing(send_name: str):
    with LOCK:
        names = os.listdir(IMG_DIR)
    for name in names:
        m = NAME_RE.match(name)
        if m and m.group(1) == send_name:
            return name
    return None


def load_runlog() -> list:
    if not os.path.exists(RUNLOG_PATH):
        return []
    with io.open(RUNLOG_PATH, encoding="utf-8") as fh:
        return json.load(fh)["rows"]


def save_runlog() -> None:
    with LOCK:
        doc = {
            "note": NOTE_TEXT,
            "endpoint": ENDPOINT,
            "model": MODEL,
            "unit_cost": UNIT_COST,
            "rows": list(ROWS),
        }
        tmp = RUNLOG_PATH + ".tmp"
        with io.open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp, RUNLOG_PATH)


def one(eid: str, entry: dict, key: str) -> str:
    if STOP.is_set():
        return "STOP"
    prev = existing(entry["send_name"])
    if prev:
        print("SKIP", eid, prev, flush=True)
        return "SKIP"
    mother = os.path.join(ROOT, entry["ref_image"].replace("/", os.sep))
    if not os.path.exists(mother):
        print("MISS", eid, mother, flush=True)
        return "MISS"
    payload = {
        "model": MODEL,
        "prompt": send_body(entry["body"]),
        "image": data_url(mother),
        "size": entry["size"],
        "watermark": False,
        "output_format": "png",
        "response_format": "url",
    }
    print("SEND", eid, entry["size"], flush=True)
    try:
        out = post(payload, key)
    except SystemExit as exc:
        STOP.set()
        print("ABORT", eid, exc, flush=True)
        return "ABORT"
    usage = out.get("usage") or {}
    if usage.get("input_images", 0) != 1:
        STOP.set()
        print("ABORT", eid, "input_images != 1", usage, flush=True)
        return "ABORT"
    raw = fetch(out["data"][0]["url"])
    jpeg_sha = hashlib.sha256(raw).hexdigest()
    raw, conv = ensure_png(raw)
    sha8 = hashlib.sha256(raw).hexdigest()[:8]
    ts = int(time.time() * 1000)
    dest = os.path.join(IMG_DIR, "%s_%s_%s.png" % (entry["send_name"], ts, sha8))
    with io.open(dest, "wb") as fh:
        fh.write(raw)
    row = {
        "id": eid,
        "send_name": entry["send_name"],
        "file": os.path.basename(dest),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size": out.get("size") or entry["size"],
        "seconds": out["_seconds"],
        "cost": UNIT_COST,
        "model": out.get("model") or MODEL,
        "input_images": 1,
        "note": conv,
        "sha256_jpeg": jpeg_sha,
    }
    with LOCK:
        ROWS.append(row)
        total = sum(1 for r in ROWS if r.get("cost")) * UNIT_COST
    save_runlog()
    print("OK", eid, os.path.basename(dest), len(raw), "%.1fs" % out["_seconds"], "累计 %.2f 元" % total, flush=True)
    return "OK"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--round", default="R11", choices=sorted(ROUNDS))
    args = ap.parse_args()

    cfg = ROUNDS[args.round]
    global LEDGER_PATH, RUNLOG_PATH, NOTE_TEXT, ROWS
    LEDGER_PATH = os.path.join(CAMPAIGN, cfg["ledger"])
    RUNLOG_PATH = os.path.join(ROOT, cfg["runlog"].replace("/", os.sep))
    NOTE_TEXT = cfg["note"]
    with io.open(LEDGER_PATH, encoding="utf-8") as fh:
        ledger = json.load(fh)
    ids = list(ledger) if args.all else args.ids
    if not ids:
        raise SystemExit("给 --ids 或 --all")
    key = load_key()
    ROWS = load_runlog()

    ok = skipped = failed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(one, eid, ledger[eid], key): eid for eid in ids}
        for fut in as_completed(futs):
            res = fut.result()
            if res == "OK":
                ok += 1
            elif res == "SKIP":
                skipped += 1
            else:
                failed += 1
            if STOP.is_set():
                for f in futs:
                    f.cancel()
                break
    total = sum(1 for r in ROWS if r.get("cost")) * UNIT_COST
    print("DONE ok=%d skip=%d fail=%d 累计 %.2f 元" % (ok, skipped, failed, total))
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
