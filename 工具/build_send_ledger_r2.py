# -*- coding: utf-8 -*-
"""生成 card3x4_R2 投放台账（34 张实景待投），逐条带底串 sha256 与 landing 路径。

R1 的投放台账是会话侧手写的；本轮改成脚本产，字段与 R1 逐字同构，好让 wire_card_main_images.py --round r2
用同一套对拍（证据的 prompt_sha256 必须等于这里登记的底串 sha）。条目来源＝数据/卡面主图提示词3x4/台账.json
里 manifest_status==MISSING 的那 34 条（派生支路只产 OK／OVERFLOW，MISSING 只能来自待投拼装支路）。

landing 用 idxNNN.png：这批卡的 manifest code 是空串，唯一稳定标识是 _idx，落点名与 wire 的 sink_key
（idx086→86）一一对应，回填时 build_card_faces.py 走 _idx 查键这条路。
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_LEDGER = os.path.join("数据", "卡面主图提示词3x4", "台账.json")
OUT = os.path.join("数据", "卡面主图提示词3x4", "投放台账R2.json")
SINK_DIR = os.path.join("数据", "视觉控制资产", "卡牌", "主图3x4")
RELEASE_QUOTE = ("用户 2026-11-08：「② 34 张实景待投未投＝11 张产品方向未点（#64）＋23 张须先新写 3:4 正文"
                 "（#49/#50/#51），花钱调用下轮要重新放行；③ 本轮未提交也未推送，需要的话我先报提交范围再动。都做」")


def main():
    os.chdir(ROOT)
    with open(SRC_LEDGER, encoding="utf-8") as fh:
        led = json.load(fh)
    todo = [x for x in led["items"] if x["manifest_status"] == "MISSING"]
    if len(todo) != 34:
        raise SystemExit("待投条数 %d≠34（台账未重生成或清单变了）" % len(todo))
    rows = []
    for it in todo:
        with open(it["file"], encoding="utf-8") as fh:
            text = fh.read()
        # 底串 txt 是生成器在 Windows 上以文本模式写的，落盘行尾是 CRLF；这里按通用换行读入再编码，
        # 故 prompt_sha256／bytes 取的是 CRLF→LF 归一后的文本字节（idx007 实读 raw 9506／归一 9497）。
        # 送入 ImageGen 的是同一份归一文本，wire 的证据对拍也以此为口径——换行差异不算内容漂移。
        raw = text.encode("utf-8")
        landing = os.path.join(SINK_DIR, "%s.png" % it["id"]).replace("\\", "/")
        rows.append({"id": it["id"], "name": it["name"],
                     "prompt_file": it["file"].replace("\\", "/"),
                     "prompt_sha256": hashlib.sha256(raw).hexdigest(),
                     "bytes": len(raw), "size": it["size"], "landing": landing,
                     "card_type": it.get("card_type", "")})
    doc = {"投放轮次": "card3x4_R2", "放行原话": RELEASE_QUOTE,
           "探针": {"id": rows[0]["id"],
                    "note": "探针用本轮同一份底串（sha 一致），确认后放量其余 33 张"},
           "口径": "底串＝数据/卡面主图提示词3x4/idxNNN-名.txt（待投拼装支路产物）；画幅 768×1024；"
                   "landing＝数据/视觉控制资产/卡牌/主图3x4/idxNNN.png（本机资产、gitignored）；"
                   "prompt_sha256 与 bytes 取 CRLF→LF 归一后的文本字节（txt 在 Windows 以文本模式落盘为 CRLF），"
                   "送入串与证据对拍同一口径",
           "条数": len(rows), "画幅": "768x1024", "items": rows}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    print(json.dumps({"条数": len(rows), "卡型分布": {k: sum(1 for r in rows if r["card_type"] == k)
                                                   for k in sorted({r["card_type"] for r in rows})},
                      "底串字节区间": [min(r["bytes"] for r in rows), max(r["bytes"] for r in rows)],
                      "台账": OUT.replace("\\", "/")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
