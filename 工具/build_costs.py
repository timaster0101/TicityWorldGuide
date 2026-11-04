# -*- coding: utf-8 -*-
"""物价与生活成本包生成器：读 物价生活源表.json（经 anchors.py 取住所锚与圈层），派生三档价、四圈层篮子、季节展示与保障标准。

手填只有每品类的必需档基准价与标准月消耗量，加上域表的行为标志；其余物价数字全部是本文件的生成物。
跑法：python 工具/build_costs.py [--out-dir DIR] [--print-basket]
"""
import argparse
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / '数据' / '物价生活源表.json'
if not SRC_PATH.exists():
    raise SystemExit('缺少 数据/物价生活源表.json：本期所有物价数字都从它派生，不允许手填正典')
SOURCE = json.loads(SRC_PATH.read_text(encoding='utf-8'))
REGISTRY = json.loads((ROOT / '数据' / '城市空间名录.json').read_text(encoding='utf-8'))['entries']

from anchors import dwelling_anchors, entry_ring

P = SOURCE['参数']
DOMAINS = {d['id']: d for d in SOURCE['域表']}
BY_ID = {e['id']: e for e in REGISTRY}
OVERLAY_KEYS = ('服饰上限覆写', '耐用品覆写')
TIERS = ('必需', '改善', '奢侈')


def unit_round(x):
    """钛币最小计价单位 0.1。"""
    return round(x, 1)


def tier_prices(required, params=P):
    return {'必需': round(required, 1),
            '改善': unit_round(required * params['改善乘数']),
            '奢侈': unit_round(required * params['奢侈乘数'])}


def is_seasonal(row):
    return DOMAINS[row['域']]['季节敏感']


def second_hand_cap(row):
    """能挂牌的品类取域基线上限，逐条覆写优先；不可挂牌返回 None。"""
    if not DOMAINS[row['域']].get('二手适用'):
        return None
    for key in OVERLAY_KEYS:
        if row['id'] in SOURCE.get(key, {}):
            return SOURCE[key][row['id']]
    return DOMAINS[row['域']]['二手折价上限']


def build_categories():
    out = []
    for row in SOURCE['品类']:
        domain = DOMAINS[row['域']]
        prices = tier_prices(row['必需档基准价'])
        cap = second_hand_cap(row)
        entry = {'id': row['id'], '名称': row['名称'], '域': row['域'],
                 '计量单位': domain['计量单位'], '三档基准价': prices,
                 '标准月消耗量': row['标准月消耗量'], '季节生效': is_seasonal(row),
                 '交易用途': domain['交易用途'], '减免归属': {t: f'WEL-{t}' for t in 'ABC'},
                 '二手适用': bool(cap), '维修适用': domain['维修适用']}
        if cap:
            listing = unit_round(prices['必需'] * cap)
            entry['二手折价上限'] = cap
            entry['二手挂牌价_必需档'] = listing
            entry['回收价_必需档'] = unit_round(listing * P['回收系数'])
        if entry['维修适用']:
            entry['维修费_必需档'] = unit_round(prices['必需'] * P['维修费比例'])
            entry['报废判定'] = '维修费不低于回收价即判 DAM-2 报废，直接走回收'
        out.append(entry)
    return out


def build_services():
    out = []
    for row in SOURCE['服务']:
        self_pay = unit_round(row['单价'] * (1 - P['减免比例'][row['减免档']]))
        out.append(dict(row, 交易用途=SOURCE['服务交易用途'],
                        减免比例=P['减免比例'][row['减免档']], 自付_钛币=self_pay,
                        单次费用_钛币=unit_round(row['单价'] * row['固定处理时长_小时'])))
    return out


def build_baskets(categories):
    base = round(sum(c['三档基准价']['必需'] * c['标准月消耗量'] for c in categories), 1)
    return {ring: unit_round(base * coef) for ring, coef in zip(P['圈层顺序'], P['商品圈层系数'])}, base


def build_seasonal_view(categories, base_basket):
    """季节只出展示值：整篮按季节敏感两域的小计浮动，不进红线判定。"""
    seasonal = sum(c['三档基准价']['必需'] * c['标准月消耗量'] for c in categories if c['季节生效'])
    fixed = base_basket - seasonal
    return {s: unit_round(fixed + seasonal * k) for s, k in P['季节系数'].items()}


def ring_anchor_median():
    anchors = dwelling_anchors()
    buckets = {}
    for key, value in anchors.items():
        buckets.setdefault(entry_ring(BY_ID[key], BY_ID), []).append(value)
    return {r: round(statistics.median(v), 1) for r, v in buckets.items()}


def build_welfare(baskets):
    medians = ring_anchor_median()
    missing = [r for r in P['圈层顺序'] if r not in medians]
    if missing:
        raise SystemExit(f'圈层缺住所锚中位数：{missing}——锚点圈层归属由 anchors.entry_ring 推导，不得手填')
    relief = P['失业救助']
    out = {}
    for ring in P['圈层顺序']:
        full = unit_round(baskets[ring] * relief['全额比例'])
        decline = unit_round(baskets[ring] * relief['递减比例'])
        out[ring] = {'生活保障标准_钛币': baskets[ring],
                     '押金_钛币': medians[ring],
                     '初始资金_钛币': unit_round(3 * baskets[ring] + medians[ring]),
                     '欠费宽限_月': P['欠费宽限月数'],
                     '失业救助_全额月_钛币': full,
                     '失业救助_递减月_钛币': decline,
                     '失业救助_连发总额_钛币': unit_round(full * relief['全额月数'] + decline * relief['递减月数'])}
    return out, medians


UNITS = [e for e in REGISTRY if e['type'] in ('城市片区', '产业小镇', '特色村落')]
SPARSE_TOTAL = SOURCE['散居农村人口']


def sparse_allocation():
    """散居人口按聚落登记人口比例摊，逐聚落向下取整，余数一次给人口最大的聚落；片区摊 0。"""
    pop = {u['id']: int(u['population']) for u in UNITS}
    settlements = [u for u in UNITS if u['id'].startswith('S')]
    settlement_pop = sum(pop[u['id']] for u in settlements)
    give = {u['id']: math.floor(SPARSE_TOTAL * pop[u['id']] / settlement_pop) for u in settlements}
    biggest = max(settlements, key=lambda u: (pop[u['id']], u['id']))['id']
    rest = SPARSE_TOTAL - sum(give.values())
    give[biggest] += rest
    return give, rest, biggest


def build_inventory(give):
    rows, city = [], 0
    for u in sorted(UNITS, key=lambda x: x['id']):
        registered = int(u['population'])
        linked = give.get(u['id'], 0)
        unit_pop = registered + linked
        households = math.floor(unit_pop / P['户均规模'] + 0.5)
        city += households
        ring = entry_ring(u, BY_ID)
        ratios = SOURCE['类型配比'][ring]
        floors = [math.floor(households * r) for r in ratios]
        floors[max(range(len(ratios)), key=lambda i: ratios[i])] += households - sum(floors)
        for h, ratio, total in zip(SOURCE['住房类型'], ratios, floors):
            quota = max(1, math.floor(total * P['兜底比例']))
            rows.append({'单元ID': u['id'], '住房类型ID': h['id'], '圈层': ring,
                         '登记人口': registered, '挂靠人口': linked, '单元人口': unit_pop,
                         '推导户数': households, '类型配比': ratio, '总量': total,
                         '兜底配额': quota, '已占用': total - quota, '可分配': quota,
                         '实际预留比例': round(quota / total, 4)})
    return rows, city


def build_canon():
    categories = build_categories()
    baskets, baseline = build_baskets(categories)
    welfare, medians = build_welfare(baskets)
    give, rest, rest_to = sparse_allocation()
    inventory, city_households = build_inventory(give)
    listing = [c for c in categories if c['二手适用']]
    repair = [c for c in categories if c['维修适用']]
    units = len({r['单元ID'] for r in inventory})
    uplift = [give[u['id']] / int(u['population']) for u in UNITS if u['id'].startswith('S')]
    city_pop = sum(int(u['population']) for u in UNITS) + SPARSE_TOTAL
    return {
        'version': '1.0', 'fictional': True, 'setting_year': SOURCE['setting_year'],
        'currency': SOURCE['currency'], 'currency_name': SOURCE['currency_name'],
        'declaration': '本文件由 工具/build_costs.py 从 物价生活源表.json＋城市空间名录.json＋参考房价租金.json 生成，属派生正典；'
                       '修改请改源表与生成器并重跑，不要手改本文件。',
        '最小计价单位': SOURCE['最小计价单位'], '参数': P, '域表': SOURCE['域表'],
        '交易用途': SOURCE['交易用途'], '面额表': SOURCE['面额表'],
        '品类': categories, '服务': build_services(),
        '篮子基线_内湖环': baseline,
        '篮子': {r: baskets[r] for r in P['圈层顺序']},
        '季节展示': build_seasonal_view(categories, baseline),
        '住所锚中位_按圈层': {r: medians[r] for r in P['圈层顺序']},
        '保障': welfare, '库存': inventory,
        '散居挂靠': {'总人口': SPARSE_TOTAL, '余数': rest, '余数归属': rest_to,
                   '方式': SOURCE['挂靠方式'],
                   '上浮比例区间': [round(min(uplift), 4), round(max(uplift), 4)]},
        '汇总': {
            '域数': len(DOMAINS), '品类数': len(categories), '服务数': len(SOURCE['服务']),
            '圈层数': len(P['圈层顺序']), '登记篮子值数': len(baskets),
            '可挂牌品类数': len(listing), '可维修品类数': len(repair),
            '禁挂牌品类数': len(categories) - len(listing),
            '单元数': units, '库存行数': len(inventory), '住房类型数': len(SOURCE['住房类型']),
            '全城户数': city_households, '全城人口': city_pop, '散居挂靠余数': rest,
            '救助发放条件数': len(P['失业救助']['发放条件']),
            '救助停发情形数': len(P['失业救助']['停发情形']),
            '救助禁则数': len(P['失业救助']['禁则']),
            '口径': '改善价＝必需×{0}，奢侈价＝必需×{1}，两档不手填；篮子只按必需档与标准月消耗量复算，'
                    '季节与二手挂牌价为展示与判定用的派生值，不参与薪酬红线。'
                    '库存 176 行是统计口径而非空间条目，散居农村不单设单元，按聚落人口比例挂靠。'
                    '失业救助三列由本圈层篮子×手填比例得出，月数与条数全部取自源表，不另填金额。'.format(
                        P['改善乘数'], P['奢侈乘数']),
        },
    }


def render_table(canon):
    """总表：八节全部从正典对象取数，脚本里不写第二个字面量。"""
    p, dom_rows, cats, svcs = canon['参数'], canon['域表'], canon['品类'], canon['服务']
    relief = p['失业救助']
    house_names = {h['id']: h['名称'] for h in SOURCE['住房类型']}
    ratios = SOURCE['类型配比']
    L = ['', '## 一、参数与面额', '', '| 参数 | 值 |', '|---|---|']
    relief_short = (f"全额比例 {relief['全额比例']}、递减比例 {relief['递减比例']}；"
                    f"全额 {relief['全额月数']} 月＋递减 {relief['递减月数']} 月＝最长连发 {relief['最长连发月数']} 月，"
                    f"再申请间隔 {relief['再申请间隔月数']} 月，复核每 {relief['复核月数']} 月一次；"
                    f"发放条件 {len(relief['发放条件'])} 条、停发情形 {len(relief['停发情形'])} 条、"
                    f"禁则 {len(relief['禁则'])} 条，三段全文见第六节")
    for k, v in p.items():
        if k == '失业救助':
            L.append(f'| {k} | {relief_short} |')
            continue
        L.append(f'| {k} | {"、".join(str(x) for x in v) if isinstance(v, (list, tuple)) else json.dumps(v, ensure_ascii=False)} |')
    L += ['', f"面额表（钛币）：{'、'.join(str(x) for x in canon['面额表'])}。"
          f"最小计价单位 {canon['最小计价单位']}；交易用途 {'、'.join(canon['交易用途'])}。", '',
          '## 二、六域口径', '', '| 域 | 名称 | 计量单位 | 季节敏感 | 可挂二手 | 可维修 | 交易用途 |',
          '|---|---|---|---|---|---|---|']
    for d in dom_rows:
        L.append(f"| {d['id']} | {d['名称']} | {d['计量单位']} | {'是' if d['季节敏感'] else '否'} "
                 f"| {'是' if d.get('二手适用') else '否'} | {'是' if d['维修适用'] else '否'} | {d['交易用途']} |")
    L += ['', '## 三、品类三档基准价与标准月消耗量', '',
          f"改善价＝必需档×{p['改善乘数']}，奢侈价＝必需档×{p['奢侈乘数']}，两档不手填；"
          f"篮子只按必需档复算，见第五节。共 {canon['汇总']['品类数']} 条，逐域列出。"]
    for d in dom_rows:
        rows = [c for c in cats if c['域'] == d['id']]
        L += ['', f"### {d['id']} {d['名称']}（{len(rows)} 条）", '',
              '| 品类 | 名称 | 必需 | 改善 | 奢侈 | 月消耗 | 季节 | 二手上限 | 挂牌价 | 回收价 | 维修费 |',
              '|---|---|---|---|---|---|---|---|---|---|---|']
        for c in rows:
            t = c['三档基准价']
            L.append(f"| {c['id']} | {c['名称']} | {t['必需']} | {t['改善']} | {t['奢侈']} "
                     f"| {c['标准月消耗量']}{c['计量单位']} | {'是' if c['季节生效'] else '否'} "
                     f"| {c.get('二手折价上限', '—')} | {c.get('二手挂牌价_必需档', '—')} "
                     f"| {c.get('回收价_必需档', '—')} | {c.get('维修费_必需档', '—')} |")
    L += ['', '## 四、公共服务与家政', '',
          '| 服务 | 名称 | 域 | 单价 | 减免档 | 减免比例 | 自付 | 处理时长 | 单次费用 | 交易用途 |',
          '|---|---|---|---|---|---|---|---|---|---|']
    for s in svcs:
        L.append(f"| {s['id']} | {s['名称']} | {s['域']} | {s['单价']} | {s['减免档']} "
                 f"| {s['减免比例']} | {s['自付_钛币']} | {s['固定处理时长_小时']}h | {s['单次费用_钛币']} | {s['交易用途']} |")
    L += ['', '## 五、四圈层基本篮子与季节展示', '',
          f"内湖环篮子基线 {canon['篮子基线_内湖环']} 钛币/户·月（{canon['汇总']['品类数']} 条品类的必需档×标准月消耗量），"
          '逐圈层只乘商品圈层系数；季节列只作展示，不进薪酬红线。', '',
          '| 圈层 | 商品系数 | 篮子_钛币/月 | 住所锚中位_钛币 |', '|---|---|---|---|']
    for i, ring in enumerate(p['圈层顺序']):
        L.append(f"| {ring} | {p['商品圈层系数'][i]} | {canon['篮子'][ring]} "
                 f"| {canon['住所锚中位_按圈层'][ring]} |")
    L += ['', '季节展示（整篮，钛币/月）：'
          + '、'.join(f"{k} {v}" for k, v in canon['季节展示'].items()) + '。', '',
          '## 六、公共保障、失业救助与初始资金', '',
          f"生活保障标准直接取本圈层篮子；初始资金＝3×生活保障标准＋押金，"
          f"欠费宽限 {p['欠费宽限月数']} 个月。", '',
          f"失业救助按本圈层篮子折算，三列全为派生值：全额月＝篮子×{relief['全额比例']}，"
          f"递减月＝篮子×{relief['递减比例']}，连发总额＝全额月×{relief['全额月数']}＋递减月×{relief['递减月数']}。"
          f"全额连发 {relief['全额月数']} 个月（与欠费宽限 {p['欠费宽限月数']} 个月同值）后转递减 {relief['递减月数']} 个月，"
          f"最长连发 {relief['最长连发月数']} 个月，用满后隔 {relief['再申请间隔月数']} 个月才可再申请，"
          f"连发期间每 {relief['复核月数']} 个月复核一次。救助按登记失业者本人发放，不乘户均规模 {p['户均规模']}。", '',
          '| 圈层 | 生活保障标准 | 押金（月租中位） | 初始资金 | 宽限月 | 救助全额月 | 救助递减月 | 连发总额 |', '|---|---|---|---|---|---|---|---|']
    for ring in p['圈层顺序']:
        w = canon['保障'][ring]
        L.append(f"| {ring} | {w['生活保障标准_钛币']} | {w['押金_钛币']} "
                 f"| {w['初始资金_钛币']} | {w['欠费宽限_月']} | {w['失业救助_全额月_钛币']} "
                 f"| {w['失业救助_递减月_钛币']} | {w['失业救助_连发总额_钛币']} |")
    L += ['', f"发放条件 {len(relief['发放条件'])} 条：{'；'.join(relief['发放条件'])}。", '',
          f"停发情形 {len(relief['停发情形'])} 条：{'；'.join(relief['停发情形'])}。", '',
          f"禁则 {len(relief['禁则'])} 条：{'；'.join(relief['禁则'])}。", '',
          f"口径：{relief['口径']}", '']
    L += ['', '## 七、二手折价与维修回收', '',
          f"可挂牌 {canon['汇总']['可挂牌品类数']} 条、可维修 {canon['汇总']['可维修品类数']} 条、"
          f"禁挂牌 {canon['汇总']['禁挂牌品类数']} 条；回收价＝挂牌价×{p['回收系数']}，"
          f"维修费＝必需档×{p['维修费比例']}，维修费不低于回收价即判报废直接走回收。", '',
          '| 域 | 可挂牌 | 上限区间 | 挂牌价区间 | 可维修 | 维修费区间 |', '|---|---|---|---|---|---|']
    for d in dom_rows:
        rows = [c for c in cats if c['域'] == d['id']]
        listed = [c for c in rows if c['二手适用']]
        fixed = [c for c in rows if c['维修适用']]
        span = lambda xs, key: '—' if not xs else f"{min(x[key] for x in xs)}—{max(x[key] for x in xs)}"
        caps = sorted({c['二手折价上限'] for c in listed})
        L.append(f"| {d['id']} {d['名称']} | {len(listed)} "
                 f"| {('—' if not caps else (str(caps[0]) if len(caps) == 1 else f'{caps[0]}—{caps[-1]}'))} "
                 f"| {span(listed, '二手挂牌价_必需档')} | {len(fixed)} | {span(fixed, '维修费_必需档')} |")
    L += ['', '## 八、社区住房库存与兜底配额', '',
          f"{canon['汇总']['单元数']} 个单元×{canon['汇总']['住房类型数']} 类住房＝{canon['汇总']['库存行数']} 行统计口径；"
          f"全城户数 {canon['汇总']['全城户数']}，全城人口 {canon['汇总']['全城人口']}（含散居农村"
          f"{canon['散居挂靠']['总人口']}，按聚落登记人口比例挂靠，余数 {canon['散居挂靠']['余数']} 归"
          f"{canon['散居挂靠']['余数归属']}，上浮比例 {canon['散居挂靠']['上浮比例区间'][0]:.4f}—"
          f"{canon['散居挂靠']['上浮比例区间'][1]:.4f}）。", '',
          f"类型配比按圈层给定：{'；'.join(r + '：' + '、'.join(str(x) for x in v) for r, v in ratios.items())}。"
          f"兜底配额＝floor(总量×{p['兜底比例']})，不足 1 户按 1 户。", '',
          '| 单元 | 圈层 | 登记人口 | 挂靠人口 | 单元人口 | 推导户数 | '
          + ' | '.join(f'{house_names[h["id"]]}(总量/配额)' for h in SOURCE['住房类型']) + ' |',
          '|---|---|---|---|---|---|' + '---|' * len(SOURCE['住房类型']) + '---']
    by_unit = {}
    for r in canon['库存']:
        by_unit.setdefault(r['单元ID'], []).append(r)
    for uid in sorted(by_unit):
        rs = by_unit[uid]
        cells = ' | '.join(f"{x['总量']}/{x['兜底配额']}" for x in rs)
        L.append(f"| {uid} | {rs[0]['圈层']} | {rs[0]['登记人口']} | {rs[0]['挂靠人口']} "
                 f"| {rs[0]['单元人口']} | {rs[0]['推导户数']} | {cells} |")
    L += ['', f"口径：{canon['汇总']['口径']}", '']
    head = ['# 钛湖城物价与生活总表', '',
            f"正典来源：`数据/物价生活源表.json`＋`数据/城市空间名录.json`＋`数据/参考房价租金.json`；"
            f"本文件由 `工具/build_costs.py` 生成，基准年 {canon['setting_year']}，货币 {canon['currency_name']}（{canon['currency']}），禁止手改。"]
    return '\n'.join(head + L)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out-dir', default=None)
    parser.add_argument('--print-basket', action='store_true')
    args = parser.parse_args()
    canon = build_canon()
    if args.print_basket:
        print(json.dumps(canon['篮子'], ensure_ascii=False))
        return
    out = Path(args.out_dir) if args.out_dir else ROOT / '数据'
    (out / '物价与生活正典.json').write_bytes(
        json.dumps(canon, ensure_ascii=False, indent=2).encode('utf-8') + b'\n')
    (out / '物价与生活总表.md').write_text(render_table(canon), encoding='utf-8')
    print(json.dumps(canon['汇总'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
