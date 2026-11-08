# -*- coding: utf-8 -*-
"""R3 卡面主图放量的逐字回绑：扫子代理 transcript 里 ImageGen 实际送入的 prompt，与仓内底串 sha 对拍。

与开图侧 verify_round.py 同口径（回绑源＝transcript 的 tool_use input），只是卡面侧的串真源是
数据/卡面主图提示词3x4/*.txt，比对键是归一（CRLF→LF）后的 sha256。
产物写仓内登记件 数据/卡面主图提示词3x4/回绑源登记R3.json；transcript 本身在会话临时区，跨会话会失效，
所以本件把逐份的在盘状态、字节数、sha 前缀与命中明细都落进仓，缺失时显式计数不判通过。
"""
import hashlib
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "数据", "卡面主图提示词3x4", "投放台账R3.json")
OUT = os.path.join(ROOT, "数据", "卡面主图提示词3x4", "回绑源登记R3.json")
DISPATCH = os.path.join(ROOT, os.pardir, "_scratch_cardref", "card3x4_r3", "dispatch_r3_full.json")
SUBDIR = os.path.join(os.path.expanduser("~"), ".qoder-cn", "projects",
                      "C--Users-TIMASTER-Documents-Qoder-2026-10-29-c8c10ff8",
                      "6b39cfae-e2ed-48a8-81fd-0af6e4887eda", "subagents")


def norm_sha(text):
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def iter_tool_inputs(path):
    """递归 walk（沿 send_ledger 的 sent_prompts 口径），取所有 ImageGen 的 tool_use input。"""
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or "imagegen" not in line.lower():
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            stack = [obj]
            while stack:
                cur = stack.pop()
                if isinstance(cur, dict):
                    stack.extend(cur.values())
                elif isinstance(cur, list):
                    stack.extend(cur)
                elif isinstance(cur, str):
                    pass
                else:
                    continue
                if isinstance(cur, dict) and str(cur.get("name", "")).lower().replace("_", "") in (
                        "imagegen", "mcpimagegen"):
                    inp = cur.get("input") or cur.get("arguments")
                    if isinstance(inp, str):
                        try:
                            inp = json.loads(inp)
                        except ValueError:
                            continue
                    if isinstance(inp, dict) and isinstance(inp.get("prompt"), str):
                        yield inp


def _merge_forms(rows):
    merged = {}
    for r in rows:
        for k, v in (r.get("命中形态") or {}).items():
            merged[k] = merged.get(k, 0) + v
    return merged


def main():
    led = json.load(io.open(LEDGER, encoding="utf-8"))
    by_sha = {}
    for it in led["items"]:
        by_sha.setdefault(it["prompt_sha256"], []).append(it["id"])
    # 底串文件以结尾换行落盘，ImageGen 送入的是去掉结尾换行的正文——两种形态都收，命中时记形态。
    by_txt = {}
    for it in led["items"]:
        raw = open(os.path.join(ROOT, it["prompt_file"]), "rb").read().replace(b"\r\n", b"\n")
        text = raw.decode("utf-8")
        by_txt.setdefault(norm_sha(text), (it["id"], "含结尾换行"))
        by_txt.setdefault(norm_sha(text.rstrip("\n")), (it["id"], "去结尾换行"))
    disp = json.load(io.open(os.path.abspath(DISPATCH), encoding="utf-8"))
    shards = list(disp.get("wave1", [])) + list(disp.get("wave2", []))
    hits, rows, missing = {}, [], 0

    def scan(path):
        raw = open(path, "rb").read()
        n_sent = 0
        matched = []
        forms = {}
        for inp in iter_tool_inputs(path):
            n_sent += 1
            sha = norm_sha(inp["prompt"])
            got = by_txt.get(sha) or (by_sha.get(sha) and (by_sha[sha][0], "台账 sha"))
            if got:
                cid, form = got
                forms[form] = forms.get(form, 0) + 1
                matched.append(cid)
                hits.setdefault(cid, 0)
                hits[cid] += 1
            else:
                matched.append(None)
        return raw, n_sent, matched, forms

    for s in shards:
        path = os.path.join(SUBDIR, "agent-%s.jsonl" % s["agentId"])
        if not os.path.isfile(path):
            missing += 1
            rows.append({"分片": s["分片"], "agentId": s["agentId"], "在盘": False})
            continue
        raw, n_sent, matched, forms = scan(path)
        rows.append({"分片": s["分片"], "agentId": s["agentId"], "在盘": True,
                     "transcript": path.replace("\\", "/"), "字节": len(raw),
                     "sha256_12": hashlib.sha256(raw).hexdigest()[:12],
                     "ImageGen送入次数": n_sent,
                     "逐字命中台账底串数": sum(1 for x in matched if x),
                     "未命中台账底串的送入数": sum(1 for x in matched if x is None),
                     "命中形态": forms})
    # 主会话 transcript 也是回绑源：违例条目的逐字补投由主会话直投，不登记就会让补投永远算未命中。
    # 主会话件在会话目录的同级同名 .jsonl（不在 subagents 的父目录里）。
    for path in [os.path.dirname(SUBDIR) + ".jsonl"]:
        if not os.path.isfile(path):
            missing += 1
            rows.append({"分片": "主会话", "agentId": os.path.basename(path), "在盘": False})
            continue
        raw, n_sent, matched, forms = scan(path)
        rows.append({"分片": "主会话", "agentId": os.path.basename(path), "在盘": True,
                     "transcript": path.replace("\\", "/"), "字节": len(raw),
                     "sha256_12": hashlib.sha256(raw).hexdigest()[:12],
                     "ImageGen送入次数": n_sent,
                     "逐字命中台账底串数": sum(1 for x in matched if x),
                     "未命中台账底串的送入数": sum(1 for x in matched if x is None),
                     "命中形态": forms})
    unmatched = [i["id"] for i in led["items"] if i["id"] not in hits]
    multi = {k: v for k, v in hits.items() if v > 1}
    out = {
        "declaration": "R3 卡面主图放量（114 条）的逐字回绑登记件。回绑源＝10 份子代理 transcript＋主会话 transcript 里 ImageGen 的 "
                       "tool_use input.prompt，归一（CRLF→LF）后 sha256 与 数据/卡面主图提示词3x4 底串对拍。"
                       "transcript 在会话临时区，跨会话会失效——本件把每份的字节数与 sha 前缀落进仓，"
                       "缺失份数显式计数，不拿缺失当通过。",
        "登记时刻": "2026-11-09",
        "放行原话": disp.get("放行原话") or "用户 2026-11-09 逐字「都做」",
        "覆盖面": disp.get("覆盖面"),
        "统计面": "台账 %d 条；回绑源 %d 份（分片登记 %d 份＋主会话 transcript 1 份）；逐字命中按 id 去重计数，"
                       "同一 id 多次送入记入「同条多枚」"
                  % (led["条数"], len(rows), len(shards)),
        "分片数": len(shards),
        "回绑源数": len(rows),
        "缺失份数": missing,
        "命中形态合计": _merge_forms(rows),
        "ImageGen送入合计": sum(r.get("ImageGen送入次数", 0) for r in rows),
        "逐字命中合计": sum(r.get("逐字命中台账底串数", 0) for r in rows),
        "未命中合计": sum(r.get("未命中台账底串的送入数", 0) for r in rows),
        "台账条目被逐字命中数": len(hits),
        "未被命中条目": unmatched,
        "同条多枚": multi,
        "分片明细": rows,
    }
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print("分片 %d／缺失 %d／送入合计 %d／逐字命中 %d／未命中 %d／台账被命中条目 %d／未命中条目 %d／同条多枚 %d"
          % (len(shards), missing, out["ImageGen送入合计"], out["逐字命中合计"], out["未命中合计"],
             len(hits), len(unmatched), len(multi)))
    if unmatched:
        print("未命中名单", unmatched[:20])
    if multi:
        print("同条多枚", json.dumps(multi, ensure_ascii=False)[:400])


if __name__ == "__main__":
    sys.exit(main())
