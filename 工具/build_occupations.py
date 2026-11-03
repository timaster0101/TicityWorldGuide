# -*- coding: utf-8 -*-
"""产业与就业层生成器：读名录＋参考房价租金＋产业就业源表，展开 64 区公司骨架、岗位卡与薪酬带。

正典只从三个 read_text 输入取得，脚本内不内嵌任何 ID、名称或坐标常量。
跑法：python 工具/build_occupations.py [--out-dir DIR]
"""
import json, math
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


def load_naming():
    block = SOURCE.get('命名') or {}
    missing = [k for k in ('口径', '字号池', '锚点简称', '小类词根', '档位后缀', '顶端名称') if k not in block]
    if missing:
        raise SystemExit(f'产业就业源表.json 的「命名」缺 {missing}：字号池、锚点简称、小类词根、档位后缀与顶端名称'
                         '只在源表手填，生成器不内嵌名称常量，也不得退回匿名骨架')
    return block


ZERO_KEYS = ('口径', '背景小类', '背景小类专属标签', '通用技能标签', '通用场景',
             '上限截断大类', '上限截断连带标签', '上限截断连带场景')


def load_zero():
    block = SOURCE.get('零消费者') or {}
    missing = [k for k in ZERO_KEYS if k not in block]
    if missing:
        raise SystemExit(f'产业就业源表.json 的「零消费者」缺 {missing}：允许无岗位卡引用的字典条目'
                         '必须逐类手填点名，生成器不代填，门禁第 30 条按同一清单对账')
    return block


ADMISSION = load_admission()
BASE_YEAR = SOURCE['setting_year']
NAMING = load_naming()
ZERO = load_zero()


def load_occ_source():
    path = ROOT / '数据' / '职业条目源表.json'
    if not path.exists():
        raise SystemExit('缺少 数据/职业条目源表.json：职业条目属手填真源，生成器不代填文本，'
                         '门禁第 32 条也不得因无条目可查而空转判绿')
    doc = json.loads(path.read_text(encoding='utf-8'))
    missing = [k for k in ('口径', '规格', '小类') if k not in doc]
    if missing:
        raise SystemExit(f'职业条目源表.json 缺 {missing}：条数带与长度带只住在本表「规格」块，生成器不内嵌常量')
    return doc


OCC_SOURCE = load_occ_source()
from build_admission import contracts_for
from anchors import dwelling_anchors, entry_ring
PARAMS = SOURCE['参数']
BY_ID = {e['id']: e for e in REGISTRY}
PRICE_BY_ID = {r['id']: r for r in PRICING}


def load_baskets(path=ROOT / '数据' / '物价与生活正典.json'):
    if not Path(path).exists():
        raise SystemExit('缺少 数据/物价与生活正典.json：先运行 python 工具/build_costs.py，红线不得静默退回只比 住所锚÷0.40')
    return json.loads(Path(path).read_text(encoding='utf-8'))['篮子']


BASKETS = load_baskets()


def red_lines(anchor, basket):
    """两条候选红线，各自向上取整到月薪取整：第1期的 住所锚÷0.40 与本期的 住所锚＋本圈层基本篮子。"""
    step = PARAMS['月薪取整']
    old = anchor / PARAMS['住所占比判据']
    return (int(math.ceil(old / step) * step),
            int(math.ceil(max(old, anchor + basket) / step) * step))


def monthly_band(anchor, level, shape, tier, basket):
    _, eff = red_lines(anchor, basket)
    base = (anchor / PARAMS['住所占比判据']) * PARAMS['层系数'][level] * shape * PARAMS['档位加成'][tier]
    lo = int(math.floor(base * PARAMS['带宽'][0] / PARAMS['月薪取整']) * PARAMS['月薪取整'])
    hi = int(math.ceil(base * PARAMS['带宽'][1] / PARAMS['月薪取整']) * PARAMS['月薪取整'])
    # 生效线只把落在线下的带顶起，不压低任何卡；带下限取大后带上限同样取大，保证 hi ≥ lo。
    return max(lo, eff), max(hi, eff)


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
SUB = {s['id']: s for s in SOURCE['小类']}
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


def subclass_for(cid, zid, seqs):
    """按大类各自独立轮转取小类；落点在净空禁区内时从轮转池里剔除低空作业小类，避免生成即判红。

    序号取本大类内的第几家，不能取全锚点通用的 k——那会让同一只吃到 k 模大类数的一个剩余类，
    大类数与池长不互质时就有小类永远轮不上（A04-B04、A04-B06 曾因此零消费者）。
    """
    pool = SUBS[cid]
    if zid in NO_FLY:
        safe = [s for s in pool if s['id'] not in LOW_ALT]
        if safe:
            pool = safe
    i = seqs.get(cid, 0)
    seqs[cid] = i + 1
    return pool[i % len(pool)]


def make_company(zid, tier, emp, cid, seq, anchor, sub_seqs):
    layer_scheme = CLASS[cid]['层制']
    allowed = TIERS[tier]['可设岗位层']
    ceiling = CLASS[cid].get('可设岗位层上限')
    if ceiling:
        allowed = [l for l in allowed if l <= ceiling]
    slots = level_slots(emp, layer_scheme, allowed)
    subclass = subclass_for(cid, zid, sub_seqs)
    shape, cards = CLASS[cid]['形状系数'], []
    basket = BASKETS[entry_ring(BY_ID[zid], BY_ID)]
    for l, n in slots:
        lo, hi = monthly_band(anchor, l, shape, tier, basket)
        old_line, eff_line = red_lines(anchor, basket)
        named = TIERS[tier]['逐家具名']
        cards.append({'id': f'POST-CORP-{zid}-{seq:02d}-{subclass["id"]}-{l}', '岗位层': l,
                      '行业小类': subclass['id'], '起始城市年': subclass['起始城市年'],
                      '名额': n, '月薪带_钛币': [lo, hi], '时薪带_钛币': list(hourly(lo, hi)),
                      '红线_钛币': {'住所四成线': old_line, '住所加篮子线': eff_line,
                                 '是否被顶起': eff_line > old_line and lo == eff_line},
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


def company_name(comp, seq_in_group):
    """四段拼接：锚点简称＋字号＋小类词根＋档位后缀；T5 行业顶端整名取源表顶端名称。"""
    if comp['档位'] == 'T5':
        return NAMING['顶端名称'][comp['大类']]
    return (NAMING['锚点简称'][comp['锚点']] + NAMING['字号池'][seq_in_group]
            + NAMING['小类词根'][comp['行业小类']] + NAMING['档位后缀'][comp['档位']])


def name_companies(companies):
    """按正典数组顺序给每个（锚点，档位）组内的具名公司编号，字号取组内序——组内不绕回即全城唯一。"""
    used = {}
    for comp in companies:
        if not comp['逐家具名']:
            continue
        key = (comp['锚点'], comp['档位'])
        seq = used.get(key, 0)
        used[key] = seq + 1
        comp['名称'] = company_name(comp, seq)
    return companies


def expand_companies():
    zw, anchors, hosts = zone_workers(), dwelling_anchors(), t5_hosts()
    host_by_anchor = {v: k for k, v in hosts.items()}
    companies = []
    sub_seqs = {}
    for zid in sorted(zw, key=lambda x: (x[0], x[1:])):
        classes = [c for c in ZONE_TO_CLASSES.get(zid, []) if CLASS[c]['可招聘'] is True] or \
                  [c for c in ZONE_TO_CLASSES.get(zid, [])]
        w, cap = zw[zid], per_company_cap(zw[zid])
        t5_emp = min(T5_BAND[1], math.floor(w * PARAMS['单公司占区配额上限'])) if zid in host_by_anchor else 0
        t4_left = 0 if BY_ID[zid].get('type') == '特色村落' else PARAMS['T4每区家数上限']
        rows = split_zone(w, cap, t4_left, t5_emp)
        for k, (tier, emp) in enumerate(rows, start=1):
            cid = host_by_anchor[zid] if tier == 'T5' else classes[(k - 1) % len(classes)]
            companies.append(make_company(zid, tier, emp, cid, k, anchors[zid], sub_seqs))
    return name_companies(companies)


def expand_occupations(companies):
    """把 数据/职业条目源表.json 的手填条目展开成正典的职业条目清单，并按小类挂上正典里真实存在的岗位层。

    OCC 编号＝OCC-{小类 ID}-{组内两位序}；起始年、公共部门、可招聘取所属小类与大类行，
    适用层／关联岗位卡数／覆盖名额由展开后的岗位卡现算——条目不重复声明任何数字，数字只有一个真源。
    """
    spec = OCC_SOURCE['规格']
    lo, hi = spec['每类条数']
    fields = spec['字段']
    cards = {}
    for comp in companies:
        for card in comp['岗位卡']:
            b = cards.setdefault(card['行业小类'], {'卡数': 0, '名额': 0, '层': set()})
            b['卡数'] += 1
            b['名额'] += card['名额']
            b['层'].add(card['岗位层'])
    entries, seen = [], {}
    for row in OCC_SOURCE['小类']:
        sid = row['小类']
        if sid not in SUB:
            raise SystemExit(f'职业条目源表.json 的小类 {sid} 不在行业小类内')
        if not SUB[sid]['生成岗位卡']:
            raise SystemExit(f'职业条目源表.json 的背景在册小类 {sid} 出了条目：背景小类不得有职业条目')
        occ = row['职业']
        if not lo <= len(occ) <= hi:
            raise SystemExit(f'职业条目源表.json 的 {sid} 有 {len(occ)} 条，越出每类 {lo}—{hi}')
        sub, cls = SUB[sid], CLASS[SUB[sid]['父大类']]
        agg = cards.get(sid, {'卡数': 0, '名额': 0, '层': set()})
        for i, o in enumerate(occ, start=1):
            absent = [f for f in fields if f not in o]
            if absent:
                raise SystemExit(f'职业条目源表.json 的 {sid} 第 {i} 条缺字段 {absent}')
            if o['名称'] in seen:
                raise SystemExit(f"职业条目源表.json 名称重复：{o['名称']}（{seen[o['名称']]} 与 {sid}）")
            seen[o['名称']] = sid
            entries.append(dict({'id': f'OCC-{sid}-{i:02d}', '小类': sid, '小类名称': sub['名称'],
                                 '大类': cls['id'], '大类名称': cls['名称'],
                                 '起始城市年': sub['起始城市年'], '公共部门': cls.get('公共部门', False),
                                 '可招聘': cls['可招聘'], '适用层': sorted(agg['层']),
                                 '关联岗位卡数': agg['卡数'], '覆盖名额': agg['名额']},
                                **{f: o[f] for f in fields}))
    band = spec['总条数区间']
    if not band[0] <= len(entries) <= band[1]:
        raise SystemExit(f'职业条目总数 {len(entries)} 越出源表声明的总量带 {band}')
    return entries


def render_occupations(canon):
    """职业条目总表：按大类分组，逐小类列出条目正文与该小类的岗位卡挂接读数。"""
    lines = ['# 钛湖城职业条目总表', '',
             '正典来源：`数据/职业条目源表.json`（手填正文与规格）＋`数据/产业就业正典.json`（派生挂接）；本文件由生成器输出，禁止手改。', '',
             OCC_SOURCE['口径'], '',
             f"合计 {canon['汇总']['职业条目数']} 条职业条目，覆盖 {canon['汇总']['职业条目覆盖小类数']} 个可出卡小类；"
             f"名称全城唯一，适用层与名额读数由该小类的岗位卡加总而来。", '']
    by_class = {}
    for e in canon['职业条目']:
        by_class.setdefault(e['大类'], []).append(e)
    for cid in sorted(by_class):
        rows = by_class[cid]
        cls = CLASS[cid]
        lines += [f"## {cid} {cls['名称']}", '',
                  f"{cls['经济属性']} · {len({r['小类'] for r in rows})} 个小类 · {len(rows)} 条条目"
                  f" · {'公共部门，岗位不可申请' if cls.get('公共部门') else '可招聘' if cls['可招聘'] else '不可招聘'}", '']
        for sid in sorted({r['小类'] for r in rows}):
            sub_rows = [r for r in rows if r['小类'] == sid]
            lines += [f"### {sid} {sub_rows[0]['小类名称']}", '',
                      f"起始城市年 {sub_rows[0]['起始城市年']} · 适用层 {'、'.join(sub_rows[0]['适用层'])}"
                      f" · 关联岗位卡 {sub_rows[0]['关联岗位卡数']} 张 · 覆盖名额 {sub_rows[0]['覆盖名额']:,}", '',
                      '| 条目 | 名称 | 职责 | 日常循环 | 交付物 | 协作对象 | 常见异常 |',
                      '|---|---|---|---|---|---|---|']
            for e in sub_rows:
                lines.append(f"| {e['id']} | {e['名称']} | {e['职责']} | {' → '.join(e['日常循环'])} "
                             f"| {e['交付物']} | {'、'.join(e['协作对象'])} | {e['常见异常']} |")
            lines.append('')
    return '\n'.join(lines).rstrip('\n') + '\n'


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
    lines += ['', '## 具名命名规则', '',
              NAMING['口径'], '', '| 档 | 后缀 | 顶端整名 |', '|---|---|---|']
    for t in canon['公司档']:
        lines.append(f"| {t['档']} {t['名称']} | {NAMING['档位后缀'][t['档']] if t['逐家具名'] else '—（不具名）'} "
                     f"| {'是' if t['档'] == 'T5' else '否'} |")
    lines += ['', '| 大类 | T5 锚点 | 顶端名称 |', '|---|---|---|']
    for comp in canon['公司']:
        if comp['档位'] == 'T5':
            lines.append(f"| {comp['大类']} | {comp['锚点']} {comp['锚点名称']} | {comp['名称']} |")
    lines += ['', '## 字典统计', '',
              f"岗位准入字典：标签 {d['标签数']} 条、场景 {d['场景数']} 项、合同类型 {d['合同类型数']} 类、"
              f"卡牌族 {d['卡牌族数']} 族；卡片侧引用共 {refs} 处，逐条取值见 `数据/岗位准入总表.md`。", '',
              '## 零消费者登记', '', ZERO['口径'], '']
    lines += ['| 类 | 条数 | 明细 |', '|---|---|---|']
    subs = {s['id']: s['名称'] for s in canon['行业']['小类']}
    tag_name = {t['id']: t['名称'] for t in ADMISSION['标签']}
    scene_name = {s['id']: s['名称'] for s in ADMISSION['场景']}
    lines.append("| 背景在册小类 | " + str(len(ZERO['背景小类']))
                 + " | " + '、'.join(f'{i} {subs.get(i, "")}' for i in ZERO['背景小类']) + ' |')
    lines.append('| 背景小类专属标签 | ' + str(len(ZERO['背景小类专属标签'])) + ' | '
                 + '、'.join(f'{i} {tag_name.get(i, "")}' for i in ZERO['背景小类专属标签']) + ' |')
    lines.append('| 通用技能 | ' + str(len(ZERO['通用技能标签'])) + ' | '
                 + '、'.join(f'{i} {tag_name.get(i, "")}' for i in ZERO['通用技能标签']) + ' |')
    lines.append('| 通用场景 | ' + str(len(ZERO['通用场景'])) + ' | '
                 + '、'.join(f'{i} {scene_name.get(i, "")}' for i in ZERO['通用场景']) + ' |')
    caps = {c['id']: c.get('可设岗位层上限') for c in canon['行业']['大类']}
    lines.append('| 上限截断大类 | ' + str(len(ZERO['上限截断大类'])) + ' | '
                 + '、'.join(f'{k}（上限 {caps.get(k)}，截断 {"／".join(v)}）'
                             for k, v in sorted(ZERO['上限截断大类'].items())) + ' |')
    lines.append('| 截断连带标签 | ' + str(len(ZERO['上限截断连带标签'])) + ' | '
                 + '、'.join(f'{i} {tag_name.get(i, "")}' for i in ZERO['上限截断连带标签']) + ' |')
    lines.append('| 截断连带场景 | ' + str(len(ZERO['上限截断连带场景'])) + ' | '
                 + '、'.join(f'{i} {scene_name.get(i, "")}' for i in ZERO['上限截断连带场景']) + ' |')
    return '\n'.join(lines) + '\n'


def render_directory(canon):
    """具名公司名录：按锚点分组的逐家名称表，只列 逐家具名=true 的行。"""
    lines = ['# 钛湖城具名公司名录', '',
             '正典来源：`数据/产业就业源表.json` 的「命名」块＋`数据/产业就业正典.json`；本文件由生成器输出，禁止手改。', '',
             NAMING['口径'], '',
             'T1 为每区一条的个体户统计口径，不具名，故不在本名录内。', '']
    by_zone = {}
    for c in canon['公司']:
        if c['逐家具名']:
            by_zone.setdefault(c['锚点'], []).append(c)
    subs = {s['id']: s for s in canon['行业']['小类']}
    for zid in sorted(by_zone):
        rows = by_zone[zid]
        lines += [f'## {zid} {rows[0]["锚点名称"]}', '',
                  '| 公司 | 名称 | 档 | 大类 | 小类 | 雇员数 |', '|---|---|---|---|---|---|']
        for c in rows:
            lines.append(f"| {c['id']} | {c['名称']} | {c['档位']} | {c['大类']} "
                         f"| {c['行业小类']} {subs[c['行业小类']]['名称']} | {c['雇员数']} |")
        lines.append('')
    return '\n'.join(lines).rstrip('\n') + '\n'


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--out-dir', default=None)
    args = parser.parse_args()
    out = Path(args.out_dir) if args.out_dir else ROOT / '数据'
    zw, anchors, companies = zone_workers(), dwelling_anchors(), expand_companies()
    occupations = expand_occupations(companies)
    lifted = [c for comp in companies for c in comp['岗位卡'] if c['红线_钛币']['是否被顶起']]
    lifted_by_ring = {}
    for comp in companies:
        ring = entry_ring(BY_ID[comp['锚点']], BY_ID)
        bucket = lifted_by_ring.setdefault(ring, [0, 0])
        bucket[0] += sum(1 for c in comp['岗位卡'] if c['红线_钛币']['是否被顶起'])
        bucket[1] += sum(c['名额'] for c in comp['岗位卡'] if c['红线_钛币']['是否被顶起'])
    canon = {
        'version': '1.0', 'fictional': True, 'setting_year': SOURCE['setting_year'],
        'currency': 'TT', 'currency_name': '钛币',
        'declaration': '本文件由 工具/build_occupations.py 从 产业就业源表.json＋职业条目源表.json＋城市空间名录.json＋参考房价租金.json 生成，属派生正典；修改请改源表与生成器并重跑，不要手改本文件。'
                       '具名公司名称按 产业就业源表.json 的「命名」块四段拼接（锚点简称＋字号＋小类词根＋档位后缀），T5 行业顶端整名取顶端名称。'
                       '职业条目正文逐字来自 数据/职业条目源表.json，本文件里的 id、适用层、起始年、关联岗位卡数与覆盖名额由生成器按同一份岗位卡展开算出。',
        '参数': PARAMS, '行业': {'大类': SOURCE['大类'], '小类': SOURCE['小类']},
        '岗位层': SOURCE['岗位层'], '公司档': SOURCE['公司档'],
        '住所锚': {k: v for k, v in sorted(anchors.items())},
        '公司': companies,
        '职业条目': occupations,
        '汇总': {
            '岗位锚点数': len(zw), '公司数': len(companies),
            '具名公司数': sum(1 for c in companies if c['逐家具名']),
            '具名命名数': sum(1 for c in companies if c['名称']),
            'T5数': sum(1 for c in companies if c['档位'] == 'T5'),
            '岗位卡数': sum(len(c['岗位卡']) for c in companies),
            '雇员总数': sum(c['雇员数'] for c in companies),
            '名录岗位总数': sum(zw.values()),
            '被顶起卡数': len(lifted), '被顶起名额数': sum(c['名额'] for c in lifted),
            '职业条目数': len(occupations),
            '职业条目覆盖小类数': len({e['小类'] for e in occupations}),
            '被顶起按圈层': {k: lifted_by_ring[k] for k in sorted(lifted_by_ring)},
            '口径': '雇员数守恒于功能区与聚落的日常岗位规模；聚落岗位数不等于常住人口。'
                    'T1 为每区一条的个体户统计口径，不计入具名公司数，名称字段为 null。'
                    '具名公司的名称由源表「命名」块四段拼接，与 具名公司数 一一对应。'
                    '被顶起按圈层的两个数是 [卡数, 名额数]，口径为 生效线 由 住所加篮子 而非 住所四成 决定的卡。'
                    '职业条目数取 数据/职业条目源表.json 展开后的条目数，覆盖小类数须等于可出卡小类数（背景在册小类除外）。',
        },
    }
    (out / '产业就业正典.json').write_text(json.dumps(canon, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / '产业与就业总表.md').write_text(render_table(canon), encoding='utf-8')
    (out / '公司具名名录.md').write_text(render_directory(canon), encoding='utf-8')
    (out / '职业条目总表.md').write_text(render_occupations(canon), encoding='utf-8')
    print(json.dumps(canon['汇总'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
