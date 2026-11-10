# -*- coding: utf-8 -*-
"""逐条打印发图串里的【取景指令】段（判 C123 点名远景用），其余段各批相同故省略。"""
import io
import json
import os
import re
import sys

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(OUT_DIR, "..", ".."))
with io.open(os.path.join(OUT_DIR, "send_bodies_19.json"), encoding="utf-8") as fp:
    BODIES = json.load(fp)

ids = sys.argv[1:] or sorted(BODIES)
ref = BODIES["L099"]["body"]
for rid in ids:
    body = BODIES[rid]["body"]
    m = re.search(r"【取景指令】(.*?)(?=【|\Z)", body, re.S)
    print("==== %s %s %s" % (rid, BODIES[rid]["name"], BODIES[rid]["size"]))
    print(m.group(1).strip() if m else "（无取景指令段）")
