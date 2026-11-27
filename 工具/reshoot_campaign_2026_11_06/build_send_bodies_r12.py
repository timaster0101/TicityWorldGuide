# -*- coding: utf-8 -*-
"""R12 台账：把 7 条「待复验」的片区按今天的串补出一版（收口用）。

为什么有这一批：C154 把 20 个片区的取景指令换成三类视点轮换后，13 条在 R9／R10 重投过，
剩 D06／D09／D10／D11／D12／D15／D20 七条走了 C155 在册裁定收口（状态保持待复验、不绑串）。
用户 2026-11-27 的口径是「没做完要处理完才能收口」，所以这 7 条按今天的串补出，
让 312 条全部有「现串产物」——收口才有可判定的准据。

成员面推导：清单里 status == 待复验 的条目，断言恰 7 条；数目变了就拒绝写盘。
母图：E1 定档池，按画幅轮转（与 R11 同口径）。
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS = os.path.join(ROOT, "工具")
sys.path.insert(0, TOOLS)
sys.path.insert(0, os.path.join(ROOT, "工具", "reshoot_campaign_2026_11_06"))

import r4_style_ref as REF  # noqa: E402
from build_send_bodies import body_of  # noqa: E402

MANIFEST = os.path.join(ROOT, "数据", "开图清单.json")
OUT = os.path.join(ROOT, "工具", "reshoot_campaign_2026_11_06", "send_bodies_r12.json")
OUT_NOTE = os.path.join(ROOT, "工具", "reshoot_campaign_2026_11_06", "send_bodies_r12_note.json")
SUFFIX = "C156E1基线补出-v01"
EXPECT = 7


def members() -> list[dict]:
    with io.open(MANIFEST, encoding="utf-8") as fh:
        manifest = json.load(fh)
    return [e for e in manifest["items"] if e.get("status") == "待复验"]


def frozen(ids) -> list[dict]:
    """按给定 ID 现取清单条目（7 条签完之后 status 已不是待复验，重算台账要靠这份冻名单）。"""
    with io.open(MANIFEST, encoding="utf-8") as fh:
        manifest = json.load(fh)
    by_id = {e["id"]: e for e in manifest["items"]}
    return [by_id[eid] for eid in ids]


def build(ids=None) -> dict:
    land = REF.check_pool(REF.LANDSCAPE, "R12 横构图")
    port = REF.check_pool(REF.PORTRAIT, "R12 竖构图")
    seq = {"land": 0, "port": 0}
    ledger = {}
    entries = sorted(members() if ids is None else frozen(ids), key=lambda x: x["id"])
    for e in entries:
        eid = e["id"]
        name, _src, body = body_of(ROOT, eid)
        prompt_rel = "数据/开图提示词/" + name
        size = e["size"]
        portrait = size.split("x")[1] > size.split("x")[0]
        key = "port" if portrait else "land"
        ref_rel, ref_dim = REF.assign(port if portrait else land, seq[key], size)
        seq[key] += 1
        send = REF.send_body(body)
        ledger[eid] = {
            "body": body,
            "body_chars": len(body),
            "chars": len(send),
            "file": prompt_rel,
            "size": size,
            "ref_image": ref_rel,
            "ref_dims": ref_dim,
            "send_name": "%s-%s" % (name[:-4] if name.endswith(".txt") else name, SUFFIX),
            "send_sha256": hashlib.sha256(send.encode("utf-8")).hexdigest(),
            "replaced_cell": (e.get("image_file") or [""])[0],
            "status_before": e.get("status"),
            "投次": 1,
            "批": "R12",
        }
    return ledger


def main() -> int:
    ledger = build()
    if len(ledger) != EXPECT:
        print("成员面 %d 条，期望 %d 条，拒绝写盘" % (len(ledger), EXPECT))
        return 2
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")
    note = {
        "批": "R12",
        "suffix": SUFFIX,
        "成员面": "清单 status==待复验 的 7 条片区（C155 已收口、不绑串）",
        "母图": "E1 定档池横 7 枚／竖 3 枚，按画幅轮转",
        "口径": "按今天的串补出，让 312 条全部有现串产物；不做缺陷检查（用户 2026-11-27）",
        "预算": "7 × 0.30 = 2.10 元",
    }
    with io.open(OUT_NOTE, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(note, ensure_ascii=False, indent=2) + "\n")
    print("写出 %d 条 → %s" % (len(ledger), os.path.relpath(OUT, ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
