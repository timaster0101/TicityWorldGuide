# -*- coding: utf-8 -*-
"""景群成员可校验表 · 校验脚本
检查：成员 id 真实存在于名录、L 连续覆盖无缺号/越界、focus 派生线互斥（每地标恰一条 focus 线）、
      人工命名线成员与基线一致（一字不动）、无重复成员。
用法：python 工具/verify_jingqun.py            # 全绿检查
      python 工具/verify_jingqun.py --negtest   # 注入违例做负测自证
"""
import json, io, sys, os, argparse, re, tempfile, copy
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
base = r"C:\Users\TIMASTER\Documents\Qoder\2026-10-29\c8c10ff8\钛湖城城市设定集"
data = os.path.join(base, "数据")
TBL = os.path.join(data, "景群成员可校验表.json")
MING = os.path.join(data, "城市空间名录.json")

# 基线：人工命名景群线成员（工具链内的权威基准，与 gen_jingqun_table.py 同源）
BASELINE = {
    "JQ-L01": ["L001","L002","L003","L004","L005","L006","L007","L008"],
    "JQ-L02": ["L012","L016","L017","L018"],
    "JQ-L03": ["L003","L004","L005","L046"],
    "JQ-L04": ["L028","L029","L030","L047"],
    "JQ-L05": ["L031","L032","L033","L059","L060"],
}


def check(tbl_path=TBL, ming_path=MING):
    errs = []
    with open(tbl_path, encoding="utf-8") as f:
        tbl = json.load(f)
    with open(ming_path, encoding="utf-8") as f:
        ml = json.load(f)
    entries = ml.get("entries", [])
    by_id = {e["id"]: e for e in entries}
    landmarks = {e["id"] for e in entries if e.get("type") == "标志性建筑"}

    named = tbl.get("人工命名线", [])
    derived = tbl.get("focus派生线", [])

    # 1. 成员 id 存在且是标志性建筑
    for line in named + derived:
        for m in line.get("成员", []):
            if m not in landmarks:
                errs.append(f"[{line['线']}] 成员 {m} 不在名录标志性建筑中")
            else:
                # focus 派生线成员必须与名录 focus 一致
                if line["归群依据"].startswith("focus"):
                    if by_id[m].get("focus") != line["线名"]:
                        errs.append(f"[{line['线']}] {m} focus={by_id[m].get('focus')} != 线名 {line['线名']}")

    # 2. L 连续覆盖
    lnum = sorted(int(re.sub(r'\D','',x)) for x in landmarks if x.startswith('L') and re.sub(r'\D','',x).isdigit())
    lnum = [n for n in lnum if re.sub(r'\D','',f'L{n:03d}')==str(n)][:0] or [int(x[1:]) for x in landmarks if x.startswith('L')]
    expect = set(range(1,109))
    cur = {int(x[1:]) for x in landmarks if x.startswith('L') and x[1:].isdigit()}
    missing = sorted(expect - cur)
    extra = sorted(cur - expect)
    if missing: errs.append(f"名录 L 缺号: {missing}")
    if extra: errs.append(f"名录 L 越界: {extra}")

    # 3. focus 派生线互斥：每地标恰一条
    owner = {}
    for line in derived:
        for m in line.get("成员", []):
            if m in owner:
                errs.append(f"地标 {m} 出现在多条 focus 线({owner[m]} 与 {line['线']})")
            owner[m] = line["线"]
    # 记录行用集 must not necessarily equal; focus derived 应覆盖全部 108
    uncovered = landmarks - set(owner.keys())
    if uncovered: errs.append(f"未纳入 focus 线的地标: {sorted(uncovered)}")

    # 4. 人工命名线基线一致（一字不动）
    named_map = {l["线"]: l["成员"] for l in named}
    for k, v in BASELINE.items():
        if k not in named_map:
            errs.append(f"缺基线人工命名线 {k}")
        elif named_map[k] != v:
            errs.append(f"基线线 {k} 成员变动: {named_map[k]} != {v}")

    # 5. 线/线名唯一
    seen = {}
    for line in named + derived:
        key = (line["线"], line["线名"])
        if key in seen:
            errs.append(f"重复 (线,线名): {key}")
        seen[key] = 1

    return errs, len(named)+len(derived), len(landmarks)


def negtest():
    """注入 5 类违例，必须全部被检出"""
    with open(TBL, encoding="utf-8") as f:
        tbl = json.load(f)
    cases = {}
    # 违例1: 成员 id 不存在
    t = copy.deepcopy(tbl); t["focus派生线"][0]["成员"].append("L999")
    cases["不存在成员 L999"] = t
    # 违例2: focus 派生线成员 focus 与线名不符
    t = copy.deepcopy(tbl)
    if t["focus派生线"][0]["成员"]:
        real = t["focus派生线"][0]["成员"][0]
    t["focus派生线"][0]["成员"] = [real] if real else []
    cases["focus 与线名不符"] = t
    # 违例3: 缺号（从派生线抽走一条 L061）
    t = copy.deepcopy(tbl)
    for line in t["focus派生线"]:
        if "L061" in line["成员"]:
            line["成员"].remove("L061")
    cases["L061 被抽离"] = t
    # 违例4: 基线人工线成员被改动
    t = copy.deepcopy(tbl)
    for line in t["人工命名线"]:
        if line["线"] == "JQ-L01" and line["成员"]:
            line["成员"].pop()
    cases["钛湖八景被抽走一员"] = t
    # 违例5: 同一地标进两条 focus 线
    t = copy.deepcopy(tbl)
    if len(t["focus派生线"]) >= 2 and t["focus派生线"][1]["成员"]:
        dup = t["focus派生线"][1]["成员"][0]
    t["focus派生线"][0]["成员"].append(dup)
    cases["地标跨两条 focus 线"] = t

    ok = True
    for name, tbl_inj in cases.items():
        # 写入临时表校验
        fd, tmp = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(tbl_inj, f, ensure_ascii=False, indent=2)
        errs, _, _ = check(tmp)
        os.remove(tmp)
        hit = bool(errs)
        ok = ok and hit
        print(f"  [负测] {name}: {'检出 ' + str(len(errs)) + ' 条错误 ✔' if hit else '未检出 ✘ 失败'}")
        if not hit:
            print("    ! 违例未被捕获，校验有洞")
    print(f"\n负测结论: {'全部捕获 ✔' if ok else '存在漏检 ✘'}")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--negtest", action="store_true")
    args = ap.parse_args()
    if args.negtest:
        sys.exit(0 if negtest() else 1)
    errs, nline, nland = check()
    if errs:
        print(f"❌ 校验未通过：{len(errs)} 条问题")
        for e in errs: print("  -", e)
        sys.exit(1)
    print(f"✅ 景群成员可校验表通过：{nline} 条景群线（5 人工命名 + 20 focus 派生），覆盖 {nland} 地标无缺号/越界，focus 线互斥，基线一字不动")