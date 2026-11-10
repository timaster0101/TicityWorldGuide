# -*- coding: utf-8 -*-
"""第9批（L061—L108）待开图清单重建：判定依据一律从本仓真源逐字切片取，不凭记忆手打。

取法：每个字段都是「源文件里的一段连续子串」，切片后立刻回读源文本做 in 断言并记 sha256，
       因此产出的 manifest 里任何一句锁定句/禁则/远景点名/日面半角都与 数据/开图提示词/L0xx-*.txt 逐字一致。
"""
import hashlib
import io
import json
import os
import re
import glob

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(OUT_DIR, "..", ".."))
PROMPT_DIR = os.path.join(ROOT, "数据", "开图提示词")

BATCH = ["L%03d" % i for i in range(61, 109)]
SECTION_RE = re.compile(r"^【(.+?)】(.*)$", re.M)
TAIL_MARK = "English tail: "
SUN_IN_RE = re.compile(
    r"the sun sits inside this frame as the canon section states \("
    r"(\d+) degrees to the (left|right) of the camera axis, "
    r"inside the (\d+) degree half-angle\)")
SUN_OUT_RE = re.compile(
    r"the sun is (\d+) degrees to the (left|right) of the camera axis and "
    r"outside this frame's (\d+) degree half-angle")


def sha256(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def kv_line(src, key):
    m = re.search("^-\\s*%s：(.*)$" % re.escape(key), src, re.M)
    if not m:
        raise KeyError(key)
    return m.group(1)


def slice_verify(src, seg, label):
    """切片后逐字回证：seg 必须原样出现在源文本里，否则直接抛错（不许静默改写）。"""
    if seg not in src:
        raise AssertionError("段与真源不一致：%s" % label)
    return seg


def parse(path):
    with io.open(path, encoding="utf-8") as fp:
        src = fp.read()
    name = os.path.basename(path)[:-4]
    loc_id = name.split("-")[0]
    body_start = src.index("## 提示词正文")
    head = src[:body_start]
    body = src[body_start:]
    tail_idx = body.index(TAIL_MARK)
    cn = body[:tail_idx]
    en = body[tail_idx + len(TAIL_MARK):].strip()

    sections = {}
    for key, val in SECTION_RE.findall(cn):
        sections[key] = val.strip()

    sun = SUN_IN_RE.search(en) or SUN_OUT_RE.search(en)
    if not sun:
        raise AssertionError("%s 的 tail 里没有日面可纳性断言" % loc_id)
    sun_inside = "inside" if SUN_IN_RE.search(en) else "outside"

    rec = {
        "id": loc_id,
        "prompt_file": "数据/开图提示词/%s.txt" % name,
        "prompt_sha256_file": sha256(src),
        "对应关系": {
            "地点ID": slice_verify(head, kv_line(head, "地点ID"), loc_id + "/地点ID"),
            "名称": kv_line(head, "名称"),
            "类型": kv_line(head, "类型"),
            "所属": kv_line(head, "所属"),
            "建议尺寸": kv_line(head, "建议尺寸"),
            "拍摄朝向": kv_line(head, "拍摄朝向"),
            "光照判定": slice_verify(head, kv_line(head, "光照判定"), loc_id + "/光照判定"),
            "名录硬参数": slice_verify(head, kv_line(head, "名录硬参数"), loc_id + "/名录硬参数"),
            "状态": kv_line(head, "状态"),
            "prompt_sha256": kv_line(head, "prompt_sha256"),
            "image_prompt_sha256": kv_line(head, "image_prompt_sha256"),
        },
        "画风锚点": sections["画风锚点"],
        "取景指令_远景": sections["取景指令"],
        "外观辨识": sections["外观辨识"],
        "人群与烟火气": sections["人群与烟火气"],
        "锁定与禁则": slice_verify(cn, sections["锁定与禁则"], loc_id + "/锁定与禁则"),
        "全局硬设定": sections["全局硬设定"],
        "tail_日面断言": slice_verify(en, sun.group(0), loc_id + "/tail日面"),
        "tail_日面_inside": sun_inside,
        "tail_日面_半角": int(sun.group(3)),
        "tail_日面_相对角": int(sun.group(1)),
        "tail_日面_左右": sun.group(2),
        "tail_远景塔约束": slice_verify(
            en,
            en[en.index("the far view must contain only"):
               en.index("; do not trace a real city")],
            loc_id + "/tail远景"),
        "English_tail": en,
    }
    rec["段一致性"] = {k: sha256(v) for k, v in [
        ("画风锚点", rec["画风锚点"]), ("取景指令", rec["取景指令_远景"]),
        ("锁定与禁则", rec["锁定与禁则"]), ("日面断言", rec["tail_日面断言"]),
        ("远景塔约束", rec["tail_远景塔约束"])]}
    return rec


def main():
    rows, checks = [], []
    for loc_id in BATCH:
        hits = glob.glob(os.path.join(PROMPT_DIR, "%s-*.txt" % loc_id))
        if len(hits) != 1:
            raise AssertionError("%s 真源文件不唯一：%r" % (loc_id, hits))
        rec = parse(hits[0])
        with io.open(hits[0], encoding="utf-8") as fh:
            src = fh.read()
        ok = all(seg in src for seg in [
            rec["画风锚点"], rec["取景指令_远景"], rec["锁定与禁则"],
            rec["tail_日面断言"], rec["tail_远景塔约束"],
            rec["对应关系"]["名录硬参数"], rec["对应关系"]["光照判定"]])
        checks.append({"id": loc_id, "逐段回真源": bool(ok),
                       "段数": 7, "不符段数": 0 if ok else 7})
        rows.append(rec)

    with io.open(os.path.join(OUT_DIR, "pending_manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"batch": "第9批 L061—L108", "rows": rows}, f,
                  ensure_ascii=False, indent=1)
    with io.open(os.path.join(OUT_DIR, "src_consistency.json"), "w", encoding="utf-8") as f:
        json.dump(checks, f, ensure_ascii=False, indent=1)

    bad = [c for c in checks if not c["逐段回真源"]]
    print("真源重建：行 %d｜逐段回真源通过 %d｜不符 %d" % (
        len(rows), len(checks) - len(bad), len(bad)))
    print("日面分档：" + "／".join(sorted({
        "%s(%d)" % (r["tail_日面_inside"], r["tail_日面_半角"]) for r in rows})))
    if bad:
        raise SystemExit("存在与真源不一致的段，清单不可用：%s" % [b["id"] for b in bad])


if __name__ == "__main__":
    main()
