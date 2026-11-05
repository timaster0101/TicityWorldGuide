# -*- coding: utf-8 -*-
"""投后逐字回绑（第9批 15 条判废第四投）：从本会话 jsonl 取 ImageGen 实发 prompt，
与 工具/batch9e_2026_11_05/send_bodies_15.json 的真源正文段逐字比对；只报不等者，不写任何真源。

发送侧字符损坏已在上一批抓到三例（移交清单 §32.4），所以这条闸门每轮都要跑，
不能按往轮通过率免除；不等者当场判「不作数」，须补投后重跑本脚本。
"""
import hashlib
import io
import json
import sys
from pathlib import Path

J = Path("C:/Users/TIMASTER/.qoder/projects/"
         "C--Users-TIMASTER-Documents-Qoder-2026-10-29-c8c10ff8---------/"
         "c0c216d9-4f5e-4156-8525-d49858e862dd.jsonl")
BODIES = json.load(io.open(Path(__file__).resolve().parent / "send_bodies_15.json", encoding="utf-8"))

sent = {}


def walk(o):
    if isinstance(o, dict):
        if o.get("name") == "ImageGen" and isinstance(o.get("input"), dict):
            yield o["input"]
        for v in o.values():
            for r in walk(v):
                yield r
    elif isinstance(o, list):
        for v in o:
            for r in walk(v):
                yield r


for line in io.open(J, encoding="utf-8"):
    if "ImageGen" not in line:
        continue
    try:
        rec = json.loads(line)
    except ValueError:
        continue
    for inp in walk(rec):
        rid = inp.get("name", "").split("-")[0]
        if rid in BODIES and inp.get("name", "").endswith("C123新串-v02"):
            sent.setdefault(rid, []).append(inp)

rows = []
for rid in sorted(BODIES):
    if rid not in sent:
        rows.append({"id": rid, "name": None, "已投": False})
        continue
    calls = sent[rid]
    inp = calls[-1]
    p = inp["prompt"]
    rows.append({
        "id": rid, "name": inp.get("name"), "size": inp.get("size"),
        "已投": True, "历史条数": len(calls), "chars": len(p),
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
print("已投且与真源逐字相等 %d/%d：%s" % (len(done), len(BODIES), " ".join(r["id"] for r in done)))
print("已投但串不等（不作数，待补投）%d：%s" % (len(gap), " ".join(gap)))
print("未投 %d：%s" % (len(todo), " ".join(todo)))
print("尺寸不符 %d %s" % (len(bad_size), bad_size))
if bad_size or gap:
    sys.exit(1)
