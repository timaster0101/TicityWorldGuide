# -*- coding: utf-8 -*-
"""产业与就业层生成器：读名录＋参考房价租金＋产业就业源表，展开 64 区公司骨架、岗位卡与薪酬带。

正典只从三个 read_text 输入取得，脚本内不内嵌任何 ID、名称或坐标常量。
跑法：python 工具/build_occupations.py [--out-dir DIR]
"""
import json, math, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = json.loads((ROOT / '数据' / '产业就业源表.json').read_text(encoding='utf-8'))
REGISTRY = json.loads((ROOT / '数据' / '城市空间名录.json').read_text(encoding='utf-8'))['entries']
PRICING = json.loads((ROOT / '数据' / '参考房价租金.json').read_text(encoding='utf-8'))['records']


def load_admission():
    path = ROOT / '数据' / '岗位准入正典.json'
    if not path.exists():
        raise SystemExit('缺少 数据/岗位准入正典.json：先运行 python 工具/build_admission.py，不得生成无引用正典')
    return json.loads(path.read_text(encoding='utf-8'))


ADMISSION = load_admission()
BASE_YEAR = SOURCE['setting_year']
from build_admission import contracts_for
PARAMS = SOURCE['参数']
BY_ID = {e['id']: e for e in REGISTRY}
PRICE_BY_ID = {r['id']: r for r in PRICING}


def household_area_proxy():
    values = [r['typical_dwelling']['avg_unit_gross_floor_area_m2'] for r in PRICING if 'typical_dwelling' in r]
    return statistics.median(values)


def district_anchors():
    """全部锚点：D 取其下属 R 的户均月租中位数；F 继承所属 D；S 用每平方米月租×户均面积代理。"""
    anchors = {}
    for d in [e for e in REGISTRY if e['type'] == '城市片区']:
        rents = [r['typical_dwelling']['monthly_rent_tt'] for r in PRICING
                 if r.get('parent') == d['id'] and 'typical_dwelling' in r]
        anchors[d['id']] = round(statistics.median(rents), 1)
    for f in [e for e in REGISTRY if e['type'] == '功能区']:
        anchors[f['id']] = anchors[f['parent']]
    proxy = household_area_proxy()
    for s in [e for e in REGISTRY if e['id'].startswith('S')]:
        anchors[s['id']] = round(PRICE_BY_ID[s['id']]['residential']['rent_tt_per_m2_month'] * proxy, 1)
    return anchors


def dwelling_anchors():
    """只保留可作为岗位锚点的 64 区（40F＋24S）；D 键只作继承，不对外暴露。"""
    return {k: v for k, v in district_anchors().items() if k[0] in 'FS'}


def monthly_band(anchor, level, shape, tier):
    red_line = anchor / PARAMS['住所占比判据']
    base = red_line * PARAMS['层系数'][level] * shape * PARAMS['档位加成'][tier]
    lo = int(math.floor(base * PARAMS['带宽'][0] / PARAMS['月薪取整']) * PARAMS['月薪取整'])
    hi = int(math.ceil(base * PARAMS['带宽'][1] / PARAMS['月薪取整']) * PARAMS['月薪取整'])
    if level == 'LVL1':
        # §5 第4条红线：一个全职岗位要撑得起住所锚 ÷ 0.40。形状系数 <1.00 的大类公式值在线下，带下限被钳平。
        lo = max(lo, int(math.ceil(red_line / PARAMS['月薪取整']) * PARAMS['月薪取整']))
    return lo, hi


def hourly(low, high):
    step = PARAMS['时薪取整']
    return (round(round(low / PARAMS['月标准工时'] / step) * step, 2),
            round(round(high / PARAMS['月标准工时'] / step) * step, 2))


def zone_workers():
    return {e['id']: int(e['daily_workers']) for e in REGISTRY if 'daily_workers' in e and e['id'][0] in 'FS'}


def per_company_cap(w):
    return max(1, min(PARAMS['单公司雇员上限'], math.floor(w * PARAMS['单公司占区配额上限'])))


BANDS = [(t['档'], t['雇员数'][0], t['雇员数'][1])
         for t in sorted(SOURCE['公司档'], key=lambda x: -x['雇员数'][0]) if t['档'] != 'T5']
NAMED_BANDS = [b for b in BANDS if b[0] != 'T1']
T5_BAND = tuple(next(t['雇员数'] for t in SOURCE['公司档'] if t['档'] == 'T5'))


def cut(budget, lo, hi):
    """把 budget 人切成尽量少的公司，每家落在 [lo, hi]；切不出返回 None，整笔余额交下一档回收。"""
    if budget < lo or hi < lo:
        return None
    n = max(1, math.ceil(budget / hi))
    if n > budget // lo:
        return None
    base, rem = divmod(budget, n)
    return [base + (1 if i < rem else 0) for i in range(n)]


def split_zone(w, cap, t4_left, t5_employees=0):
    """按档位人数配比切各区岗位池：T4→T2 依次认领，切不动的整笔向下结转，T1 收全部余数并合记一条。

    T1 在源表里 逐家具名=false，是统计口径而非一家个体户，所以这一行的人数可以越过个体户的 1—5 人档区间，
    单公司占区配额上限也不套在它身上——verify_occupations 的第 3 条门禁按 逐家具名 跳过统计条。
    """
    rows = [('T5', t5_employees)] if t5_employees else []
    pool = w - t5_employees
    carry, allocated = 0, 0
    for tier, lo, hi in NAMED_BANDS:
        hi = min(hi, cap)
        budget = carry + math.floor(pool * PARAMS['档位人数配比'][tier] + 0.5)
        if tier == 'T4':
            if t4_left <= 0:
                carry = budget
                continue
            budget = min(budget, t4_left * hi)
        chunks = cut(budget, lo, hi)
        if not chunks:
            carry = budget
            continue
        rows += [(tier, e) for e in chunks]
        carry, allocated = 0, allocated + sum(chunks)
    return rows + [('T1', pool - allocated)]


def t5_hosts():
    """每个大类恰好一家 T5，且一锚只放一家：按候选最少的类先占位，避免多类撞同一锚。"""
    zw = zone_workers()
    min_zone = math.ceil(T5_BAND[0] / PARAMS['单公司占区配额上限'])
    pools = {c['id']: sorted((z for z in c['可落锚点'] if z in zw and zw[z] >= min_zone),
                             key=lambda z: (-zw[z], z)) for c in SOURCE['大类']}
    for cid, cand in pools.items():
        if not cand:
            raise SystemExit(f'T5 无可用锚点：{cid}（需要 daily_workers ≥ {min_zone} 的可落锚点）')
    hosts, taken = {}, set()
    for cid in sorted(pools, key=lambda k: (len(pools[k]), k)):
        for z in pools[cid]:
            if z not in taken:
                hosts[cid] = z
                taken.add(z)
                break
        else:
            raise SystemExit(f'T5 锚点冲突：{cid} 的候选被占满，请回源表补可落锚点，不要放宽门禁')
    return hosts


SUBS = {s['父大类']: [] for s in SOURCE['小类']}
for _s in SOURCE['小类']:
    if _s['生成岗位卡']:
        SUBS[_s['父大类']].append(_s)
TIERS = {t['档']: t for t in SOURCE['公司档']}
CLASS = {c['id']: c for c in SOURCE['大类']}
ZONE_TO_CLASSES = {}
for _c in SOURCE['大类']:
    for _z in _c['可落锚点']:
        ZONE_TO_CLASSES.setdefault(_z, []).append(_c['id'])


def level_slots(emp, scheme, allowed):
    """最大余额法按层名额分布切人：整数名额之和恒等于雇员数，不产生 0 人层；最低层保底 1 人。

    名额分布先在被允许的那几层内部归一：T1／T2 只开到 LVL3，5 层配额在这三层上只合计 0.84，
    不归一就会少分掉名额（余额个数超过可选层数），守恒式在岗位卡层面破掉。
    """
    quota = PARAMS['层名额分布'][f'{scheme}层']
    levels = [l for l in allowed if quota.get(l, 0) > 0]
    share = sum(quota[l] for l in levels)
    raw = [(l, emp * quota[l] / share) for l in levels]
    counts = {l: math.floor(v) for l, v in raw}
    for l, _ in sorted(raw, key=lambda x: counts[x[0]] - x[1])[:emp - sum(counts.values())]:
        counts[l] += 1
    if counts[levels[0]] == 0:
        donor = max(levels, key=lambda l: counts[l])
        counts[donor] -= 1
        counts[levels[0]] = 1
    return [(l, counts[l]) for l in levels if counts[l] > 0]


def required_tags(level, sub_id, class_id):
    """按 层级标签绑定 展开本卡必需标签：专属取本小类，经历与资质取本大类。"""
    out = []
    for b in ADMISSION['层级标签绑定'][level]:
        kind, need, count = b['族'], b['要求'], b['最少']
        if kind in ('S1', 'S2'):
            out.append(['SKL-' + sub_id + '-' + kind, need])
        elif kind == '经历':
            out.extend([['SKL-E-' + class_id + '-' + str(i), need] for i in range(1, count + 1)])
        else:
            out.append(['SKL-Q-' + class_id, need])
    return out


def scenes_for(level, class_id):
    """该层可判定的行业关键场景；通用场景跨层共用，不挂在具体卡片上。"""
    return [s['id'] for s in ADMISSION['场景'] if s['类别'] == '行业'
            and level in s['触发岗位层'] and class_id in s['适用大类']]


NO_FLY = set(SOURCE['禁则']['无人机禁区'])
LOW_ALT = set(SOURCE['禁则']['低空作业小类'])


def subclass_for(cid, seq, zid):
    """轮转取小类；落点在净空禁区内时从轮转池里剔除低空作业小类，避免生成即判红。"""
    pool = SUBS[cid]
    if zid in NO_FLY:
        safe = [s for s in pool if s['id'] not in LOW_ALT]
        if safe:
            pool = safe
    return pool[seq % len(pool)]


def make_company(zid, tier, emp, cid, seq, anchor):
    layer_scheme = CLASS[cid]['层制']
    allowed = TIERS[tier]['可设岗位层']
    ceiling = CLASS[cid].get('可设岗位层上限')
    if ceiling:
        allowed = [l for l in allowed if l <= ceiling]
    slots = level_slots(emp, layer_scheme, allowed)
    subclass = subclass_for(cid, seq, zid)
    shape, cards = CLASS[cid]['形状系数'], []
    for l, n in slots:
        lo, hi = monthly_band(anchor, l, shape, tier)
        named = TIERS[tier]['逐家具名']
        cards.append({'id': f'POST-CORP-{zid}-{seq:02d}-{subclass["id"]}-{l}', '岗位层': l,
                      '行业小类': subclass['id'], '起始城市年': subclass['起始城市年'],
                      '名额': n, '月薪带_钛币': [lo, hi], '时薪带_钛币': list(hourly(lo, hi)),
                      '用工形态': ['全职', '兼职', '轮班', '临时', '自由接单'],
                      '占用名额': True,
                      '准入标签': required_tags(l, subclass['id'], cid),
                      '关键场景': scenes_for(l, cid),
                      '合同类型': ['CTR-06', 'CTR-07'] if not named
                                  else contracts_for(l, tier, subclass['准入形态']),
                      '释放状态': 'RLS-01' if subclass['起始城市年'] > BASE_YEAR else 'RLS-02'})
    return {'id': f'CORP-{zid}-{seq:02d}', '档位': tier, '大类': cid, '行业小类': subclass['id'],
            '锚点': zid, '锚点名称': BY_ID[zid]['name'], '办公地点': zid, '岗位配额来自': zid,
            '雇员数': emp, '可招聘': CLASS[cid]['可招聘'], '逐家具名': TIERS[tier]['逐家具名'],
            '名称': None, '岗位卡': cards}


def expand_companies():
    zw, anchors, hosts = zone_workers(), dwelling_anchors(), t5_hosts()
    host_by_anchor = {v: k for k, v in hosts.items()}
    companies = []
    for zid in sorted(zw, key=lambda x: (x[0], x[1:])):
        classes = [c for c in ZONE_TO_CLASSES.get(zid, []) if CLASS[c]['可招聘'] is True] or \
                  [c for c in ZONE_TO_CLASSES.get(zid, [])]
        w, cap = zw[zid], per_company_cap(zw[zid])
        t5_emp = min(T5_BAND[1], math.floor(w * PARAMS['单公司占区配额上限'])) if zid in host_by_anchor else 0
        t4_left = 0 if BY_ID[zid].get('type') == '特色村落' else PARAMS['T4每区家数上限']
        rows = split_zone(w, cap, t4_left, t5_emp)
        for k, (tier, emp) in enumerate(rows, start=1):
            cid = host_by_anchor[zid] if tier == 'T5' else classes[(k - 1) % len(classes)]
            companies.append(make_company(zid, tier, emp, cid, k, anchors[zid]))
    return companies


def render_table(canon):
    lines = ['# 钛湖城产业与就业总表', '',
             '正典来源：`数据/产业就业源表.json`＋`数据/城市空间名录.json`＋`数据/参考房价租金.json`；本文件由生成器输出，禁止手改。', '',
             '## 行业大类', '', '| 大类 | 小类数 | 层制 | 形状系数 | 起始年下限 | 顶端雇主 | 可招聘 |', '|---|---|---|---|---|---|---|']
    subs = {}
    for s in canon['行业']['小类']:
        subs[s['父大类']] = subs.get(s['父大类'], 0) + 1
    for c in canon['行业']['大类']:
        lines.append(f"| {c['id']} {c['名称']} | {subs[c['id']]} | {c['层制']} | {c['形状系数']:.2f} "
                     f"| {c['起始年下限']} | {'是' if c['顶端雇主'] else '否'} | {'是' if c['可招聘'] else '否（背景在册）'} |")
    lines += ['', '## 分区公司骨架', '', '| 锚点 | 名称 | 岗位规模 | 公司数 | 具名家数 | 档位分布 | LVL1月薪带下限 | 住所锚 |',
              '|---|---|---|---|---|---|---|---|']
    by_zone = {}
    for c in canon['公司']:
        by_zone.setdefault(c['锚点'], []).append(c)
    for zid in sorted(by_zone):
        rows = by_zone[zid]
        dist = {}
        for c in rows:
            dist[c['档位']] = dist.get(c['档位'], 0) + 1
        floor1 = min(min(row['岗位卡'][0]['月薪带_钛币']) for row in rows if row['岗位卡'])
        lines.append(f"| {zid} | {rows[0]['锚点名称']} | {sum(c['雇员数'] for c in rows)} | {len(rows)} "
                     f"| {sum(1 for c in rows if c['逐家具名'])} "
                     f"| {'、'.join(f'{k}×{v}' for k, v in sorted(dist.items()))} | {floor1} | {canon['住所锚'][zid]} |")
    d = ADMISSION['汇总']
    refs = sum(len(c['准入标签']) + len(c['关键场景']) + len(c['合同类型']) + 1
               for comp in canon['公司'] for c in comp['岗位卡'])
    lines += ['', '## 字典统计', '',
              f"岗位准入字典：标签 {d['标签数']} 条、场景 {d['场景数']} 项、合同类型 {d['合同类型数']} 类、"
              f"卡牌族 {d['卡牌族数']} 族；卡片侧引用共 {refs} 处，逐条取值见 `数据/岗位准入总表.md`。", '']
    return '\n'.join(lines) + '\n'


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--out-dir', default=None)
    args = parser.parse_args()
    out = Path(args.out_dir) if args.out_dir else ROOT / '数据'
    zw, anchors, companies = zone_workers(), dwelling_anchors(), expand_companies()
    canon = {
        'version': '1.0', 'fictional': True, 'setting_year': SOURCE['setting_year'],
        'currency': 'TT', 'currency_name': '钛币',
        'declaration': '本文件由 工具/build_occupations.py 从 产业就业源表.json＋城市空间名录.json＋参考房价租金.json 生成，属派生正典；修改请改源表与生成器并重跑，不要手改本文件。公司具名与具体职业条目属后续分期，本期为骨架与参数。',
        '参数': PARAMS, '行业': {'大类': SOURCE['大类'], '小类': SOURCE['小类']},
        '岗位层': SOURCE['岗位层'], '公司档': SOURCE['公司档'],
        '住所锚': {k: v for k, v in sorted(anchors.items())},
        '公司': companies,
        '汇总': {
            '岗位锚点数': len(zw), '公司数': len(companies),
            '具名公司数': sum(1 for c in companies if c['逐家具名']),
            'T5数': sum(1 for c in companies if c['档位'] == 'T5'),
            '岗位卡数': sum(len(c['岗位卡']) for c in companies),
            '雇员总数': sum(c['雇员数'] for c in companies),
            '名录岗位总数': sum(zw.values()),
            '口径': '雇员数守恒于功能区与聚落的日常岗位规模；聚落岗位数不等于常住人口。'
                    'T1 为每区一条的个体户统计口径，不计入具名公司数。',
        },
    }
    (out / '产业就业正典.json').write_text(json.dumps(canon, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / '产业与就业总表.md').write_text(render_table(canon), encoding='utf-8')
    print(json.dumps(canon['汇总'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
