# -*- coding: utf-8 -*-
"""2026-11-22 用户十项点单第 ②③ 项：把两条裁定成文为「补记」追加进既有条目，不新增编号。

为什么不新增编号：`工具/test_costs.py:267 test_rulings_are_154` 钉 `len(rulings)==154` 且末条编号为 C154，
新开 C155 要同时改 13 处条数钉，而这两件事本身是既有条目语义的补齐（C153 的烤字边界、C134 的读数与目视关系），
属补记不属新裁。
怎么写：在原文里按 json 编码后的整串值定位（出现次数必须恰为 1），只把新段落接在该值闭引号之前，
文件其余字节一个不动——现读 409056 字节、937 行 CRLF，非 `json.dumps` 直出形态，整体重排会把历史正文的
行尾形态顶掉（那就不是补记而是重写）。
"""
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, '..', '数据', '设定裁定记录.json')
NOTES = os.path.join(HERE, '..', '数据', '开图验收备注.json')
CAMPAIGN = os.path.join(HERE, 'reshoot_campaign_2026_11_06')

IDS = ('R002 R008 R014 R016 R020 R030 R032 R037 R044 R046 R048 R053 R055 R056 '
       'R064 R066 R068 R070 R072 R076 R078 R080 R082 R084 R088 R090 R092 R116')

ADD153 = (
    "\n\n(7) **门侧红斗方的形近装饰字不构成 C152 烤字违例（2026-11-22 用户十项点单第 ② 项"
    "「红斗方裁定成文进 C153」；成员面与读数一律从 `数据/开图验收备注.json` 现算，脚本与条数钉都不手抄名单）**："
    "现读带「例外待裁」的行共 **28 行／28 条**，28 行的抬头全部以「2026-11-20 R6 组画风目视（核验人：Qoder 会话代理」起句，"
    "ID 面＝%s。缺陷句实测五种写法（逐字，只截到「复核方式」之前）：20 × 「例外待裁：门侧红斗方形近装饰字「福」」／"
    "4 × 「例外待裁：门侧红斗方形近装饰字「福」，笔画不成清晰真字，按伪汉字放行」／"
    "2 × 「例外待裁：门侧红斗方为传统装饰字，厚涂下形近「福」但笔画不成清晰真字，按伪汉字放行，请签收轮复核」／"
    "1 × 「例外待裁：门侧红底斗方形近装饰字「福」」（R032）／"
    "1 × 「例外待裁：玻璃门侧红斗方形近装饰字「福」」（R068）；28 行全部含「福」，"
    "其中 6 行自带放行结论、22 行只登记缺陷没写结论。"
    "这 22 行的「待裁」不是图有问题没结论，而是同一件事缺一句话成文判词，逐条等裁＝22 次人工重复裁定同一件事。\n"
    "  **裁定**：单个节令装饰字（斗方、春联单字、幌子上的吉祥字）按纹样读、不按文案读，"
    "不属 C152「不烤文案／不烤标识」违例，也不据此判废。判据是「能不能拼读成句」而不是「像不像字」："
    "C152 拦的是可拼读、可拼成句的文案与台标／签名／地面文字，笔触糊到拼不成字的形近装饰字落在禁令之外。"
    "这条与 C153 (1) 的措辞实验同向——厚涂档必然把小字糊掉，把「糊掉的装饰字」判成违例等于按轮次抽签判废。\n"
    "  **边界（不许往回扩）**：烤成可拼读成句的文案照旧判违例、判废重出，不走本通道。"
    "同轮在册的反面样本就是 L069：上一枚「主楼檐口白色横幅烤入完全可拼读汉字『云浦结算中心』」——那一条是违例，"
    "本条不为其开脱；判定线在可拼读性，不在载体是不是红纸。\n"
    "  **处置面**：这 28 条自本裁定起结为「装饰字不属 C152 烤字违例」，签收轮按本条判、不再逐条等裁。"
    "备注真源按既定制只追加，不回头改写那 28 行原文，所以五种历史写法原样保留，结案依据由本条承担；"
    "28 是成文当轮现读数，其后同类缺陷句按本裁定同样适用，不回来改本条数字。\n"
    "  **代价（写明再签）**：一次性覆盖 28 条意味着条目级复核不再发生。若人工目视发现某一枚的斗方其实拼得成句，"
    "处理是按上面的判定线单条判废重投（花钱调用，逐轮放行，先探针），而不是给那一枚另开例外通道。"
) % IDS

ADD134 = (
    "\n\n【2026-11-22 补记｜用户十项点单第 ③ 项「D19 CLIP 照片侧 0.963906 与目视达标之间写书面裁定」，"
    "同轮对 D19 画风面另裁原话「2 达标」】事实面（各轮 p_photo 逐字取自备注里对应目视行的「CLIP 旁证」括注，"
    "阈值取自 `工具/reshoot_campaign_2026_11_06/clip_style_r1_readings.json` 的 `正典对照.正典阈值`＝0.9023535）："
    "D19 四轮 p_photo＝R1 0.998775／R6 0.985188／R7 **0.963906**／R8 **0.843343**。"
    "R7 那枚人工目视判「达标（半写实数字厚涂档）」而读数落在照片侧，是本条降级以后唯一还悬着的读数—目视分歧。"
    "R8 是与 R7 **同一条送入串、同一张画风母图**的重抽：`send_bodies_r4.json`／`send_bodies_r7.json`／"
    "`send_bodies_r8.json` 三份台账里 D19 的 `send_sha256` 全等（前 12 位 `ee0cbe447f27`）、`ref_image` 同值"
    "（D11-北屏生态片区-E1定档-v01），本轮唯一变量＝这一次抽取；重抽后读数落到绘画侧，跨阈值挪了 0.120563。"
    "同向抖动的另两条同样单变量可查：D18 0.988365（R6）→0.369968（R7）→0.325434（R8），最大摆幅 0.618397；"
    "L069 0.122296（R6）→0.621543（R7）→0.833429（R8），而这枚的目视结论是 R7 判废、R8 画风栏达标——"
    "读数在判废那一枚上走低、在达标那一枚上走高，方向与目视相反。\n"
    "  **裁定**：人工目视结论不因 CLIP 读数改判，也不因 CLIP 读数跨过正典阈值改判；D19 R7 的「画风达标」维持。"
    "本条上文已把机检量降级为「只作读数、不作判据」，本补记钉住它的另一半——**读数同样不得反向用作推翻既有目视结论的证据**："
    "同串同母图重抽的轮间抖动（实测 0.12～0.62）本身就大于分档间距，而本条已实测同地点两档读数区间重叠（D03），"
    "拿一条自身抖动大于间距的线去否决一次逐张目视，等于用随机数复核眼睛。\n"
    "  **改判通道只有一条**：人工重看在册格原图，并在签收轮撤销该条结论——不由 `clip_style_r1.py` 的数字触发，"
    "也不由任何脚本代签（`accepted` 恒 0 的口径不变）。\n"
    "  **代价与用途收窄（写明）**：CLIP 面（现读 312 格：照片侧 53／绘画侧 259）从此只允许用于"
    "「人工目视优先排序」这一件事，不得用于分档、放量、判废、验收或任何闸门判定；"
    "跨轮比较只作观察记录。`工具/verify_readout_stance.py` 钉的是判据原句、C134 标注行、四件实验产物与读数表同集这四类事实，"
    "本补记不改它，也不新增读数阈值。取景与量级栏的缺陷（D19 远景未点名塔群、日盘 sun_blob_px=816 入画）"
    "按 C154(1) 另账处理，与本条无关，不因画风达标而勾销。"
)


def _splice(txt, code, extra):
    rules = json.loads(txt)
    hit = [r for r in rules if r['编号'] == code]
    assert len(hit) == 1, (code, len(hit))
    old_val = hit[0]['裁定']
    assert extra[:24] not in old_val, (code, '补记已在条目里，重跑会把同一段接第二遍')
    needle = json.dumps(old_val, ensure_ascii=False)
    assert txt.count(needle) == 1, (code, '编码后的原值在文件里出现 %d 次，定位不唯一，停手' % txt.count(needle))
    return txt.replace(needle, json.dumps(old_val + extra, ensure_ascii=False)), old_val


def _read(path):
    with io.open(path, encoding='utf-8', newline='') as fp:
        return fp.read()


def derive_face():
    """成文用的读数一律从真源现算并与本脚本写进裁定的数字对拍——补记里那些计数不是抄来的，是这一轮量出来的。"""
    import collections
    notes = json.loads(_read(NOTES))['备注']
    segs = []
    for eid, lines in sorted(notes.items()):
        for s in lines:
            if '例外待裁' in s and '复核方式' in s:
                segs.append((eid, s[s.index('例外待裁'):s.index('复核方式')].rstrip('。：')))
    assert len(segs) == 28 and len({e for e, _ in segs}) == 28, len(segs)
    for eid, seg in segs:
        assert seg.startswith('例外待裁：') and '福' in seg, (eid, seg[:40])
    shapes = collections.Counter(seg for _, seg in segs)
    assert len(shapes) == 5, dict(shapes)
    assert sorted(shapes.values()) == [1, 1, 2, 4, 20], dict(shapes)
    assert sum(1 for _, seg in segs if '按伪汉字放行' in seg) == 6
    assert IDS.split() == sorted({e for e, _ in segs}), 'ID 面与名单对不上'
    return shapes


def main():
    shapes = derive_face()
    with io.open(PATH, encoding='utf-8', newline='') as fp:
        raw = fp.read()
    notes_txt = _read(NOTES)
    for num in ('0.998775', '0.985188', '0.963906', '0.843343', '0.988365', '0.369968', '0.325434',
                '0.122296', '0.621543', '0.833429'):
        assert num in notes_txt, ('C134 补记里的 p_photo 读数 %s 在备注真源里找不到' % num)
    ledger = [json.loads(_read(os.path.join(CAMPAIGN, 'send_bodies_%s.json' % g))) for g in ('r4', 'r7', 'r8')]
    assert len({r['D19']['send_sha256'] for r in ledger}) == 1, 'D19 三轮送入串摘要不全等，C134 补记的单变量前提不成立'
    assert ledger[0]['D19']['send_sha256'].startswith('ee0cbe447f27')
    assert len({r['D19']['ref_image'] for r in ledger}) == 1, 'D19 三轮母图不全等'
    clip = json.loads(_read(os.path.join(CAMPAIGN, 'clip_style_r1_readings.json')))
    assert clip['正典对照']['正典阈值'] == 0.9023535, clip['正典对照']['正典阈值']
    assert clip['R1读数']['落在正典阈值照片侧的枚数'] == 53 and clip['R1读数']['行数'] == 312
    assert 0.843343 < 0.9023535 < 0.963906, 'R8 落绘画侧／R7 落照片侧这个说法与阈值对不上'
    before = json.loads(raw)
    assert len(before) == 154, '现读 %d 条，本脚本只做补记，不动条数' % len(before)
    assert before[-1]['编号'] == 'C154', '末条不是 C154'
    codes_before = [r['编号'] for r in before]

    for code, extra in (('C153', ADD153), ('C134', ADD134)):
        assert u'…' not in extra, (code, '补记里混进 U+2026 省略号，会被读成工具传输吞字')
        raw, old_val = _splice(raw, code, extra)
        _check = json.loads(raw)
        now = [r for r in _check if r['编号'] == code][0]['裁定']
        assert now == old_val + extra, (code, '补记接不上原值尾部')
        assert len(now) > len(old_val), (code, '长度没变＝没写进去')

    after = json.loads(raw)
    assert [r['编号'] for r in after] == codes_before, '编号序列变了'
    for a, b in zip(after, before):
        if a['编号'] in ('C153', 'C134'):
            assert a['裁定'].startswith(b['裁定']), (a['编号'], '历史正文被改写')
            assert all(a[k] == b[k] for k in a if k != '裁定'), (a['编号'], '除裁定外的键变了')
        else:
            assert a == b, ('非补记条目内容变了：' + a['编号'])
    assert raw.count('\r\n') == 937, '行尾形态变了（现读 937 行 CRLF）'
    assert '\r' not in raw.replace('\r\n', ''), '出现裸 CR'
    with io.open(PATH, 'w', encoding='utf-8', newline='') as fp:
        fp.write(raw)
    print('C153 裁定 %d→%d 字（+%d）｜C134 裁定 %d→%d 字（+%d）'
          % (len([r for r in before if r['编号'] == 'C153'][0]['裁定']),
             len([r for r in after if r['编号'] == 'C153'][0]['裁定']),
             len(ADD153),
             len([r for r in before if r['编号'] == 'C134'][0]['裁定']),
             len([r for r in after if r['编号'] == 'C134'][0]['裁定']),
             len(ADD134)))
    print('条数 %d→%d｜末条 %s｜编号序列未变｜非补记条目逐条相等｜CRLF 恒 937' % (len(before), len(after), after[-1]['编号']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
