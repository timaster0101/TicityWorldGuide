# -*- coding: utf-8 -*-
"""R7 判废补重投（画风目视判废的 3 枚）·实际送入串台账：与 R4 同臂同母图，唯一变量是这一次抽取。

成员面现算，不手抄 ID 名单：真源 `数据/开图验收备注.json` 里每条 ID 最后一条带「R6 组画风目视」的结论行，
行内含「｜判废」的就是本轮待重投面（2026-11-20 那轮 310 枚目视给出 3 条）。

串面一个字都不动，理由与 R4 相同：送入串＝`r4_style_ref.PREFIX_LINE` 一行＋现串正文逐字，
逐字回绑比的是这一整串；C153 已把措辞杠杆打穿并整条回退，本轮不再加任何「不烤字」一类补丁串。
所以本生成器多一道 R4 没有的断言——本轮 body 必须与 `send_bodies_r4.json` 同条的 body 逐字节相等，
不等就说明正文或前导在两轮之间漂了，那笔钱花的就不是「同串重抽」，当场停手。

母图沿用 R4 台账里该条的 `ref_image` 原值（不重算分配）：`r4_style_ref.assign()` 的映射随成员面重排，
三轮名单单独重跑会把母图换掉，那样一次投放同时动了两个变量，判废原因（烤字／混档）也就无从归因。
分配口径在 C154(2) 写明：已投出的条目按台账登记的 ref_image 原值复核，不靠重算。

占格对象＝`current_cells()` 现读的在册格（本轮实测就是那条 C154母图重投 格），按行种取而不写死档串，
这样万一在册格在别处又被换过，台账钉的是「当下在册那一格」而不是历史那一格。

跑法：python -X utf8 工具/reshoot_campaign_2026_11_06/build_send_bodies_r7.py
"""
import hashlib
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
WORKSPACE = os.path.abspath(os.path.join(ROOT, '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, '工具'))
sys.path.insert(0, HERE)
import r4_style_ref as REF  # noqa: E402
from build_send_bodies import body_of, txt_sha  # noqa: E402
from current_cells import current_cells  # noqa: E402

OUT = os.path.join(HERE, 'send_bodies_r7.json')
NOTE = os.path.join(HERE, 'send_bodies_r7_note.json')
R4_LEDGER = os.path.join(HERE, 'send_bodies_r4.json')
PASTE_DIR = os.path.join(WORKSPACE, '_scratch_reshoot_r7', 'paste')
SUFFIX = 'C154判废补重投-v01'
VISUAL_HEAD = 'R6 组画风目视'
RELEASE_QUOTE = ('用户 2026-11-20 逐字「1 不用重跑」「2 重投」（两条点单，第 2 条原文另起一行）——'
                 '第 2 项指 §55.58 下一窗待办①「3 枚判废（D18／D19／L069）重投与投后接线」，'
                 '本轮放行面＝3 次付费调用（先探针 1 枚，绿了再投其余 2 枚）。')
TS = re.compile(r'_(1\d{12})_')


def judged_failed():
    """现读目视真源：每条 ID 最后一条「R6 组画风目视」结论行里带「｜判废」的，就是本轮成员面。"""
    with io.open(os.path.join(ROOT, '数据', '开图验收备注.json'), encoding='utf-8') as fp:
        notes = json.load(fp)['备注']
    todo, reviewed = [], 0
    for eid, rows in notes.items():
        hits = [s for s in rows if VISUAL_HEAD in s]
        if not hits:
            continue
        reviewed += 1
        tail = hits[-1]
        m = re.search(r'｜(达标|判废)（(\S+?档)）', tail)
        if m is None:
            raise SystemExit('%s 的目视结论行没有「｜达标／｜判废（X档）」标记，成员面取不出来' % eid)
        if m.group(1) == '判废':
            todo.append((eid, m.group(2)))
    return reviewed, sorted(todo)


def main():
    reviewed, todo = judged_failed()
    assert todo, '目视结论里一条判废都没有，本轮无事可做（先确认 R6 那轮结论是否已落笔）'
    with io.open(R4_LEDGER, encoding='utf-8') as fp:
        r4 = json.load(fp)
    with io.open(os.path.join(ROOT, '数据', '开图清单.json'), encoding='utf-8') as fp:
        man = json.load(fp)
    with io.open(os.path.join(ROOT, '数据', '提示词基准冻结.json'), encoding='utf-8') as fp:
        snap = json.load(fp)
    base = {e['id']: e['prompt_sha256'] for e in snap['entries']}
    by_id = {it['id']: it for it in man['items']}
    _q, cells_rows, excluded = current_cells(ROOT)
    cells = {r['id']: r for r in cells_rows}
    REF.check_pool(REF.LANDSCAPE, '主链横向母图')
    REF.check_pool(REF.PORTRAIT, '主链竖向母图')

    out = {}
    for eid, why in todo:
        item = by_id.get(eid)
        assert item, (eid, '清单里没有这条 ID')
        name, src, body = body_of(ROOT, eid)
        assert body.startswith('【画风锚点】'), eid
        sha = txt_sha(src)
        assert sha == item['prompt_sha256'], (eid, 'txt 去元数据摘要 ≠ 清单 prompt_sha256，真源与清单已分叉')
        assert sha == base.get(eid), (eid, '清单 prompt_sha256 ≠ 冻结快照：基准在冻结后变过')
        send = REF.send_body(body)
        assert eid in r4, (eid, 'R4 台账里没有这条，母图沿用与「同串重抽」断言都无从成立')
        assert send == r4[eid]['body'], (eid, '本轮送入串与 R4 逐字不等：动的不止一次抽取这个变量，停手')
        assert hashlib.sha256(send.encode('utf-8')).hexdigest() == r4[eid]['send_sha256'], eid
        ref_rel = r4[eid]['ref_image']
        assert os.path.isfile(os.path.join(ROOT, ref_rel.replace('/', os.sep))), (eid, ref_rel, 'R4 母图不在盘')
        ref_dims = REF.dims(ref_rel)
        size = item['size']
        assert size == r4[eid]['size'], (eid, '清单画幅与 R4 台账不符')
        assert ref_dims == size, (eid, ref_dims, size, '母图尺寸与本轮画幅不符，同画幅条件破了')
        assert not os.path.basename(ref_rel).startswith(eid), (eid, '母图就是被重投的那枚判废图')
        assert eid not in excluded, (eid, '在册格取不到：%s' % [x for x in excluded if x['id'] == eid])
        cell = cells[eid]
        assert cell['在盘'], (eid, '在册格不在盘：%s' % cell['cell'])
        files = list(item['image_file'] or [])
        hit = [f for f in files if os.path.basename(str(f)) == os.path.basename(cell['cell'])]
        assert len(hit) == 1, (eid, '在册格在清单 image_file 里命中 %d 枚（应恰 1）' % len(hit))
        out[eid] = {
            'group': 'R7_判废补重投',
            'file': '数据/开图提示词/' + name,
            'send_name': '%s-%s' % (name[:-4], SUFFIX),
            'size': size,
            'chars': len(send),
            'body_chars': len(body),
            'sha256': sha,
            'send_sha256': hashlib.sha256(send.encode('utf-8')).hexdigest(),
            'replaced_cell': cell['cell'],
            'untouched_cells': [f for f in files if f != cell['cell']],
            'status_before': item['status'],
            'body': send,
            'ref_image': ref_rel,
            'ref_dims': ref_dims,
            '占格口径': '替换 %s 那一格（R6 目视判废、本轮同串同母图重抽）' % cell['档串'],
            '判废原因': why,
            'R4_落盘': os.path.basename(r4[eid].get('replaced_cell') or '') or None,
            '投次': 1,
        }

    os.makedirs(PASTE_DIR, exist_ok=True)
    for eid, rec in out.items():
        p = os.path.join(PASTE_DIR, '%s.txt' % eid)
        with io.open(p, 'w', encoding='utf-8', newline='') as fp:
            fp.write(rec['body'])
        with open(p, 'rb') as fp:
            assert hashlib.sha256(fp.read()).hexdigest() == rec['send_sha256'], (eid, 'paste 落盘后自证不等')
    meta = {
        'declaration': ('R7 判废补重投（画风目视判废 %d 条）实际送入串台账见 %s，本件是轮次级口径说明。'
                        'body＝ImageGen 真实送入的整串（前导声明一行＋现串正文逐字），与 send_bodies_r4.json '
                        '同条逐字节相等（已 assert）；sha256＝冻结基准的 prompt_sha256，按 C135 绑的是它。'
                        % (len(out), os.path.basename(OUT))),
        '臂': '现串正文逐字＋跨题材画风母图（图生图）——与 R4 完全同臂同母图，本轮唯一变量是这次抽取',
        '放行原话': RELEASE_QUOTE,
        '前导声明': REF.PREFIX_LINE,
        '成员面': {'目视参与': reviewed, '本轮待重投': len(out),
                  '逐条判废档': {eid: v['判废原因'] for eid, v in sorted(out.items())}},
        '母图沿用': {eid: v['ref_image'] for eid, v in sorted(out.items())},
        '画幅分布': {v['size']: sum(1 for x in out.values() if x['size'] == v['size'])
                     for v in sorted(out.values(), key=lambda x: x['size'])},
        '统计面': ('成员面＝备注里末条「%s」结论行的「｜判废」现算；串面＝数据/开图提示词/<ID>-*.txt 逐字截正文段，'
                   '并与 R4 台账逐字节对拍；占格＝current_cells() 现读的在册格（本轮实测档串 %s）。'
                   % (VISUAL_HEAD, 'C154母图重投')),
        '条数': len(out),
    }
    with io.open(NOTE, 'w', encoding='utf-8', newline='\n') as fp:
        json.dump(meta, fp, ensure_ascii=False, indent=1)
        fp.write('\n')
    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1, sort_keys=True)
        fp.write('\n')
    print('R7 台账 %d 条｜目视参与 %d／本轮待重投 %d（判废档 %s）'
          % (len(out), reviewed, len(out),
             '、'.join('%s:%s' % (e, w) for e, w in todo)))
    print('  与 R4 逐字节相等：已逐条 assert（send_sha256 全等）｜母图沿用 %s'
          % '／'.join(sorted(os.path.basename(v['ref_image'])[:12] for v in out.values())))
    print('  画幅分布 %s｜送入串字数 %s'
          % (meta['画幅分布'], '／'.join('%s=%d字符' % (e, v['chars']) for e, v in sorted(out.items()))))
    print('  paste 落盘 %d 份（逐字节自证 send_sha256）→ %s' % (len(out), PASTE_DIR.replace('\\', '/')))
    print('  台账 %s %d 字节｜note %s %d 字节'
          % (OUT.replace('\\', '/'), os.path.getsize(OUT),
             os.path.basename(NOTE), os.path.getsize(NOTE)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
