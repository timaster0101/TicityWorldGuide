# -*- coding: utf-8 -*-
"""第9批 f 轮 12 张第五投 v02 新图逐张测量打表（只读，不写任何真源）。

复用 工具/reinject_2026_11_05/measure_images.py 的 measure(path) 口径。
产物文件按 §32.6 的时间戳带选取：只认探针 ts（FLOOR）及其后的那一张，
同名档的历史文件（9c／9e 轮也投过同一批 v02）一律不作本轮产物。

实发串与真源不相等的条目（sent_binding.json 逐字相等=false）标记「不参与回填」，仍照常测量留档。
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VIBE = ROOT / "vibe_images"
OUT = HERE / "batch9f_measure.json"

FLOOR = 1793901894424  # 本轮探针 L083 的落盘 ts，带内文件才是本轮产物

spec = importlib.util.spec_from_file_location(
    "m9f", ROOT / "工具/reinject_2026_11_05/measure_images.py"
)
m9 = importlib.util.module_from_spec(spec)
sys.argv = [str(spec.origin), str(OUT)]
spec.loader.exec_module(m9)

BODIES = json.loads((HERE / "send_bodies_12.json").read_text(encoding="utf-8"))
BIND = {r["id"]: r for r in json.loads((HERE / "sent_binding.json").read_text(encoding="utf-8"))}
MANIFEST = json.loads((ROOT / "数据/开图清单.json").read_text(encoding="utf-8"))
ITEMS = {it["id"]: it for it in MANIFEST["items"]}

FLOOR_VAR = 0.000414  # C134：极轻档地板（塔臂）只作读数参照；低于此不再判非油画（实测无法分离照片与绘画）
SUN_MIN = 1500  # C134：上半区日面连通块面积的读数分档线，只作记录不作判据
TS = r"_(\d{13})_"

rows = []
missing = []
for rid in BODIES:
    all_v02 = [p for p in VIBE.glob("%s-*C123新串-v02*.png" % rid) if re.search(TS, p.name)]
    band = [p for p in all_v02 if int(re.search(TS, p.name).group(1)) >= FLOOR]
    if not band:
        missing.append((rid, [p.name for p in all_v02]))
        continue
    assert len(band) == 1, (rid, "带内多于 1 张，本轮重复投放", [p.name for p in band])
    path = band[0]
    rec = m9.measure(path)
    rec["id"] = rid
    rec["file"] = path.name
    rec["v02_files_total"] = len(all_v02)
    it = ITEMS.get(rid)
    if it:
        rec["entry_name"] = it["name"]
        rec["expected_size"] = it["size"]
        rec["size_match"] = rec["dims"] == it["size"]
        rec["image_file_now"] = it["image_file"]
        rec["camera_facing_deg"] = it["camera_facing_deg"]
        rec["sun_relative_deg"] = it["sun_relative_deg"]
    b = BIND.get(rid, {})
    rec["逐字相等"] = b.get("逐字相等")
    rec["sent_sha12"] = b.get("sent_sha12")
    rec["canon_sha12"] = b.get("canon_sha12")
    rec["参与回填"] = bool(b.get("逐字相等")) and rec.get("size_match")
    rec["油画量级"] = "off-floor" if rec["fine_var_full"] >= FLOOR_VAR else "below-floor"  # C134：仅读数，不作判废依据
    rec["疑似日盘"] = rec["sun_blob_px"] >= SUN_MIN  # C134：仅读数，不作判废依据
    rows.append(rec)
    print(
        "%-5s %s %10d caBX=%d iTXt=%d AIGC=%s fvar=%.6f cvar=%.6f sun=%-6d p99=%-5s match=%s 相等=%s 回填=%s"
        % (
            rid,
            rec["dims"],
            rec["bytes"],
            rec["container"]["cabx"],
            rec["container"]["itxt"],
            rec["container"]["aigc"],
            rec["fine_var_full"],
            rec["fine_var_center"],
            rec["sun_blob_px"],
            rec["p99_lum"],
            rec.get("size_match"),
            rec["逐字相等"],
            rec["参与回填"],
        ),
        flush=True,
    )

rows.sort(key=lambda r: r["id"])
OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

n = len(rows)
print("---- 汇总 ----")
print("读到 %d 张（名单 %d 条，带内缺文件 %d）" % (n, len(BODIES), len(missing)))
for rid, c in missing:
    print("  缺:", rid, c)
print("尺寸不符 %d:" % sum(1 for r in rows if not r.get("size_match")),
      [r["id"] for r in rows if not r.get("size_match")])
print("逐字相等 false %d:" % sum(1 for r in rows if r["逐字相等"] is False),
      [r["id"] for r in rows if r["逐字相等"] is False])
print("参与回填 %d / 不参与 %d" % (sum(1 for r in rows if r["参与回填"]),
                                   sum(1 for r in rows if not r["参与回填"])))
bad_container = [r["id"] for r in rows if not (r["container"]["cabx"] >= 1 or r["container"]["aigc"])]
print("AIGC 标识缺失 %d:" % len(bad_container), bad_container)
print("细尺度方差区间 %.6f ~ %.6f（极轻档地板 %.6f，仅读数）；低于地板 %d 张（仅读数，不作判据）"
      % (min(r["fine_var_full"] for r in rows), max(r["fine_var_full"] for r in rows), FLOOR_VAR,
         sum(1 for r in rows if r["fine_var_full"] < FLOOR_VAR)))
print("日面读数>=1500px（C134 起仅读数，不作判据）%d 张:" % sum(1 for r in rows if r["疑似日盘"]),
      [(r["id"], r["sun_blob_px"]) for r in rows if r["疑似日盘"]])
print("sha12 重复:", [s for s in {r["sha256_12"] for r in rows}
                     if sum(1 for r in rows if r["sha256_12"] == s) > 1])
print("->", OUT)
