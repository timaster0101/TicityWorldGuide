# -*- coding: utf-8 -*-
"""R11 台账：把「在册首格不是 E1 母图轮产出」的条目全部按 E1 基线重出一版。

用户口径（2026-11-27）：「139 张早期图要重新出，之前不是按照 E1 出也也要重新出，
图出完就行，不用检查是否有缺陷，以后遇到了再弄。」

成员面推导（不手抄名单）：
  1. 取 数据/开图清单.json 全部条目；
  2. 在册首格（image_file[0]）的档名落在 `四向…` 或 `C138主向重投` 的，就是要重出的——
     前者是 2026-10 首批四向基准照，后者母图是 L095 而不是 E1 定档件；
  3. 断言余量恰为 140 条（139 四向 + 1 C138），数目变了就判红，防名单悄悄漂移。

母图：一律取 E1 定档池（横 7 枚 / 竖 3 枚），按画幅子池轮转（REF.assign），
与 R4／R10 同一口径——同画幅优先，避免把竖构图母图喂给横幅尺寸。

占格口径：本轮不占格、不改状态。出图只进 vibe_images，回填另由 backfill 跑
（本轮用户已明示「不用检查缺陷」，故回填时只做机械对拍，不做目视判词）。
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
OUT = os.path.join(ROOT, "工具", "reshoot_campaign_2026_11_06", "send_bodies_r11.json")
OUT_NOTE = os.path.join(ROOT, "工具", "reshoot_campaign_2026_11_06", "send_bodies_r11_note.json")
SUFFIX = "C156E1基线重出-v01"
EXPECT = 140


def is_legacy(entry: dict) -> bool:
    files = entry.get("image_file") or []
    if not files:
        return True
    name = os.path.basename(files[0])
    return "四向" in name or "C138主向重投" in name


def members() -> list[dict]:
    with io.open(MANIFEST, encoding="utf-8") as fh:
        manifest = json.load(fh)
    return [e for e in manifest["items"] if is_legacy(e)]


def frozen(ids) -> list[dict]:
    """按给定 ID 现取清单条目（回填之后成员面会自己清空，重算台账要靠这份冻名单）。"""
    with io.open(MANIFEST, encoding="utf-8") as fh:
        manifest = json.load(fh)
    by_id = {e["id"]: e for e in manifest["items"]}
    return [by_id[eid] for eid in ids]


def build(ids=None) -> dict:
    """build() 按现算成员面出表；build(ids=[...]) 按冻名单重算。

    为什么留 ids 入口：R11 回填之后那 140 条的 image_file 首格已经换成 C156E1基线重出，
    is_legacy 现算归零，凭现算面重建就只能得到空表——而「台账可重算复现」这条判据
    要验的是「同样的名单与同样的正文仍能算出逐字相同的台账」，名单得从台账自身冻住。
    """
    land = REF.check_pool(REF.LANDSCAPE, "R11 横构图")
    port = REF.check_pool(REF.PORTRAIT, "R11 竖构图")
    seq = {"land": 0, "port": 0}
    ledger = {}
    entries = sorted(members() if ids is None else frozen(ids), key=lambda x: x["id"])
    for e in entries:
        eid = e["id"]
        name, src, body = body_of(ROOT, eid)
        size = e["size"]
        portrait = size.split("x")[1] > size.split("x")[0]
        key = "port" if portrait else "land"
        pool = port if portrait else land
        ref_rel, ref_dim = REF.assign(pool, seq[key], size)
        seq[key] += 1
        send_name = "%s-%s" % (name[:-4] if name.endswith(".txt") else name, SUFFIX)
        send = REF.send_body(body)
        ledger[eid] = {
            "body": body,
            "body_chars": len(body),
            "chars": len(send),
            "file": src,
            "size": size,
            "ref_image": ref_rel,
            "ref_dims": ref_dim,
            "send_name": send_name,
            "send_sha256": hashlib.sha256(send.encode("utf-8")).hexdigest(),
            "replaced_cell": (e.get("image_file") or [""])[0],
            "status_before": e.get("status"),
            "投次": 1,
            "批": "R11",
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
        "批": "R11",
        "suffix": SUFFIX,
        "成员面": "在册首格为四向基准照或 C138主向重投的条目（%d 条）" % len(ledger),
        "母图": "E1 定档池横 7 枚／竖 3 枚，按画幅子池轮转",
        "口径": "出图不占格、不改状态；用户 2026-11-27 明示不做缺陷检查",
        "预算": "140 × 0.30 = 42.00 元（pro，1792/1536/1280/1024 长边同价）",
    }
    with io.open(OUT_NOTE, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(note, ensure_ascii=False, indent=2) + "\n")
    print("写出 %d 条 → %s" % (len(ledger), os.path.relpath(OUT, ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
