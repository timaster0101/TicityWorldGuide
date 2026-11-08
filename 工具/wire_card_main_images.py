# -*- coding: utf-8 -*-
"""卡面 3:4 投放证据合并与主图接线（只读子代理证据、只写落点件与核验件）。

每个投放轮次的分档子代理各写一份仓外 jsonl（R1 七片 80 张、R2 三片 34 张）。本脚本把它们并回一份台账、
逐条与投放台账的 prompt_sha256 对拍，并核对 landing 真实字节/尺寸/sha256；全部合规格才把该轮的落点
并进 `数据/卡面主图提示词3x4/主图3x4落点.json`（纯 {键: 路径}，供 build_card_faces.py --sources 消费）。
任何一条缺证据、尺寸不是 768×1024、sha 与底串不符或落盘缺失，都只报不写，避免把半批图接进渲染器。

键的口径：有 code 的卡用 code（L009／D01）；code 为空的卡（职业／兑换／物品／能力／景群）用 _idx 十进制串，
证据与投放台账里这类条目的 id 写作 idxNNN，这里剥成数字——build_card_faces.py 的 --sources 查键顺序是
code → 文件名 stem → _idx，空 code 卡只剩 _idx 这一条路可走。
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH_DIR = os.path.join(ROOT, os.pardir, "_scratch_cardref")
EXPECT = (768, 1024)
ROUNDS = {
    "r1": {"scratch": "card3x4_r1", "ledger": "投放台账.json",
           "report": "投放核验.json", "sinks": "主图3x4落点.json"},
    "r2": {"scratch": "card3x4_r2", "ledger": "投放台账R2.json",
           "report": "投放核验R2.json", "sinks": "主图3x4落点.json"},
    "r3": {"scratch": "card3x4_r3", "ledger": "投放台账R3.json",
           "report": "投放核验R3.json", "sinks": "主图3x4落点.json"},
}


def sink_key(card_id):
    m = re.match(r"^idx0*(\d+)$", card_id)
    return m.group(1) if m else card_id


def collect_evidence(scratch):
    ev = {}
    files = sorted(glob.glob(os.path.join(scratch, "sent_shard*.jsonl")))
    for path in files:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                ev[row["id"]] = dict(row, _evidence_file=os.path.basename(path))
    return ev, [os.path.basename(p) for p in files]


def check(code, led_row, ev_row):
    problems = []
    if ev_row is None:
        return ["分档证据缺失（未投放或子代理未落行）"]
    if ev_row.get("status") != "ok":
        problems.append("证据 status=%s" % ev_row.get("status"))
    if ev_row.get("prompt_sha256") != led_row["prompt_sha256"]:
        problems.append("送入串 sha256 与底串不符")
    landing = os.path.join(ROOT, led_row["landing"])
    if not os.path.isfile(landing):
        problems.append("landing 缺失")
        return problems
    raw = open(landing, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    try:
        with Image.open(landing) as im:
            im.load()
            size = im.size
    except Exception as exc:  # 图坏了不算合规格
        problems.append("PIL 打不开：%s" % exc)
        return problems
    if size != EXPECT:
        problems.append("尺寸 %s≠%s" % (list(size), list(EXPECT)))
    if str(ev_row.get("landing_bytes")) != str(len(raw)):
        problems.append("证据字节 %s≠实读 %d" % (ev_row.get("landing_bytes"), len(raw)))
    if ev_row.get("landing_sha256") != sha:
        problems.append("证据 sha256≠实读")
    return problems, {"bytes": len(raw), "size": list(size), "sha256": sha}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", default="r1", choices=sorted(ROUNDS))
    ns, rest = ap.parse_known_args(argv)
    cfg = ROUNDS[ns.round]
    scratch = os.path.join(SCRATCH_DIR, cfg["scratch"])
    led_path = os.path.join("数据", "卡面主图提示词3x4", cfg["ledger"])
    report_path = os.path.join("数据", "卡面主图提示词3x4", cfg["report"])
    sinks_path = os.path.join("数据", "卡面主图提示词3x4", cfg["sinks"])
    if rest:
        ap.error("未知参数：%s" % " ".join(rest))
    os.chdir(ROOT)
    with open(led_path, encoding="utf-8") as fh:
        led = json.load(fh)
    ev, evidence_files = collect_evidence(scratch)
    rows, bad = [], []
    for it in led["items"]:
        got = check(it["id"], it, ev.get(it["id"]))
        if isinstance(got, tuple):
            problems, reading = got
        else:
            problems, reading = got, None
        if problems:
            bad.append({"id": it["id"], "problems": problems})
        else:
            rows.append({"id": it["id"], "sink": sink_key(it["id"]),
                         "name": it["name"], "prompt_file": it["prompt_file"],
                         "prompt_sha256": it["prompt_sha256"], "landing": it["landing"],
                         "imagegen_path": ev[it["id"]].get("imagegen_path"),
                         "bytes": reading["bytes"], "size": reading["size"],
                         "landing_sha256": reading["sha256"],
                         "timestamp_ms": ev[it["id"]].get("timestamp_ms")})
    report = {"投放轮次": led.get("投放轮次"), "证据件": evidence_files, "证据件数": len(evidence_files),
              "应投": led["条数"], "合规格": len(rows), "不合规格": len(bad),
              "统计面": "只数 %s 列出的 %d 条；证据只取 %s 的 sent_shard*.jsonl；"
                       "尺寸真源＝PIL 打开 landing 取 size；串 sha 真源＝数据/卡面主图提示词3x4 下的本轮 .txt"
                       % (led_path, led["条数"], scratch.replace("\\", "/")),
              "逐条": rows, "问题清单": bad}
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    print("应投 %d／合规格 %d／不合规格 %d" % (report["应投"], report["合规格"], report["不合规格"]))
    for x in bad[:8]:
        print("  ✗", x["id"], "；".join(x["problems"]))
    if len(rows) == led["条数"]:
        sinks = {r["sink"]: r["landing"] for r in rows}
        old = {}
        if os.path.isfile(sinks_path):
            with open(sinks_path, encoding="utf-8") as fh:
                old = json.load(fh)
        clash = {k: v for k, v in sinks.items() if k in old and old[k] != v}
        merged = dict(old)
        merged.update(sinks)
        with open(sinks_path, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, ensure_ascii=False, indent=1)
        print("落点件已写 %s（旧 %d＋本轮 %d＝并集 %d 键，同键改指 %d）"
              % (sinks_path, len(old), len(sinks), len(merged), len(clash)))
        return 0
    print("落点件未写：合规格 %d＜应投 %d（半批不接线）" % (len(rows), led["条数"]))
    return 1


if __name__ == "__main__":
    sys.exit(main())
