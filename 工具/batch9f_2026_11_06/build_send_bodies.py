# -*- coding: utf-8 -*-
"""第9批 f 轮 12 条判废条目第五投（12 次付费生成：探针 1＋余量 11）的发图串登记。

串与 §35.1 同源：本轮没有任何提示词真源改动（9b／9c 只动卡牌与背景卡真源，实测 `prompt_sha256` 变更 0/312），
所以仍按 `C123新串-v02` 档串发起。串一律从 数据/开图提示词/*.txt 的「## 提示词正文」之后正文段逐字取，
并逐条与 工具/batch9e_2026_11_05/send_bodies_15.json 的存档 body 比对——两次投放之间真源若被动过即停。

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
PREV = os.path.join(ROOT, "工具", "batch9e_2026_11_05", "send_bodies_15.json")

# §35.1 的仍待开图名单（12 条）
REJECT = ["L081", "L083", "L085", "L093", "L094", "L099",
          "L100", "L101", "L103", "L105", "L106", "L108"]

# 探针：L083 数岸算力塔（竖幅，与 §35 的探针同条，C126 的杆高阈值可落到数上）
PROBE = "L083"

清单 = json.load(io.open(os.path.join(ROOT, "数据", "开图清单.json"), encoding="utf-8"))
by_id = {i["id"]: i for i in 清单["items"]}
prev = json.load(io.open(PREV, encoding="utf-8"))

out = {}
for loc_id in REJECT:
    hits = glob.glob(os.path.join(PROMPT_DIR, "%s-*.txt" % loc_id))
    assert len(hits) == 1, (loc_id, hits)
    src = io.open(hits[0], encoding="utf-8").read()
    name = os.path.basename(hits[0])[:-4]
    heads = [m.start() for m in re.finditer(r"^## 提示词正文$", src, re.M)]
    assert len(heads) == 1, (loc_id, heads)
    body = src[heads[0] + len("## 提示词正文"):].strip()
    assert body in src and body.startswith("【画风锚点】"), loc_id
    assert body == prev[loc_id]["body"], (loc_id, "与 §35 存档串不等，真源在两次投放之间被动过")
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() == prev[loc_id]["sha256"], loc_id
    item = by_id[loc_id]
    assert item["status"] == "待开图", (loc_id, item["status"])
    assert not item["image_file"], (loc_id, "判废条目不该已占格")
    assert not item["image_prompt_sha256"], (loc_id, "既有绑定未清，先查是谁签的")
    out[loc_id] = {
        "file": "数据/开图提示词/%s.txt" % name,
        "name": name.split("-", 1)[1],
        "size": item["size"],
        "chars": len(body),
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "body": body,
    }

assert PROBE in out
assert len(out) == 12 == len(REJECT), len(out)
assert 清单["pending"] == 12, 清单["pending"]

path = os.path.join(OUT_DIR, "send_bodies_12.json")
with io.open(path, "w", encoding="utf-8", newline="\n") as fp:
    json.dump(out, fp, ensure_ascii=False, indent=1, sort_keys=True)
    fp.write("\n")
print("send_bodies_12: %d 条｜探针 %s｜档 C123新串-v02" % (len(out), PROBE))
for loc_id in REJECT:
    print("  %s %s｜%s｜%d 字｜%s" % (loc_id, out[loc_id]["name"], out[loc_id]["size"],
                                    out[loc_id]["chars"], out[loc_id]["sha256"][:12]))
