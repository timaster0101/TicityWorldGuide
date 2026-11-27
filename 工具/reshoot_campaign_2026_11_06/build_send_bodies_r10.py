# -*- coding: utf-8 -*-
"""R10 取景换档后全量补投（14 枚）·实际送入串台账：R9 三枚照抄 + 未裁定 11 枚新出。

成员面怎么来的（不手抄名单）：
1. 待复验的片区＝`数据/开图清单.json` 里 status 为「待复验」且 id 以 D 开头（C154 补记 8 之后
   D01–D20 全部 20 条都被撤销绑定）；
2. 减掉候选表里已有现态裁定的（D09 卡面不重投、D06/D10/D11/D15/D12/D20 三对同构图在册接受）；
3. 再减掉 R9 已建台账的三条（其中 D18／D19 属片区样面，L069 是地标、串未变）；
剩 11 条＝本轮新出。三条 R9 成员照抄 send_bodies_r9.json 的 body 与发名，只在写盘前按盘上现态
复核 send sha 与占格，不重算母图（C154(2)：已建台账的条目按登记值复核）。

母图口径：R9 三条沿用 R4 台账 ref_image 原值；11 条新出按 `r4_style_ref.assign` 的确定性轮转，
在同一画幅子池（1792×1024 四枚 E1 定档件）里按 id 升序从第 0 位起摊平——理由见 assign docstring
（哈希分把缺陷集中复制，轮转把复用摊到 ⌈n/池⌉）。

跑法：python -X utf8 工具/reshoot_campaign_2026_11_06/build_send_bodies_r10.py
"""
import hashlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, '工具'))
sys.path.insert(0, HERE)
import r4_style_ref as REF  # noqa: E402
from build_send_bodies import body_of, txt_sha  # noqa: E402
from current_cells import current_cells  # noqa: E402

OUT = os.path.join(HERE, 'send_bodies_r10.json')
NOTE = os.path.join(HERE, 'send_bodies_r10_note.json')
R9 = os.path.join(HERE, 'send_bodies_r9.json')
R4 = os.path.join(HERE, 'send_bodies_r4.json')
SUFFIX = 'C154取景换档重投-v01'
PROBE = 'D18'


def load_json(rel):
    with io.open(os.path.join(ROOT, rel), encoding='utf-8') as fp:
        return json.loads(fp.read())


def members(man, cand):
    """14 条成员面：R9 三条 + 待复验片区减去已有裁定与 R9 成员后的余量。"""
    ruled = {r['id'] for r in cand['候选'] if not r['现态裁定'].startswith('未定')}
    r9_ids = [r['id'] for r in cand['候选'] if r['现态裁定'].startswith('未定')]
    nr = [i for i, it in man.items() if i.startswith('D') and it['status'] == '待复验']
    rest = sorted(set(nr) - ruled - set(r9_ids))
    assert r9_ids == ['D18', 'D19', 'L069'], r9_ids
    assert rest == ['D01', 'D02', 'D03', 'D04', 'D05', 'D07', 'D08',
                    'D13', 'D14', 'D16', 'D17'], rest
    return r9_ids, rest


def audit(man, ledger, cell, pool_dims):
    """台账对盘上现态的复核：逐条回绑串面正文、发名、母图、占格。返回问题表，空表才算过。

    抽成函数是为了负测能把同一套判据怼到篡改件上——判据只写一份，正反两跑。
    """
    bad = []
    for eid, row in ledger.items():
        it = man.get(eid)
        if it is None:
            bad.append('%s：不在开图清单' % eid)
            continue
        try:
            name, src, text = body_of(ROOT, eid)
        except Exception as e:  # noqa: BLE001 —— 缺失就是问题，别让异常冒成全批停
            bad.append('%s：取正文失败 %s' % (eid, e))
            continue
        if txt_sha(src) != it['prompt_sha256']:
            bad.append('%s：正文 sha 与清单 prompt_sha256 不等' % eid)
        if row.get('body') != text:
            bad.append('%s：台账 body 与盘上正文不是逐字相同' % eid)
        send = REF.send_body(row.get('body') or '')
        if row.get('send_sha256') != hashlib.sha256(send.encode('utf-8')).hexdigest():
            bad.append('%s：send_sha256 与实际送入串不符' % eid)
        if row.get('chars') != len(send):
            bad.append('%s：chars 与送入串长度不符' % eid)
        if row.get('file') != name:
            bad.append('%s：file 与清单地名不符' % eid)
        # 占格判据两种合法现态：回填前＝本轮要替换的那一格；回填后＝本轮自己那一枚接管了该格。
        # 写死只认 replaced_cell 会让台账在回填成功之后自己判红——那不是「回填断了」，是判据没跟上。
        live = cell.get(eid) or ''
        if live != row.get('replaced_cell') and row.get('send_name') not in live:
            bad.append('%s：占格与 current_cells 现读不符（既不是本轮要替换的那格，也不是本轮自己那一枚）：%s'
                       % (eid, live))
        ref = row.get('ref_image')
        if not ref or not os.path.isfile(os.path.join(ROOT, ref.replace('/', os.sep))):
            bad.append('%s：母图不在盘 %s' % (eid, ref))
        else:
            actual = REF.dims(ref)
            reg = pool_dims.get(ref)
            if reg is not None and actual != reg:
                bad.append('%s：母图实测 %s 与池登记 %s 不符' % (eid, actual, reg))
            if actual != it['size']:
                bad.append('%s：母图 %s 与被投尺寸 %s 不同画幅' % (eid, actual, it['size']))
    return bad


def main():
    man = load_json('数据/开图清单.json')
    man = {i['id']: i for i in man['items']}
    cand = load_json('数据/下一轮重投候选.json')
    r9_ids, rest = members(man, cand)
    r9 = load_json('工具/reshoot_campaign_2026_11_06/send_bodies_r9.json')
    r4 = load_json('工具/reshoot_campaign_2026_11_06/send_bodies_r4.json')
    _q, cells, exc = current_cells(ROOT)
    assert not exc, exc
    cell = {r['id']: r['cell'] for r in cells}
    pool = REF.check_pool(REF.LANDSCAPE, 'R10 横向下池')

    out, diff = {}, {}
    for eid in r9_ids:
        it = man[eid]
        name, src, body = body_of(ROOT, eid)
        assert txt_sha(src) == it['prompt_sha256'], eid
        send = REF.send_body(body)
        sha = hashlib.sha256(send.encode('utf-8')).hexdigest()
        assert sha == r9[eid]['send_sha256'], (eid, sha, r9[eid]['send_sha256'])
        out[eid] = dict(r9[eid])
        out[eid].update({'file': name, 'status_before': it['status'],
                         'replaced_cell': cell[eid], '批': 'R10（照抄 R9 串面）'})
        diff[eid] = {'来源': 'send_bodies_r9.json 逐字照抄',
                     'send_sha12': sha[:12],
                     '与 R4 逐字相同': body == r4[eid]['body']}

    for idx, eid in enumerate(rest):
        it = man[eid]
        name, src, body = body_of(ROOT, eid)
        assert txt_sha(src) == it['prompt_sha256'], eid
        assert it['size'] == '1792x1024', (eid, it['size'])
        ref_rel, ref_dims = REF.assign(pool, idx, it['size'])
        send = REF.send_body(body)
        sha = hashlib.sha256(send.encode('utf-8')).hexdigest()
        out[eid] = {
            'body': body,
            'body_chars': len(body),
            'chars': len(send),
            'file': name,
            'size': it['size'],
            'ref_image': ref_rel,
            'ref_dims': ref_dims,
            'send_name': '%s-%s-%s' % (eid, it['name'], SUFFIX),
            'send_sha256': sha,
            'replaced_cell': cell[eid],
            'status_before': it['status'],
            '投次': 1,
            '批': 'R10（本批新出）',
        }
        diff[eid] = {'来源': '本轮按现串新出',
                     'send_sha12': sha[:12],
                     '母图轮转序号': idx,
                     '与 R4 逐字相同': body == r4[eid]['body'] if eid in r4 else None}

    order = r9_ids + rest
    body = {eid: out[eid] for eid in order}
    pool_dims = dict(pool)
    bad = audit(man, body, cell, pool_dims)
    assert not bad, bad
    note = {
        '成员面': order,
        '成员数': len(order),
        '探针': PROBE,
        '串面': '现串正文逐字（C154 补记 8 之后的取景段）＋ r4_style_ref 前导一行',
        '母图': 'R9 三条沿用 R4 登记值；11 条新出按同画幅子池轮转（1792×1024 四枚）',
        '占格对象': 'current_cells 现读在册格',
        '串面差异': diff,
        '发法': '先发 %s 探针一枚；403 code 112 就地停手，其余 13 条不发；绿则续发' % PROBE,
    }
    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(json.dumps(body, ensure_ascii=False, indent=2) + '\n')
    with io.open(NOTE, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(json.dumps(note, ensure_ascii=False, indent=2) + '\n')
    for eid in order:
        print('%s｜%d 字符｜send %s｜ref %s｜%s'
              % (eid, out[eid]['chars'], out[eid]['send_sha256'][:12],
                 os.path.basename(out[eid]['ref_image']), out[eid]['send_name']))
    print('成员 %d 条，探针 %s' % (len(order), PROBE))
    return 0


if __name__ == '__main__':
    sys.exit(main())
