# -*- coding: utf-8 -*-
"""第9批余量投放（31 次）的发图串登记：从 数据/开图提示词/*.txt 取「## 提示词正文」之后的正文段，
逐字回证在源文件里，记 sha256；投放只允许用本表 body 字段，且投后须与会话 jsonl 的实发串逐字相等。"""
import glob
import hashlib
import io
import json
import os
import re

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(OUT_DIR, "..", ".."))
PROMPT_DIR = os.path.join(ROOT, "数据", "开图提示词")

PENDING = ["L063", "L065", "L067", "L073", "L075", "L076", "L080", "L081", "L083",
           "L085", "L086", "L087", "L089", "L090", "L092", "L093", "L094", "L095",
           "L097", "L099", "L100", "L101", "L102", "L103", "L104", "L105", "L106",
           "L107", "L108"]
EXTRA = ["R063", "R066"]

清单 = json.load(io.open(os.path.join(ROOT, "数据", "开图清单.json"), encoding="utf-8"))
by_id = {i["id"]: i for i in 清单["items"]}

out = {}
for loc_id in PENDING + EXTRA:
    hits = glob.glob(os.path.join(PROMPT_DIR, "%s-*.txt" % loc_id))
    assert len(hits) == 1, (loc_id, hits)
    src = io.open(hits[0], encoding="utf-8").read()
    name = os.path.basename(hits[0])[:-4]
    # 行首锚定：对应关系段的 review_note 里会原样引用「## 提示词正文」这句，不能用 index 取首次出现
    heads = [m.start() for m in re.finditer(r"^## 提示词正文$", src, re.M)]
    assert len(heads) == 1, (loc_id, heads)
    body = src[heads[0] + len("## 提示词正文"):].strip()
    assert body in src, loc_id
    assert body.startswith("【画风锚点】"), loc_id
    item = by_id[loc_id]
    out[loc_id] = {
        "file": "数据/开图提示词/%s.txt" % name,
        "size": item["size"],
        "status": item["status"],
        "chars": len(body),
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "body": body,
    }

with io.open(os.path.join(OUT_DIR, "send_bodies_31.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

print("发图串 %d 条（待开图 %d＋R063/R066 %d）｜尺寸分布 %s"
      % (len(out), len(PENDING), len(EXTRA),
         {s: sum(1 for v in out.values() if v["size"] == s) for s in sorted({v["size"] for v in out.values()})}))
print("探针 L063：chars=%d sha256=%s size=%s"
      % (out["L063"]["chars"], out["L063"]["sha256"][:16], out["L063"]["size"]))
