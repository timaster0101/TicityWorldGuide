# -*- coding: utf-8 -*-
"""第9批 19 条判废条目重投（19 次付费生成）的发图串登记。

串与上一批同源：仍从 数据/开图提示词/*.txt 的「## 提示词正文」之后正文段逐字取，
并逐条与 工具/batch9c_2026_11_05/send_bodies_31.json 的存档 sha 比对——本轮没换真源，
两条 sha 不相等就说明有人在两次投放之间改过提示词，须先查清再投。
投放只允许用本表 body 字段；投后须与会话 jsonl 的实发串逐字相等（发送侧字符损坏见 §32.4）。
"""
import glob
import hashlib
import io
import json
import os
import re

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(OUT_DIR, "..", ".."))
PROMPT_DIR = os.path.join(ROOT, "数据", "开图提示词")
PREV = os.path.join(ROOT, "工具", "batch9c_2026_11_05", "send_bodies_31.json")

# §32.5 的判废名单：13 条 L007 独占形制复制＋5 条其它冠部／桅杆记号＋1 条触本条锁定禁则
REJECT = ["L065", "L080", "L081", "L083", "L085", "L090", "L092", "L093", "L094", "L095",
          "L099", "L100", "L101", "L103", "L104", "L105", "L106", "L107", "L108"]

with io.open(os.path.join(ROOT, "数据", "开图清单.json"), encoding="utf-8") as fp:
    清单 = json.load(fp)
by_id = {i["id"]: i for i in 清单["items"]}
with io.open(PREV, encoding="utf-8") as fh:
    prev = json.load(fh)

out = {}
for loc_id in REJECT:
    hits = glob.glob(os.path.join(PROMPT_DIR, "%s-*.txt" % loc_id))
    assert len(hits) == 1, (loc_id, hits)
    with io.open(hits[0], encoding="utf-8") as _fh:
        src = _fh.read()
    name = os.path.basename(hits[0])[:-4]
    heads = [m.start() for m in re.finditer(r"^## 提示词正文$", src, re.M)]
    assert len(heads) == 1, (loc_id, heads)
    body = src[heads[0] + len("## 提示词正文"):].strip()
    assert body in src and body.startswith("【画风锚点】"), loc_id
    assert body == prev[loc_id]["body"], (loc_id, "与上一批存档串不等，真源被动过")
    item = by_id[loc_id]
    assert item["status"] == "待开图", (loc_id, item["status"])
    out[loc_id] = {
        "file": "数据/开图提示词/%s.txt" % name,
        "name": name.split("-", 1)[1],
        "size": item["size"],
        "chars": len(body),
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "body": body,
    }

with io.open(os.path.join(OUT_DIR, "send_bodies_19.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

dist = {s: sum(1 for v in out.values() if v["size"] == s) for s in sorted({v["size"] for v in out.values()})}
print("发图串 %d 条（真源与上一批存档逐字相等 %d/%d）｜尺寸分布 %s"
      % (len(out), len(out), len(REJECT), dist))
for k in REJECT:
    print("%s %s %s chars=%d sha256=%s" % (k, out[k]["name"], out[k]["size"], out[k]["chars"], out[k]["sha256"][:16]))
