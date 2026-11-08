# -*- coding: utf-8 -*-
"""卡面满幅主图 3:4 提示词生成器（C147 路线 B + 用户 2026-11-08 拍板「按 3:4 原生重投」）。

卡面是 768×1024 的 3:4 满幅主图，文字与浮层由 HTML 叠在图上。既有开图提示词按 3:2 横幅写，
直接 object-fit:cover 会裁掉左右，因此这 80 张有 3:2 正文可派生的卡（`code` 非空，即全部实景卡）单独派生 3:4 串。
与 build_card_source_prompts.py 同一姿态：不重写正典，只取正文、在【取景指令】前挂一条画幅约束，
其余逐字保留；底串的【全局硬设定】仍写 3:2，故约束句自带「冲突以本条为准」。

2026-11-08 追加待投支路（C149）：职业／兑换／物品／能力／景群这 34 张从来没有 3:2 底串，正文由
`数据/卡面主图正文待投.json` 分段提供，骨架五段（画风锚点／全局硬设定／English tail 风格前缀／
English tail 画幅句／English tail 禁则后缀）逐字复用 80 张同源件的 3:2 原文并带指纹对拍，
画幅约束改用面向场景与人物构图的 CLAUSE_SCENE；清单以 manifest 为准，正文与 `pending_indices()`
（空 code 且非模板正面／非模板背面的结构判）逐 idx 不等就抛错，不产半份台账。
投放状态不进这条口径：34 张补投转 OK 后若仍按 `status == "MISSING"` 筛，待投名单会归零、
整条拼装支路被静默关掉，正文字数与台账条数随即对不上。
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "工具"))

MANIFEST = os.path.join("数据", "视觉控制资产", "卡牌", "768x1024", "manifest.json")
LIST = os.path.join("数据", "开图清单.json")
PENDING = os.path.join("数据", "卡面主图正文待投.json")
OUT_DIR = os.path.join("数据", "卡面主图提示词3x4")
SIZE = "768x1024"
CLAUSE = (
    "画幅为3:4竖幅（768×1024，满幅铺整卡，不作裁切适配）：主体完整入画、冠部与基座一律不得裁切，"
    "主体竖向轮廓居中略偏上；顶部留出不少于画面高度14%的文字安全区（卡名与副标题由页面叠在此处，"
    "该带只许天空、远景墙体或均匀暗部，不得有枝叶、构件或灯杆切入），"
    "底部留出不少于画面高度22%的暗部安全区（底部文案浮层叠在此处，该带以地面、阴影与实物体量为主，"
    "不放关键构件、不放人群正面与可读招牌，画面下沿12%内保持均匀暗面）；"
    "本条只改取景距离、画幅与上下安全区，主体外观、光照方位与人群密度沿用下文原句，不因此增删建筑构件；"
    "下文【全局硬设定】仍按 3:2 横幅措辞处，画幅与上下安全区以本条为准；"
    "竖幅只是同一机位的画幅变化，不因此获得新的背景授权：背景天际线仍然只许出现【取景指令】逐一点名的独立远景对象，"
    "未点名的现代高层群、玻璃塔群与塔吊一律不入画。"
)


def sha12(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def derive(prompt_file):
    with open(prompt_file, encoding="utf-8") as fh:
        text = fh.read()
    start = text.find("【画风锚点】")
    if start < 0:
        raise ValueError("提示词正文缺画风锚点段：" + prompt_file)
    lines = text[start:].strip().split("\n")
    for i, line in enumerate(lines):
        if line.startswith("【取景指令】"):
            lines[i] = "【取景指令】" + CLAUSE + line[len("【取景指令】"):]
            break
    else:
        raise ValueError("提示词正文缺取景指令段：" + prompt_file)
    return "\n".join(lines)


def compose_pending(item, skeleton, clause_scene):
    """待投卡（职业／兑换／物品／能力／景群）没有可派生的 3:2 底串，正文按 数据/卡面主图正文待投.json 分段拼装：
    骨架五段逐字复用 80 张同源件的 3:2 原文，画幅约束改用面向场景与人物构图的 CLAUSE_SCENE。

    English tail 不是整段复用：80 条的 tail 有 51 种变体（主体句与机位几何句逐卡不同），所以拆成
    「风格前缀＋统一画幅句＋本条 tail_extra＋全库公共禁则后缀」四截拼，禁则后缀里含平台 AIGC 角标与
    TC260 元数据须原样保留那句，属合规项、逐条不许省。
    """
    s = item["sections"]
    for field in ("画面定位", "取景指令", "外观辨识", "人群与烟火气", "锁定与禁则"):
        if not (s.get(field) or "").strip():
            raise ValueError("待投正文缺分段 %s：%s" % (field, item["name"]))
    extra = (item.get("tail_extra") or "").strip().rstrip(",; ")
    if not extra:
        raise ValueError("待投正文缺 tail_extra：%s" % item["name"])
    # 四截一律剥掉收尾逗号再统一以 ", " 拼接：骨架的画幅句登记时自带收尾逗号，
    # 先前按「段 + ","」拼会在 tail 里造出 "text,, Foreground…" 的双逗号。
    def clause(x):
        return x.strip().rstrip(",;").strip()
    tail = ", ".join([clause(skeleton["English tail 风格前缀"]),
                      clause(skeleton["English tail 画幅句"]),
                      clause(extra),
                      clause(skeleton["English tail 禁则后缀"])])
    lines = [skeleton["画风锚点"],
             "【画面定位】" + s["画面定位"].strip(),
             "【取景指令】" + clause_scene + s["取景指令"].strip(),
             "【外观辨识】" + s["外观辨识"].strip(),
             "【人群与烟火气】" + s["人群与烟火气"].strip(),
             "【锁定与禁则】" + s["锁定与禁则"].strip(),
             skeleton["全局硬设定"],
             "",
             tail]
    return "\n".join(lines) + "\n"


def pending_indices(man):
    """待投（无 3:2 底串、须走拼装正文）名单的单一真源口径，`merge_pending_specs.py` 与本脚本共用。

    按结构判、不按投放状态判：这批卡 `code` 恒空（无 ID 可查 3:2 正文）、模板正面按档 A 不投实景、
    模板背面走程序面——所以「没有可派生底串的卡」＝空 code 且非两种模板面。
    早先各处写的是 `status == "MISSING"`，34 张补投转 OK 的当轮就会与正文清单判不平而把整条支路关掉。
    """
    return sorted(c["idx"] for c in man if not c["code"]
                  and c["card_type"] != "模板正面" and c["template"] != "back")


def main(argv=None):
    os.chdir(ROOT)
    with open(MANIFEST, encoding="utf-8") as fh:
        man = json.load(fh)["cards"]
    # `and c["code"]` 是承重项：34 张待投卡回填后 status 也转了 OK，但它们没有 3:2 底串，只能走拼装支路。
    codes = [c["code"] for c in man if c["status"] in ("OK", "OVERFLOW") and c["code"]]
    keep = set(argv or [])
    if keep:
        codes = [k for k in codes if k in keep]
    with open(LIST, encoding="utf-8") as fh:
        entries = {e["id"]: e for e in json.load(fh)["items"]}
    os.makedirs(OUT_DIR, exist_ok=True)
    ledger = []
    for code in codes:
        e = entries[code]
        prompt = derive(e["prompt_file"])
        path = os.path.join(OUT_DIR, "%s-%s.txt" % (code, e["name"]))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(prompt + "\n")
        ledger.append({"id": code, "name": e["name"], "file": path.replace("\\", "/"),
                       "size": SIZE, "aspect": "3:4 竖幅满幅，含顶部14%与底部22%文字安全区",
                       "len": len(prompt), "base_prompt_file": e["prompt_file"].replace("\\", "/"),
                       "card_type": next(c["card_type"] for c in man if c["code"] == code),
                       "manifest_status": next(c["status"] for c in man if c["code"] == code)})
    # 待投支路（C149）：职业／兑换／物品／能力／景群这 34 张没有 3:2 底串，正文来自 数据/卡面主图正文待投.json。
    # 清单以 manifest 为准：正文条数与「MISSING 且非模板正面」必须逐 idx 相等，多写少写都在这里当场挂。
    with open(PENDING, encoding="utf-8") as fh:
        pend = json.load(fh)
    need = ("画风锚点", "全局硬设定", "English tail 风格前缀", "English tail 禁则后缀", "English tail 画幅句")
    sk = pend.get("骨架") or {}
    if any(not (sk.get(k) or "").strip() for k in need):
        raise ValueError("待投真源骨架缺段，应段：%s；现段：%s" % (list(need), list(sk)))
    for k in need:  # 骨架是「逐字复用 80 张同源件」的承诺，被手改过就当场挂，不让它拼进 34 条串
        if sha12(sk[k]) != pend["骨架指纹"][k]:
            raise ValueError("骨架段 %s 与登记指纹不符：%s≠%s" % (k, sha12(sk[k]), pend["骨架指纹"][k]))
    by_idx = {c["idx"]: c for c in man}
    want = pending_indices(man)
    got = sorted(it["idx"] for it in pend["items"])
    if got != want:
        raise ValueError("待投正文与 manifest 待投清单不平：正文 %d 条／应投 %d 条，差集 %s"
                         % (len(got), len(want), sorted(set(got) ^ set(want))))
    for it in pend["items"]:
        pid = "idx%03d" % it["idx"]
        if keep and pid not in keep and str(it["idx"]) not in keep:
            continue
        rec = by_idx[it["idx"]]
        if rec["card_type"] != it["card_type"]:
            raise ValueError("待投正文类型与 manifest 不符：%s %s≠%s"
                             % (pid, it["card_type"], rec["card_type"]))
        prompt = compose_pending(it, pend["骨架"], pend["CLAUSE_SCENE"])
        path = os.path.join(OUT_DIR, "%s-%s.txt" % (pid, it["name"]))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(prompt)
        ledger.append({"id": pid, "name": it["name"], "file": path.replace("\\", "/"),
                       "size": SIZE, "aspect": "3:4 竖幅满幅，含顶部14%与底部22%文字安全区",
                       "len": len(prompt), "base_prompt_file": PENDING.replace("\\", "/"),
                       "card_type": it["card_type"], "anchor": it.get("anchor", ""),
                       "manifest_status": rec["status"]})
    with open(os.path.join(OUT_DIR, "台账.json"), "w", encoding="utf-8") as fh:
        json.dump({"生成者": "build_card_main_prompts.py", "口径": "80 张派生自 3:2 底串、只改画幅与上下安全区；"
                                                                "待投卡按 数据/卡面主图正文待投.json 分段拼装，骨架五段逐字复用",
                   "条数": len(ledger), "画幅": SIZE, "items": ledger}, fh, ensure_ascii=False, indent=1)
    print(json.dumps({"条数": len(ledger), "画幅": SIZE,
                      "字数区间": [min(x["len"] for x in ledger), max(x["len"] for x in ledger)],
                      "OK": sum(1 for x in ledger if x["manifest_status"] == "OK"),
                      "OVERFLOW": sum(1 for x in ledger if x["manifest_status"] == "OVERFLOW"),
                      "实景待投": sum(1 for x in ledger if x["manifest_status"] == "MISSING")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
