# -*- coding: utf-8 -*-
"""R9 第二轮取景补重投（3 枚）·实际送入串台账：与 R4 同臂同母图，串面换成本轮取景模板。

与本轮（2026-11-22「投 3 枚」）的关系：C154 补记（8）把 20 个片区的取景段改成三类视点轮换，
D18／D19 正是片区、串面随之换了；L069 是地标、串未变。三条的画风臂、母图沿用 R4 台账原值
（C154(2)：已投出的条目按台账登记值复核），本轮唯一变量是「取景段换模板后的现串」。

成员面不手抄：从 `数据/下一轮重投候选.json` 里取「现态裁定以未定开头」的三条——候选表本身
已由闸门钉住（在册件 sha12、R8 读数与卡面/片区复验互指）。

跑法：python -X utf8 工具/reshoot_campaign_2026_11_06/build_send_bodies_r9.py
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
from build_send_bodies import body_of  # noqa: E402
from current_cells import current_cells  # noqa: E402

OUT = os.path.join(HERE, 'send_bodies_r9.json')
NOTE = os.path.join(HERE, 'send_bodies_r9_note.json')
R4 = os.path.join(HERE, 'send_bodies_r4.json')
SUFFIX = 'C154取景二次重投-v01'


def main():
    with io.open(os.path.join(ROOT, '数据', '下一轮重投候选.json'), encoding='utf-8') as _h35:
        cand = json.loads(_h35.read())
    ids = [r['id'] for r in cand['候选'] if r['现态裁定'].startswith('未定')]
    assert ids == ['D18', 'D19', 'L069'], ids
    with io.open(R4, encoding='utf-8') as _h38:
        r4 = json.loads(_h38.read())
    with io.open(os.path.join(ROOT, '数据', '开图清单.json'), encoding='utf-8') as _h40:
        man = {i['id']: i for i in json.loads(_h40.read())['items']}
    _q, cells, exc = current_cells(ROOT)
    assert not exc, exc
    cell = {r['id']: r['cell'] for r in cells}
    out, note = {}, {'成员面': ids, '串面': '现串正文逐字（C154 补记 8 之后的取景段）',
                     '母图': '沿用 R4 台账 ref_image 原值', '占格对象': 'current_cells 现读在册格'}
    for eid in ids:
        it = man[eid]
        name, _src, body = body_of(ROOT, eid)
        send = REF.send_body(body)
        out[eid] = {
            'body': body,
            'body_chars': len(body),
            'chars': len(send),
            'file': name,
            'size': it['size'],
            'ref_image': r4[eid]['ref_image'],
            'send_name': '%s-%s-%s' % (eid, it['name'], SUFFIX),
            'send_sha256': hashlib.sha256(send.encode('utf-8')).hexdigest(),
            'replaced_cell': cell[eid],
            'status_before': it['status'],
            '投次': 1,
        }
        note.setdefault('串面差异', {})[eid] = {
            'r4_body_sha12': hashlib.sha256(r4[eid]['body'].encode('utf-8')).hexdigest()[:12],
            'r9_body_sha12': hashlib.sha256(body.encode('utf-8')).hexdigest()[:12],
            '与 R4 逐字相同': body == r4[eid]['body'],
            '母图与 R4 相同': out[eid]['ref_image'] == r4[eid]['ref_image'],
        }
    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
    with io.open(NOTE, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(json.dumps(note, ensure_ascii=False, indent=2) + '\n')
    for eid in ids:
        print('%s｜%s｜body %d 字符｜send %s｜size %s｜ref %s｜与 R4 同串=%s'
              % (eid, out[eid]['file'], out[eid]['body_chars'], out[eid]['send_sha256'][:12],
                 out[eid]['size'], os.path.basename(out[eid]['ref_image']),
                 note['串面差异'][eid]['与 R4 逐字相同']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
