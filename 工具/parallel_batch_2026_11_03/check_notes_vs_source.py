# -*- coding: utf-8 -*-
"""逐小节把 visual_notes.md 的读数与真源核对：
sha12/字节/尺寸对 measure.json；facing/sunrel/锁定层数米对 数据/开图提示词 与 数据/开图清单.json；
日面断言引文逐字回真源 tail；结论行分类计数。任一不符即退出码 1。
run() 以笔记正文当入参，是为了 negtest_batch9_notes.py 能把篡改后的正文喂进来，验这条闸门判得红。"""
import io, json, os, re, sys

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
NOTES = os.path.join(BASE, "工具", "parallel_batch_2026_11_03", "visual_notes.md")
MEASURE = os.path.join(BASE, "工具", "parallel_batch_2026_11_03", "measure.json")
PROMPT_DIR = os.path.join(BASE, "数据", "开图提示词")
MANIFEST = os.path.join(BASE, "数据", "开图清单.json")

HEAD = re.compile(r"^## (L\d{3}) (\S+?)（(\d+)x(\d+)，facing([\d.]+) sunrel([+-])([\d.]+)，锁定(\d+)层(\d+)米")
SHA = re.compile(r"/ ([0-9a-f]{12})；")
BYTES = re.compile(r"✓ / (\d+) /")
SUN_OUT = re.compile(r"「the sun is (\d+) degrees to the (left|right) of the camera axis and outside this frame's (\d+) degree half-angle」")
SUN_IN = re.compile(r"「the sun sits inside this frame as the canon section states \((\d+) degrees to the (left|right) of the camera axis, inside the (\d+) degree half-angle\)」")


def run(notes_text, measure, manifest, src):
    bad, rows, concl, checks = [], [], {}, 0
    for sec in re.split(r"(?m)^(?=## L)", notes_text):
        if not sec.startswith("## L"):
            continue
        m = HEAD.match(sec)
        if not m:
            bad.append((sec.split("\n")[0][:60], "HEADER 不可解析"))
            continue
        sid, name, w, h, facing, sgn, sunrel, floors, meters = m.groups()
        mr, mf, ps = measure.get(sid), manifest.get(sid), src.get(sid, "")
        if not (mr and mf and ps):
            bad.append((sid, "缺 measure/清单/真源"))
            continue
        checks += 1

        def chk(cond, msg, _sid=sid):
            nonlocal checks
            checks += 1
            if not cond:
                bad.append((_sid, msg))

        chk(mr["dims"] == "%sx%s" % (w, h), "尺寸与测得不符 笔记%s 测得%s" % (w + "x" + h, mr["dims"]))
        chk(mf["size"] == "%sx%s" % (w, h), "尺寸与清单不符 笔记%s 清单%s" % (w + "x" + h, mf["size"]))
        g = SHA.search(sec)
        chk(g and g.group(1) == mr["sha256_12"], "sha12 不符 笔记%s 磁盘%s" % (g and g.group(1), mr["sha256_12"]))
        b = BYTES.search(sec)
        chk(b and int(b.group(1)) == mr["bytes"], "字节不符 笔记%s 磁盘%s" % (b and b.group(1), mr["bytes"]))
        chk(abs(float(facing) - mf["camera_facing_deg"]) < 0.01, "facing 不符 笔记%s 清单%s" % (facing, mf["camera_facing_deg"]))
        chk(abs(float(sgn + sunrel) - mf["sun_relative_deg"]) < 0.01, "sunrel 不符 笔记%s 清单%s" % (sgn + sunrel, mf["sun_relative_deg"]))
        chk(name == mf["name"], "名称不符 笔记%s 清单%s" % (name, mf["name"]))
        lock = re.search(r"锁定(\d+)层(\d+)米", ps)
        chk(lock and lock.group(1) == floors and lock.group(2) == meters,
            "锁定不符 笔记%s层%s米 真源%s层%s米" % (floors, meters, lock and lock.group(1), lock and lock.group(2)))
        so, si = SUN_OUT.search(sec), SUN_IN.search(sec)
        chk(bool(so) ^ bool(si), "日面可纳性行无可解析引文" if not (so or si) else "日面可纳性行同时出现两种句式")
        if so:
            chk(("the sun is %s degrees to the %s of the camera axis and outside this frame's %s degree half-angle" % so.groups()) in ps,
                "日面引文与真源 tail 不符（OUT %s°/%s/半角%s）" % so.groups())
        if si:
            chk(("the sun sits inside this frame as the canon section states (%s degrees to the %s of the camera axis, inside the %s degree half-angle)" % si.groups()) in ps,
                "日面引文与真源 tail 不符（IN %s°/%s/半角%s）" % si.groups())
        ck = re.findall(r"- 结论：([^（\n]+)", sec)
        chk(bool(ck), "无结论行")
        if ck:
            key = ck[-1].strip()
            concl[key] = concl.get(key, 0) + 1
        rows.append(sid)
    return rows, concl, bad, checks


def load():
    measure = {r["id"]: r for r in json.load(io.open(MEASURE, encoding="utf-8"))}
    manifest = {i["id"]: i for i in json.load(io.open(MANIFEST, encoding="utf-8"))["items"]}
    src = {}
    for f in os.listdir(PROMPT_DIR):
        if re.match(r"L\d{3}-", f):
            src[f[:4]] = io.open(os.path.join(PROMPT_DIR, f), encoding="utf-8").read().replace("\r\n", "\n")
    return measure, manifest, src


def main():
    measure, manifest, src = load()
    rows, concl, bad, checks = run(io.open(NOTES, encoding="utf-8").read(), measure, manifest, src)
    print("小节 %d｜核对项 %d｜不符 %d" % (len(rows), checks, len(bad)))
    print("结论分布", concl, "合计", sum(concl.values()))
    for x in bad:
        print("  ✗", x[0], x[1])
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
