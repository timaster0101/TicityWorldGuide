# -*- coding: utf-8 -*-
"""第4期运行参数派生器：读 运行参数源表.json ＋ 名录几何，产出交通矩阵、天气年历与两张查表。

手填只有五组常量、十个圈层对的实测声明值与十二个月天气游程；矩阵与年历一律是本文件的生成物。
跑法：python 工具/build_params.py [--out-dir DIR] [--print-matrix]
"""
import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / '数据' / '运行参数源表.json'
if not SRC_PATH.exists():
    raise SystemExit('缺少 数据/运行参数源表.json：本期所有查表值都从它派生，不允许手填正典')
SOURCE = json.loads(SRC_PATH.read_text(encoding='utf-8'))
COSTS_SRC = json.loads((ROOT / '数据' / '物价生活源表.json').read_text(encoding='utf-8'))
OCC_SRC = json.loads((ROOT / '数据' / '产业就业源表.json').read_text(encoding='utf-8'))

from anchors import pair_key, ring_pair_stats

P = SOURCE['参数']
SP = P['交通']
WEATHER = P['天气']
MODE_ORDER = [m['码'] for m in SP['方式']]
MONTH_DAYS = dict(zip(range(1, 13), [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]))
INNER = ('内湖环', '外城环')


def transfer_minutes(mode, a, b):
    """公交跨圈层 +8；区域铁路恰好一端属城市内圈层时 +15，两端同属外围时 0；其余 0。"""
    if mode == 'TR-BUS' and a != b:
        return SP['公交跨圈换乘分钟']
    if mode == 'TR-RAIL' and (a in INNER) != (b in INNER):
        return SP['铁路内外衔接分钟']
    return 0


def cell_minutes(median_km, speed, transfer):
    route = median_km * SP['绕行系数']
    step = SP['取整分钟']
    return math.ceil((route / speed * 60 + transfer) / step) * step, round(route, 2)


def expand_runs(runs):
    return [code for code, count in runs for _ in range(count)]


def build_matrix(stats):
    cells = []
    for row in P['圈层对']:
        a, b, key = row['A'], row['B'], pair_key(row['A'], row['B'])
        got = stats[key]
        for src_field, stat_field in (('声明中位直线km', '中位直线km'), ('声明最小km', '最小km'),
                                      ('声明最大km', '最大km'), ('声明最大偏差km', '最大偏差km')):
            if abs(row[src_field] - got[stat_field]) > 0.05:
                raise SystemExit(f'圈层对实测漂移：{key} 的{src_field} 登记 {row[src_field]}，名录算出 '
                                 f'{got[stat_field]}——改名录坐标后须重跑本派生器并同步源表')
        if row['锚点对数'] != got['锚点对数']:
            raise SystemExit(f'圈层对锚点数漂移：{key} 登记 {row["锚点对数"]}，实得 {got["锚点对数"]}')
        for mode in SP['方式']:
            usable = key in mode['覆盖']
            transfer = transfer_minutes(mode['码'], a, b) if usable else 0
            mins, route = (cell_minutes(got['中位直线km'], mode['速度km_h'], transfer)
                           if usable else (None, None))
            cells.append({'A': a, 'B': b, '圈层对': key, '方式': mode['码'], '方式名': mode['名'],
                          '耗时分钟': mins, '路线km': route, '换乘分钟': transfer,
                          '中位直线km': got['中位直线km'], '最大偏差km': got['最大偏差km'],
                          '最小km': got['最小km'], '最大km': got['最大km']})
    deferred = {m['码'] for m in SP['延后方式']}
    stray = deferred & {c['方式'] for c in cells}
    if stray:
        raise SystemExit(f'延后方式进了矩阵：{sorted(stray)}——轮渡／机场／山外接驳的耗时待第5期清单落定')
    return cells


def build_year_table():
    states = {s['码']: s for s in WEATHER['态']}
    sea_of = {}
    for sea, info in P['季节月份'].items():
        for m in info['月']:
            sea_of[str(m)] = sea
    year, day_no = [], 0
    for m in range(1, 13):
        codes = expand_runs(WEATHER['逐月游程'][str(m)])
        if len(codes) != MONTH_DAYS[m]:
            raise SystemExit(f'{m} 月游程展开 {len(codes)} 天，与 2013 年该月 {MONTH_DAYS[m]} 天不符')
        for i, code in enumerate(codes, start=1):
            if code not in states:
                raise SystemExit(f'天气态码不在字典内：{code}（{m} 月第 {i} 天）')
            day_no += 1
            s = states[code]
            year.append({'年内第几天': day_no, '月': m, '日': i, 'SEA': sea_of[str(m)],
                         '态': code, '名': s['名'], '画面': s['画面'], '温度带': s['温度带']})
    if day_no != 365:
        raise SystemExit(f'天气年历 {day_no} 格，不等于 365')
    return year, sea_of


def check_sea同源():
    price_keys = sorted(COSTS_SRC['参数']['季节系数'])
    mine = sorted(P['季节月份'])
    if price_keys != mine:
        raise SystemExit(f'SEA 键与物价侧不一致：物价 {price_keys} 本表 {mine}——季节与月份对应由两侧共用，不各立一套')
    classes = [c['id'] for c in OCC_SRC['大类']]
    if len(classes) != 20 or not all(c.startswith('A') for c in classes):
        raise SystemExit(f'行业大类不是 A01—A20：实得 {len(classes)} 个')


def build_canon():
    check_sea同源()
    stats = ring_pair_stats()
    cells = build_matrix(stats)
    year, sea_of = build_year_table()
    canon = dict(SOURCE)
    canon['参数'] = P
    canon['交通矩阵'] = cells
    canon['延后方式'] = SP['延后方式']
    canon['技能等级阈值'] = P['技能']['等级阈值月']
    canon['月季节'] = sea_of
    canon['天气年历'] = year
    canon['季节日照'] = WEATHER['日照时段']
    canon['逐月游程'] = WEATHER['逐月游程']
    canon['汇总'] = {'圈层对数': len(P['圈层对']), '矩阵格数': len(cells),
                    '可用格数': sum(1 for c in cells if c['耗时分钟'] is not None),
                    '不可用格数': sum(1 for c in cells if c['耗时分钟'] is None),
                    '方式数': len(SP['方式']), '延后方式数': len(SP['延后方式']),
                    '天气态数': len(WEATHER['态']), '年历格数': len(year),
                    '月数': len(WEATHER['逐月游程']), '季节数': len(P['季节月份']),
                    '等级阈值档数': len(P['技能']['等级阈值月']),
                    '冷却级别数': len(P['事件']['冷却天']),
                    '口径': '全部为固定值查表：零随机、零逐人模拟、零路网建模。天气与交通不进任何判定，'
                            '只作画面与叙事条件；耗时不因高峰、施工、天气或事故变化。'}
    return canon


def _cell(v):
    if v is None:
        return '—'
    if isinstance(v, bool):
        return '是' if v else '否'
    if isinstance(v, dict):
        return '、'.join(f'{k} {x}' for k, x in v.items())
    if isinstance(v, list):
        return '、'.join(str(x) for x in v)
    return str(v)


def _md(v):
    """圈层对键名里的 `|` 是表格分隔符，落到 markdown 单元格必须转义，否则一格被拆成两列。"""
    return _cell(v).replace('|', '\\|')


def render_table(canon):
    p, sp, w = canon['参数'], canon['参数']['交通'], canon['参数']['天气']
    lines = ['# 运行参数总表', '',
             f'本文件由 `工具/build_params.py` 生成，基准年 {canon["setting_year"]}，'
             '货币 钛币（TT），禁止手改。', '',
             f'规模：{canon["汇总"]["圈层对数"]} 个圈层对 × {canon["汇总"]["方式数"]} 种方式 '
             f'＝ {canon["汇总"]["矩阵格数"]} 格（可用 {canon["汇总"]["可用格数"]} 格，'
             f'不通 {canon["汇总"]["不可用格数"]} 格）；天气年历 {canon["汇总"]["年历格数"]} 格。', '']

    lines += ['## 一、技能成长与退化', '', '| 项 | 值 |', '| --- | --- |']
    for k, v in p['技能'].items():
        lines.append(f'| {k} | {_cell(v)} |')
    lines += ['', '### 等级阈值', '', '| LVL | 累计经验月 |', '| --- | --- |']
    for lvl, months in canon['技能等级阈值'].items():
        lines.append(f'| {lvl} | {months} |')

    lines += ['', '## 二、季节月份与日照时段', '',
              '| SEA | 名 | 月份 | 天数 | 温度带 | 画面基调 |', '| --- | --- | --- | --- | --- | --- |']
    for sea, info in p['季节月份'].items():
        lines.append(f'| {sea} | {info["名"]} | {_cell(info["月"])} 月 | {info["天数"]} | '
                     f'{info["温度带"]} | {info["画面基调"]} |')
    lines += ['', '| 季 | 日出 | 正午 | 日落 | 黄昏 |', '| --- | --- | --- | --- | --- |']
    for sea, info in canon['季节日照'].items():
        lines.append(f'| {p["季节月份"][sea]["名"]}（{sea}） | {info["日出"]} | {info["正午"]} | '
                     f'{info["日落"]} | {info["黄昏"]} |')
    lines += ['', '| 季 | 各态次数区间（天） |', '| --- | --- |']
    for sea, rng in w['次数区间'].items():
        lines.append(f'| {p["季节月份"][sea]["名"]}（{sea}） | '
                     + '、'.join(f'{code} {v[0]}—{v[1]}' for code, v in rng.items()) + ' |')

    lines += ['', '## 三、交通固定耗时', '', '### 3.1 圈层对几何（实测自名录中心点）', '',
              '| A | B | 锚点对数 | 中位直线 km | 最小 km | 最大 km | 最大偏差 km |',
              '| --- | --- | --- | --- | --- | --- | --- |']
    pair_rows = {pair_key(r['A'], r['B']): r for r in p['圈层对']}
    for c in canon['交通矩阵']:
        if c['方式'] != MODE_ORDER[0]:
            continue
        lines.append(f'| {c["A"]} | {c["B"]} | {pair_rows[c["圈层对"]]["锚点对数"]} | '
                     f'{c["中位直线km"]} | {c["最小km"]} | {c["最大km"]} | {c["最大偏差km"]} |')
    lines += ['', '### 3.2 方式与覆盖', '', '| 方式名 | 码 | 速度 km/h | 覆盖圈层对 | 覆盖对数 |',
              '| --- | --- | --- | --- | --- |']
    for m in sp['方式']:
        lines.append(f'| {m["名"]} | {m["码"]} | {m["速度km_h"]} | {_md(m["覆盖"])} | '
                     f'{len(m["覆盖"])} |')
    lines += ['', '### 3.3 固定耗时矩阵', '',
              '| 方式 | 方式名 | 圈层对 | 耗时分钟 | 路线km | 换乘分钟 |',
              '| --- | --- | --- | --- | --- | --- |']
    for c in canon['交通矩阵']:
        lines.append(f'| {c["方式"]} | {c["方式名"]} | {_md(c["圈层对"])} | {_cell(c["耗时分钟"])} | '
                     f'{_cell(c["路线km"])} | {c["换乘分钟"]} |')
    lines += ['', '### 3.4 延后方式（不进矩阵）', '', '| 名 | 码 | 待落定的清单 |',
              '| --- | --- | --- |']
    for m in canon['延后方式']:
        lines.append(f'| {m["名"]} | {m["码"]} | {m["待"]} |')

    lines += ['', '## 四、天气年历（2013 公共日历，零随机）', '',
              '| 年内第几天 | 月 | 日 | SEA | 态 | 名 |', '| --- | --- | --- | --- | --- | --- |']
    for d in canon['天气年历']:
        lines.append(f'| {d["年内第几天"]} | {d["月"]} | {d["日"]} | {d["SEA"]} | {d["态"]} | {d["名"]} |')

    lines += ['', '## 五、事件冷却与负面配额', '', '| 项 | 值 |', '| --- | --- |']
    for k, v in p['事件'].items():
        lines.append(f'| {k} | {_cell(v)} |')

    lines += ['', '## 六、检查点频率', '', '| 项 | 值 |', '| --- | --- |']
    for k, v in p['检查点'].items():
        lines.append(f'| {k} | {_cell(v)} |')

    lines += ['', '## 七、口径与不做项', '']
    for text in (canon['汇总']['口径'], sp['口径'], sp['换乘口径'], sp['城市内不设站'],
                 w['索引口径'], w['编排约束'], w['口径'], p['技能']['口径']):
        lines.append(f'- {text}')
    return '\n'.join(lines) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-dir', default=str(ROOT / '数据'))
    ap.add_argument('--print-matrix', action='store_true')
    args = ap.parse_args()
    canon = build_canon()
    if args.print_matrix:
        for c in canon['交通矩阵']:
            print([c['圈层对'], c['方式'], c['耗时分钟']])
        return
    out = Path(args.out_dir)
    (out / '运行参数正典.json').write_bytes(
        (json.dumps(canon, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    (out / '运行参数总表.md').write_text(render_table(canon), encoding='utf-8')
    print(json.dumps(canon['汇总'], ensure_ascii=False))


if __name__ == '__main__':
    main()
