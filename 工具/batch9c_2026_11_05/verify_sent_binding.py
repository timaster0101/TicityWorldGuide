# -*- coding: utf-8 -*-
"""投后逐字回绑：从本会话 jsonl 取 ImageGen 实发 prompt，与 工具/batch9c_2026_11_05/send_bodies_31.json
的真源正文段逐字比对；只报不相等者，不写任何真源。"""
import hashlib
import io
import json
import sys
from pathlib import Path

J = Path("C:/Users/TIMASTER/.qoder/projects/"
         "C--Users-TIMASTER-Documents-Qoder-2026-10-29-c8c10ff8---------/"
         "c0c216d9-4f5e-4156-8525-d49858e862dd.jsonl")
with io.open(Path(__file__).resolve().parent / "send_bodies_31.json", encoding="utf-8") as fp:
    BODIES = json.load(fp)

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


with io.open(J, encoding="utf-8") as fh:
    for line in fh:
        if "ImageGen" not in line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        for inp in walk(rec):
            nm = inp.get("name", "")
            rid = nm.split("-")[0]
            if rid in BODIES:
                sent.setdefault(rid, []).append(inp)

rows = []
for rid in sorted(sent):
    inp = sent[rid][-1]  # 同 id 往轮可能投过多次，只取文件顺序末条作本轮实发
    p = inp["prompt"]
    rows.append({
        "id": rid, "name": inp.get("name"), "size": inp.get("size"),
        "历史条数": len(sent[rid]),
        "chars": len(p),
        "sent_sha12": hashlib.sha256(p.encode("utf-8")).hexdigest()[:12],
        "canon_sha12": BODIES[rid]["sha256"][:12],
        "逐字相等": p == BODIES[rid]["body"],
        "尺寸与清单一致": inp.get("size") == BODIES[rid]["size"],
    })

out = Path(__file__).resolve().parent / "sent_binding.json"
out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
done = [r for r in rows if r["逐字相等"]]
todo = [r["id"] for r in rows if not r["逐字相等"]]
bad_size = [r["id"] for r in done if not r["尺寸与清单一致"]]
print("本轮已投（末条与真源逐字相等）%d/31：%s" % (len(done), " ".join(r["id"] for r in done)))
print("未投（末条仍是往轮旧串）%d：%s" % (len(todo), " ".join(todo)))
print("尺寸不符 %d %s" % (len(bad_size), bad_size))
if bad_size:
    sys.exit(1)
