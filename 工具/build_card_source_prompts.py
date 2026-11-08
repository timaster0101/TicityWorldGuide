# -*- coding: utf-8 -*-
"""卡面专用图提示词生成器（C143）。

竖幅 2:3 的塔与钟楼放进卡面横窗会溢出窗带下沿，按「不裁切、窗内不留白、不挤压标题区」三条，
只能为这几张单独生成 3:2 横幅图。本脚本不重写正典，只从既有开图提示词里取正文，
在【取景指令】前挂一条横幅构图约束，其余逐字保留。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "工具"))
import build_card_faces as B  # noqa: E402

OUT_DIR = os.path.join("数据", "卡面专用提示词")
WIDE_CLAUSE = ("画幅为3:2横幅：相机后撤到能容纳主体完整高度的距离，主体竖向轮廓居中略偏，"
               "顶部与底部各留出不少于画面高度8%的呼吸区，不得裁切冠部或基座；"
               "本条只改取景距离与画幅，主体外观、光照方位与人群密度沿用下文原句，不因此增删建筑构件。")


def build(prompt_file):
    with open(prompt_file, encoding="utf-8") as fh:
        text = fh.read()
    start = text.find("【画风锚点】")
    if start < 0:
        raise ValueError("提示词正文缺画风锚点段：" + prompt_file)
    body = text[start:].strip()
    lines = body.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("【取景指令】"):
            lines[i] = "【取景指令】" + WIDE_CLAUSE + line[len("【取景指令】"):]
            break
    else:
        raise ValueError("提示词正文缺取景指令段：" + prompt_file)
    return "\n".join(lines)


def main():
    os.chdir(ROOT)
    entries = {}
    with open(os.path.join("数据", "开图清单.json"), encoding="utf-8") as fh:
        for e in json.load(fh)["items"]:
            entries[e["id"]] = e
    codes = sys.argv[1:] or ["L003", "L007", "L022", "L033", "L038"]
    os.makedirs(OUT_DIR, exist_ok=True)
    ledger = []
    for code in codes:
        e = entries[code]
        prompt = build(e["prompt_file"])
        path = os.path.join(OUT_DIR, "%s-%s.txt" % (code, e["name"]))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(prompt + "\n")
        ledger.append({"id": code, "name": e["name"], "file": path, "size": "1536x1024",
                       "aspect": "3:2 横幅，容纳主体完整高度并留出上下呼吸区",
                       "len": len(prompt), "base_prompt_file": e["prompt_file"]})
    with open(os.path.join(OUT_DIR, "卡面专用提示词台账.json"), "w", encoding="utf-8") as fh:
        json.dump({"生成者": os.path.basename(__file__), "口径": "只改画幅与取景距离，正典段逐字保留",
                   "条数": len(ledger), "items": ledger}, fh, ensure_ascii=False, indent=1)
    print(json.dumps({"条数": len(ledger), "字数区间": [min(x["len"] for x in ledger),
                                                 max(x["len"] for x in ledger)],
                      "清单": [(x["id"], x["name"], x["size"]) for x in ledger]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
