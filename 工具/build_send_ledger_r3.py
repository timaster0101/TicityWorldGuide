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
                 "且方向已锁死为「无框主图 + 不烤文案」，要你一句「开始重投」我才发。／把这个做了」；"
                 "本轮放行原话＝用户 2026-11-09 逐字「都做」，针对的是主会话申报的三条偏差，其中第一条逐字为"
                 "「R3 的 112 张放量未投——甲的门槛『够到绘画档才放』未满足（p7/p8 整幅读出厚涂，但近景人物面部"
                 "与镀铬闸机仍照片/CG 侧），且属花钱调用需你重新放行」")
GATE_NOTE = ("放量面按甲的原措辞是「其余 112 张」，现算改回 **114 张全发**：`数据/提示词基准冻结.json` 的 "
             "frozen_at_ms 在 2026-11-09 02:02:24.427 重钉过，而 verify_round 的分带下界就是这个值，"
             "02:02 之前那 4 枚证据（23:40—23:47 探针 L022／idx007、00:34—00:35 对照 p5／p6、00:49 现串探针 p7／p8）"
             "全部落在带外，不能充当本轮发起；故含两枚探针卡在内按现串重发，多花的调用数是 2 张。"
             "**放量前置条件未满足这件事按申报处理、不降级**：C153 的目视结论是「厚涂与干边在中远景与建筑／地面达成，"
             "近景人物面部与金属件未达成」，甲的门槛「够到绘画档才放 112 张」未满足；用户「都做」是在读到这句申报之后给的，"
             "本件据此放量，画风判废权仍在用户，产出仍可能整批判废——这条不是脚本能判的，见 C153 后果③。")


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
                            "与旧轮同卡同机位可直接对拍；探针投于 11-08 23:40—23:47 与 11-09 00:49，"
                            "均在 11-09 02:02 基准重钉之前，故本轮按现串重发、不再豁免"},
           "放量前置": GATE_NOTE,
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
