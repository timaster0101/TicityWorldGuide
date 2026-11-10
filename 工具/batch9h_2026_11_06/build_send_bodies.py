# -*- coding: utf-8 -*-
"""待开图 9 条第七投（9 次生成）的发图串登记。

串与第六投（§40／工具/batch9g_2026_11_06）同源：第六投之后没有任何提示词真源改动
（C131 只动打卡口径与手册/索引措辞，`prompt_sha256` 变更 0/312），所以仍按 `C123新串-v02` 档串发起。
串一律从 数据/开图提示词/*.txt 的「## 提示词正文」之后正文段逐字取，并逐条与
工具/batch9g_2026_11_06/send_bodies_9.json 的存档 body 比对——两次投放之间真源若被动过即停。

名单不手抄：从 数据/开图清单.json 现读 `status == 待开图` 且 `image_file` 为空的条目，
并要求它恰为第六投那 9 条（名单变了说明别处动过格）。

投放只允许用本表 body 字段；投后须与会话 jsonl 的实发串逐字相等（发送侧字符损坏见 §32.4）。
本轮额度口径由用户 2026-11-06 改定：「之后不用考虑额度的事，直接做就行了」，故不设探针闸，
但 403 code 112 一出现仍当场停手报告（那是通道故障，不是额度问题）。
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
PREV = os.path.join(ROOT, "工具", "batch9g_2026_11_06", "send_bodies_9.json")

with io.open(os.path.join(ROOT, "数据", "开图清单.json"), encoding="utf-8") as fh:
    清单 = json.load(fh)
by_id = {i["id"]: i for i in 清单["items"]}
with io.open(PREV, encoding="utf-8") as _fh:
    prev = json.load(_fh)

REJECT = sorted(i["id"] for i in 清单["items"] if i["status"] == "待开图" and not i["image_file"])
assert REJECT == sorted(prev), (REJECT, sorted(prev))
assert 清单["pending"] == 9 == len(REJECT), 清单["pending"]

out = {}
for loc_id in REJECT:
    hits = glob.glob(os.path.join(PROMPT_DIR, "%s-*.txt" % loc_id))
    assert len(hits) == 1, (loc_id, hits)
    with io.open(hits[0], encoding="utf-8") as _fp:
        src = _fp.read()
    name = os.path.basename(hits[0])[:-4]
    heads = [m.start() for m in re.finditer(r"^## 提示词正文$", src, re.M)]
    assert len(heads) == 1, (loc_id, heads)
    body = src[heads[0] + len("## 提示词正文"):].strip()
    assert body in src and body.startswith("【画风锚点】"), loc_id
    assert body == prev[loc_id]["body"], (loc_id, "与第六投存档串不等，真源在两次投放之间被动过")
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() == prev[loc_id]["sha256"], loc_id
    item = by_id[loc_id]
    assert not item["image_prompt_sha256"], (loc_id, "既有绑定未清，先查是谁签的")
    out[loc_id] = {
        "file": "数据/开图提示词/%s.txt" % name,
        "name": name.split("-", 1)[1],
        "size": item["size"],
        "chars": len(body),
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "body": body,
    }

path = os.path.join(OUT_DIR, "send_bodies_9.json")
with io.open(path, "w", encoding="utf-8", newline="\n") as fp:
    json.dump(out, fp, ensure_ascii=False, indent=1, sort_keys=True)
    fp.write("\n")
print("send_bodies_9（第七投）: %d 条｜档 C123新串-v02（与第六投逐字同串）" % len(out))
for loc_id in REJECT:
    print("  %s %s｜%s｜%d 字｜%s" % (loc_id, out[loc_id]["name"], out[loc_id]["size"],
                                    out[loc_id]["chars"], out[loc_id]["sha256"][:12]))
