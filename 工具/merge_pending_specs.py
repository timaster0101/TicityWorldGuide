# -*- coding: utf-8 -*-
"""合并三个分片代理的待投正文，并逐字段刷新 数据/卡面主图正文待投.json。

三个分片件在仓外 `_scratch_cardref/pending_specs_shard{A,B,C}.json`（职业 12＋职业8/景群3＋产品决策11）。
本脚本只做四件事：① 校验条目形态与 manifest 待投清单严格相等；② 从 80 张同源件的 **3:2 原文**按段名行首
重取骨架（画风锚点／全局硬设定／English tail 风格前缀／English tail 禁则后缀）并核对全库唯一变体；
③ 把分片的 tail_extra 规范化（画幅句由真源统一注入，逐条不许自带画幅措辞）；④ 整份重写真源并打印读数。

上一版骨架是从派生后的 3:4 txt 里用子串 find 取的，结果把 CLAUSE 里那句「下文【全局硬设定】仍按 3:2…」
当成了段首（1753 字 vs 真段 999 字），tail「基座」也误取单张卡的整串（含该卡主体）。本脚本改成从
数据/开图提示词/ 原文按 `^【段名】` 取段，并对前缀/后缀做全 80 条的逐字一致性断言。
"""
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "工具"))
# 待投名单口径不许有第二份：与生成器共用 pending_indices()（结构判，不看投放状态）。
from build_card_main_prompts import pending_indices as _pending_indices
SCRATCH = os.path.join(ROOT, os.pardir, "_scratch_cardref")
SHARDS = ["pending_specs_shardA.json", "pending_specs_shardB.json", "pending_specs_shardC.json"]
PENDING = os.path.join("数据", "卡面主图正文待投.json")
MANIFEST = os.path.join("数据", "视觉控制资产", "卡牌", "768x1024", "manifest.json")
LEDGER = os.path.join("数据", "卡面主图提示词3x4", "台账.json")
SECTIONS = ["画面定位", "取景指令", "外观辨识", "人群与烟火气", "锁定与禁则"]
# 分片代理各写各的画幅措辞会造成 34 条口径不齐；这里剥掉自带画幅句，统一由 ASPECT_LINE 注入。
ASPECT_RE = re.compile(r"\b(?:3:2|2:3|3:4)\b[^,]*(?:aspect|横幅|竖幅)[^,]*,?\s*", re.I)
ASPECT_LINE = (
    "3:4 portrait 768x1024, full-bleed inside the card with no crop; any 3:2 banner wording elsewhere "
    "in this prompt is superseded by this clause; main subject and key figures fully inside the frame; "
    "the top 14 percent of the frame is sky, upper wall or even dark tone and the bottom 22 percent is "
    "ground, shadow and solid mass, both reserved for the page's overlaid text,"
)


def sha12(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def section(text, name):
    m = re.search(r"^【%s】" % name, text, re.M)
    if not m:
        raise ValueError("缺段 " + name)
    nxt = re.search(r"^【[^】]+】|^English tail:", text[m.end():], re.M)
    end = m.end() + (nxt.start() if nxt else len(text[m.end():]))
    return text[m.start():end].strip()


def tail(text):
    m = re.search(r"^English tail:", text, re.M)
    if not m:
        raise ValueError("缺 English tail")
    return text[m.start():].strip()


def common_prefix(strings):
    """逐串对齐求最长公共前缀，切点落在空格边界。
    注意 rfind 会命中上一轮留下的尾部空格，不先 rstrip 就是原地不动的死循环（本机踩过，跑满 2 分钟才被停）。"""
    p = strings[0]
    for s in strings[1:]:
        while not s.startswith(p):
            p = p.rstrip(" ")
            cut = p.rfind(" ")
            if cut < 0:
                raise ValueError("无公共前缀")
            p = p[: cut + 1]
    return p


def common_suffix(strings):
    """求最长公共后缀，切点同样落在空格边界，并防原地不动。"""
    s = strings[0]
    for x in strings[1:]:
        while not x.endswith(s):
            s = s.lstrip(" ")
            cut = s.find(" ")
            if cut < 0:
                raise ValueError("无公共后缀")
            s = s[cut + 1:]
    return s
def trim_to_clause(p, strings):
    """公共前缀常停在半个子句（80 条在此分叉为 painted landmark tower…／painted high-angle district…）。
    截到最后一个逗号，得到可独立成句的风格段，再回验全部 80 条仍以它开头。"""
    p = p.rstrip()
    cut = p.rfind(",")
    if cut < 0:
        raise ValueError("公共前缀里没有逗号，无法截到子句边界")
    p = p[: cut + 1]
    bad = [i for i, s in enumerate(strings) if not s.startswith(p)]
    if bad:
        raise ValueError("截子句后 %d 条 tail 不再以该前缀开头" % len(bad))
    return p


def read_pending_codes():
    with open(os.path.join(ROOT, MANIFEST), encoding="utf-8") as fh:
        man = json.load(fh)["cards"]
    # 用生成器的结构判。此前这里是 `status == "MISSING"`，34 张补投回填转 OK 后归零，
    # 合并器会误判「分片件多写」而拒绝重跑——正是这次要防的第二个口径。
    want = _pending_indices(man)
    by_idx = {c["idx"]: c for c in man}
    return want, by_idx


def load_items():
    items, from_file = {}, {}
    for name in SHARDS:
        path = os.path.join(SCRATCH, name)
        if not os.path.isfile(path):
            raise SystemExit("分片件缺失：%s（本轮不合并）" % path.replace("\\", "/"))
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        for it in (doc["items"] if isinstance(doc, dict) else doc):
            if it["idx"] in items:
                raise SystemExit("idx %s 在两个分片里重复" % it["idx"])
            items[it["idx"]] = it
            from_file[it["idx"]] = name
    return items, from_file


def check_item(it, by_idx, name):
    problems = []
    rec = by_idx[it["idx"]]
    if rec["card_type"] != it["card_type"]:
        problems.append("card_type %s≠manifest %s" % (it["card_type"], rec["card_type"]))
    if rec["code"]:
        problems.append("manifest code 非空（%s），本支路只接空 code 卡" % rec["code"])
    s = it.get("sections") or {}
    for field in SECTIONS:
        if not (s.get(field) or "").strip():
            problems.append("缺分段 %s" % field)
    if not (it.get("tail_extra") or "").strip():
        problems.append("缺 tail_extra")
    if not re.search(r"\(\s*-?\d+\.\d+\s*,\s*-?\d+\.\d+\s*\)", s.get("画面定位", "")):
        problems.append("画面定位无坐标读数")
    for bad, why in (("□", "含 □ 占位"),):
        if bad in json.dumps(s, ensure_ascii=False):
            problems.append(why)
    if problems:
        raise SystemExit("idx %s（%s，%s）：%s" % (it["idx"], it["name"], name, "；".join(problems)))


def main():
    os.chdir(ROOT)
    want, by_idx = read_pending_codes()
    items, from_file = load_items()
    got = sorted(items)
    if got != want:
        raise SystemExit("待投清单与 manifest 不平：分片 %d 条／应投 %d 条，差集 %s"
                         % (len(got), len(want), sorted(set(got) ^ set(want))))
    for idx in want:
        check_item(items[idx], by_idx, from_file[idx])

    with open(os.path.join(ROOT, LEDGER), encoding="utf-8") as fh:
        led = json.load(fh)
    # 台账现含 114 行：派生 80 行的 base_prompt_file 是 3:2 原文（骨架从这里取），
    # 待投 34 行的 base_prompt_file 指向本文件自己，切不出【画风锚点】，必须排除。
    derived = [it for it in led["items"] if it.get("manifest_status") in ("OK", "OVERFLOW")]
    if len(derived) != 80:
        raise SystemExit("台账派生行数不是 80（现 %d），骨架取数范围已变" % len(derived))
    texts = []
    for it in derived:
        with open(it["base_prompt_file"], encoding="utf-8") as fh:
            texts.append(fh.read())
    anchor = {section(t, "画风锚点") for t in texts}
    hard = {section(t, "全局硬设定") for t in texts}
    tails = [tail(t) for t in texts]
    if len(anchor) != 1 or len(hard) != 1:
        raise SystemExit("骨架中文段非全库唯一（画风锚点 %d／全局硬设定 %d 变体）" % (len(anchor), len(hard)))
    sk_anchor, sk_hard = list(anchor)[0], list(hard)[0]
    raw_pre = common_prefix(tails)
    pre = trim_to_clause(raw_pre, tails)
    suf = common_suffix(tails)
    for name, val in (("画风锚点", sk_anchor), ("全局硬设定", sk_hard),
                      ("English tail 风格前缀", pre), ("English tail 禁则后缀", suf)):
        print("%s %d 字／sha12 %s" % (name, len(val), sha12(val)))
    print("风格前缀截子句：%d→%d 字，尾部 %r" % (len(raw_pre), len(pre), pre[-48:]))
    if len(pre) + len(suf) > len(min(tails, key=len)):
        raise SystemExit("前缀与后缀在最短串上重叠，骨架不可分")
    merged = []
    stripped = 0
    for idx in want:
        it = items[idx]
        te = it["tail_extra"].strip()
        new_te = ASPECT_RE.sub("", te)
        if new_te != te:
            stripped += 1
        row = {"idx": idx, "name": it["name"], "card_type": it["card_type"],
               "anchor": it.get("anchor", ""), "方向依据": it.get("方向依据", ""),
               "sections": {k: it["sections"][k].strip() for k in SECTIONS},
               "tail_extra": new_te.strip().rstrip(",; ") + ",",
               "分片": from_file[idx]}
        if "方向备选" in it:
            row["方向备选"] = it["方向备选"]
            row["选定方向"] = it.get("选定方向", "")
        merged.append(row)

    with open(PENDING, encoding="utf-8") as fh:
        doc = json.load(fh)
    # 头部「生成者／口径」两条写的是「骨架三段」，那是首轮误取（把 CLAUSE 污染段与单张卡整串当骨架）时的说法，
    # 真骨架是五段；在合并时一并订正，免得重跑本脚本又把旧口径抄回来。
    n_fixed = 0
    for k in ("生成者", "口径"):
        if "骨架三段" in doc.get(k, ""):
            doc[k] = doc[k].replace("骨架三段", "骨架五段")
            n_fixed += 1
    print("头部字段骨架段数订正 %d 条" % n_fixed)
    doc["骨架"] = {"画风锚点": sk_anchor, "全局硬设定": sk_hard,
                   "English tail 风格前缀": pre, "English tail 禁则后缀": suf,
                   "English tail 画幅句": ASPECT_LINE.strip()}
    doc["骨架出处"] = ("骨架五段一律取自 80 张同源件的 3:2 原文（数据/开图提示词/，经 数据/卡面主图提示词3x4/台账.json "
                       "的 base_prompt_file 列出），取段用 ^【段名】 行首正则而非子串 find；"
                       "English tail 取全 80 条的最长公共前缀与最长公共后缀，主体句与机位几何句属逐卡差异段、不进骨架。")
    doc["骨架指纹"] = {k: sha12(v) for k, v in doc["骨架"].items()}
    doc["骨架字数"] = {k: len(v) for k, v in doc["骨架"].items()}
    doc["条数"] = len(merged)
    doc["items"] = merged
    doc["合并读数"] = {"分片件": SHARDS, "条目": len(merged),
                       "带方向备选条数": sum(1 for r in merged if "方向备选" in r),
                       "剥掉自带画幅措辞条数": stripped,
                       "坐标行全覆盖": sum(1 for r in merged
                                          if re.search(r"\(\s*-?\d+\.\d+\s*,\s*-?\d+\.\d+\s*\)", r["sections"]["画面定位"]))}
    with open(PENDING, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    print("已写 %s：items %d／带方向备选 %d／剥画幅 %d"
          % (PENDING, len(merged), doc["合并读数"]["带方向备选条数"], stripped))
    print("指纹", json.dumps(doc["骨架指纹"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
