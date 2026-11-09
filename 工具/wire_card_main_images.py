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
    # r4＝画风母图臂（图生图）：台账没有 prompt_sha256，底串摘要在 base_sha256、
    # 实际送入串（前导一行＋底串逐字）摘要在 send_sha256。分片证据里的 prompt_sha256 按规程
    # 记的是「真实喂进去那串」，所以这一轮的对拍目标是 send_sha256；核验件逐条里仍留底串摘要（与 R1—R3 同语义）。
    "r4": {"scratch": "card3x4_r4", "ledger": "投放台账R4.json",
           "report": "投放核验R4.json", "sinks": "主图3x4落点.json",
           "ev_sha_field": "send_sha256"},
}


def sink_key(card_id):
    m = re.match(r"^idx0*(\d+)$", card_id)
    return m.group(1) if m else card_id


def normalize(raw_row):
    """把两种分片证据形态归一成一份口径。

    wave1（R3 分片 1—5 与探针/补投）落 landing_bytes／landing_sha256（全 64 位）／width／height／imagegen_path；
    wave2（R3 分片 6—10）落 copy_bytes／copy_sha256_12（只有 12 位前缀）／size=[w,h]／gen_path。
    归一后统一用 wave1 的键名，并记下证据 sha 的位数——短前缀只按前缀对拍，不假装是全串校验。
    """
    row = dict(raw_row)
    if not row.get("landing_bytes") and row.get("copy_bytes"):
        row["landing_bytes"] = row["copy_bytes"]
    if not row.get("landing_sha256") and row.get("copy_sha256_12"):
        row["landing_sha256"] = row["copy_sha256_12"]
    if not row.get("imagegen_path") and row.get("gen_path"):
        row["imagegen_path"] = row["gen_path"]
    if "width" not in row and isinstance(row.get("size"), (list, tuple)) and len(row["size"]) == 2:
        row["width"], row["height"] = row["size"]
    row["_证据sha位数"] = len(row.get("landing_sha256") or "")
    return row


def collect_evidence(scratch):
    """同一 id 多行时留 timestamp_ms 最大的那一行（＝最后一次发起），与 R1 的「留后来出的」同口径。

    探针与补投的分档文件按文件名排在放量之后，若按文件顺序覆盖就会让早先旧串的发起顶掉现串，
    判成「送入串 sha256 与底串不符」。
    """
    ev = {}
    dup = {}
    files = sorted(glob.glob(os.path.join(scratch, "sent_shard*.jsonl")))
    for path in files:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = normalize(json.loads(line))
                prev = ev.get(row["id"])
                if prev is not None:
                    dup.setdefault(row["id"], 0)
                    dup[row["id"]] += 1
                    if int(row.get("timestamp_ms") or 0) <= int(prev.get("timestamp_ms") or 0):
                        continue
                ev[row["id"]] = dict(row, _evidence_file=os.path.basename(path))
    return ev, [os.path.basename(p) for p in files], dup


def check(code, led_row, ev_row, sha_field="prompt_sha256"):
    problems = []
    if ev_row is None:
        return ["分档证据缺失（未投放或子代理未落行）"]
    if ev_row.get("status") != "ok":
        problems.append("证据 status=%s" % ev_row.get("status"))
    if ev_row.get("prompt_sha256") != led_row[sha_field]:
        problems.append("送入串 sha256 与台账 %s 不符" % sha_field)
    landing = os.path.join(ROOT, led_row["landing"])
    if not os.path.isfile(landing):
        problems.append("landing 缺失")
        return problems
    with open(landing, "rb") as fh:
        raw = fh.read()
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
    ev_sha = ev_row.get("landing_sha256") or ""
    if len(ev_sha) == 64:
        if ev_sha != sha:
            problems.append("证据 sha256≠实读")
    elif len(ev_sha) >= 12:
        if sha[:len(ev_sha)] != ev_sha:
            problems.append("证据 sha 前缀≠实读")
    else:
        problems.append("证据无 sha256（位数 %d）" % len(ev_sha))
    return problems, {"bytes": len(raw), "size": list(size), "sha256": sha,
                      "证据sha位数": len(ev_sha)}


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
    ev, evidence_files, dup = collect_evidence(scratch)
    sha_field = cfg.get("ev_sha_field", "prompt_sha256")
    rows, bad = [], []
    for it in led["items"]:
        got = check(it["id"], it, ev.get(it["id"]), sha_field)
        if isinstance(got, tuple):
            problems, reading = got
        else:
            problems, reading = got, None
        if problems:
            bad.append({"id": it["id"], "problems": problems})
        else:
            rows.append({"id": it["id"], "sink": sink_key(it["id"]),
                         "name": it["name"], "prompt_file": it["prompt_file"],
                         # r4 台账把底串摘要记在 base_sha256；核验件这一列沿 R1—R3 语义仍是底串摘要，
                         # 送入串摘要另见台账 send_sha256（对拍目标由 sha_field 决定）。
                         "prompt_sha256": it.get("prompt_sha256") or it.get("base_sha256"),
                         "landing": it["landing"],
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
