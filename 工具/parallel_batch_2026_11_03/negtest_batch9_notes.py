# -*- coding: utf-8 -*-
"""check_notes_vs_source 的违例负测：把人工笔记逐类改错，闸门必须逐类判红。
没有这一份，「核对项 576｜不符 0」只是一句绿灯，看不出它到底管不管得住篡改。"""
import io, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_notes_vs_source as gate

measure, manifest, src = gate.load()
text = io.open(gate.NOTES, encoding="utf-8").read()
rows, concl, bad, checks = gate.run(text, measure, manifest, src)
assert bad == [], "基线本身就不干净，负测无从判起：%s" % bad[:3]
print("基线：小节 %d｜核对项 %d｜不符 %d" % (len(rows), checks, len(bad)))


def sec_of(sid):
    m = re.search(r"(?m)^## %s .*?(?=^## L|\Z)" % sid, text, re.S)
    assert m, sid
    return m.group(0)


hits = [0]


def tamper(old, new, sid, keyword, expect_ids=None):
    """只替换第一处命中，保证改的是一个已知小节；闸门必须报出含 keyword 的不符。"""
    assert old in sec_of(sid), (sid, old)
    _, _, tbad, _ = gate.run(text.replace(old, new, 1), measure, manifest, src)
    assert tbad, (sid, keyword, "篡改后仍全绿")
    hit = [b for b in tbad if keyword in b[1]]
    assert hit, (sid, keyword, "报了别的不符：%s" % tbad[:2])
    if expect_ids is not None:
        assert {b[0] for b in hit} == set(expect_ids), (sid, keyword, sorted({b[0] for b in hit}))
    hits[0] += 1
    print("  判红 ✓ %-14s %-14s → %s" % (sid, keyword, hit[0][1][:56]))


# L088 是本批唯一「通过」小节，读数齐、锁定值与 tail 都在，拿它当被改对象最干净。
S = "L088"
sha = gate.SHA.search(sec_of(S)).group(1)
tamper("/ %s；" % sha, "/ %s；" % ("0" + sha[1:] if sha[0] != "0" else "1" + sha[1:]), S, "sha12 不符")
b = gate.BYTES.search(sec_of(S)).group(1)
tamper("✓ / %s /" % b, "✓ / %s /" % (b[:-1] + ("7" if b[-1] != "7" else "3")), S, "字节不符")
lock = re.search(r"锁定(\d+)层(\d+)米", sec_of(S))
tamper(lock.group(0), "锁定%d层%s米" % (int(lock.group(1)) + 1, lock.group(2)), S, "锁定不符", [S])
tamper("facing%s " % gate.HEAD.match(sec_of(S)).group(5), "facing0 ", S, "facing 不符")
dims = "%sx%s" % (gate.HEAD.match(sec_of(S)).group(3), gate.HEAD.match(sec_of(S)).group(4))
tamper("（%s，" % dims, "（1024x1024，", S, "尺寸与测得不符")
so = gate.SUN_OUT.search(sec_of(S)) or gate.SUN_IN.search(sec_of(S))
tamper(so.group(0), so.group(0).replace(so.group(1), "%d" % (int(so.group(1)) + 1), 1), S, "日面引文与真源 tail 不符")
tamper(sec_of(S).split("- 结论：")[0].split("\n")[-1] + "- 结论：" +
       sec_of(S).split("- 结论：")[1].split("\n")[0], "", S, "无结论行")
tamper("## %s " % S, "## %s 名字被改" % S, S, "名称不符")
# HEADER 不可解析：ID 头保留、括注参数破坏，小节整节被闸门认不出来（改 ID 头会让 split 断点消失，
# 内容被并进上一节，反而测不到这一支，所以必须破坏参数段而不是前缀）。
tamper("（1536x1024，facing", "（宽1536 米，facing", S, "HEADER 不可解析")
# 半角数被改小：句式仍可解析，但组合句不在真源 tail 里，必须按「与真源不符」判红而不是放行。
tamper(so.group(0), so.group(0).replace(so.group(3), "%d" % (int(so.group(3)) + 2), 1), S, "日面引文与真源 tail 不符")

print("违例负测全部判红：%d 类篡改各命中一条不符" % hits[0])
