# -*- coding: utf-8 -*-
"""逐段与真源一致性核对（独立实现）：不复用 build_pending_manifest 的字符串切片，
改用字节级 count/find 在源文件里定位每段，并给出偏移量、命中次数与字节数。"""
import hashlib
import io
import json
import os

DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(DIR, "..", ".."))
with io.open(os.path.join(DIR, "pending_manifest.json"), encoding="utf-8") as fp:
    MANIFEST = json.load(fp)

SEG_KEYS = ["画风锚点", "取景指令_远景", "外观辨识", "人群与烟火气",
            "锁定与禁则", "全局硬设定", "tail_日面断言", "tail_远景塔约束",
            "English_tail"]
HEAD_KEYS = ["名录硬参数", "光照判定", "建议尺寸", "拍摄朝向"]


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


rows, total, miss, sha_where = [], 0, [], {}
for rec in MANIFEST["rows"]:
    path = os.path.join(ROOT, rec["prompt_file"])
    with io.open(path, "rb") as fh:
        raw = fh.read()
    txt = raw.decode("utf-8").replace("\r\n", "\n")
    crlf = b"\r\n" in raw
    hits = {}
    for k in SEG_KEYS:
        b = rec[k].encode("utf-8")
        cnt, off = raw.count(b), raw.find(b)
        hits[k] = {"命中次数": cnt, "字节偏移": off, "字节数": len(b)}
        total += 1
        if cnt < 1 or off < 0:
            miss.append("%s/%s" % (rec["id"], k))
    for k in HEAD_KEYS:
        b = rec["对应关系"][k].encode("utf-8")
        cnt = raw.count(b)
        hits["对应关系." + k] = {"命中次数": cnt, "字节偏移": raw.find(b), "字节数": len(b)}
        total += 1
        if cnt < 1:
            miss.append("%s/对应关系.%s" % (rec["id"], k))
    body = txt[txt.index("## 提示词正文"):]
    en = body[body.index("English tail: ") + len("English tail: "):].strip()
    cand = {"整文件": sha(txt), "提示词正文全段": sha(body), "English_tail": sha(en)}
    which = [k for k, v in cand.items() if v == rec["对应关系"]["prompt_sha256"]]
    sha_where["+".join(which) if which else "三种口径均不等"] = \
        sha_where.get("+".join(which) if which else "三种口径均不等", 0) + 1
    rows.append({"id": rec["id"], "源文件换行": "CRLF" if crlf else "LF",
                 "文件sha256": cand["整文件"],
                 "清单内prompt_sha256命中口径": which, "段核对": hits})

out = {"rows": len(rows), "段核对总数": total, "不一致段数": len(miss),
       "不一致清单": miss, "sha256口径计数": sha_where,
       "口径说明": ("清单内 prompt_sha256 与整文件/正文段/English tail 三种文件摘要均不等属预期："
                 "该值是「不含状态、摘要与回填字段的基准生成输入摘要」（工具/build_prompts.py:614 计算、"
                 ":664 定义），不是落盘文件的摘要。落盘文件是否为当前代生成物，改由重跑 build_prompts 后"
                 "看数据/开图提示词是否零变更来证。")}
with io.open(os.path.join(DIR, "src_consistency.json"), "w", encoding="utf-8") as _fh:
    json.dump(out, _fh,
              ensure_ascii=False, indent=1)
print("核对行 %d｜段核对 %d 处｜与真源不一致 %d" % (len(rows), total, len(miss)))
print("清单内 prompt_sha256 命中口径分布：" + "／".join(
      "%s %d 行" % (k, v) for k, v in sorted(sha_where.items())))
print("源文件换行分布：" + "／".join(sorted({
      "%s %d 行" % (nl, sum(1 for r in rows if r["源文件换行"] == nl))
      for nl in {r["源文件换行"] for r in rows}})))
if miss:
    print("不一致：" + "、".join(miss[:20]))
