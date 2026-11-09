# -*- coding: utf-8 -*-
"""R4 卡面主图放量（85 枚母图臂）的逐字回绑：扫 transcript 里 ImageGen 实际送入的 prompt 与 images，两件都对上才算命中。

与 bind_check_card_r3.py 的实质差别有两处，都是这一轮新形态带来的：
1. 比对目标从底串摘要换成台账 send_sha256（前导声明一行＋底串逐字）。底串摘要仍记在 base_sha256，
   按 C135 写进卡面真源的还是它——备案与绑定是两件事，拿 base 去核盘面串会 85 条全判未命中。
2. 命中之外还要核 images：母图漏传＝投成裸串（探针实测裸串两枚出照片质感，一枚还带卡框与台标），
   而裸串那次连 prompt 都对不上（少前导一行）会被逐字列挡下；真正的漏法是「前导写了、图没挂」，
   那种发起 prompt 逐字相等、只有 images 列能判红。所以本件按台账 ref_image 的文件名逐条核 images。
3. 逐字命中还不等于投出来了：额度墙（403 code 112）与参数校验失败都是「串发进去了、零产物」，
   而该条 landing 路径上压着的是上一轮判废的旧图——只看在盘与否会把零产物洗成已投（本轮实测 D04／D20
   两枚命中、landing mtime 停在 04:09／04:13 的旧版，证据行根本没有）。所以命中之后按逐片证据行
   （sent_shard*.jsonl 的 landing_sha256）与落地实读字节对拍，分「落盘相符／零产物／落盘漂移」三档，
   续投差集只认「落盘相符」那一档。发名也分档：放量臂 card3x4r4-<id>、探针 card3x4r4ref-/probe-、
   其余记异名——探针可以合法地借别的母图（本轮 L001 探针挂 L016 而台账派 L010），混在一档会把
   探针的母图偏差算成放量违例，反过来也会把放量违例藏在探针里。

回绑源＝派单登记R4.json 里各分片的 transcript ＋ 主会话 jsonl（违例补投由主会话直投）。
transcript 在会话临时区、跨会话会失效，故逐份的在盘状态、字节数与 sha 前缀都落进仓内登记件，缺失显式计数。
"""
import glob
import hashlib
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "数据", "卡面主图提示词3x4", "投放台账R4.json")
REG = os.path.join(ROOT, "数据", "卡面主图提示词3x4", "派单登记R4.json")
OUT = os.path.join(ROOT, "数据", "卡面主图提示词3x4", "回绑源登记R4.json")
EVID = os.path.join(os.path.dirname(ROOT), "_scratch_cardref", "card3x4_r4")
# 本轮自己的发名前缀：放量臂与两种探针。用了这些名字却没命中台账串＝发送侧字符损坏，须判红；
# 往轮／别组的发名不命中是预期。提成常量是为了让负测能对它做变异（置空即该支空转）。
ROUND_NAME_PREFIXES = ("card3x4r4-", "card3x4r4ref-", "card3x4r4probe-")
SESSION = os.path.expanduser('~') + r'/.qoder-cn/projects/C--Users-TIMASTER-Documents-Qoder-2026-10-29-c8c10ff8/6b39cfae-e2ed-48a8-81fd-0af6e4887eda'


def norm_sha(text):
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def iter_tool_inputs(path):
    """递归 walk 取所有 ImageGen 的 tool_use input（含 prompt 与 images 两路）。"""
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
                elif not isinstance(cur, str):
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


def sources(reg, session=SESSION):
    """登记件里的 transcript ＋ 主会话 jsonl；在盘与否按扫的这一刻实测，不信登记时的快照
    （transcript 在会话临时区，登记之后被清掉是常态），不在盘的显式列进缺失，不拿缺失当通过。"""
    hit, gone = [], []
    for s in reg["卡面分片"]:
        for h in s["命中"]:
            p = h["transcript"]
            (hit if os.path.isfile(p) else gone).append((("分片%d" % s["分片"]), p))
    main = os.path.abspath(session + ".jsonl").replace("\\", "/")
    (hit if os.path.isfile(main) else gone).append(("主会话", main))
    return hit, gone


def send_form(name, cid):
    """发名分档：放量臂逐字等于 card3x4r4-<id>；探针另立一档；其余是异名（串对了名字不对，也是违例）。"""
    if name == "card3x4r4-%s" % cid:
        return "放量"
    if name.startswith("card3x4r4ref-") or name.startswith("card3x4r4probe-"):
        return "探针"
    return "异名"


def load_evidence(evid_dir):
    """逐片证据行 → id → [(文件, 行)]。只认带 landing＋landing_sha256 的行：
    探针证据（sent_shard_probe_ref.jsonl）没有落点字段，它是「产物留在 vibe_images」的凭据，不是落盘凭据。"""
    ev, files = {}, sorted(glob.glob(os.path.join(evid_dir, "sent_shard*.jsonl")))
    files = [os.path.abspath(p).replace("\\", "/") for p in files]
    for p in files:
        with io.open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                if not r.get("landing") or not r.get("landing_sha256"):
                    continue
                ev.setdefault(r["id"], []).append((os.path.abspath(p).replace("\\", "/"), r))
    return ev, files


def landing_state(item, ev, root):
    """命中之后这一发到底有没有落下来。返回（判档, 实读 sha12, 证据 sha12）。
    零产物＝没有本轮证据行（403／参数校验失败／探针未 copy）；此时 landing 在盘也不算，那是上一轮的旧图。"""
    rows = ev.get(item["id"]) or []
    if not rows:
        return "零产物", "", ""
    path, r = rows[-1]
    want_sha = r["landing_sha256"]
    if r.get("status") != "ok":
        return "证据非ok", "", want_sha[:12]
    land = os.path.join(root, item["landing"])
    # 比归一后的绝对路径，不比 basename：只比文件名会让「数据/别处/D01.png」混过（负测 test_d2 实测）。
    if os.path.normcase(os.path.abspath(r["landing"])) != os.path.normcase(os.path.abspath(land)):
        return "落点不符", "", want_sha[:12]
    if not os.path.isfile(land):
        return "落盘缺失", "", want_sha[:12]
    with open(land, "rb") as fh:
        got = hashlib.sha256(fh.read()).hexdigest()
    return ("落盘相符" if got == want_sha else "落盘漂移"), got[:12], want_sha[:12]


def scan(led, reg, root, paste_dir, evid_dir, session=SESSION):
    """回绑扫描本体（与落盘路径解耦，便于 tempfile 夹具做违例负测）。返回（登记件 dict, rc）。"""
    items = {it["id"]: it for it in led["items"]}
    # 送入串的两个合法形态只差结尾换行（paste 逐字节不带结尾换行，子代理从文件读有时会带上）：
    # 都收，但命中形态要分档计数——R3 实测「去结尾换行 112／含结尾换行 3」，混成一档就看不见换行漂移。
    by_sha = {}
    for it in led["items"]:
        p = os.path.join(paste_dir, "%s.txt" % it["id"])
        with io.open(p, encoding="utf-8", newline="") as fh:
            text = fh.read()
        # paste 逐字节复验＝台账 send_sha256：这一列对不上，后面所有「命中」都不作数。
        assert norm_sha(text) == it["send_sha256"], (it["id"], "paste 字节与台账 send_sha256 不符")
        by_sha[it["send_sha256"]] = (it["id"], "去结尾换行")
        by_sha[norm_sha(text + "\n")] = (it["id"], "含结尾换行")
    ev, ev_files = load_evidence(evid_dir)
    srcs, missing = sources(reg, session)
    hits, ref_bad, rows, detail = {}, {"放量": set(), "探针": set(), "异名": set()}, [], []
    bad_name, unmatched_names, round_unmatched = [], {}, []
    for label, path in srcs:
        with open(path, "rb") as fh:
            raw = fh.read()
        n_sent = matched = 0
        forms, arms = {}, {}
        for inp in iter_tool_inputs(path):
            n_sent += 1
            name = str(inp.get("name") or "")
            got = by_sha.get(norm_sha(inp["prompt"]))
            if got is None:
                unmatched_names[name] = unmatched_names.get(name, 0) + 1
                # 本轮发名却没命中台账串＝发送侧字符损坏（§32.4）。往轮／别组的发名不命中是预期，
                # 但 card3x4r4-／card3x4r4ref-／card3x4r4probe- 是本轮自己的名字，混进「未命中分布」
                # 不判红就等于把改坏的串当成没投过——主链侧 F007 被插 442 字声明正是这一类。
                if name.startswith(ROUND_NAME_PREFIXES):
                    round_unmatched.append({"来源": label, "发名": name, "送入字符数": len(inp["prompt"]),
                                            "送入sha12": norm_sha(inp["prompt"])[:12]})
                continue
            cid, form = got
            matched += 1
            forms[form] = forms.get(form, 0) + 1
            arm = send_form(name, cid)
            arms[arm] = arms.get(arm, 0) + 1
            hits.setdefault(cid, 0)
            hits[cid] += 1
            want = os.path.basename(items[cid]["ref_image"])
            got_imgs = [os.path.basename(str(x.get("source") if isinstance(x, dict) else x))
                        for x in (inp.get("images") or [])]
            ref_ok = want in got_imgs
            if not ref_ok:
                ref_bad[arm].add(cid)
            if arm == "异名":
                bad_name.append({"id": cid, "来源": label, "发名": name})
            state, got_sha, ev_sha = landing_state(items[cid], ev, root)
            detail.append({"id": cid, "来源": label, "发名": name, "发名档": arm, "命中形态": form,
                           "size": inp.get("size"), "母图相符": ref_ok,
                           "台账母图": want, "实挂母图": got_imgs,
                           "落盘判": state, "落地sha12": got_sha, "证据sha12": ev_sha})
        rows.append({"来源": label, "transcript": path, "字节": len(raw),
                     "sha256_12": hashlib.sha256(raw).hexdigest()[:12],
                     "ImageGen送入次数": n_sent, "逐字命中台账送入串数": matched,
                     "未命中数": n_sent - matched, "命中形态": forms, "命中发名档": arms})
    unmatched = [i for i in items if i not in hits]
    states = {}
    for d in detail:
        if d["发名档"] != "放量":
            continue
        states.setdefault(d["落盘判"], []).append(d["id"])
    landed = sorted(set(states.get("落盘相符", [])))
    drift = sorted(set(states.get("落盘漂移", []) + states.get("落盘缺失", [])
                       + states.get("落点不符", []) + states.get("证据非ok", [])))
    rc = 1 if (drift or bad_name or round_unmatched or ref_bad["放量"] or ref_bad["异名"] or missing) else 0
    out = {
        "declaration": "card3x4_R4（85 枚画风判废母图臂重投）的逐字回绑登记件。回绑源＝派单登记R4.json 里各分片 transcript "
                       "＋ 主会话 jsonl 中 ImageGen 的 tool_use input；prompt 归一（CRLF→LF）后与台账 send_sha256 对拍，"
                       "images 那一路按台账 ref_image 的文件名逐条核，再按逐片证据行的 landing_sha256 与落地实读字节对拍。"
                       "三条都对上才算本轮真投出来那一发：漏挂母图的发起串面逐字相等，只看串会把它投成裸串这一事实洗掉；"
                       "403／参数校验失败的发起串面也逐字相等，只看串（或只看 landing 在盘）会把零产物洗成已投——"
                       "那条 landing 上压着的是上一轮判废旧图。续投差集只认「放量已落盘条目」。",
        "登记时刻": reg.get("登记时刻", ""),
        "统计面": "台账 %d 条；回绑源在盘 %d 份、缺失 %d 份；证据文件 %d 份（只认带 landing＋landing_sha256 的行，"
                  "探针证据无落点字段故不计）；逐字命中按 id 去重计数，同 id 多次送入记入「同条多枚」；"
                  "发名分「放量 card3x4r4-<id>／探针 card3x4r4ref-|probe-／异名」三档，落盘判与母图判红都只在放量＋异名档上算，"
                  "探针档的母图偏差单列（探针可合法借别的放行枚）；「未命中发名分布」按发名逐条归因，"
                  "往轮与别组的送入不命中本轮台账是预期、不是违例，但本轮自己的发名（card3x4r4-／ref-／probe-）"
                  "却未命中的发起另立「本轮发名却未命中」并判红——那是发送侧字符损坏，不是没投过"
                  % (led["条数"], len(srcs), len(missing), len(ev_files)),
        "回绑源在盘份数": len(srcs), "缺失份数": len(missing),
        "缺失清单": [x[1] for x in missing],
        "证据文件": ev_files,
        "命中形态合计": {k: sum((r["命中形态"].get(k) or 0) for r in rows) for k in ("去结尾换行", "含结尾换行")},
        "命中发名档合计": {k: sum((r["命中发名档"].get(k) or 0) for r in rows) for k in ("放量", "探针", "异名")},
        "ImageGen送入合计": sum(r["ImageGen送入次数"] for r in rows),
        "逐字命中合计": sum(r["逐字命中台账送入串数"] for r in rows),
        "未命中合计": sum(r["未命中数"] for r in rows),
        "未命中发名分布": dict(sorted(unmatched_names.items())),
        "本轮发名却未命中": round_unmatched,
        "台账条目被逐字命中数": len(hits), "未被命中条目": unmatched,
        "放量已落盘条目数": len(landed), "放量已落盘条目": landed,
        "放量落盘判分布": {k: sorted(set(v)) for k, v in sorted(states.items())},
        "放量落盘异常条目": drift,
        "母图未对上的条目": {k: sorted(v) for k, v in ref_bad.items() if v},
        "发名不符的命中": bad_name,
        "同条多枚": {k: v for k, v in hits.items() if v > 1},
        "逐条明细": detail,
        "逐份明细": rows,
    }
    return out, rc


def main():
    if not os.path.isfile(REG):
        print("✗ 派单登记件缺失：%s：先跑 工具/register_r4_transcripts.py" % REG)
        return 1
    led = json.load(io.open(LEDGER, encoding="utf-8"))
    reg = json.load(io.open(REG, encoding="utf-8"))
    out, rc = scan(led, reg, ROOT, os.path.join(EVID, "paste"), EVID)
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print("回绑源在盘 %d／缺失 %d｜送入 %d｜逐字命中 %d｜未命中 %d｜被命中条目 %d／未命中条目 %d"
          % (out["回绑源在盘份数"], out["缺失份数"], out["ImageGen送入合计"], out["逐字命中合计"],
             out["未命中合计"], out["台账条目被逐字命中数"], len(out["未被命中条目"])))
    print("发名档 %s｜放量落盘判 %s｜放量已落盘 %d 枚｜母图未对上 %s｜发名不符 %d｜本轮发名却未命中 %d｜EXIT=%d"
          % (out["命中发名档合计"], {k: len(v) for k, v in out["放量落盘判分布"].items()},
             out["放量已落盘条目数"], out["母图未对上的条目"], len(out["发名不符的命中"]),
             len(out["本轮发名却未命中"]), rc))
    if out["本轮发名却未命中"]:
        print("✗ 本轮发名却未命中（发送侧字符损坏）", out["本轮发名却未命中"][:5])
    if out["放量落盘异常条目"]:
        print("✗ 放量落盘异常", out["放量落盘异常条目"])
    if out["发名不符的命中"]:
        print("✗ 发名不符", out["发名不符的命中"][:5])
    if out["母图未对上的条目"].get("放量"):
        print("✗ 放量母图未对上", out["母图未对上的条目"]["放量"])
    if out["缺失份数"]:
        print("✗ 缺失回绑源", out["缺失清单"][:5])
    return rc


if __name__ == "__main__":
    sys.exit(main())
