# -*- coding: utf-8 -*-
"""生成 card3x4_R4 投放台账（画风目视判废的 85 枚，走「现串逐字 + 跨卡型画风母图」臂）。

成员面现算，不手抄：真源 `数据/卡面主图画风目视.json` 的逐枚表里「判定＝判废」的那批，
键面取串文件名主干（目视件对 34 张拼装卡把 id 写成裸数字 "7"，台账侧是 "idx007"，只有主干两侧一致），
逐枚必须全部命中 R3 投放台账——解析出 0 条也打印 PASS 是这类脚本最常见的假绿，所以这里把覆盖面钉死成
「114 行全命中、miss 非空即停」。

与 R3 的实质差别只有一个：本轮是图生图。送入串＝前导一行（声明图1 只借媒介不借构图）+ 底串正文逐字，
所以底串摘要（base_sha256）与实际送入串摘要（send_sha256）必然不同，两个都登记：
绑定与回绑核的是 send_sha256（盘面上真实发出去的那串字），而按 C135「绑的是提示词串」写进卡面真源的
仍是 base_sha256。备案与绑定是两件事，口径同 工具/reshoot_campaign_2026_11_06/画风通道实验-2026-11-06.md §9。

母图池＝本轮目视「放行」的 29 枚卡面主图本身（同画幅、同 E1 厚涂档），按卡型分子池轮转；
能力卡没有同类放行枚，退到职业卡池——这条退档是申报项，见 SUBSTITUTION。
"""
import hashlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r4_style_ref as REF  # noqa: E402  前导与分配的唯一口径

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EYE = os.path.join("数据", "卡面主图画风目视.json")
SRC_LEDGER = os.path.join("数据", "卡面主图提示词3x4", "投放台账R3.json")
OUT = os.path.join("数据", "卡面主图提示词3x4", "投放台账R4.json")
SINK_DIR = os.path.join("数据", "视觉控制资产", "卡牌", "主图3x4")
RELEASE_QUOTE = ("用户 2026-11-09 逐字「卡面 85 枚＋R1 310 枚判废后的重投（花钱调用，方向已锁死"
                 "「无框主图＋不烤文案」） 去做」")
GATE_NOTE = ("放量臂不是裸投现串：同轮四枚双臂探针实测，裸投的 R043／L001 两枚读回照片质感，"
             "L001 那枚还带圆角卡框与「ai generate」台标（装帧禁令与不烤文案双双违例）；"
             "加画风母图臂的 L001／idx072 两枚媒介落到厚涂侧且无框。故本轮一律带母图投放，"
             "代价按探针实测写明——母图只借媒介不借构图时取景会漂移（机位前移、构件换位），"
             "投后目视须分「画风」「取景」两栏，取景违例单独成清单，不混进画风判废。")


def lf_sha(text):
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def main():
    os.chdir(ROOT)
    with io.open(EYE, encoding="utf-8") as fp:
        eye = json.load(fp)
    with io.open(SRC_LEDGER, encoding="utf-8") as _fh:
        led = json.load(_fh)
    by_key = {it["id"]: it for it in led["items"]}
    rows_all = eye["逐枚"]
    # 放行面（母图池）与判废面（成员面）都从同一张目视表派生，两张表互斥且并起来是 114。
    rejected, passed = [], []
    for r in rows_all:
        key = os.path.splitext(str(r["file"]))[0]
        if key not in by_key:
            raise SystemExit("目视件有 %d 枚按文件名主干取不到 R3 台账行（键面变了先修本脚本）：%s"
                             % (len([x for x in rows_all if os.path.splitext(str(x["file"]))[0] not in by_key]), key))
        (rejected if str(r.get("判定")) == "判废" else passed).append(key)
    if len(rows_all) != 114:
        raise SystemExit("目视逐枚行数 %d≠114（覆盖面变了）" % len(rows_all))
    if len(rejected) + len(passed) != 114 or set(rejected) & set(passed):
        raise SystemExit("判废 %d＋放行 %d 不等于 114 或两侧有交集：判定字段不再是二值"
                         % (len(rejected), len(passed)))

    # 母图子池：按卡型把放行枚分组；卡型真源仍是 R3 台账（目视件不带 card_type）。
    pools = {}
    for key in passed:
        pools.setdefault(by_key[key]["card_type"], []).append(key)
    pool_paths = REF.check_pool([os.path.join(SINK_DIR, "%s.png" % k).replace("\\", "/") for k in passed],
                                "卡面放行母图")
    pool_by_key = {os.path.splitext(os.path.basename(p))[0]: (p, d) for p, d in pool_paths}
    for k in passed:
        if pool_by_key[k][1] != "768x1024":
            raise SystemExit("放行枚 %s 实测画幅 %s≠768x1024，不能当卡面母图" % (k, pool_by_key[k][1]))

    items, subs = [], []
    seq = {}
    for key in sorted(rejected):
        base = by_key[key]
        ctype = base["card_type"]
        pool_keys = pools.get(ctype)
        if not pool_keys:
            sub = REF.SUBSTITUTION.get(ctype)
            if not sub or not pools.get(sub):
                raise SystemExit("%s 判废条目无同类放行母图，退档面（%s）也取不到池：%s" % (ctype, sub, key))
            pool_keys = pools[sub]
            subs.append((key, ctype, sub))
        pool = [pool_by_key[k] for k in sorted(pool_keys)]
        ref_rel, ref_dims = REF.assign(pool, seq.get(ctype, 0), "768x1024")
        seq[ctype] = seq.get(ctype, 0) + 1
        if os.path.splitext(os.path.basename(ref_rel))[0] == key:
            raise SystemExit("母图与被投条目同一枚（%s），轮转分配失效" % key)
        with io.open(base["prompt_file"], encoding="utf-8") as fh:
            text = fh.read()
        body = REF.send_body(text.rstrip("\n"))
        ref_abs = os.path.join(ROOT, ref_rel.replace("/", os.sep))
        with open(ref_abs, "rb") as _fp:
            items.append({
                "id": key, "name": base["name"], "prompt_file": base["prompt_file"],
                "base_sha256": lf_sha(text), "base_bytes_lf": len(text.replace("\r\n", "\n").encode("utf-8")),
                "send_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(), "send_chars": len(body),
                "ref_image": ref_rel, "ref_dims": ref_dims,
                "ref_sha256": hashlib.sha256(_fp.read()).hexdigest(),
                "size": base["size"], "landing": os.path.join(SINK_DIR, "%s.png" % key).replace("\\", "/"),
                "card_type": ctype,
            })
    for it in items:
        if it["size"] != "768x1024":
            raise SystemExit("台账画幅 %s≠768x1024（ImageGen size 参数按本字段写）：%s" % (it["size"], it["id"]))
        for must in ("四边装帧禁令", "文案不烤进图"):
            with io.open(it["prompt_file"], encoding="utf-8") as _handle:
                if must not in _handle.read():
                    raise SystemExit("底串缺本轮约束 %s：%s" % (must, it["prompt_file"]))

    reuse = {}
    for it in items:
        reuse[it["ref_image"]] = reuse.get(it["ref_image"], 0) + 1
    # 投放面 paste：与主链同一条契约——文件逐字节＝实际送入串（不带结尾换行），写完立刻按 send_sha256 自证。
    # 探针那两张差一个换行的教训写在 工具/r4_style_ref.py 头注释里：换行形态不进台账就等于把逐字回绑交给运气。
    paste_dir = os.path.join(os.path.dirname(ROOT), "_scratch_cardref", "card3x4_r4", "paste")
    os.makedirs(paste_dir, exist_ok=True)
    for it in items:
        with io.open(it["prompt_file"], encoding="utf-8") as _h124:
            body = REF.send_body(_h124.read().rstrip("\n"))
        p = os.path.join(paste_dir, "%s.txt" % it["id"])
        with io.open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(body)
        with open(p, "rb") as _h129:
            assert hashlib.sha256(_h129.read()).hexdigest() == it["send_sha256"], it["id"]

    doc = {"投放轮次": "card3x4_R4", "臂": "现串逐字＋跨卡型画风母图（图生图）",
           "放行原话": RELEASE_QUOTE, "放量前置": GATE_NOTE,
           "前导声明": REF.PREFIX_LINE,
           "送入串形态": "前导声明一行 + 换行 + 底串全文去掉结尾换行；底串正文逐字不动，"
                          "故 send_sha256≠base_sha256 是本轮的常态而不是违例。绑定按 C135 写 base_sha256，"
                          "回绑与逐字核验按 send_sha256。",
           "口径": "成员面＝目视真源判定「判废」的 %d 枚（放行 %d 枚只作母图、不重投）；"
                   "底串＝数据/卡面主图提示词3x4/<ID>.txt（与 R3 同一批串，本轮串面未改）；"
                   "画幅 768×1024；landing＝数据/视觉控制资产/卡牌/主图3x4/<ID>.png（本机资产、gitignored，"
                   "旧版已在 主图3x4.zip 还原点内，本轮覆盖判废版）"
                   % (len(items), len(passed)),
           "母图退档": {"能力卡→职业卡池": len(subs), "明细": subs},
           "母图复用": {"池内枚数": len(pool_paths), "最高复用": max(reuse.values()),
                        "复用分布": sorted(reuse.values(), reverse=True)[:8]},
           "条数": len(items), "画幅": "768x1024", "items": items}
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    print("R4 卡面台账 %d 条｜放行母图 %d 枚｜退档条目 %d｜最高复用 %d 次/枚｜sha 面：base≠send %d 条"
          % (len(items), len(passed), len(subs), max(reuse.values()),
             sum(1 for i in items if i["base_sha256"] != i["send_sha256"])))
    print("卡型分布", {k: sum(1 for i in items if i["card_type"] == k)
                       for k in sorted({i["card_type"] for i in items})})
    print("落盘 %s %d 字节" % (OUT.replace("\\", "/"), os.path.getsize(OUT)))
    print("paste %d 份逐字节自证通过 → %s" % (len(items), paste_dir.replace("\\", "/")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
