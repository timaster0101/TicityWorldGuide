# -*- coding: utf-8 -*-
"""二创稿校验器：拿正典对一遍你自己写的稿子。

用法（在仓库根执行）：
    python -X utf8 工具/validate_derivative.py 我的故事.md
    python -X utf8 工具/validate_derivative.py 稿子目录 --glob "*.md" --strict
    Get-Content 稿.md -Raw | python -X utf8 工具/validate_derivative.py -

退出码：0 无违例；1 有违例（--strict 时提示级也算）；2 用法或读取失败。

判据（每条都能举证，不做风格评价）：
    UNKNOWN_ID      文本里出现名录中不存在的 D/F/L/R/S 编号
    TYPE_MISMATCH   「居民区 L069」这类把编号安到错误类型上的写法
    NAME_MISMATCH   编号后面跟的名称与名录不一致（「D01 东湖金融片区」）
    SCALE_CONFLICT  同句写了编号或名称，层数/高度却与名录不符
    GLOBAL_NUMBER   全市人口、区域面积与正典分母不一致
    FICTION_BREAK   把虚构城市说成真实存在
    UNKNOWN_RULING  引用了不存在的裁定编号（C1–C157 之外）
    RULING_OVERRIDE 主张推翻/撤销既有裁定（须走裁定流程，不能在二创里单方面废止）

只读：本脚本不改任何文件。
"""
import argparse
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANON_REL = os.path.join("数据", "城市空间名录.json")
RULING_REL = os.path.join("数据", "设定裁定记录.json")

ID_RE = re.compile(r"(?<![A-Za-z0-9])([SDRFL])(\d{2,3})(?!\d)")
TYPE_WORDS = ("城市片区", "功能区", "标志性建筑", "居民区", "产业小镇", "特色村落")
# 「D01 东湖金融片区」：编号 + 紧邻的、以地名后缀结尾的中文串
NAME_AFTER_ID_RE = re.compile(
    r"([SDRFL]\d{2,3})\s*[《（(]?\s*"
    r"([\u4e00-\u9fa5]{2,14}(?:片区|功能区|中心|馆|院|园|镇|村|广场|大厦|学校|医院|车站|塔|寺|码头))"
)
TYPE_BEFORE_ID_RE = re.compile(
    r"(" + "|".join(TYPE_WORDS) + r")\s*[《（(]?\s*([SDRFL]\d{2,3})"
)
FLOORS_RE = re.compile(r"(\d{1,3})\s*层")
HEIGHT_RE = re.compile(r"(\d{1,4}(?:\.\d+)?)\s*米")
POP_RE = re.compile(r"(?:全市|总人口|区域|城市)\D{0,12}?人口\D{0,6}?(\d[\d,，.]*)\s*万")
AREA_RE = re.compile(r"(?:区域|全市|城市|总)面积\D{0,6}?(\d[\d,，.]*)\s*(?:平方公里|平方千米|km²|KM²)")
FICTION_WORDS = ("真实城市", "确有此地", "真实存在", "不是虚构", "并非虚构", "真实地名")
OVERRIDE_WORDS = ("推翻", "废止", "撤销", "不再适用", "应删除", "作废")
RULING_RE = re.compile(r"(?<![A-Za-z0-9])C(\d{1,3})(?!\d)")


def _num(s):
    return float(s.replace(",", "").replace("，", "").replace(" ", ""))


def load_canon(root=ROOT):
    """返回 (entries_by_id, rulings, globals)。entries 里带 floors/height_m（有则带）。"""
    with io.open(os.path.join(root, CANON_REL), encoding="utf-8") as fp:
        doc = json.load(fp)
    entries = {}
    for e in doc.get("entries") or []:
        entries[e["id"]] = e
    rulings = set()
    rpath = os.path.join(root, RULING_REL)
    if os.path.isfile(rpath):
        with io.open(rpath, encoding="utf-8") as fp:
            rows = json.load(fp)
        rows = rows if isinstance(rows, list) else rows.get("裁定") or []
        for r in rows:
            num = str(r.get("编号") or "").strip()
            if num.startswith("C"):
                rulings.add(num)
    pop = doc.get("population") or {}
    globals_ = {
        "region_area_km2": doc.get("region_area_km2"),
        "regional_total": pop.get("regional_total"),
        "city_core": pop.get("city_core"),
        "urban_radius_km": doc.get("urban_radius_km"),
    }
    return entries, rulings, globals_


def _line_no(text, pos):
    return text.count("\n", 0, pos) + 1


def _finding(code, level, line, excerpt, message, hint=""):
    return {"code": code, "level": level, "line": line,
            "excerpt": excerpt.strip()[:80], "message": message, "hint": hint}


def check_text(text, entries, rulings, globals_=None):
    """对一段文本跑全部判据，返回违例列表（按行号排序）。"""
    out = []
    globals_ = globals_ or {}

    # 1) 编号存在性 + 名称一致性
    for m in ID_RE.finditer(text):
        eid = m.group(1) + m.group(2)
        line = _line_no(text, m.start())
        if eid not in entries:
            out.append(_finding("UNKNOWN_ID", "error", line, _ctx(text, m.start()),
                                "「%s」不在城市空间名录里（312 个编号之外）" % eid,
                                "新增地点请写成无编号的小地点，或走真源流程升版本"))
    for m in NAME_AFTER_ID_RE.finditer(text):
        eid, name = m.group(1), m.group(2)
        if eid not in entries:
            continue
        canon = entries[eid]["name"]
        if name == canon or canon.startswith(name) or name.startswith(canon):
            continue
        if name in TYPE_WORDS:
            # 「D01 片区」这种泛称不算错
            continue
        if not any(name.endswith(s) for s in ("片区", "功能区", "小镇", "村落", "居民区")):
            # 只在写成「行政区名」时才判；「D17食品配送支持场馆」这类描述性写法不判
            continue
        if not any(canon.endswith(s) for s in ("片区", "功能区", "小镇", "村落", "居民区")):
            continue
        out.append(_finding("NAME_MISMATCH", "error", _line_no(text, m.start()), _ctx(text, m.start()),
                            "「%s」的名称是「%s」，不是「%s」" % (eid, canon, name),
                            "名称属硬正典，引用时照抄"))

    # 2) 类型错配
    for m in TYPE_BEFORE_ID_RE.finditer(text):
        written, eid = m.group(1), m.group(2)
        if eid not in entries:
            continue
        canon_type = entries[eid].get("type")
        if written != canon_type:
            out.append(_finding("TYPE_MISMATCH", "error", _line_no(text, m.start()), _ctx(text, m.start()),
                                "「%s」的类型是「%s」，不是「%s」" % (eid, canon_type, written),
                                "编号前缀即类型：S 聚落、D 片区、F 功能区、L 地标、R 居民区"))

    # 3) 量级矛盾：同句出现编号或名称，且写了层数/高度
    for m in FLOORS_RE.finditer(text):
        written = int(m.group(1))
        target = _locate_nearest(text, m.start(), entries)
        if not target:
            continue
        floors = target.get("floors")
        if not floors or int(floors) == written:
            continue
        out.append(_finding("SCALE_CONFLICT", "error", _line_no(text, m.start()), _ctx(text, m.start()),
                            "%s 在正典里是 %s 层，文中写 %d 层" % (target["id"], floors, written),
                            "量级读 `数据/城市空间名录.json` 的 floors/height_m"))
    for m in HEIGHT_RE.finditer(text):
        written = _num(m.group(1))
        target = _locate_nearest(text, m.start(), entries)
        if not target:
            continue
        hm = target.get("height_m")
        if not hm:
            continue
        if abs(written - float(hm)) <= max(3.0, float(hm) * 0.15):
            continue
        out.append(_finding("SCALE_CONFLICT", "error", _line_no(text, m.start()), _ctx(text, m.start()),
                            "%s 的高度是 %s 米，文中写 %s 米" % (target["id"], hm, m.group(1)),
                            "允许 ±15% 的叙述弹性，超出即算矛盾"))

    # 4) 全局分母
    total = globals_.get("regional_total")
    if total:
        for m in POP_RE.finditer(text):
            written = _num(m.group(1)) * 10000
            if abs(written - float(total)) / float(total) <= 0.02:
                continue
            core = globals_.get("city_core")
            if core and abs(written - float(core)) / float(core) <= 0.02:
                continue
            out.append(_finding("GLOBAL_NUMBER", "error", _line_no(text, m.start()), _ctx(text, m.start()),
                                "区域总人口是 %s，文中写约 %s" % (_fmt(total), _fmt(written)),
                                "全市数要么写 3,574,200，要么写中心城 3,200,000"))
    area = globals_.get("region_area_km2")
    if area:
        for m in AREA_RE.finditer(text):
            written = _num(m.group(1))
            if abs(written - float(area)) / float(area) <= 0.02:
                continue
            out.append(_finding("GLOBAL_NUMBER", "error", _line_no(text, m.start()), _ctx(text, m.start()),
                                "区域面积是 %s km²，文中写 %s" % (area, m.group(1)),
                                "面积属硬正典，不可改"))

    # 5) 虚构声明
    for w in FICTION_WORDS:
        for m in re.finditer(re.escape(w), text):
            out.append(_finding("FICTION_BREAK", "error", _line_no(text, m.start()), _ctx(text, m.start()),
                                "「%s」把虚构城市说成真实存在" % w,
                                "钛湖城完全虚构（fictional=true），改写成「设定中的城市」"))

    # 6) 裁定引用
    for m in RULING_RE.finditer(text):
        num = "C" + m.group(1)
        if rulings and num not in rulings:
            out.append(_finding("UNKNOWN_RULING", "warn", _line_no(text, m.start()), _ctx(text, m.start()),
                                "引用了一次不存在的裁定「%s」" % num,
                                "现有裁定是 C1–C%s" % _max_ruling(rulings)))
    for m in RULING_RE.finditer(text):
        num = "C" + m.group(1)
        if rulings and num not in rulings:
            continue
        seg = _sentence(text, m.start())
        for w in OVERRIDE_WORDS:
            if w in seg:
                out.append(_finding("RULING_OVERRIDE", "error", _line_no(text, m.start()), _ctx(text, m.start()),
                                    "在二创里主张「%s」裁定 %s" % (w, num),
                                    "既有裁定不接受在二创中废止；要改请走裁定流程并升版本"))
                break

    out.sort(key=lambda r: (r["line"], r["code"]))
    return out


def _ctx(text, pos, width=28):
    """摘录用整句：跨行上下文读起来串味，也不利于定位。"""
    sent = _sentence(text, pos).replace("\n", " ").strip()
    return sent or text[pos:pos + width]


def _sentence(text, pos):
    start = max(text.rfind("。", 0, pos), text.rfind("\n", 0, pos), text.rfind("；", 0, pos),
                text.rfind("!", 0, pos), text.rfind("？", 0, pos), 0)
    ends = [i for i in (text.find("。", pos), text.find("\n", pos), text.find("；", pos)) if i >= 0]
    end = min(ends) if ends else len(text)
    return text[start:end]


def _locate_nearest(text, pos, entries):
    """取数字前面最近的那一个地点（编号优先，其次名称）。

    量级判据必须这样做：一句里常并列多个地点（「L019 6层、32米，L020 4层、24米」），
    按句首第一个取会把后者的数字算到前者头上，制造假红。
    """
    start = max(text.rfind("。", 0, pos), text.rfind("\n", 0, pos), text.rfind("；", 0, pos),
                text.rfind("!", 0, pos), text.rfind("？", 0, pos), 0)
    prefix = text[start:pos]
    last = None
    for m in ID_RE.finditer(prefix):
        eid = m.group(1) + m.group(2)
        if eid in entries:
            last = (m.start(), entries[eid])
    for eid, e in entries.items():
        nm = e.get("name")
        if not nm:
            continue
        i = prefix.rfind(nm)
        if i >= 0 and (last is None or i > last[0]):
            last = (i, e)
    return last[1] if last else None


def _fmt(n):
    return "{:,}".format(int(round(float(n))))


def _max_ruling(rulings):
    nums = sorted(int(r[1:]) for r in rulings if r[1:].isdigit())
    return nums[-1] if nums else 0


def collect_files(target, glob_pat="*.md"):
    if os.path.isfile(target):
        return [target]
    out = []
    for dirpath, _dirs, files in os.walk(target):
        for f in sorted(files):
            if glob_pat and not f.lower().endswith(glob_pat.lstrip("*").lower()):
                continue
            out.append(os.path.join(dirpath, f))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="用正典校验你的二创稿")
    ap.add_argument("target", help="稿子文件、目录，或 - 表示标准输入")
    ap.add_argument("--glob", default="*.md", help="目录模式下的扩展名过滤（默认 *.md）")
    ap.add_argument("--strict", action="store_true", help="提示级也算失败")
    ap.add_argument("--json", action="store_true", help="输出机读 JSON")
    ap.add_argument("--quiet", action="store_true", help="只输出汇总")
    args = ap.parse_args(argv)

    try:
        entries, rulings, globals_ = load_canon(ROOT)
    except Exception as exc:  # noqa: BLE001 - 读不到正典就是用法错误
        print("读不到正典：%s" % exc, file=sys.stderr)
        return 2
    if not entries:
        print("正典为空，无法校验", file=sys.stderr)
        return 2

    if args.target == "-":
        text = sys.stdin.read()
        docs = [("<stdin>", text)]
    else:
        files = collect_files(args.target, args.glob)
        if not files:
            print("没找到可校验的文件：%s" % args.target, file=sys.stderr)
            return 2
        docs = []
        for p in files:
            try:
                with io.open(p, encoding="utf-8") as fp:
                    docs.append((p, fp.read()))
            except UnicodeDecodeError:
                print("跳过非 UTF-8 文件：%s" % p, file=sys.stderr)

    report, total_err, total_warn = [], 0, 0
    for path, text in docs:
        found = check_text(text, entries, rulings, globals_)
        errs = [f for f in found if f["level"] == "error"]
        warns = [f for f in found if f["level"] == "warn"]
        total_err += len(errs)
        total_warn += len(warns)
        report.append({"file": path, "errors": len(errs), "warnings": len(warns), "findings": found})

    if args.json:
        print(json.dumps({"canon_entries": len(entries),
                          "rulings": len(rulings),
                          "errors": total_err, "warnings": total_warn,
                          "files": report}, ensure_ascii=False, indent=1))
    else:
        for r in report:
            if not r["findings"]:
                continue
            print("\n== %s ==" % r["file"])
            for f in r["findings"]:
                if args.quiet and f["level"] == "warn":
                    continue
                print("  %-15s 第%d行  %s" % (f["code"], f["line"], f["message"]))
                print("      ...%s..." % f["excerpt"])
                if f["hint"]:
                    print("      → %s" % f["hint"])
        print("\n正典：%d 个地点、%d 条裁定" % (len(entries), len(rulings)))
        print("结果：%d 个错误、%d 个提示（%d 份文件）" % (total_err, total_warn, len(report)))
        print("判定：%s" % ("失败" if total_err or (args.strict and total_warn) else "通过"))

    failed = total_err > 0 or (args.strict and total_warn > 0)
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001 - 老解释器没有 reconfigure
        pass
    sys.exit(main())
