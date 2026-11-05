# -*- coding: utf-8 -*-
"""投后逐字回绑（第9批 f 轮 12 条判废第五投）：从本会话 jsonl 取 ImageGen 实发 prompt，
与 send_bodies_12.json 的真源正文段逐字比对；只报不等者，不写任何真源。

两条本轮特有的收紧：
1. §32.4 的发送侧字符损坏闸门每轮都跑，不按往轮通过率免除；不等者当场判「不作数」，须补投后重跑。
2. 本轮档串仍是 `C123新串-v02`（串未变），与本会话里 §32／§33／§35 三往轮的同名发送撞档，
   所以只认落盘文件名时间戳段 >= FLOOR 的那次发起（探针 L083 的 1793901894424）。
   不加这道闸，往轮的历史发送会被当成本轮「已投」，回绑就成了自证。
"""
import hashlib
import io
import json
import re
import sys
from pathlib import Path

J = Path("C:/Users/TIMASTER/.qoder/projects/"
         "C--Users-TIMASTER-Documents-Qoder-2026-10-29-c8c10ff8---------/"
         "c0c216d9-4f5e-4156-8525-d49858e862dd.jsonl")
BODIES = json.load(io.open(Path(__file__).resolve().parent / "send_bodies_12.json", encoding="utf-8"))
FLOOR = 1793901894424

uses = {}
saved = {}


def walk(o):
    if isinstance(o, dict):
        if o.get("type") in ("tool_use", "tool_result"):
            yield o
        for v in o.values():
            for r in walk(v):
                yield r
    elif isinstance(o, list):
        for v in o:
            for r in walk(v):
                yield r


# 两段扫：ImageGen 的发起记录里有 "ImageGen" 字样，回执记录里只有落盘路径与 tool_use_id，
# 所以先按字样收发起，再全量扫一次只为把落盘时间戳配回去。
wanted = set()
for line in io.open(J, encoding="utf-8"):
    if "ImageGen" not in line:
        continue
    try:
        rec = json.loads(line)
    except ValueError:
        continue
    for blk in walk(rec):
        if blk.get("type") == "tool_use" and blk.get("name") == "ImageGen":
            inp = blk.get("input") or {}
            rid = (inp.get("name") or "").split("-")[0]
            if rid in BODIES:
                uses.setdefault(rid, []).append((blk.get("id"), inp))
                wanted.add(blk.get("id"))

for line in io.open(J, encoding="utf-8"):
    if "_1793901" not in line and "tool_result" not in line:
        continue
    try:
        rec = json.loads(line)
    except ValueError:
        continue
    for blk in walk(rec):
        if blk.get("type") == "tool_result" and blk.get("tool_use_id") in wanted:
            txt = json.dumps(blk.get("content"), ensure_ascii=False)
            m = re.search(r"_(\d{13})_[0-9a-f]{8}\.png", txt)
            if m:
                saved[blk.get("tool_use_id")] = int(m.group(1))

rows = []
for rid in sorted(BODIES):
    hits = []
    for call_id, inp in uses.get(rid, []):
        ts = saved.get(call_id)
        if ts is not None and ts >= FLOOR and (inp.get("name") or "").endswith("C123新串-v02"):
            hits.append((ts, inp))
    if not hits:
        rows.append({"id": rid, "name": None, "已投": False})
        continue
    hits.sort()
    ts, inp = hits[-1]
    p = inp["prompt"]
    rows.append({
        "id": rid, "name": inp.get("name"), "size": inp.get("size"),
        "落盘时间戳": ts, "已投": True, "本轮发起次数": len(hits), "chars": len(p),
        "sent_sha12": hashlib.sha256(p.encode("utf-8")).hexdigest()[:12],
        "canon_sha12": BODIES[rid]["sha256"][:12],
        "逐字相等": p == BODIES[rid]["body"],
        "尺寸与清单一致": inp.get("size") == BODIES[rid]["size"],
    })

out = Path(__file__).resolve().parent / "sent_binding.json"
out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
done = [r for r in rows if r.get("逐字相等")]
gap = [r["id"] for r in rows if r["已投"] and not r["逐字相等"]]
todo = [r["id"] for r in rows if not r["已投"]]
bad_size = [r["id"] for r in done if not r["尺寸与清单一致"]]
print("本轮发起且与真源逐字相等 %d/%d：%s" % (len(done), len(BODIES), " ".join(r["id"] for r in done)))
print("本轮发起但串不等（不作数，待补投）%d：%s" % (len(gap), " ".join(gap)))
print("本轮未投 %d：%s" % (len(todo), " ".join(todo)))
print("尺寸不符 %d %s" % (len(bad_size), bad_size))
print("本轮发起合计 %d 次（探针在内）" % sum(r.get("本轮发起次数", 0) for r in rows))
if bad_size or gap:
    sys.exit(1)
