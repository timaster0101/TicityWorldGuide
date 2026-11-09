# -*- coding: utf-8 -*-
"""按 transcript 反查重建 R4 主链缺失的证据行（只对已在盘的产物补记录，不据此判任何一条合格）。

为什么要这一步：放量改子代理分片投放后，投放规程第 4 节要求「每出一张立刻追加一行」，
但 D14／F007／F019 三条的代理产物在盘、发起在 transcript 里，行却没写就收尾了。
主链 `_scratch_cardref/reshoot_r4/sent_shard*.jsonl` 目前零代码消费方（`sent_shard` 的读取点
都在卡面侧 bind_check_card_r4.py 与 wire_card_main_images.py），主链逐字回绑的真源是 transcript，
所以补行不改动任何闸门读数；补的行必须与代理当场写的行分得开，故规程 16 字段之后另挂 provenance 段。

status 只由机械判据决定，任一不符即 failed。F007 的实投串被插了 442 字符，必须记 failed，
不得因为「产物在盘」就写成 ok（口径见 设计/2026-11-03-待办移交清单.md §48.7 ⑤⑦）。

timestamp_ms 仍按规程第 4 节取写入当刻；真实投放时刻另记在 provenance 的 投放时刻_ms
（取自产物文件名内嵌的毫秒时间戳），两者不混。
"""
import argparse
import difflib
import hashlib
import io
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE = os.path.dirname(ROOT)
SCRATCH = os.path.join(WORKSPACE, "_scratch_cardref", "reshoot_r4")
REGISTRY = os.path.join(ROOT, "工具", "reshoot_campaign_2026_11_06", "transcripts_r4.json")
READINGS = os.path.join(ROOT, "工具", "reshoot_campaign_2026_11_06", "rebuild_evidence_r4_readings.json")
DEFAULT_IDS = ("D14", "F007", "F019")
SOURCE_TAG = "主会话按 transcript 重建（非代理当场所写）"
TS_RE = re.compile(r"^(.+)_(1\d{12})_[0-9a-f]{8}\.png$")
# 产物落盘时刻与工具回执时刻的允许带宽：回执晚于落盘几十毫秒是常态，带宽给到 10 分钟只为挡住配错枚。
PAIR_BAND_MS = 600000

FIELDS = ("id", "arm", "send_name", "size", "send_sha256", "send_chars", "imagegen_path",
          "image_bytes", "image_sha256", "width", "height", "ref_image", "ref_sha256",
          "status", "error", "timestamp_ms")


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha_file(path):
    with open(path, "rb") as fh:
        return sha_bytes(fh.read())


def walk_collect(rec, uses, results, source, ctx):
    """递归收 ImageGen 的 tool_use（含 id）与 tool_result（按 tool_use_id 索引）。

    不能只扫顶层：发起与回执都嵌在 message.content 数组里，顶层扫行会解析出 0 条还打印成功。
    timestamp／uuid／toolUseResult 只长在顶层记录上，故按 ctx 往下传，不在嵌套 dict 上取。
    """
    if isinstance(rec, dict):
        if rec.get("type") == "tool_use" and rec.get("name") == "ImageGen":
            inp = rec.get("input") or {}
            uses.setdefault(inp.get("name"), []).append({
                "source": source, "ts": ctx[0], "uuid": ctx[1],
                "tool_use_id": rec.get("id"), "input": inp,
            })
        if rec.get("type") == "tool_result" and rec.get("tool_use_id"):
            results[rec["tool_use_id"]] = {
                "source": source, "ts": ctx[0],
                "toolUseResult": ctx[2], "content": rec.get("content"),
            }
        for v in rec.values():
            walk_collect(v, uses, results, source, ctx)
    elif isinstance(rec, list):
        for v in rec:
            walk_collect(v, uses, results, source, ctx)


def scan_sources(paths):
    """返回 (按发名索引的发起, 按 tool_use_id 索引的回执, 缺失路径)。缺失显式计数，不静默少扫。"""
    uses, results, missing = {}, {}, []
    for p in paths:
        if not os.path.isfile(p):
            missing.append(p)
            continue
        with io.open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                ctx = (rec.get("timestamp"), rec.get("uuid"), rec.get("toolUseResult"))
                walk_collect(rec, uses, results, p, ctx)
    return uses, results, missing


def registry_paths(reg):
    paths = sorted(set(reg["transcripts"].values()))
    if reg.get("主会话jsonl"):
        paths.append(reg["主会话jsonl"])
    return paths


def load_items(scratch, ids):
    """从分片清单取条目；返回 [(片号, 条目)]。一个 id 在多个片里出现即停（名单面坏了）。"""
    found = {}
    shard_dir = os.path.join(scratch, "shards")
    for name in sorted(os.listdir(shard_dir)):
        m = re.match(r"^shard_(\d+)\.json$", name)
        if not m:
            continue
        with io.open(os.path.join(shard_dir, name), encoding="utf-8") as fh:
            doc = json.load(fh)
        for it in doc.get("条", []):
            if it.get("id") in ids:
                found.setdefault(it["id"], []).append((int(m.group(1)), it))
    out = []
    for eid in ids:
        hits = found.get(eid, [])
        if len(hits) != 1:
            raise SystemExit("✗ %s 在分片清单里命中 %d 处（须恰 1）：先修名单，不要猜分片" % (eid, len(hits)))
        out.append(hits[0])
    return out


def existing_ids(scratch, shard_no):
    p = os.path.join(scratch, "sent_shard%02d.jsonl" % shard_no)
    if not os.path.isfile(p):
        return set(), p
    ids = set()
    with io.open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                ids.add(json.loads(line)["id"])
    return ids, p


def file_eol(path):
    """沿用目标文件已有的行尾，不重写字节：既有证据行是 CRLF／LF 混着的（C151 已裁定不做行尾归一）。"""
    if not os.path.isfile(path):
        return "\n"
    with open(path, "rb") as fh:
        return "\r\n" if b"\r\n" in fh.read() else "\n"


def iso_to_ms(iso):
    if not iso:
        return None
    try:
        dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return int(dt.timestamp() * 1000)


def ms_to_local(ms):
    return datetime.fromtimestamp(ms / 1000.0).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def ms_to_utc(ms):
    return datetime.fromtimestamp(ms / 1000.0, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def first_diff(a, b):
    """串面差异取证。

    「位置」取逐字符的首处不同（＝最长公共前缀长），不是 difflib 的首个非 equal opcode 起点：
    插入段里若含原串也有的字，difflib 会把 opcode 起点往前挪（夹具实测插在第 20 字符、opcode 报 14）。
    opcode 只用来描述差异段的形状，另列在 首处opcode 里。
    """
    n = min(len(a), len(b))
    pre = 0
    while pre < n and a[pre] == b[pre]:
        pre += 1
    suf = 0
    while suf < n - pre and a[len(a) - 1 - suf] == b[len(b) - 1 - suf]:
        suf += 1
    op = None
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "equal":
            op = {"类型": tag, "paste段": [i1, i2], "实投段": [j1, j2]}
            break
    return {"位置": pre, "公共前缀长": pre, "公共后缀长": suf,
            "多出字符": len(b) - len(a), "首处opcode": op}


def measure_image(path):
    from PIL import Image
    with open(path, "rb") as fh:
        raw = fh.read()
    with Image.open(io.BytesIO(raw)) as im:
        w, h = im.size
    return {"bytes": len(raw), "sha256": sha_bytes(raw), "width": w, "height": h}


def evaluate(item, use, result, now_ms):
    """算一条重建行。硬前提（产物在盘、回执配对、母图在盘）不满足即抛 SystemExit，不写半条行。

    返回 (row, checks)；checks 每项 {名, 符, 读数}，全部进 provenance，便于后续统计分来源。
    """
    inp = use["input"]
    tur = (result or {}).get("toolUseResult") or {}
    prod = tur.get("filePath")
    if not result or not prod:
        raise SystemExit("✗ %s 发起 %s 取不到带 filePath 的回执：不是成功投放，不补行"
                         % (item["id"], use["tool_use_id"]))
    prod = prod.replace("\\", os.sep)
    if not os.path.isfile(prod):
        raise SystemExit("✗ %s 回执产物不在盘（%s）：本脚本只对已在盘的产物补记录，缺枚走补投不走补行"
                         % (item["id"], prod))
    ref = item["ref_image"].replace("/", os.sep)
    if not os.path.isfile(ref):
        raise SystemExit("✗ %s 母图不在盘（%s）：母图摘要无从实读，先停手" % (item["id"], ref))
    paste_path = item["paste"].replace("/", os.sep)
    if not os.path.isfile(paste_path):
        raise SystemExit("✗ %s paste 不在盘（%s）" % (item["id"], paste_path))
    with open(paste_path, "rb") as fh:
        paste_raw = fh.read()
    paste_text = paste_raw.decode("utf-8")
    if sha_bytes(paste_raw) != item["send_sha256"] or len(paste_text) != int(item["send_chars"]):
        raise SystemExit("✗ %s paste 字节摘要／字符数与清单不符（实读 %s／%d，清单 %s／%s）：输入面坏了先修清单"
                         % (item["id"], sha_bytes(paste_raw)[:12], len(paste_text),
                            item["send_sha256"][:12], item["send_chars"]))

    prompt = inp.get("prompt") or ""
    prompt_raw = prompt.encode("utf-8")
    img = measure_image(prod)
    base = os.path.basename(prod)
    m = TS_RE.match(base)
    prod_ms = int(m.group(2)) if m else None
    res_ms = iso_to_ms(result.get("ts"))
    images = [x.get("source") if isinstance(x, dict) else x for x in (inp.get("images") or [])]
    ref_sha = sha_file(ref)
    want_w, want_h = (int(x) for x in str(item["size"]).split("x"))
    delta = abs(prod_ms - res_ms) if (prod_ms is not None and res_ms is not None) else None

    checks = [
        {"名": "串面逐字", "符": prompt_raw == paste_raw,
         "读数": "实投 %d 字符／paste %d 字符" % (len(prompt), len(paste_text))},
        {"名": "size 声明相符", "符": str(inp.get("size")) == str(item["size"]),
         "读数": "实投 %s／清单 %s" % (inp.get("size"), item["size"])},
        {"名": "尺寸实读相符", "符": (img["width"], img["height"]) == (want_w, want_h),
         "读数": "%dx%d" % (img["width"], img["height"])},
        {"名": "母图挂载相符",
         "符": [os.path.basename(str(x).replace("\\", "/")) for x in images]
               == [os.path.basename(item["ref_image"].replace("\\", "/"))],
         "读数": "images %d 项：%s" % (len(images), [os.path.basename(str(x)) for x in images])},
        {"名": "母图摘要相符", "符": ref_sha == item["ref_sha256"], "读数": ref_sha[:12]},
        {"名": "产物名绑发名", "符": base.startswith(item["send_name"] + "_") and m is not None,
         "读数": base},
        {"名": "落盘与回执同带", "符": delta is not None and delta <= PAIR_BAND_MS,
         "读数": "差 %s ms（带宽 %d）" % (delta, PAIR_BAND_MS)},
    ]
    ok = all(c["符"] for c in checks)
    diff = None if checks[0]["符"] else first_diff(paste_text, prompt)

    stamp = ms_to_local(now_ms)
    err = "证据行由主会话在 %s（本地，重建时刻_ms=%d）按 transcript 反查重建，非代理当场所写。" % (stamp, now_ms)
    if not ok:
        bad = ["%s=False（%s）" % (c["名"], c["读数"]) for c in checks if not c["符"]]
        err += "机械判据不通过：" + "；".join(bad) + "。"
        if not checks[0]["符"]:
            err += ("串面不符的产物按 §48.7 ⑤ 判废待重投：重投须登记投次+1／作废发起+1／作废删除，"
                    "并把坏枚物理移出 vibe_images 归档进 backup/（落盘计数纯按文件名 glob，光登记不过滤）。")
            if diff:
                err += ("串面差异取证：首处不同在第 %d 字符（公共前缀 %d／公共后缀 %d），实投比 paste 多 %d 字符；"
                        "difflib 首处 opcode %s。"
                        % (diff["位置"], diff["公共前缀长"], diff["公共后缀长"], diff["多出字符"],
                           json.dumps(diff["首处opcode"], ensure_ascii=False)))

    row = {
        "id": item["id"], "arm": "ref", "send_name": item["send_name"], "size": item["size"],
        # send_sha256／send_chars 按规程第 4 节定义＝该条 paste 的逐字节摘要与字符数（与清单一致）；
        # 盘面上真实发出去的那串另记 provenance.实投串_*，两者在 F007 上必然不同。
        "send_sha256": item["send_sha256"], "send_chars": item["send_chars"],
        "imagegen_path": prod.replace(os.sep, "\\"), "image_bytes": img["bytes"],
        "image_sha256": img["sha256"], "width": img["width"], "height": img["height"],
        "ref_image": item["ref_image"], "ref_sha256": ref_sha,
        "status": "ok" if ok else "failed", "error": err, "timestamp_ms": now_ms,
        "来源": SOURCE_TAG, "重建时刻_ms": now_ms,
        "重建依据": {"transcript": use["source"].replace(os.sep, "/"),
                     "tool_use_id": use["tool_use_id"], "发起时刻_utc": use["ts"],
                     "发起记录uuid": use["uuid"], "回执时刻_utc": result.get("ts"),
                     "requestId": tur.get("requestId")},
        "投放时刻_ms": prod_ms, "投放时刻_utc": ms_to_utc(prod_ms) if prod_ms else None,
        "实投串_sha256": sha_bytes(prompt_raw), "实投串_chars": len(prompt),
        "串面相符": bool(checks[0]["符"]), "串面差异": diff, "机械判据": checks,
    }
    return row, checks


def backup_targets(paths, backup_dir):
    """写前把每个目标文件整份 copy 进备份目录并逐字节对拍；一个文件只备一次（同片多条也不撞位）。"""
    out = {}
    todo = sorted(set(p for p in paths if os.path.isfile(p)))
    if todo:
        os.makedirs(backup_dir, exist_ok=True)
    for p in todo:
        dst = os.path.join(backup_dir, os.path.basename(p))
        if os.path.exists(dst):
            raise SystemExit("✗ 备份位已占用（%s）：同一轮不许覆盖备份" % dst)
        shutil.copyfile(p, dst)
        if sha_file(dst) != sha_file(p):
            raise SystemExit("✗ 备份与原件字节不符，停手")
        out[p] = dst.replace(os.sep, "/")
    return out


def append_row(path, row, backed):
    """只追加、不重写字节；行尾沿用目标文件已有的那种（C151 已裁定不做行尾归一）。"""
    eol = file_eol(path)
    line = json.dumps(row, ensure_ascii=False)
    with io.open(path, "a", encoding="utf-8", newline="") as fh:
        fh.write(line + eol)
    return {"备份": backed.get(path), "行尾": "CRLF" if eol == "\r\n" else "LF",
            "追加字节": len((line + eol).encode("utf-8"))}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ids", default=",".join(DEFAULT_IDS))
    ap.add_argument("--scratch", default=SCRATCH)
    ap.add_argument("--registry", default=REGISTRY)
    ap.add_argument("--readings", default=READINGS)
    ap.add_argument("--dry", action="store_true", help="只取读数，不写证据行、不写报告、不建备份")
    args = ap.parse_args(argv)
    ids = [x.strip() for x in args.ids.split(",") if x.strip()]
    scratch = os.path.abspath(args.scratch)
    with io.open(args.registry, encoding="utf-8") as fh:
        reg = json.load(fh)
    paths = registry_paths(reg)
    uses, results, missing = scan_sources(paths)
    if missing:
        raise SystemExit("✗ 回绑源缺失 %d 份（%s）：跨会话路径会失效，先重新登记当轮路径"
                         % (len(missing), missing))
    items = load_items(scratch, ids)
    now_ms = int(time.time() * 1000)
    stamp = datetime.fromtimestamp(now_ms / 1000.0).strftime("%Y%m%d-%H%M%S")
    backup_dir = os.path.join(scratch, "bak_evidence_rebuild", stamp)

    rows, refusals = [], []
    for shard_no, item in items:
        eid = item["id"]
        have, path = existing_ids(scratch, shard_no)
        if eid in have:
            refusals.append("%s 已在 %s 里有行，拒跑（幂等：不重投也不重写）" % (eid, os.path.basename(path)))
            continue
        hits = uses.get(item["send_name"], [])
        if len(hits) != 1:
            refusals.append("%s 按发名在 %d 份回绑源里命中 %d 次发起（须恰 1）"
                            % (eid, len(paths), len(hits)))
            continue
        use = hits[0]
        row, checks = evaluate(item, use, results.get(use["tool_use_id"]), now_ms)
        rows.append({"片号": shard_no, "目标": path.replace(os.sep, "/"), "row": row, "checks": checks})
        print("%s %s｜片%02d｜%s｜串面相符=%s｜实投 %d 字符／paste %d｜产物 %d 字节 sha12=%s｜%dx%d｜母图摘要符=%s"
              % ("✓" if row["status"] == "ok" else "✗", eid, shard_no, row["status"], row["串面相符"],
                 row["实投串_chars"], row["send_chars"], row["image_bytes"], row["image_sha256"][:12],
                 row["width"], row["height"],
                 next(c["符"] for c in checks if c["名"] == "母图摘要相符")))
        for c in checks:
            if not c["符"]:
                print("    ✗ %s：%s" % (c["名"], c["读数"]))
        if row["串面差异"]:
            print("    串面差异：%s" % json.dumps(row["串面差异"], ensure_ascii=False))
    for r in refusals:
        print("✗ 拒跑：%s" % r)

    report = {
        "轮次": "R4_画风母图重投", "档串": reg.get("suffix"), "生成器": "工具/rebuild_r4_evidence.py",
        "口径": ("只对已在盘的产物补记录，不据此判定任何一条合格；status 只由机械判据决定，任一不符即 failed。"
                 "补建行带 来源＝%s 与 provenance 段，与代理当场写的 16 字段行可分。"
                 "timestamp_ms 按规程取写入当刻，真实投放时刻另记 投放时刻_ms。" % SOURCE_TAG),
        "dry": bool(args.dry), "重建时刻_ms": now_ms, "重建时刻_本地": ms_to_local(now_ms),
        "回绑源": {"登记件": args.registry.replace(os.sep, "/"), "在盘份数": len(paths),
                   "缺失份数": len(missing), "路径": [p.replace(os.sep, "/") for p in paths]},
        "统计面": ("扫登记件 transcripts 字典 %d 份＋主会话 jsonl 1 份，共 %d 份；"
                   "条目取自 %s/shards/shard_*.json 的「条」数组，只取 --ids 点名的 %d 个 id；"
                   "产物只认回执 toolUseResult.filePath 那一个路径，不做目录扫描。"
                   % (len(reg["transcripts"]), len(paths), scratch.replace(os.sep, "/"), len(ids))),
        "请求条数": len(ids), "可重建条数": len(rows), "拒跑条数": len(refusals), "拒跑": refusals,
        "status 分布": {s: sum(1 for r in rows if r["row"]["status"] == s) for s in ("ok", "failed")},
        "逐条": [{"id": r["row"]["id"], "片号": r["片号"], "目标": r["目标"],
                  "status": r["row"]["status"], "机械判据": r["checks"],
                  "投放时刻_ms": r["row"]["投放时刻_ms"], "image_sha256": r["row"]["image_sha256"],
                  "image_bytes": r["row"]["image_bytes"], "实投串_chars": r["row"]["实投串_chars"],
                  "send_chars": r["row"]["send_chars"], "串面差异": r["row"]["串面差异"],
                  "重建依据": r["row"]["重建依据"]} for r in rows],
    }
    if args.dry:
        print("—— --dry：未写证据行、未写报告、未建备份 ——")
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 1 if refusals else 0
    if refusals:
        raise SystemExit("✗ 有 %d 条拒跑，整轮不写（避免半批落盘）" % len(refusals))
    backed = backup_targets([r["目标"] for r in rows], backup_dir)
    for r in rows:
        r["落盘"] = append_row(r["目标"], r["row"], backed)
        print("落盘 %s → %s（%s，备份 %s）" % (r["row"]["id"], r["目标"], r["落盘"]["行尾"], r["落盘"]["备份"]))
    report["备份目录"] = backup_dir.replace(os.sep, "/")
    report["落盘"] = [{"id": r["row"]["id"], "目标": r["目标"], **r["落盘"]} for r in rows]
    with io.open(args.readings, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print("报告：%s（%d 字节）" % (args.readings, os.path.getsize(args.readings)))
    return 0


if __name__ == "__main__":
    sys.exit(main())