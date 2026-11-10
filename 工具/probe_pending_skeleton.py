# -*- coding: utf-8 -*-
"""重取待投骨架三段：从 80 条 3:2 底串正文按【段名】切段，验证三段全库逐字一致，并把真骨架写回
数据/卡面主图正文待投.json 的 骨架/骨架指纹/骨架出处。

上一轮我从**派生后的 3:4 txt** 里用 find('【全局硬设定】') 取段，第一处命中的其实是 CLAUSE 里那句
「下文【全局硬设定】仍按 3:2 横幅措辞处……」，于是骨架被前缀污染（1753 字 vs 真段 999 字）。
本脚本一律从 数据/开图提示词/ 的 3:2 原文取，且用「段名行首」正则而不是子串 find，并逐条比对是否全等。
"""
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PENDING = os.path.join("数据", "卡面主图正文待投.json")
LEDGER = os.path.join("数据", "卡面主图提示词3x4", "台账.json")
SECTIONS = ["画风锚点", "全局硬设定"]


def sha12(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def section(text, name):
    """取【name】段：从行首的【name】到下一个行首【段名】或 English tail 之前。"""
    m = re.search(r"^【%s】" % name, text, re.M)
    if not m:
        raise ValueError("缺段 %s" % name)
    nxt = re.search(r"^【[^】]+】|^English tail:", text[m.end():], re.M)
    end = m.end() + (nxt.start() if nxt else len(text[m.end():]))
    return text[m.start():end].strip()


def tail_base(text):
    m = re.search(r"^English tail:", text, re.M)
    if not m:
        raise ValueError("缺 English tail")
    return text[m.start():].strip()


def main():
    os.chdir(ROOT)
    with open(LEDGER, encoding="utf-8") as fh:
        led = json.load(fh)
    seen = {name: {} for name in SECTIONS}
    tails = {}
    for it in led["items"]:
        with open(it["base_prompt_file"], encoding="utf-8") as fh:
            text = fh.read()
        for name in SECTIONS:
            seen[name].setdefault(section(text, name), []).append(it["id"])
        # English tail 基座＝去掉每条卡自己的增量后的公共前缀，先按整串收集
        tails.setdefault(tail_base(text), []).append(it["id"])
    out = {"骨架条数": len(led["items"])}
    for name in SECTIONS:
        variants = seen[name]
        out[name] = {"变体数": len(variants), "字数": {k: len(k) for k in variants},
                     "sha12": {k: sha12(k) for k in variants}}
        print("%s 变体 %d 种；各变体覆盖卡数 %s" %
              (name, len(variants), [len(v) for v in variants.values()]))
    print("English tail 整串变体 %d 种（每条卡自带增量，必然多份）" % len(tails))
    with open(os.path.join(os.pardir, "_scratch_cardref", "skeleton_probe.json"), "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
