# -*- coding: utf-8 -*-
"""生成 card3x4_R3 投放台账（114 张整批判废后的无框重投），逐条带底串 sha256 与 landing 路径。

覆盖面＝`数据/卡面主图提示词3x4/台账.json` 的全部 114 条（派生 80＋拼装 34），不再按投放状态筛：
本轮是「整批判废后重投」，两条支路一张都不留。字段与 R1／R2 逐字同构，好让
`wire_card_main_images.py --round r3` 用同一套对拍。

底串取的是本轮重生成后的 txt（串面已带「四边装帧禁令」与「文案不烤进图」两条），
所以 prompt_sha256 与 R1／R2 台账里的值必然全数不同——那两轮记的是当时送入的串，属 as-run 历史，
不回头改；谁把这里的条数或 sha 口径改成「沿用旧台账」，wire 的证据对拍会当场判红。
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_LEDGER = os.path.join("数据", "卡面主图提示词3x4", "台账.json")
OUT = os.path.join("数据", "卡面主图提示词3x4", "投放台账R3.json")
SINK_DIR = os.path.join("数据", "视觉控制资产", "卡牌", "主图3x4")
PROBES = ["L022", "idx007"]
RELEASE_QUOTE = ("用户 2026-11-08：「卡面主图整批判废后的重投。§55.32 遗留清单第 2 条：画风判废权在你手里"
                 "（103/114 机器落在照片侧，idx090 机器判绘画、人眼仍像实拍）。重投是花钱的 ImageGen 批量调用，"
                 "且方向已锁死为「无框主图 + 不烤文案」，要你一句「开始重投」我才发。／把这个做了」")


def main():
    os.chdir(ROOT)
    with open(SRC_LEDGER, encoding="utf-8") as fh:
        led = json.load(fh)
    items = led["items"]
    if len(items) != 114:
        raise SystemExit("台账条数 %d≠114（生成器没重跑或清单变了）" % len(items))
    rows = []
    for it in items:
        with open(it["file"], encoding="utf-8") as fh:
            text = fh.read()
        for must in ("四边装帧禁令", "文案不烤进图"):
            if must not in text:
                raise SystemExit("底串缺本轮约束 %s：%s" % (must, it["file"]))
        if "满幅铺整卡" in text:
            raise SystemExit("底串还留着邀请画卡的旧措辞：%s" % it["file"])
        raw = text.encode("utf-8")
        rows.append({"id": it["id"], "name": it["name"], "prompt_file": it["file"].replace("\\", "/"),
                     "prompt_sha256": hashlib.sha256(raw).hexdigest(),
                     "bytes": len(raw), "size": it["size"],
                     "landing": os.path.join(SINK_DIR, "%s.png" % it["id"]).replace("\\", "/"),
                     "card_type": it.get("card_type", "")})
    doc = {"投放轮次": "card3x4_R3", "放行原话": RELEASE_QUOTE,
           "探针": {"ids": PROBES,
                    "note": "探针取 R1／R2 各自的探针卡（L022＝派生支路、idx007＝拼装支路），"
                            "与旧轮同卡同机位可直接对拍；确认后放量其余 112 张"},
           "口径": "覆盖面＝台账.json 全部 114 条（派生 80＋拼装 34），本轮整批重投、不按投放状态筛；"
                   "底串＝数据/卡面主图提示词3x4/<ID>.txt（本轮重生成，串面含四边装帧禁令与文案不烤进图）；"
                   "画幅 768×1024；landing＝数据/视觉控制资产/卡牌/主图3x4/<ID>.png（本机资产、gitignored，"
                   "旧版已在 主图3x4.zip 还原点内）；"
                   "prompt_sha256 与 bytes 取 CRLF→LF 归一后的文本字节，送入串与证据对拍同一口径",
           "条数": len(rows), "画幅": "768x1024", "items": rows}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    print(json.dumps({"条数": len(rows), "探针": PROBES,
                      "卡型分布": {k: sum(1 for r in rows if r["card_type"] == k)
                                   for k in sorted({r["card_type"] for r in rows})},
                      "底串字节区间": [min(r["bytes"] for r in rows), max(r["bytes"] for r in rows)],
                      "台账": OUT.replace("\\", "/")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
