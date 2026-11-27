# -*- coding: utf-8 -*-
"""C155 在册裁定收口：把「在册接受／不重投」的裁定落成逐条可追溯的一行，状态停在待复验。

为什么不能走 C139 代签：代签的绑串凭据是 image_prompt_sha256＝当前 prompt_sha256，而这几条的
在册格是 C154 取景换档**之前**的串所出——换档申报只「撤销绑定、不补绑」，那一格没有任何一份投后读数
能证明它与今天这条串逐字相等（历史轮的读数是当时的事实，不能当今天的证明）。绑上去，等于把一张
旧串产物记成新串产物；不绑又过不了 check_sign_declaration 的「已验收必须复述绑定摘要」。
所以这 7 条的收口只能是：裁定入账、状态保持待复验、不绑串、写明须重投方能签。

裁定内容不手抄：一律从 数据/下一轮重投候选.json 的「现態裁定」（在册接受／不重投）现取，
本脚本只补「委托来源、在册格、不可签理由」。

跑法：
    python 工具/ruling_closeout.py            干跑
    python 工具/ruling_closeout.py --execute  落盘（备注＋ 数据/在册裁定收口.json）
"""
import argparse
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / '数据' / '开图清单.json'
NOTES = ROOT / '数据' / '开图验收备注.json'
CANDIDATES = ROOT / '数据' / '下一轮重投候选.json'
ROUND_R10 = ROOT / '工具' / 'reshoot_campaign_2026_11_06' / 'round_readings_r10.json'
OUT = ROOT / '数据' / '在册裁定收口.json'

HEAD = 'C155在册裁定收口'
DELEGATION = '用户 2026-11-27 逐字「2 处理并收口」（对「还有待办的事情么」第 2 条的应答）'
KINDS = ('在册接受', '不重投')
MUST_SAY = ('不可签理由', '不绑串', '须重投')


def jload(p):
    with io.open(p, encoding='utf-8') as fp:
        return json.load(fp)


def r10_basenames(path=ROUND_R10):
    if not Path(path).exists():
        return set()
    return {os.path.basename(r['file']) for r in jload(path)['rows']}


def candidates_rows():
    """候选表现态裁定：id → 裁定原文。表里没有的条不属收口面。"""
    d = jload(CANDIDATES)
    rows = d.get('候选') or d.get('条目') or d.get('rows') or d.get('items') or []
    out = {}
    for r in rows:
        raw = (r.get('现态裁定') or '').strip()
        if raw.startswith(KINDS):
            out[r['id']] = raw
    return out


def switch_declared(notes, eid):
    """该条是否申报过 C154 取景换档（只撤销绑定、不补绑）——决定这一格能不能绑串。"""
    return any('C154取景换档申报' in r for r in notes.get(eid, []))


def cell_of(item):
    """在册的重投期格：取第一枚带 vNN 档串的格；没有则返回 None。"""
    for f in item.get('image_file') or []:
        base = os.path.basename(str(f).replace('\\', '/'))
        if '-v01_' in base:
            return base
    return None


def build_row(item, notes, ruling, r10):
    eid = item['id']
    cell = cell_of(item)
    parts = ['裁定=' + ruling, '委托来源=' + DELEGATION]
    if not cell:
        parts.append('在册格=无（该条只有四向外挂载，没有重投期格）')
    else:
        parts.append('在册格=' + cell)
        parts.append('该格本串投后读数=' + ('有' if cell in r10 else '无'))
    parts.append('不可签理由=该格是 C154 取景换档前的串所出，换档申报只撤销绑定、不补绑，'
                 '没有任何投后读数能证明它与今天这条串逐字相等；绑串即把旧串产物记成新串产物')
    parts.append('处置=状态保持待复验、不绑串；须重投一版本串产物方能走 C139 代签')
    return '%s%s：' % (HEAD, eid) + '；'.join(parts)


def audit(row, item):
    """收口行的判据：抬头点名本人、裁定档在册、要素齐全。"""
    eid = item['id']
    bad = []
    if not row.startswith('%s%s：' % (HEAD, eid)):
        bad.append('收口行抬头点名的 ID 与本条不符')
    if '裁定=' not in row:
        bad.append('收口行缺裁定原文')
    for tok in MUST_SAY:
        if tok not in row:
            bad.append('收口行缺要素:' + tok)
    return bad


def ruleable(manifest, notes, cand, r10):
    """哪些条该收口：候选表有在册裁定／不重投、清单仍待复验、且在册格无本串投后读数。"""
    out, refused = [], []
    for item in manifest['items']:
        eid = item['id']
        ruling = cand.get(eid)
        if not ruling:
            continue
        if item.get('status') != '待复验':
            refused.append('%s 状态＝%s，不在待复验面，不收口' % (eid, item.get('status')))
            continue
        cell = cell_of(item)
        if cell and cell in r10:
            refused.append('%s 的在册格已有本串投后读数（%s），该走 C139 代签而不是裁定收口' % (eid, cell))
            continue
        if cell and not switch_declared(notes, eid):
            refused.append('%s 的在册格无本串读数，但也没有换档申报，来源不清、不收口' % eid)
            continue
        row = build_row(item, notes, ruling, r10)
        viol = audit(row, item)
        if viol:
            refused.append('%s 收口行不合规格：%s' % (eid, viol))
            continue
        out.append((item, ruling, row))
    return out, refused


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--execute', action='store_true')
    args = ap.parse_args()

    manifest = jload(MANIFEST)
    notes_doc = jload(NOTES)
    notes = notes_doc['备注']
    cand = candidates_rows()
    r10 = r10_basenames()
    plan, refused = ruleable(manifest, notes, cand, r10)

    print('候选表现态裁定（在册接受／不重投）%d 条：%s' % (len(cand), sorted(cand)))
    print('本轮收口 %d 条；不收口 %d 条' % (len(plan), len(refused)))
    for r in refused:
        print('   · %s' % r)
    for item, ruling, row in plan:
        print('   ✓ %s：%s' % (item['id'], ruling))
        print('      %s' % row)
    if not args.execute:
        print('（干跑，未落盘。加 --execute 才写备注与 %s）' % OUT.name)
        return 0
    for item, ruling, row in plan:
        notes.setdefault(item['id'], []).append(row)
        # 占格时申报过「维持原绑定」的过期绑定一并撤销：这一格的串已换、图未重投，留着就是假绑定。
        item.pop('image_prompt_sha256', None)
    with io.open(NOTES, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(json.dumps(notes_doc, ensure_ascii=False, indent=2) + '\n')
    with io.open(MANIFEST, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    doc = {
        '口径': 'C155：在册接受／不重投的裁定入账；状态保持待复验、不绑串、须重投方能签。',
        '委托来源': DELEGATION,
        '统计': {'收口': len(plan), '不收口': len(refused), '裁定面': len(cand)},
        '逐条': [{'ID': i['id'], '裁定': r, '在册格': cell_of(i), '状态': i.get('status')} for i, r, _ in plan],
    }
    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(json.dumps(doc, ensure_ascii=False, indent=2) + '\n')
    print('✅ 已落盘：收口 %d 条 → %s' % (len(plan), OUT.name))
    return 0


if __name__ == '__main__':
    sys.exit(main())
