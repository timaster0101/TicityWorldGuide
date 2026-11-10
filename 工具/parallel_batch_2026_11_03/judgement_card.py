# -*- coding: utf-8 -*-
"""按条打印判定依据卡：锁定句/禁则/远景点名/日面断言全部从 pending_manifest（真源切片）取，
读数从 measure.json 取。目视打表时以本输出为唯一依据，不凭记忆。"""
import io
import json
import os
import sys

DIR = os.path.dirname(os.path.abspath(__file__))
with io.open(os.path.join(DIR, "pending_manifest.json"), encoding="utf-8") as fp:
    ROWS = json.load(fp)["rows"]
with io.open(os.path.join(DIR, "measure.json"), encoding="utf-8") as fh:
    MEAS = {r["id"]: r for r in json.load(fh)}

for ident in sys.argv[1:]:
    rec = [r for r in ROWS if r["id"] == ident]
    if not rec:
        raise SystemExit("清单里没有 %s" % ident)
    rec, m = rec[0], MEAS.get(ident, {})
    print("=" * 100)
    print("%s %s｜%s｜%s｜太阳相对 %s" % (
        ident, rec["对应关系"]["名称"], rec["对应关系"]["建议尺寸"],
        rec["对应关系"]["拍摄朝向"], rec["对应关系"]["名录硬参数"].split("；")[0]))
    print("【读数】%s %d字节 sha12=%s caBX=%d iTXt=%d fvar全图=%.6f 中央=%.6f 日面核=%d 尺寸相符=%s" % (
        m.get("dims"), m.get("bytes", 0), m.get("sha256_12"),
        (m.get("container") or {}).get("cabx"), (m.get("container") or {}).get("itxt"),
        m.get("fine_var_full", 0), m.get("fine_var_center", 0),
        m.get("sun_blob_px", 0), m.get("size_match")))
    print("【取景指令·远景点名】" + rec["取景指令_远景"])
    print("【锁定与禁则】" + rec["锁定与禁则"])
    print("【tail日面断言】" + rec["tail_日面断言"])
    print("【文件】vibe_images 下 %s-C118新串-v01*.png" % ident)
