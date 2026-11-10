# -*- coding: utf-8 -*-
"""重投队列生成器：把「1056 格（画风判废）＋60 格（绑定关口）」做成机器可数、可续跑的台账。

队列不手抄：条目与格一律现读 数据/开图清单.json 的 image_file，分组口径写死在下面的判据里，
分界线来自 数据/提示词基准冻结.json（frozen_at）与 §54 关口A 的「图集 jpg 无毫秒时间戳＝定档前通道产物」。

两组口径：
  R1 画风判废重投：该条全部格都不带文件名毫秒时间戳（backup/数据/图集 那批 jpg），依 §54 关口A
     首批 32/32 同档判废＋C93 通道作废整批推定判废。
     配额口径（C137 裁定）：这批无时间戳格 100% 是四向挂载格（每条目 4 张朝向日拍图），
     而冻结基准每条目只有 1 串，因此 R1 按「每条 1 格」计配额，四向格只登记不折算；
     一旦真源里出现非四向的无时间戳格，按格逐枚计入配额，防止裁定被当成万能豁免。
     这 1 格是四向里的哪一格由 C138 裁定，指针现读同目录 pick_primary_cell.locate() 逐条挂到行上
     （主向格／定位方式／角差），定位违例或并列待人工非空即退出非零——队列不带悬空指针出盘。
  R2 绑定关口重投：该格带毫秒时间戳且时间戳 < frozen_at_ms（§54 关口B：基准 aa3d777 换档晚于生成时刻，
     0/60 可主张，依 build_prompts.py 的 declaration「不得只复制摘要补绑」，只能重投）。
  时间戳 ≥ frozen_at_ms 的格不进队列——那是冻结后已投的新格，走正常验收通道。

跑法：python 工具/reshoot_campaign_2026_11_06/build_queue.py
"""
import io
import json
import os
import re
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from pick_primary_cell import locate  # noqa: E402  主向格定位规则只此一份，队列与定位器不许各写一遍
MS_TS = re.compile(r'_(1\d{12})_')


def main():
    with io.open(os.path.join(ROOT, '数据', '开图清单.json'), encoding='utf-8') as fh:
        man = json.load(fh)
    with io.open(os.path.join(ROOT, '数据', '提示词基准冻结.json'), encoding='utf-8') as _fh:
        snap = json.load(_fh)
    floor = int(snap['frozen_at_ms'])
    base = {e['id']: e['prompt_sha256'] for e in snap['entries']}

    r1, r2, frozen_side = [], [], []
    p_rows, p_viol, p_stats = locate(man['items'])
    prim = {r['id']: r for r in p_rows}
    for it in man['items']:
        cells = list(it.get('image_file') or [])
        if not cells:
            continue
        ts = []
        for c in cells:
            m = MS_TS.search(Path(c).name)
            ts.append(int(m.group(1)) if m else None)
        nops = sum(1 for t in ts if t is None)
        nops_4dir = sum(1 for c, t in zip(cells, ts) if t is None and '四向' in Path(c).name)
        pre = sum(1 for t in ts if t is not None and t < floor)
        post = sum(1 for t in ts if t is not None and t >= floor)
        row = {
            'id': it['id'], 'name': it['name'], 'type': it['type'], 'size': it['size'],
            'cells': len(cells), 'cells_无时间戳': nops, 'cells_冻结前': pre, 'cells_冻结后': post,
            'cells_无时间戳四向': nops_4dir, 'cells_无时间戳非四向': nops - nops_4dir,
            'R1配额格数': (1 if nops else 0) + (nops - nops_4dir),
            '主向格定位方式': prim[it['id']]['way'] if it['id'] in prim else None,
            '主向格': prim[it['id']]['cell'] if it['id'] in prim else None,
            '主向格角差': prim[it['id']]['delta_deg'] if it['id'] in prim else None,
            'prompt_sha256': it['prompt_sha256'],
            '在冻结快照内': base.get(it['id']) == it['prompt_sha256'],
            '绑定': it.get('image_prompt_sha256'), 'status': it['status'],
        }
        if post:
            frozen_side.append(row)
        if nops:
            r1.append(row)
        if pre:
            r2.append(row)

    out = {
        'declaration': '本文件只读派生，不手抄：真源为 数据/开图清单.json 与 数据/提示词基准冻结.json。'
                       '同一格可同时计入 R1 与 R2（既有定档前旧格又有定档前带时间戳格时）。'
                       '重投完成判据 = 该条 R1 配额格（每格一串一取景）全部被冻结后新格替换且 R2 格归零；'
        '四向旧格只作历史登记、不折算配额（C137：264 条只有 264 串，按 1056 格配工作量是把挂载口径当成了投放口径）；'
        '每条目投的那一格＝主向格，指针由 pick_primary_cell.locate() 现读清单派生（C138：其余三向没有取景原文可绑，不进队列，另立四向控制资产缺项）；'
                       '逐轮发起/落盘/判废台账按组分档：R2 见 ledger.json、R1 见 ledger_r1.json，两本都由 verify_round.py 追加（record_round.py 已不在盘）。',
        'frozen_at': snap['frozen_at'],
        'frozen_at_ms': floor,
        '统计面': {
            '清单条目数': len(man['items']),
            '有格条目数': sum(1 for it in man['items'] if it.get('image_file')),
            '格总数': sum(len(list(it.get('image_file') or [])) for it in man['items']),
            'R1无时间戳格数': sum(r['cells_无时间戳'] for r in r1),
            'R1四向旧格数': sum(r['cells_无时间戳四向'] for r in r1),
            'R1非四向无时间戳格数': sum(r['cells_无时间戳非四向'] for r in r1),
            'R1配额格数': sum(r['R1配额格数'] for r in r1),
            'R1四向条目数': sum(1 for r in r1 if r['主向格定位方式']),
            'R1主向格已指认数': sum(1 for r in r1 if r['主向格']),
            'R1主向并列待人工数': sum(1 for r in r1 if r['主向格定位方式'] == 'ambiguous'),
            '主向定位方式分布_全清单': p_stats['按方式'],
            '主向定位违例数': len(p_viol),
            'R2冻结前带时间戳格数': sum(r['cells_冻结前'] for r in r2),
            '冻结后格数': sum(r['cells_冻结后'] for r in frozen_side),
            '基准不在快照内的条目数': sum(1 for it in man['items'] if base.get(it['id']) != it['prompt_sha256']),
        },
        'R1_画风判废': {'条目数': len(r1), 'entries': r1},
        'R2_绑定关口': {'条目数': len(r2), 'entries': r2},
        '冻结后已投': {'条目数': len(frozen_side), 'entries': frozen_side},
    }
    path = os.path.join(HERE, 'queue.json')
    with io.open(path, 'w', encoding='utf-8', newline='\n') as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1)
        fp.write('\n')
    s = out['统计面']
    print('queue.json 写入：%s' % path)
    print('  统计面=%s' % json.dumps(s, ensure_ascii=False))
    print('  R1 画风判废重投 %d 条 / 配额 %d 格（旧格登记：四向 %d + 非四向 %d = %d 格，四向格按 C137 不折算配额）'
          % (len(r1), s['R1配额格数'], s['R1四向旧格数'], s['R1非四向无时间戳格数'], s['R1无时间戳格数']))
    print('  R2 绑定关口重投 %d 条 / %d 格' % (len(r2), s['R2冻结前带时间戳格数']))
    print('  冻结后已投 %d 条 / %d 格' % (len(frozen_side), s['冻结后格数']))
    unpointed = [r['id'] for r in r1 if r['主向格定位方式'] and not r['主向格']]
    print('  主向格指针（C138）：%d/%d 条已指认，全清单定位方式=%s，并列待人工 %d 条 %s，定位违例 %d 条'
          % (s['R1主向格已指认数'], s['R1四向条目数'],
             json.dumps(s['主向定位方式分布_全清单'], ensure_ascii=False),
             len(unpointed), unpointed[:10], s['主向定位违例数']))
    for v in p_viol[:5]:
        print('    ✗ %s' % v)
    off = [r['id'] for r in r1 + r2 if not r['在冻结快照内']]
    print('  基准不在快照内的条目=%d %s（非空说明队列建在换档后的基准上，须先 --force 重冻）' % (len(off), off[:10]))
    return 0 if not off and not p_viol and not unpointed else 1


if __name__ == '__main__':
    sys.exit(main())
