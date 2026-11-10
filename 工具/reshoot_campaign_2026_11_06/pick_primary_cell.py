# -*- coding: utf-8 -*-
"""C138 的主向格定位器：264 条四向挂载条目，逐条指认「哪一格是主向」，产 primary_cells.json。

为什么要有这个文件：C137 把 R1 的配额从 1056 格订正成 264 格（每条 1 格），但没说这 1 格是四向里的哪一格。
投放面要落得下去，必须先有逐条的主向格指针；而四向的另外 3 向在真源里没有任何取景原文（264 条的【取景指令】段
各只有 1 份、绑死在主向机位上），所以本轮只投主向，其余三向另立「四向控制资产缺项」，不在重投队列里折算工作量。

定位规则（按优先级，命中即止，读数逐条写进产物）：
  labeled        —— 文件名带「主向」标签，直接取该格；再读同名的 `四向DEG-` 数值角或「朝X」八分方位词，
                    与清单 `camera_facing_deg` 对拍，记角差。角差 >22.5° 单列为量化档（方位词只有 45° 步长，
                    而 D 片区朝向落在 36° 网格（十边形）、另有 4 条 facing 落在 30°/240° 的非网格值上，
                    实测量化档＝ D 系列 8 条 @27° ＋ R066 1 条 @30°，是网格取整而非标签错），>45° 判红（那才是标签真错）。
  octant_nearest —— 无「主向」标签（R057—R080 一族 24 条）时，取「朝X」八分角与 facing 夹角最小的那格；
                    两格并列最小 → 记 ambiguous，交人工点，不猜。
判红四条：缺 camera_facing_deg／同一条出现两枚「主向」／labeled 角差 >45°／四格既无主向标签也无可读方位词。
另有一条「挂满四向的条目数 == 进入定位的条目数」守恒自检（数据侧无注入路径，只防未来分支漏计，不列入 --negtest）。

跑法：
  python -X utf8 工具/reshoot_campaign_2026_11_06/pick_primary_cell.py            正检并写产物
  python -X utf8 工具/reshoot_campaign_2026_11_06/pick_primary_cell.py --negtest  违例注入自证（仓库外临时目录）
"""
import argparse
import io
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
OUT = os.path.join(HERE, 'primary_cells.json')
PREFIX = 'primary_cell_neg_'

OCT = {'北': 0, '东北': 45, '东': 90, '东南': 135, '南': 180, '西南': 225, '西': 270, '西北': 315}
QUANT_MAX = 22.5   # 方位词只有 45° 步长，八分角内都算自洽
HARD_MAX = 45.0    # 再大就是标签真错


def angle_of(name):
    m = re.search(r'四向(\d{2,3})-', name)
    if m:
        return int(m.group(1)), 'deg'
    m = re.search(r'朝(东北|西北|东南|西南|北|南|东|西)', name)
    if m:
        return OCT[m.group(1)], 'octant'
    return None, None


def sep(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def four_way_cells(item):
    return [p for p in (item.get('image_file') or []) if '四向' in p]


def locate(items):
    """返回 (逐条定位结果, 违例列表, 统计面)。只读 items，不写盘。"""
    rows, viol, skipped = [], [], []
    for it in items:
        cells = four_way_cells(it)
        if len(cells) < 4:
            continue
        eid = it['id']
        if it.get('camera_facing_deg') is None:
            viol.append('缺朝向字段：%s 无 camera_facing_deg，无法定位主向' % eid)
            continue
        facing = float(it['camera_facing_deg'])
        named = [c for c in cells if '主向' in os.path.basename(c)]
        if len(named) > 1:
            viol.append('双主向标签：%s 命中 %d 枚 %s' % (eid, len(named), [os.path.basename(c) for c in named]))
            continue
        if named:
            base = os.path.basename(named[0])
            ang, kind = angle_of(base)
            d = None if ang is None else sep(ang, facing)
            way = 'labeled'
            if d is None:
                viol.append('主向格读不出角：%s %s' % (eid, base))
                continue
            if d > HARD_MAX:
                viol.append('标签与朝向矛盾：%s 主向格 %s° 与 camera_facing_deg %s° 差 %.1f° > %.1f°'
                            % (eid, ang, facing, d, HARD_MAX))
            rows.append({'id': eid, 'type': it.get('type'), 'way': way, 'cell': named[0],
                         'cell_deg': ang, 'deg_source': kind, 'facing_deg': facing,
                         'delta_deg': round(d, 1), 'quantized': d > QUANT_MAX})
            continue
        cands = []
        for c in cells:
            ang, kind = angle_of(os.path.basename(c))
            if ang is not None:
                cands.append((sep(ang, facing), c, ang, kind))
        if not cands:
            viol.append('无法定位：%s 四格既无主向标签也无可读方位词' % eid)
            continue
        cands.sort()
        if len(cands) > 1 and abs(cands[0][0] - cands[1][0]) < 1e-9:
            skipped.append(eid)
            rows.append({'id': eid, 'type': it.get('type'), 'way': 'ambiguous', 'cell': None,
                         'cell_deg': None, 'deg_source': None, 'facing_deg': facing,
                         'delta_deg': round(cands[0][0], 1), 'quantized': cands[0][0] > QUANT_MAX})
            continue
        d, c, ang, kind = cands[0]
        rows.append({'id': eid, 'type': it.get('type'), 'way': 'octant_nearest', 'cell': c,
                     'cell_deg': ang, 'deg_source': kind, 'facing_deg': facing,
                     'delta_deg': round(d, 1), 'quantized': d > QUANT_MAX})
    fw_total = sum(1 for it in items if len(four_way_cells(it)) >= 4)
    if fw_total != len(rows) + len(viol):
        viol.append('漏条目：挂满四向的条目 %d 条，进入定位的只有 %d 条'
                    % (fw_total, len(rows) + len(viol)))
    ways = {}
    for r in rows:
        ways[r['way']] = ways.get(r['way'], 0) + 1
    stats = {'进入定位流程条目数': len(rows) + len(viol),
             '定位成功': len([r for r in rows if r['cell']]), '按方式': ways,
             '量化档位数': sum(1 for r in rows if r['quantized']),
             '角差读数': {'最小': min([r['delta_deg'] for r in rows if r['delta_deg'] is not None], default=None),
                        '最大': max([r['delta_deg'] for r in rows if r['delta_deg'] is not None], default=None)},
             '并列待人工': len(skipped), '并列清单': skipped, '违例数': len(viol)}
    return rows, viol, stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--negtest', action='store_true', help='违例注入自证，须在仓库外临时目录跑')
    args = ap.parse_args()
    if args.negtest:
        return negtest()
    with io.open(os.path.join(ROOT, '数据', '开图清单.json'), encoding='utf-8') as fh:
        man = json.load(fh)
    rows, viol, stats = locate(man['items'])
    ids = [r['id'] for r in rows]
    if len(ids) != len(set(ids)):
        viol.append('条目重复定位')
    payload = {'说明': '本文件由 pick_primary_cell.py 现读 数据/开图清单.json 派生，不手抄；四向条目＝image_file 里含「四向」的格数 ≥4。',
               '口径': 'C138：重投面按每条目主向 1 格，其余三向不进队列、另立四向控制资产缺项；主向按 labeled（带「主向」标签，与 camera_facing_deg 对拍）'
                       '或 octant_nearest（无相对标签族按「朝X」八分角取最近）定位，并列者记 ambiguous 交人工。',
               '统计面': stats, 'rows': rows}
    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as fp:
        fp.write(json.dumps(payload, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps(stats, ensure_ascii=False))
    if viol:
        print('❌ 主向定位判红 %d 条：' % len(viol))
        for v in viol:
            print('   ✗ %s' % v)
        return 1
    print('✅ 主向格定位 %d/%d 条（%s），量化档 %d 条（D 片区 36° 网格、R066 facing 30° 落在方位词 45° 步长之外，非标签错），'
          '并列待人工 %d 条；产物 primary_cells.json'
          % (stats['定位成功'], stats['进入定位流程条目数'],
             '／'.join('%s %d' % (k, v) for k, v in sorted(stats['按方式'].items())),
             stats['量化档位数'], stats['并列待人工']))
    return 0


def negtest():
    tmp = Path(tempfile.mkdtemp(prefix=PREFIX))
    lines, rc = [], 0
    try:
        items = [{'id': 'L001', 'type': '标志性建筑', 'camera_facing_deg': 0.0,
                  'image_file': ['数据/图集/四向/L001/四向00-主向-朝北-r01.jpg',
                                 '数据/图集/四向/L001/四向180-背向-朝南-r01.jpg',
                                 '数据/图集/四向/L001/四向270-逆向-朝西-r01.jpg',
                                 '数据/图集/四向/L001/四向90-顺向-朝东-r02.jpg']},
                 {'id': 'R057', 'type': '居民区', 'camera_facing_deg': 0.0,
                  'image_file': ['数据/图集/四向/R057/R057-岚风家庭苑-四向外-R057方向-朝东-r01.jpg',
                                 '数据/图集/四向/R057/R057-岚风家庭苑-四向外-R057方向-朝北-r01.jpg',
                                 '数据/图集/四向/R057/R057-岚风家庭苑-四向外-R057方向-朝南-r01.jpg',
                                 '数据/图集/四向/R057/R057-岚风家庭苑-四向外-R057方向-朝西-r01.jpg']}]
        rows, viol, stats = locate(items)
        lines.append('对照（夹具原样）：%d 违例，定位 %s＝%s' % (len(viol), sorted(stats['按方式']), [r['way'] for r in rows]))
        if viol:
            print('\n'.join(lines) + '\n✗ 夹具本底不干净')
            return 1
        # 五条注入：前四条各打一条判红通道（缺朝向字段／双主向／角差超 45°／四格读不出方位词），
        # 第五条要求「不猜、记并列待人工」——拦截通道不同，故判据也不同。
        for name, expect, mutate in [
            ('双主向标签', 'viol', lambda its: its[0]['image_file'].__setitem__(
                1, '数据/图集/四向/L001/四向180-主向-朝南-r01.jpg')),
            ('标签与朝向矛盾', 'viol', lambda its: its[0].__setitem__('camera_facing_deg', 180.0)),
            ('四格无可读方位词', 'viol', lambda its: its[1].__setitem__(
                'image_file', ['数据/图集/四向/R057/a.jpg', '数据/图集/四向/R057/b.jpg',
                               '数据/图集/四向/R057/c.jpg', '数据/图集/四向/R057/d.jpg'])),
            ('缺朝向字段', 'viol', lambda its: its[0].__delitem__('camera_facing_deg')),
            ('方位角落在两格正中（并列）', 'ambiguous', lambda its: its[1].__setitem__('camera_facing_deg', 45.0)),
        ]:
            its = json.loads(json.dumps(items))
            mutate(its)
            _, v, s = locate(its)
            hit = bool(v) if expect == 'viol' else (
                s['并列待人工'] == 1 and s['按方式'].get('ambiguous') == 1
                and s['定位成功'] == len(its) - 1)
            rc |= 0 if hit else 1
            lines.append('%s %s（要求%s）→ 违例 %s ／ 并列 %d'
                         % ('✓' if hit else '✗', name, expect, v[:1], s['并列待人工']))
        residue = [p.name for p in Path(ROOT).rglob('*') if PREFIX in p.name]
        lines.append('仓库内 %s 残留 %d' % (PREFIX, len(residue)))
        if residue:
            rc = 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        lines.append('临时目录已删：%s 存在=%s' % (tmp.name, tmp.exists()))
    print('\n'.join(lines))
    print('%s 主向定位负测' % ('✅' if rc == 0 else '❌'))
    return rc


if __name__ == '__main__':
    sys.exit(main())
