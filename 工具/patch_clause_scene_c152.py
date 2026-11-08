# -*- coding: utf-8 -*-
"""把 CLAUSE_SCENE（34 条拼装支路的画幅约束）改成 R3 口径：加四边装帧禁令与文案不烤进图。

真源件 数据/卡面主图正文待投.json 里只有这一个字段要动，骨架五段与 34 条正文一字不改，
所以走「整份读入 → 断言旧串恰 1 次 → 字面替换 → 写临时件逐字节对拍除该行外全等」这条路，
不用 json.load/dump 重排整份文件（那会把缩进与键序一起改掉，字节链就看不出真正改了什么）。
"""
import hashlib
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REL = os.path.join("数据", "卡面主图正文待投.json")

OLD_HEAD = '"CLAUSE_SCENE": "画幅为3:4竖幅（768×1024，满幅铺整卡，不作裁切适配）：'
NEW_HEAD = '"CLAUSE_SCENE": "画幅为3:4竖幅（768×1024，画面铺满整幅画布、不作裁切适配，本图是画面本身而不是一张带装帧的卡片）：'
OLD_TOP = "顶部留出不少于画面高度14%的文字安全区（卡名与副标题由页面叠在此处，该带只许天面、"
NEW_TOP = ("顶部留出不少于画面高度14%的文字安全区（卡名与副标题由页面叠在此处，"
           "主图本身在该带内不得含任何文字或图形叠加物，该带只许天面、")
OLD_BOTTOM = "底部留出不少于画面高度22%的暗部安全区（底部文案浮层叠在此处，该带以地面、"
NEW_BOTTOM = ("底部留出不少于画面高度22%的暗部安全区（底部文案浮层叠在此处，"
              "主图本身在该带内同样不得含任何文字，该带以地面、")
# 装帧与文案两条插在【本条只改画幅】那句之前，与派生支路的 CLAUSE 同位置。
OLD_TAIL = "本条只改画幅与上下安全区，主体外观、光照方位与人物密度沿用下文原句，不因此增删场景构件；"
NEW_TAIL = ("四边装帧禁令：卡框、边框、内框、双线框、装饰角花、描边、圆角、白边、投影边框与暗角压边一律禁止，"
            "画面内容必须满幅铺到画布的四个像素边缘，不得在画面里画出「一张卡片」「一幅装裱画」这类带边的载体；"
            "文案不烤进图：卡名、副标题、编号、数值、价格、属性图标、徽章、水印与任何可读字形一律不得出现在主图内，"
            "版面文字全部由页面在图外叠加；画面内唯一允许的文字仍是【全局硬设定】点名的店铺招牌、灯箱与门牌，"
            "且只许是不可读笔画，不得拼读；" + OLD_TAIL)

PAIRS = [(OLD_HEAD, NEW_HEAD), (OLD_TOP, NEW_TOP), (OLD_BOTTOM, NEW_BOTTOM), (OLD_TAIL, NEW_TAIL)]


def sha12(b):
    return hashlib.sha256(b).hexdigest()[:12]


def main():
    os.chdir(ROOT)
    with io.open(REL, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-8")
    print("改前 %d 字节／%s" % (len(raw), sha12(raw)))
    for old, new in PAIRS:
        n = text.count(old)
        if n != 1:
            raise SystemExit("锚点命中 %d 次（须恰 1）：%s" % (n, old[:40]))
        text = text.replace(old, new, 1)
    out = text.encode("utf-8")
    # 对拍：新旧两份按行切，差异行必须只有 CLAUSE_SCENE 那一行，行数不变。
    before = raw.decode("utf-8").split("\n")
    after = text.split("\n")
    if len(before) != len(after):
        raise SystemExit("行数变了 %d→%d，本脚本只许改一行" % (len(before), len(after)))
    diff = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    if len(diff) != 1:
        raise SystemExit("差异行 %d 处（须恰 1）：%s" % (len(diff), diff))
    if "CLAUSE_SCENE" not in after[diff[0]]:
        raise SystemExit("唯一差异行不是 CLAUSE_SCENE：%s" % after[diff[0]][:60])
    if out.count(b"\r") != raw.count(b"\r"):
        raise SystemExit("CR 数变了 %d→%d，行尾口径不许动" % (raw.count(b"\r"), out.count(b"\r")))
    tmp = REL + ".c152tmp"
    with io.open(tmp, "wb") as fh:
        fh.write(out)
    os.replace(tmp, REL)
    with io.open(REL, "rb") as fh:
        now = fh.read()
    print("改后 %d 字节／%s（差异行号 %d，行内含 CLAUSE_SCENE）" % (len(now), sha12(now), diff[0] + 1))
    print("哨兵：装帧禁令=%d 文案不烤进图=%d 满幅铺整卡=%d"
          % (now.count("四边装帧禁令".encode("utf-8")),
             now.count("文案不烤进图".encode("utf-8")),
             now.count("满幅铺整卡".encode("utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
