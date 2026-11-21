# -*- coding: utf-8 -*-
"""R8 取景补重投（R7 目视画风达标、但取景与量级缺陷在册的 3 枚）·实际送入串台账：与 R4 同臂同母图。

成员面现算，不手抄 ID 名单：真源 `数据/开图验收备注.json` 里每条 ID 最后一条带「R7 组画风目视」的结论行，
行内出现「取景与量级栏」的就是本轮待重投面（2026-11-20 那轮 3 枚目视达标，逐枚另记了取景与量级缺陷）。
画风判定本身不参与本轮名单——三条都是「｜达标」，若把它们当判废面去取，本轮名单会是空集。

串面一个字都不动，理由与 R7 相同：送入串＝`r4_style_ref.PREFIX_LINE` 一行＋现串正文逐字，
逐字回绑比的是这一整串。取景缺陷的正解不是加措辞：C153 早把措辞杠杆打穿并整条回退，
C123 也已把「背景只许画【取景指令】逐一点名的对象」写进英文尾段并实投过，这轮违例是在那句已生效之后发生的。
所以本轮与 R4 同臂，多一道断言——body 必须与 `send_bodies_r4.json` 同条逐字节相等，不等就当场停手。

母图沿用 R4 台账里该条的 `ref_image` 原值（不重算分配），口径见 C154(2)：已投出的条目按台账登记值复核。

占格对象＝`current_cells()` 现读的在册格（本轮实测就是那条 C154判废补重投 格）。

跑法：python -X utf8 工具/reshoot_campaign_2026_11_06/build_send_bodies_r8.py
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

OUT = os.path.join(HERE, 'send_bodies_r8.json')
NOTE = os.path.join(HERE, 'send_bodies_r8_note.json')
R4_LEDGER = os.path.join(HERE, 'send_bodies_r4.json')
PASTE_DIR = os.path.join(WORKSPACE, '_scratch_reshoot_r8', 'paste')
SUFFIX = 'C154取景补重投-v01'
VISUAL_HEAD = 'R7 组画风目视'
DEFECT_MARK = '取景与量级栏'
RELEASE_QUOTE = ('用户 2026-11-21 逐字「1 重投」「2 达标」「3 提交并推送」「4 不用重跑」「5 处理」（五条点单，按 §55.59 '
                 '终报里那五条编号作答）——第 1 项指「三枚的取景与量级缺陷要不要再处理」，'
                 '本轮放行面＝3 次付费调用（探针 1 枚 D18 先行，绿了再投其余 2 枚）；'
                 '第 2 项裁 D19 画风面维持达标、不因 CLIP 照片侧读数改判、不劳人工复看。')
TS = re.compile(r'_(1\d{12})_')


def framing_defect_face():
    """现读目视真源：每条 ID 最后一条「R7 组画风目视」结论行里带「取景与量级栏」的，就是本轮成员面。"""
    with io.open(os.path.join(ROOT, '数据', '开图验收备注.json'), encoding='utf-8') as fp:
        notes = json.load(fp)['备注']
    todo, reviewed = [], 0
    for eid, rows in notes.items():
        hits = [s for s in rows if VISUAL_HEAD in s]
        if not hits:
            continue
        reviewed += 1
        tail = hits[-1]
        if DEFECT_MARK not in tail:
            continue
        m = re.search(r'｜(达标|判废)（(\S+?档)）', tail)
        if m is None:
            raise SystemExit('%s 的目视结论行没有「｜达标／｜判废（X档）」标记，画风面无法复核' % eid)
        if m.group(1) != '达标':
            raise SystemExit('%s 画风判废却进了取景面：取景轮不该接手画风判废条目' % eid)
        seg = re.search(DEFECT_MARK + r'[^：:]*[：:](.+?)。复核方式', tail, re.S)
        why = (seg.group(1).replace('\n', '、').strip() if seg else '')
        assert why, (eid, '取景与量级栏里没有正文，缺陷归因取不出来')
        todo.append((eid, why))
    return reviewed, sorted(todo)


def main():
    reviewed, todo = framing_defect_face()
    assert todo, 'R7 目视结论里一条取景缺陷都没记，本轮无事可做（先确认那轮的分栏是否落笔）'
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
        assert not os.path.basename(ref_rel).startswith(eid), (eid, '母图就是被重投的那枚缺陷图')
        assert eid not in excluded, (eid, '在册格取不到：%s' % [x for x in excluded if x['id'] == eid])
        cell = cells[eid]
        assert cell['在盘'], (eid, '在册格不在盘：%s' % cell['cell'])
        assert 'C154判废补重投' in cell['档串'], (eid, '在册格档串不是 R7 那一格：占格对象漂了，%s' % cell['档串'])
        files = list(item['image_file'] or [])
        hit = [f for f in files if os.path.basename(str(f)) == os.path.basename(cell['cell'])]
        assert len(hit) == 1, (eid, '在册格在清单 image_file 里命中 %d 枚（应恰 1）' % len(hit))
        out[eid] = {
            'group': 'R8_取景补重投',
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
            '占格口径': '替换 %s 那一格（R7 目视画风达标但取景与量级缺陷在册、本轮同串同母图重抽）' % cell['档串'],
            '取景缺陷栏': why,
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
        'declaration': ('R8 取景补重投（R7 目视画风达标而取景与量级缺陷在册 %d 条）实际送入串台账见 %s，本件是轮次级口径说明。'
                        'body＝ImageGen 真实送入的整串（前导声明一行＋现串正文逐字），与 send_bodies_r4.json '
                        '同条逐字节相等（已 assert）；sha256＝冻结基准的 prompt_sha256，按 C135 绑的是它。'
                        % (len(out), os.path.basename(OUT))),
        '臂': '现串正文逐字＋跨题材画风母图（图生图）——与 R4／R7 完全同臂同母图，本轮唯一变量是这次抽取；'
              '取景缺陷不加措辞，因为 C123 的「背景只许画逐一点名对象」与 English tail 的日盘出画句都已在串内生效',
        '放行原话': RELEASE_QUOTE,
        '前导声明': REF.PREFIX_LINE,
        '成员面': {'目视参与': reviewed, '本轮待重投': len(out),
                  '逐条取景缺陷': {eid: v['取景缺陷栏'] for eid, v in sorted(out.items())}},
        '母图沿用': {eid: v['ref_image'] for eid, v in sorted(out.items())},
        '画幅分布': {v['size']: sum(1 for x in out.values() if x['size'] == v['size'])
                     for v in sorted(out.values(), key=lambda x: x['size'])},
        '统计面': ('成员面＝备注里末条「%s」结论行的「%s」现算（三条画风判定均为达标，画风面不归本轮管）；'
                   '串面＝数据/开图提示词/<ID>-*.txt 逐字截正文段，并与 R4 台账逐字节对拍；'
                   '占格＝current_cells() 现读的在册格（本轮实测档串 %s，已 assert）。'
                   % (VISUAL_HEAD, DEFECT_MARK, 'C154判废补重投')),
        '条数': len(out),
    }
    with io.open(NOTE, 'w', encoding='utf-8', newline='\n') as fp:
        json.dump(meta, fp, ensure_ascii=False, indent=1)
        fp.write('\n')
    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1, sort_keys=True)
        fp.write('\n')
    print('R8 台账 %d 条｜目视参与 %d／本轮待重投 %d'
          % (len(out), reviewed, len(out)))
    for eid, why in todo:
        print('  %s 取景缺陷：%s' % (eid, why[:110]))
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
