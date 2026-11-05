# -*- coding: utf-8 -*-
"""按 id 打印发图串的中文分段（真源逐字切片），供人工目视读图时对照。

用法：python -X utf8 工具/batch9c_2026_11_05/print_digest.py L063 L067 ...
只读 工具/batch9c_2026_11_05/send_bodies_31.json（该文件本身由真源切片而来、
投后已与实发串逐字相等），不写任何真源。
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BODIES = json.loads((HERE / "send_bodies_31.json").read_text(encoding="utf-8"))
SEC = re.compile(r"^【(.+?)】", re.M)


def sections(body):
    cuts = [(m.start(), m.end(), m.group(1)) for m in SEC.finditer(body)]
    out = {}
    for i, (start, end, name) in enumerate(cuts):
        stop = cuts[i + 1][0] if i + 1 < len(cuts) else len(body)
        out[name] = body[end:stop].strip()
    return out


for rid in sys.argv[1:]:
    b = BODIES[rid]
    secs = sections(b["body"])
    print("=" * 8, rid, b["size"], b["sha256"][:12], "=" * 8)
    for name, val in secs.items():
        if name in ("画风锚点", "全局硬设定"):
            continue
        print("【%s】%s" % (name, val))
    tail = b["body"].split("English tail:", 1)[1]
    sun = re.search(
        r"the sun (sits inside this frame as the canon section states \(\d+ degrees to the "
        r"(?:left|right) of the camera axis, inside the \d+ degree half-angle\)"
        r"|\d+ degrees to the (?:left|right) of the camera axis and outside this frame's "
        r"\d+ degree half-angle)",
        tail,
    )
    print("〔日面分支〕%s" % (sun.group(1) if sun else re.search(r".{0,80}the sun.{0,240}", tail).group(0)))
    far = re.findall(
        r"L\d{3}[^,;]{0,90}?\(\d+(?:\.\d+)? degrees to the (?:left|right)[^,;]{0,60}", tail
    )
    for f in far:
        print("〔远景点名〕%s" % f)
    print()
