# -*- coding: utf-8 -*-
"""产业与就业层闸门：三十五条判红全部落在数据层（十条产业＋六条字典＋四条物价＋五条运行参数＋四条具名命名＋一条零消费者对账＋一条产业图层对账＋一条职业条目对账＋一条失业救助对账＋一条五维开局对账＋一条卡牌实例对账），任一失败即非零退出。跑法：python 工具/verify_occupations.py"""
import json, math, re
from pathlib import Path

from anchors import entry_ring, RINGS, pair_key, ring_pair_stats

ROOT = Path(__file__).resolve().parents[1]
SOURCE = json.loads((ROOT / '数据' / '产业就业源表.json').read_text(encoding='utf-8'))
REGISTRY = json.loads((ROOT / '数据' / '城市空间名录.json').read_text(encoding='utf-8'))['entries']
# 失业救助的比例与月数只住在这份手填真源里；正典的 参数 块是它的副本，拿副本对副本等于本表自证，故直接读源表。
COST_SRC_PATH = ROOT / '数据' / '物价生活源表.json'
if not COST_SRC_PATH.exists():
    raise SystemExit('缺少 数据/物价生活源表.json：失业救助三列金额由它派生，'
                     '救助门禁不得因无源表可查而空转判绿')
COST_SOURCE = json.loads(COST_SRC_PATH.read_text(encoding='utf-8'))['参数']
# 第 34 条的三条等式要拿长期习惯卡的幅度上限做对照，那句中文措辞住在手填的岗位准入源表里。
ADM_SRC_PATH = ROOT / '数据' / '岗位准入源表.json'
if not ADM_SRC_PATH.exists():
    raise SystemExit('缺少 数据/岗位准入源表.json：CRD-A3 的幅度上限与效果对象只住在这份手填真源里，'
                     '开局等式门禁不得因无源表可查而空转判绿')
ADM_SOURCE = json.loads(ADM_SRC_PATH.read_text(encoding='utf-8'))


def num(x):
    """与 build_params.num 同式：0.1×100 的浮点尾巴会咬死跨源等式，点数一律先收敛到整数。"""
    r = round(x, 6)
    return int(r) if r == int(r) else r

MONTH_DAYS = dict(zip(range(1, 13), [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]))
INNER = ('内湖环', '外城环')


def expand_runs(runs):
    return [code for code, count in runs for _ in range(count)]


def transfer_minutes(sp, code, a, b):
    if code == 'TR-BUS' and a != b:
        return sp['公交跨圈换乘分钟']
    if code == 'TR-RAIL' and (a in INNER) != (b in INNER):
        return sp['铁路内外衔接分钟']
    return 0


def sea_of(params):
    out = {}
    for sea, info in params['参数']['季节月份'].items():
        for m in info['月']:
            out[str(m)] = sea
    return out


def issues(canon, source, registry, adm, costs, params, psource, layer, occ_source, card_source):
    out, p = [], canon['参数']
    by_id = {e['id']: e for e in registry}
    bands = {t['档']: tuple(t['雇员数']) for t in source['公司档']}
    zw = {e['id']: int(e['daily_workers']) for e in registry if 'daily_workers' in e and e['id'][0] in 'FS'}
    by_zone = {}
    for c in canon['公司']:
        by_zone.setdefault(c['锚点'], []).append(c)
    subs = {s['id']: s for s in canon['行业']['小类']}

    # 1 逐区守恒：公司雇员之和必须等于名录日常岗位，锚点集合不得多也不得少
    for z, want in sorted(zw.items()):
        got = sum(c['雇员数'] for c in by_zone.get(z, []))
        if got != want:
            out.append(f'守恒: {z} 公司雇员 {got} != 名录日常岗位 {want}')
    if set(by_zone) != set(zw):
        out.append(f'守恒: 锚点集合不一致 {sorted(set(by_zone) ^ set(zw))[:6]}')

    # 2 T5 恰好每大类一家
    t5 = [c for c in canon['公司'] if c['档位'] == 'T5']
    if len(t5) != len(source['大类']):
        out.append(f'T5: 数量 {len(t5)} != 大类数 {len(source["大类"])}')
    if len({c['大类'] for c in t5}) != len(t5):
        out.append('T5: 同大类出现多家')

    # 3 档位区间、单公司占比、T4 家数与 T1 统计口径
    #   T1 在源表里 逐家具名=false，是每区一条的个体户统计口径，不套个体户 1—5 人档区间与占比上限
    ratio, t4_max = p['单公司占区配额上限'], p['T4每区家数上限']
    for c in canon['公司']:
        if not c['逐家具名']:
            continue
        lo, hi = bands[c['档位']]
        if not lo <= c['雇员数'] <= hi:
            out.append(f'档位区间: {c["id"]} {c["档位"]} 雇员 {c["雇员数"]} 不在 [{lo}, {hi}]')
        if c['雇员数'] > max(1, math.floor(zw[c['锚点']] * ratio)):
            out.append(f'占比: {c["id"]} 雇员 {c["雇员数"]} 超过所在区配额上限')
    for z, rows in sorted(by_zone.items()):
        n_t4 = sum(1 for x in rows if x['档位'] == 'T4')
        if n_t4 > t4_max:
            out.append(f'T4: {z} 有 {n_t4} 家，超过上限 {t4_max}')
        if n_t4 and by_id[z].get('type') == '特色村落':
            out.append(f'落点: {z} 特色村落没有专属功能区，不该有 T4')
        if sum(1 for x in rows if x['逐家具名'] is False) != 1:
            out.append(f'T1统计口径: {z} 应有且只应有 1 条')

    # 4 住所覆盖红线：LVL1 带下限不得低于住所锚 ÷ 判据
    for c in canon['公司']:
        for card in c['岗位卡']:
            if card['岗位层'] != 'LVL1':
                continue
            floor = canon['住所锚'][c['锚点']] / p['住所占比判据']
            if card['月薪带_钛币'][0] < floor:
                out.append(f'住所覆盖红线: {card["id"]} 月薪下限 {card["月薪带_钛币"][0]} < {floor:.0f}')

    # 5 层系数严格单调且不倒挂
    coef, order = p['层系数'], ['LVL1', 'LVL2', 'LVL3', 'LVL4', 'LVL5']
    for a, b in zip(order, order[1:]):
        if coef[b] <= coef[a]:
            out.append(f'层系数非单调: {a}->{b}')
    if coef['LVL5'] / coef['LVL1'] > 5.0:
        out.append('层系数: LVL5/LVL1 超过 5.0')

    # 6 起始年窗口，且卡片起始年必须等于所属小类
    win0, win1 = source['禁则']['起始年窗口']
    for s in canon['行业']['小类']:
        if not win0 <= s['起始城市年'] <= win1:
            out.append(f'起始年越窗: {s["id"]} {s["起始城市年"]}')
    for c in canon['公司']:
        for card in c['岗位卡']:
            sub = subs.get(card['行业小类'])
            if sub and card['起始城市年'] != sub['起始城市年']:
                out.append(f'起始年漂移: {card["id"]}')

    # 7 A08 职责禁则：关键词不得出现在层职责或生成岗位卡的小类名称里，背景小类不得生成卡
    for cid, words in source['禁则']['职责关键词'].items():
        texts = [l['职责'] for l in source['岗位层']]
        texts += [subs[k]['名称'] for k in subs if subs[k]['父大类'] == cid and subs[k]['生成岗位卡']]
        texts += [c['名称'] for c in canon['公司'] if c['大类'] == cid and c['名称']]
        for text in texts:
            for w in words:
                if w in text:
                    out.append(f'A08禁则: 职责或小类名称出现"{w}"（{text[:24]}）')
    for card in [x for c in canon['公司'] if c['大类'] == 'A08' for x in c['岗位卡']]:
        if card['行业小类'] in source['禁则']['A08背景小类']:
            out.append(f'A08禁则: 背景小类生成岗位卡 {card["id"]}')

    # 8 不可申请边界：公职大类整类 可招聘=false，两区不得留任何在池名额
    for c in canon['公司']:
        if c['大类'] in source['禁则']['不可申请大类'] and c['可招聘'] is not False:
            out.append(f'公职边界: {c["id"]} 可招聘未置 false')
    pool = sum(c['雇员数'] for c in canon['公司']
               if c['可招聘'] and c['锚点'] in source['禁则']['不可申请锚点'])
    if pool:
        out.append(f'公职边界: F001／F002 名额池仍有 {pool} 人在池内')

    # 9 字段黑名单：正典全文不得出现现实金融与前世设定字段
    blob = json.dumps(canon, ensure_ascii=False)
    for w in source['禁则']['字段黑名单']:
        if w in blob:
            out.append(f'字段黑名单: 出现"{w}"')

    # 10 无人机禁区：低空作业小类与含无人机字样的具名公司都不得落在净空受限聚落
    low_alt = set(source['禁则']['低空作业小类'])
    for zid in source['禁则']['无人机禁区']:
        for c in canon['公司']:
            if c['锚点'] != zid:
                continue
            if c['行业小类'] in low_alt:
                out.append(f'无人机禁空: {c["id"]} 低空作业小类 {c["行业小类"]} 落在 {zid}')
            if c['名称'] and any(k in c['名称'] for k in source['禁则']['无人机关键词']):
                out.append(f'无人机禁空: {c["id"]} 具名含无人机字样，落在 {zid}')
    out += adm_issues(canon, adm, params)
    out += cost_issues(canon, costs, registry)
    out += param_issues(params, psource, costs, canon)
    out += naming_issues(canon, source)
    out += zero_consumer_issues(canon, adm, source)
    out += layer_issues(canon, registry, layer)
    out += occupation_issues(canon, source, occ_source)
    out += relief_issues(costs, canon, registry, COST_SOURCE)
    out += dim_issues(params, psource, ADM_SOURCE, canon)
    out += card_issues(canon, adm, card_source, params, source, registry)
    return out


def count_groups(companies):
    """（锚点，档位）组内的具名家数——字号池容量须不小于它的最大值，否则组内会绕回。"""
    g = {}
    for c in companies:
        if c['逐家具名']:
            key = (c['锚点'], c['档位'])
            g[key] = g.get(key, 0) + 1
    return g


def naming_issues(canon, source):
    """第 26 至 29 条：具名命名完整、名称逐段回查、命名池齐套、名称禁则与长度。

    五段池一律取自手填源表的「命名」块，不取正典自带的同一份——与交通矩阵同源口径一致，
    派生器改写了拼接规则或池内容即在门禁炸出。
    """
    out = []
    pool = source.get('命名') or {}
    zi, short = pool.get('字号池', []), pool.get('锚点简称', {})
    root, suffix, apex = pool.get('小类词根', {}), pool.get('档位后缀', {}), pool.get('顶端名称', {})
    band = pool.get('名称长度区间', [0, 0])
    named = [c for c in canon['公司'] if c['逐家具名']]
    by_id = {s['id'] for s in canon['行业']['小类']}

    # 26 具名命名完整：逐家具名与名称非空一一对应、全城逐字唯一、汇总读数与逐行数一致
    for c in canon['公司']:
        if c['逐家具名'] and not c['名称']:
            out.append(f'具名命名: {c["id"]} 逐家具名但名称为空')
        if not c['逐家具名'] and c['名称']:
            out.append(f'具名命名: {c["id"]} T1 统计口径带了名称')
    holder = {}
    for c in named:
        if c['名称'] in holder:
            out.append(f'具名命名: 名称重复「{c["名称"]}」（{holder[c["名称"]]} 与 {c["id"]}）')
        holder.setdefault(c['名称'], c['id'])
    got = sum(1 for c in canon['公司'] if c['名称'])
    if canon['汇总'].get('具名命名数') != got:
        out.append(f'具名命名: 汇总读数 {canon["汇总"].get("具名命名数")} != 非空名称 {got}')
    if canon['汇总'].get('具名公司数') != len(named):
        out.append(f'具名命名: 汇总具名数 {canon["汇总"].get("具名公司数")} != 逐家具名行数 {len(named)}')

    # 27 名称逐段回查：按正典数组顺序给（锚点，档位）组内编号，非顶端名称逐段等于简称＋字号[序]＋词根＋后缀
    seq = {}
    for c in named:
        key = (c['锚点'], c['档位'])
        i = seq.get(key, 0)
        seq[key] = i + 1
        if c['档位'] == 'T5':
            if c['名称'] != apex.get(c['大类']):
                out.append(f'顶端名称: {c["id"]} 名称「{c["名称"]}」不等于源表顶端名称「{apex.get(c["大类"])}」')
            continue
        parts = [short.get(c['锚点']), zi[i] if i < len(zi) else None,
                 root.get(c['行业小类']), suffix.get(c['档位'])]
        want = ''.join(parts) if all(parts) else None
        if c['名称'] != want:
            out.append(f'名称回查: {c["id"]} 名称「{c["名称"]}」不等于 简称＋字号[{i}]＋词根＋后缀＝「{want}」')

    # 28 命名池齐套：字号池不重复且不短于最大组、简称对齐具名锚点且不重复、词根不漏不多、后缀与顶端键对齐
    if len(set(zi)) != len(zi):
        dup = [w for w in set(zi) if zi.count(w) > 1][:3]
        out.append(f'命名池: 字号池有重词 {dup}')
    group_max = max(seq.values()) if seq else 0
    if len(zi) < group_max:
        out.append(f'命名池: 字号池 {len(zi)} 短于最大（锚点，档位）组 {group_max}，组内会绕回')
    anchors_named = {c['锚点'] for c in named}
    if set(short) != anchors_named:
        out.append(f'命名池: 锚点简称与具名锚点不齐 {sorted(set(short) ^ anchors_named)[:6]}')
    if len(set(short.values())) != len(short):
        dup = [w for w in set(short.values()) if list(short.values()).count(w) > 1][:3]
        out.append(f'命名池: 锚点简称有重复，跨锚点无法靠简称区分')
    if set(root) != by_id:
        out.append(f'命名池: 小类词根与 163 小类不齐 {sorted(set(root) ^ by_id)[:6]}')
    tiers_named = {c['档位'] for c in named}
    tiers_flag = {t['档'] for t in source['公司档'] if t['逐家具名']}
    if set(suffix) != tiers_flag:
        out.append(f'命名池: 档位后缀与逐家具名档位不齐 {sorted(set(suffix) ^ tiers_flag)}')
    if set(apex) != {c['大类'] for c in named if c['档位'] == 'T5'}:
        out.append(f"命名池: 顶端名称与 T5 大类不齐 {sorted(set(apex) ^ {c['大类'] for c in named if c['档位'] == 'T5'})}")
    for label, values in (('字号池', zi), ('锚点简称', list(short.values())),
                          ('小类词根', list(root.values())), ('档位后缀', list(suffix.values())),
                          ('顶端名称', list(apex.values()))):
        for v in values:
            if not isinstance(v, str) or not v.strip():
                out.append(f'命名池: {label} 有空词')
            if any(ch in v for ch in (' ', '　', '\u3000')):
                out.append(f'命名池: {label}「{v}」含空白字符')

    # 29 名称禁则与长度：全城名称不命中现实品牌与禁则词、长度落进源表区间、顶端名称以 T5 后缀收尾
    banned = set(source['禁则'].get('名称禁词', [])) | set(source['禁则']['字段黑名单'])
    for words in source['禁则']['职责关键词'].values():
        banned |= set(words)
    banned |= set(source['禁则']['无人机关键词'])
    for c in named:
        if not c['名称']:
            continue  # 空名称由第 26 条报，此处不得对 None 取子串
        for w in sorted(banned):
            if w in c['名称']:
                out.append(f'名称禁则: {c["id"]}「{c["名称"]}」含禁词「{w}」')
        lo, hi = band
        if not lo <= len(c['名称']) <= hi:
            out.append(f'名称禁则: {c["id"]}「{c["名称"]}」长度 {len(c["名称"])} 越出 {lo}—{hi}')
        if c['档位'] == 'T5' and not c['名称'].endswith(suffix.get('T5', '')):
            out.append(f"名称禁则: {c['id']} 顶端名称未以 {suffix.get('T5')} 收尾")
    return out


ZERO_KEYS = ('口径', '背景小类', '背景小类专属标签', '通用技能标签', '通用场景',
             '上限截断大类', '上限截断连带标签', '上限截断连带场景')


def zero_counts(canon, adm):
    """实测三个零消费集合的规模：(无引用标签数, 无引用场景数, 无卡小类数)。"""
    cards = [x for comp in canon['公司'] for x in comp['岗位卡']]
    used_tags = {t for c in cards for t, _ in c['准入标签']}
    used_scenes = {s for c in cards for s in c['关键场景']}
    nocard = {s['id'] for s in canon['行业']['小类']} - {c['行业小类'] for c in cards}
    return (len({t['id'] for t in adm['标签']} - used_tags),
            len({s['id'] for s in adm['场景']} - used_scenes), len(nocard))


def zero_consumer_issues(canon, adm, source):
    """第 30 条：零消费者对账——字典里允许无岗位卡引用的条目必须与手填声明逐字相等。

    声明块只认手填源表 产业就业源表.json 的「零消费者」，正典自带的同一份不作数。
    无卡小类、无引用标签、无引用场景三个集合双向比差：多一个判红（有暗桩没登记），
    少一个也判红（登记口径已经漂了），缺块更判红——门禁不得因无声明可查而空转判绿。
    """
    out = []
    block = source.get('零消费者') or {}
    missing = [k for k in ZERO_KEYS if k not in block]
    if missing:
        return [f'零消费者对账: 产业就业源表.json 的「零消费者」缺 {missing}，须逐类点名，不得留空']
    cards = [x for comp in canon['公司'] for x in comp['岗位卡']]
    subs = {s['id']: s for s in canon['行业']['小类']}
    classes = {c['id']: c for c in canon['行业']['大类']}
    tags = {t['id'] for t in adm['标签']}
    scenes = {s['id'] for s in adm['场景']}

    for label, ids, known in (('标签', block['背景小类专属标签'] + block['通用技能标签']
                               + block['上限截断连带标签'], tags),
                              ('场景', block['通用场景'] + block['上限截断连带场景'], scenes)):
        if len(set(ids)) != len(ids):
            out.append(f'零消费者对账: 声明的{label}清单有重复条目')
        for i in sorted(set(ids) - known):
            out.append(f'零消费者对账: 声明的{label} {i} 在字典中不存在')
    for i in block['背景小类']:
        if i not in subs:
            out.append(f'零消费者对账: 登记的背景小类 {i} 不在行业小类中')
        elif subs[i]['生成岗位卡'] is not False:
            out.append(f'零消费者对账: {i} 登记为背景小类却声明可生成岗位卡')

    nocard = set(subs) - {c['行业小类'] for c in cards}
    for i in sorted(nocard - set(block['背景小类'])):
        out.append(f'零消费者对账: 小类 {i} 声明可生成岗位卡却无一张岗位卡落它')

    used_tags = {t for c in cards for t, _ in c['准入标签']}
    want_tags = set(block['背景小类专属标签']) | set(block['通用技能标签']) | set(block['上限截断连带标签'])
    for i in sorted((tags - used_tags) - want_tags):
        out.append(f'零消费者对账: 标签 {i} 无卡片引用却未登记为零消费者')
    for i in sorted(used_tags & want_tags):
        out.append(f'零消费者对账: 标签 {i} 登记为零消费者却已被卡片引用')

    used_scenes = {s for c in cards for s in c['关键场景']}
    want_scenes = set(block['通用场景']) | set(block['上限截断连带场景'])
    for i in sorted((scenes - used_scenes) - want_scenes):
        out.append(f'零消费者对账: 场景 {i} 无卡片引用却未登记为零消费者')
    for i in sorted(used_scenes & want_scenes):
        out.append(f'零消费者对账: 场景 {i} 登记为零消费者却已被卡片引用')

    caps = {cid for cid, c in classes.items() if c.get('可设岗位层上限')}
    if caps != set(block['上限截断大类']):
        out.append(f'零消费者对账: 声明的截断大类与源表设了可设岗位层上限的大类不对账 '
                   f'{sorted(caps ^ set(block["上限截断大类"]))}')
    levels = [l['层'] for l in canon['岗位层']]
    for cid, cut in block['上限截断大类'].items():
        ceiling = classes.get(cid, {}).get('可设岗位层上限')
        for l in cut:
            if ceiling is None or l not in levels or levels.index(l) <= levels.index(ceiling):
                out.append(f'零消费者对账: {cid} 声明截断层 {l} 不在上限 {ceiling} 之上')
        have = {c['岗位层'] for comp in canon['公司'] if comp['大类'] == cid for c in comp['岗位卡']}
        for l in sorted(set(cut) & have):
            out.append(f'零消费者对账: {cid} 声明截断 {l} 却仍有该层岗位卡')
    return out


def adm_issues(canon, adm, params):
    """第 11 至 16 条：引用完整性、标签体系、关键场景、合同矩阵、卡牌边界、释放流程。"""
    out = []
    tags = {t['id']: t for t in adm['标签']}
    scenes = {s['id']: s for s in adm['场景']}
    contracts = {c['id']: c for c in adm['合同类型']}
    states = {s['id']: s for s in adm['释放状态']}
    forms = {s['id']: s['准入形态'] for s in canon['行业']['小类']}
    classes = {c['id']: c for c in canon['行业']['大类']}
    cards = [(comp, x) for comp in canon['公司'] for x in comp['岗位卡']]

    known = set(tags) | set(scenes) | set(contracts) | set(states) | {f['id'] for f in adm['卡牌族']}
    blob = json.dumps(canon, ensure_ascii=False) + json.dumps(adm, ensure_ascii=False)
    for tok in sorted({m.group(0) for m in re.finditer(r'(?:SKL|SCN|CTR|CRD|RLS)-[A-Za-z0-9-]+', blob)}):
        if tok not in known:
            out.append(f'引用完整性: 未登记的 ID {tok}')

    subs = {s['id'] for s in canon['行业']['小类']}
    own = {t['id'] for t in adm['标签'] if t['族'] == '专属技能'}
    want = {'SKL-' + s + '-' + k for s in subs for k in ('S1', 'S2')}
    if own != want:
        out.append(f'标签体系: 专属标签集合与小类不对账 {sorted(own ^ want)[:5]}')
    levels_ok = set(adm['阶']) | set(adm['非阶要求'].values())
    for t in adm['标签']:
        if not set(t['可推进途径']) <= set(adm['途径']):
            out.append(f'标签体系: {t["id"]} 途径越枚举')
        if t['族'] == '资质' and 'WKS' in t['可推进途径']:
            out.append(f'标签体系: 资质标签 {t["id"]} 可由工作途径推进')
        if t['可由日常活动推进'] != ('LEV' in t['可推进途径']):
            out.append(f'标签体系: {t["id"]} 日常活动标记与途径不自洽')

    for comp, card in cards:
        lvl, zsub = card['岗位层'], card['行业小类']
        for tid, need in card['准入标签']:
            if tid not in tags:
                out.append(f'引用完整性: {card["id"]} 标签 {tid} 不存在')
                continue
            t = tags[tid]
            if t['父小类'] and t['父小类'] != zsub:
                out.append(f'引用完整性: {card["id"]} 标签 {tid} 父小类与卡片小类不一致')
            if not t['父小类'] and t['父大类'] and t['父大类'] != comp['大类']:
                out.append(f'引用完整性: {card["id"]} 标签 {tid} 父大类与公司大类不一致')
            if need not in levels_ok:
                out.append(f'标签体系: {card["id"]} 要求阶 {need} 不在四阶与非阶要求内')
        cls = classes[comp['大类']]
        if lvl in ('LVL3', 'LVL4', 'LVL5'):
            if not card['关键场景']:
                out.append(f'关键场景: {card["id"]} {lvl} 无场景可判定')
            for sid in card['关键场景']:
                s = scenes.get(sid)
                if not s:
                    out.append(f'引用完整性: {card["id"]} 场景 {sid} 不存在')
                elif comp['大类'] not in s['适用大类'] or lvl not in s['触发岗位层']:
                    out.append(f'关键场景: {card["id"]} 场景 {sid} 与大类或岗位层不匹配')
        elif card['关键场景']:
            out.append(f'关键场景: {card["id"]} {lvl} 不该挂场景')
        if lvl == 'LVL4' and cls['层制'] == 4:
            out.append(f'关键场景: {card["id"]} 4 层制大类出现 LVL4')
        if lvl in ('LVL4', 'LVL5') and comp['大类'] == 'A01':
            out.append(f'关键场景: {card["id"]} A01 超出可设岗位层上限')

    for comp, card in cards:
        lvl, tier = card['岗位层'], comp['档位']
        if not comp['逐家具名']:
            if card['合同类型'] != ['CTR-06', 'CTR-07']:
                out.append(f'合同矩阵: {card["id"]} 统计条合同集应恰为 CTR-06 与 CTR-07')
            continue
        if not card['合同类型']:
            out.append(f'合同矩阵: {card["id"]} 合同集为空')
        for cid in card['合同类型']:
            c = contracts.get(cid)
            if not c:
                out.append(f'引用完整性: {card["id"]} 合同 {cid} 不存在')
                continue
            if c['用工形态'] not in card['用工形态']:
                out.append(f'合同矩阵: {cid} 用工形态不属于 {card["id"]}')
            if lvl not in c['可适用岗位层'] or tier not in c['可适用公司档']:
                out.append(f'合同矩阵: {cid} 未覆盖 {card["id"]} 的层或档')
            cap = c['月工时上限_相对174']
            if cap is not None and cap > 1.0:
                out.append(f'合同矩阵: {cid} 月工时上限大于 1.00')
        if lvl in ('LVL4', 'LVL5') and 'CTR-08' in card['合同类型']:
            out.append(f'合同矩阵: {card["id"]} 高职级挂学徒培训')
        form = forms[card['行业小类']]
        if form in ('受雇', '背景在册') and lvl == 'LVL1'                 and not ({'CTR-01', 'CTR-02', 'CTR-08'} & set(card['合同类型'])):
            out.append(f'合同矩阵: {card["id"]} 入门卡缺无固定期限／固定期限／学徒之一')
        if form == '自由接单' and lvl != 'LVL1' and 'CTR-07' not in card['合同类型']:
            out.append(f'合同矩阵: {card["id"]} 接单卡缺自由接单承揽')

    p = adm['参数']
    for f in adm['卡牌族']:
        if f['效果类型'] not in p['卡牌效果类型'] or f['类别'] not in p['卡牌类别']:
            out.append(f'卡牌边界: {f["id"]} 效果类型或类别越枚举')
        if f['禁则'] != p['全局禁则']:
            out.append(f'卡牌边界: {f["id"]} 未逐条复读全局禁则')
        body = json.dumps({k: v for k, v in f.items() if k != '禁则'}, ensure_ascii=False)
        for w in ('资金', '估值', '轮次', '股权', '公职'):
            if w in body:
                out.append(f'卡牌边界: {f["id"]} 出现违禁字样「{w}」')
        if f['效果类型'] == '标签阶推进':
            m = re.search(r'阶提升\s*(\d+)', f['幅度上限'])
            if not m or int(m.group(1)) > 1 or '权威' not in f['幅度上限']:
                out.append(f'卡牌边界: {f["id"]} 阶推进幅度越界或未禁止权威')
        if f['效果类型'] == '五维微调':
            skill = params['参数']['技能']
            fine = skill.get('五维微调比例') or {}
            keys = ('单卡占跨度上限', '同维度累计占跨度上限')
            nums = [int(x) for x in re.findall(r'(\d+)\s*点', f['幅度上限'])]
            absent = [k for k in keys if k not in fine]
            if absent:
                out.append(f'卡牌边界: {f["id"]} 反推五维点数缺比例键 {absent}——该键须登记在运行参数技能块')
            else:
                span = skill['五维刻度'][1] - skill['五维刻度'][0]
                want = [round(span * fine[k]) for k in keys]
                if not nums or nums != want:
                    out.append(f'卡牌边界: {f["id"]} 五维点数 {nums} 不等于刻度跨度 {span} 反推的 {want}——刻度与点数脱钩')
    lim = p['持有上限']
    if not all(isinstance(v, int) and v > 0 for v in lim.values()):
        out.append('卡牌边界: 持有上限须为正整数')
    if lim['跨轮继承'] > lim['总持有']:
        out.append('卡牌边界: 跨轮继承上限大于总持有')

    for comp, card in cards:
        want_state = 'RLS-01' if card['起始城市年'] > canon['setting_year'] else 'RLS-02'
        if card['释放状态'] not in states:
            out.append(f'引用完整性: {card["id"]} 释放状态 {card["释放状态"]} 不存在')
        elif card['释放状态'] != want_state:
            out.append(f'释放流程: {card["id"]} 状态 {card["释放状态"]} 与起始年 {card["起始城市年"]} 不符')
    if len(states) != len(adm['释放状态']):
        out.append('释放流程: 状态 id 不唯一')
    for s in adm['释放状态']:
        if not set(s['去向']) <= set(states):
            out.append(f'释放流程: {s["id"]} 去向含未登记状态')
    if states['RLS-05']['去向'] != p['释放规则']['释放去向白名单']:
        out.append('释放流程: RLS-05 去向偏离白名单')
    if states['RLS-06']['去向']:
        out.append('释放流程: 撤编不得回流')
    return out



LAYER_KEYS = ('来源', '图幅', '口径', '投影', '汇总', '大类', '圈层', '锚点')


def layer_issues(canon, registry, layer):
    """第 31 条：产业图层对账——图层里的每一个计数都必须能从产业正典独立重算出来。

    图层是派生件，闸门不 import build_maps，而是拿 公司 逐锚点重算一遍公司数、岗位卡数、雇员数、
    大类分布、主导大类与气泡半径，再和逐圈层、逐大类、汇总三层加总双向比差。
    锚点坐标另与名录 center_km 逐字相等：图上不许自带一份没人维护的坐标。
    """
    out = []
    missing = [k for k in LAYER_KEYS if k not in layer]
    if missing:
        return [f'产业图层对账: 产业空间图层.json 缺 {missing}，缺件即判红，不得以空图层放行']
    by_id = {e['id']: e for e in registry}
    want = {}
    for c in canon['公司']:
        a = want.setdefault(c['锚点'], {'公司数': 0, '岗位卡数': 0, '雇员数': 0, '分布': {}})
        a['公司数'] += 1
        a['岗位卡数'] += len(c['岗位卡'])
        a['雇员数'] += c['雇员数']
        d = a['分布'].setdefault(c['大类'], {'公司数': 0, '雇员数': 0, '岗位卡数': 0})
        d['公司数'] += 1
        d['雇员数'] += c['雇员数']
        d['岗位卡数'] += len(c['岗位卡'])
    got = {r['锚点']: r for r in layer['锚点']}
    if set(got) != set(want):
        out.append(f"产业图层对账: 锚点集合与正典不一致 {sorted(set(got) ^ set(want))[:6]}")
    max_emp = max(a['雇员数'] for a in want.values())
    for zid in sorted(set(got) & set(want)):
        g, w = got[zid], want[zid]
        for k in ('公司数', '岗位卡数', '雇员数'):
            if g[k] != w[k]:
                out.append(f'产业图层对账: {zid} {k} 图层 {g[k]} != 正典 {w[k]}')
        if g['center_km'] != by_id[zid]['center_km']:
            out.append(f"产业图层对账: {zid} 坐标与名录不符 图层 {g['center_km']} 名录 {by_id[zid]['center_km']}")
        if g['圈层'] != entry_ring(by_id[zid], by_id):
            out.append(f"产业图层对账: {zid} 圈层 {g['圈层']} 与名录推导不符")
        if set(g['大类分布']) != set(w['分布']):
            out.append(f'产业图层对账: {zid} 大类分布键不一致 {sorted(set(g["大类分布"]) ^ set(w["分布"]))}')
        else:
            for cid, wd in sorted(w['分布'].items()):
                gd = g['大类分布'][cid]
                if any(gd[k] != wd[k] for k in ('公司数', '雇员数', '岗位卡数')):
                    out.append(f'产业图层对账: {zid}/{cid} 分布 图层 {gd} != 正典 {wd}')
        wdom = max(w['分布'].items(), key=lambda kv: (kv[1]['雇员数'], kv[1]['公司数'], kv[0]))[0]
        if g['主导大类'] != wdom:
            out.append(f"产业图层对账: {zid} 主导大类 {g['主导大类']} != 实测 {wdom}")
        if g['主导大类名称'] != next(c['名称'] for c in canon['行业']['大类'] if c['id'] == wdom):
            out.append(f"产业图层对账: {zid} 主导大类名称与正典大类名不符")
        if abs(g['气泡半径km'] - round(0.28 + 1.05 * math.sqrt(w['雇员数'] / max_emp), 3)) > 1e-9:
            out.append(f"产业图层对账: {zid} 气泡半径 {g['气泡半径km']} 不符面积公式")
    for row in layer['大类']:
        cid = row['id']
        hits = [z for z, a in want.items() if cid in a['分布']]
        agg = {k: sum(want[z]['分布'][cid][k] for z in hits) for k in ('公司数', '雇员数', '岗位卡数')}
        for k, v in agg.items():
            if row[k] != v:
                out.append(f'产业图层对账: 大类 {cid} {k} 图层 {row[k]} != 逐锚点加总 {v}')
        if row['落点数'] != len(hits):
            out.append(f"产业图层对账: 大类 {cid} 落点数 {row['落点数']} != {len(hits)}")
        if sorted(row['落点']) != sorted(hits):
            out.append(f'产业图层对账: 大类 {cid} 落点清单与逐锚点分布不符')
    if {r['id'] for r in layer['大类']} != {c['id'] for c in canon['行业']['大类']}:
        out.append('产业图层对账: 图层大类集合与正典不齐')
    for row in layer['圈层']:
        hits = [z for z, a in want.items() if entry_ring(by_id[z], by_id) == row['圈层']]
        if [row['锚点数'], row['公司数'], row['雇员数']] != [
                len(hits), sum(want[z]['公司数'] for z in hits), sum(want[z]['雇员数'] for z in hits)]:
            out.append(f"产业图层对账: 圈层 {row['圈层']} 小计与逐锚点加总不符")
    if {r['圈层'] for r in layer['圈层']} != set(RINGS):
        out.append(f"产业图层对账: 圈层行不齐 {sorted(r['圈层'] for r in layer['圈层'])}")
    s = canon['汇总']
    for k in ('岗位锚点数', '公司数', '岗位卡数', '雇员总数'):
        if layer['汇总'][k] != s[k]:
            out.append(f"产业图层对账: 汇总 {k} 图层 {layer['汇总'][k]} != 正典汇总 {s[k]}")
    if layer['汇总']['最大单锚雇员数'] != max_emp:
        out.append(f"产业图层对账: 汇总 最大单锚雇员数 {layer['汇总']['最大单锚雇员数']} != 实测 {max_emp}")
    return out


OCC_SOURCE_KEYS = ('口径', '规格', '小类')


def occupation_issues(canon, source, occ_source):
    """第 32 条：职业条目对账——手填正文逐条重扫，派生字段逐条重算，两边都不得漂。

    长度带与条数带取自手填的 职业条目源表.json「规格」块，禁则词与低空白名单仍取自 产业就业源表.json「禁则」块，
    两处各管各的口径，谁也不复制谁。派生的 id、适用层、关联岗位卡数与覆盖名额一律按正典岗位卡独立重算，
    生成器若改了挂接规则就在这里炸出来。
    """
    out = []
    missing = [k for k in OCC_SOURCE_KEYS if k not in occ_source]
    if missing:
        return [f'职业条目对账: 职业条目源表.json 缺 {missing}，缺件即判红，不得以空条目放行']
    if '职业条目' not in canon:
        return ['职业条目对账: 正典没有 职业条目 一节，派生件缺件不得空转判绿']
    spec = occ_source['规格']
    for k in ('每类条数', '总条数区间', '字段', '名称长度', '职责长度', '日常循环条数', '日常循环长度',
              '交付物长度', '协作对象条数', '协作对象长度', '常见异常长度', '禁用字符'):
        if k not in spec:
            out.append(f'职业条目对账: 规格缺 {k}')
    if out:
        return out
    J = source['禁则']
    banned = set(J['字段黑名单']) | set(J['名称禁词']) | set(J['无人机关键词'])
    for words in J['职责关键词'].values():
        banned |= set(words)
    a08_words = set(J['职责关键词']['A08'])
    drone_ok = set(J['低空作业小类'])
    band = {'名称': tuple(spec['名称长度']), '职责': tuple(spec['职责长度']),
            '交付物': tuple(spec['交付物长度']), '常见异常': tuple(spec['常见异常长度'])}
    loop_band, partner_band = tuple(spec['日常循环长度']), tuple(spec['协作对象长度'])
    fields, loop_n = spec['字段'], spec['日常循环条数']
    sub_lo, sub_hi = spec['每类条数']
    total_lo, total_hi = spec['总条数区间']
    quote_chars = set(spec['禁用字符'])

    subs = {s['id']: s for s in canon['行业']['小类']}
    classes = {c['id']: c for c in canon['行业']['大类']}
    writable = {i for i, s in subs.items() if s['生成岗位卡']}
    by_sub = {}
    for comp in canon['公司']:
        for card in comp['岗位卡']:
            b = by_sub.setdefault(card['行业小类'], {'卡数': 0, '名额': 0, '层': set()})
            b['卡数'] += 1
            b['名额'] += card['名额']
            b['层'].add(card['岗位层'])

    rows = occ_source['小类']
    covered = [r['小类'] for r in rows]
    if len(covered) != len(set(covered)):
        out.append(f"职业条目对账: 源表小类行重复 {sorted({c for c in covered if covered.count(c) > 1})}")
    for sid in sorted(set(covered) - writable):
        out.append(f'职业条目对账: {sid} 不在可出卡小类内却出了条目（背景在册小类不得有职业条目）')
    for sid in sorted(writable - set(covered)):
        out.append(f'职业条目对账: {sid} 可出卡却没有任何职业条目')
    if len(rows) != len(writable):
        out.append(f'职业条目对账: 源表 {len(rows)} 个小类 != 可出卡小类 {len(writable)} 个')

    counts = {}
    for r in rows:
        counts[r['小类']] = len(r['职业'])
        if not sub_lo <= len(r['职业']) <= sub_hi:
            out.append(f"职业条目对账: {r['小类']} 有 {len(r['职业'])} 条，越出每类 {sub_lo}—{sub_hi}")

    entries = canon['职业条目']
    if len(entries) != sum(counts.values()):
        out.append(f'职业条目对账: 正典 {len(entries)} 条 != 源表展开 {sum(counts.values())} 条')
    if not total_lo <= len(entries) <= total_hi:
        out.append(f'职业条目对账: 总数 {len(entries)} 越出总量带 {total_lo}—{total_hi}')
    if canon['汇总'].get('职业条目数') != len(entries):
        out.append(f"职业条目对账: 汇总 职业条目数 {canon['汇总'].get('职业条目数')} != 实际 {len(entries)}")
    if canon['汇总'].get('职业条目覆盖小类数') != len({e['小类'] for e in entries}):
        out.append('职业条目对账: 汇总 职业条目覆盖小类数 与实际小类集合不符')

    names, ids = {}, {}
    want = {}
    for r in sorted(rows, key=lambda x: x['小类']):
        sid = r['小类']
        if sid not in subs:
            continue
        agg = by_sub.get(sid, {'卡数': 0, '名额': 0, '层': set()})
        for i, o in enumerate(r['职业'], start=1):
            sub, cls = subs[sid], classes[subs[sid]['父大类']]
            want[f'OCC-{sid}-{i:02d}'] = dict(
                {'id': f'OCC-{sid}-{i:02d}', '小类': sid, '小类名称': sub['名称'], '大类': cls['id'],
                 '大类名称': cls['名称'], '起始城市年': sub['起始城市年'],
                 '公共部门': cls.get('公共部门', False), '可招聘': cls['可招聘'],
                 '适用层': sorted(agg['层']), '关联岗位卡数': agg['卡数'], '覆盖名额': agg['名额']},
                **{f: o[f] for f in fields if f in o})

    for e in entries:
        eid = e.get('id')
        if eid in ids:
            out.append(f'职业条目对账: 条目 id 重复 {eid}')
            continue
        ids[eid] = True
        if e['名称'] in names:
            out.append(f"职业条目对账: 名称重复 {e['名称']}（{names[e['名称']]} 与 {eid}）")
        else:
            names[e['名称']] = eid
        if eid not in want:
            out.append(f'职业条目对账: {eid} 与源表展开不符（小类或组内序对不上）')
            continue
        w = want[eid]
        for k in list(fields) + ['小类', '小类名称', '大类', '大类名称', '起始城市年', '公共部门',
                                  '可招聘', '适用层', '关联岗位卡数', '覆盖名额']:
            if k not in w:
                out.append(f'职业条目对账: 源表条目 {eid} 缺字段 {k}')
            elif e.get(k) != w[k]:
                out.append(f'职业条目对账: {eid} 字段 {k} 与重算值不符（{e.get(k)!r} != {w[k]!r}）')
        absent = [f for f in fields if f not in e]
        if absent:
            out.append(f'职业条目对账: {eid} 缺字段 {absent}')
            continue
        for f, (lo, hi) in band.items():
            if not lo <= len(e[f]) <= hi:
                out.append(f"职业条目对账: {eid}「{e['名称']}」{f}长度 {len(e[f])} 不在 {lo}—{hi}")
        loop = e['日常循环']
        if len(loop) != loop_n or len(set(loop)) != loop_n:
            out.append(f"职业条目对账: {eid} 日常循环须 {loop_n} 条且不重复")
        if any(not loop_band[0] <= len(x) <= loop_band[1] for x in loop):
            out.append(f"职业条目对账: {eid} 日常循环单条长度越出 {loop_band[0]}—{loop_band[1]}")
        partner = e['协作对象']
        p_lo, p_hi = spec['协作对象条数']
        if not p_lo <= len(partner) <= p_hi:
            out.append(f"职业条目对账: {eid} 协作对象 {len(partner)} 条越出 {p_lo}—{p_hi}")
        if any(not partner_band[0] <= len(x) <= partner_band[1] for x in partner):
            out.append(f"职业条目对账: {eid} 协作对象单条长度越出 {partner_band[0]}—{partner_band[1]}")
        blob = e['名称'] + e['职责'] + ''.join(loop) + e['交付物'] + ''.join(partner) + e['常见异常']
        sid = e['小类']
        # 低空作业白名单小类可以出现四个无人机词，其余小类一律不得出现——豁免的是词，不是小类 ID。
        allow = set(J['无人机关键词']) if sid in drone_ok else set()
        for w in sorted(banned - allow):
            if w in blob:
                out.append(f"职业条目对账: {eid}「{e['名称']}」出现禁词「{w}」")
        if sid.startswith('A08'):
            for w in sorted(a08_words):
                if w in blob:
                    out.append(f"职业条目对账: A08 口径 {eid}「{e['名称']}」出现职责禁词「{w}」")
        for ch in sorted(quote_chars):
            if ch in blob:
                out.append(f'职业条目对账: {eid} 含禁用字符 {ch}')
    for eid in sorted(set(want) - set(ids)):
        out.append(f'职业条目对账: 源表条目 {eid} 未进正典')
    return out


RELIEF_GROUPS = (('岗位', '公职'), ('减免',), ('叙述',))


HALT_WORDS = ('仍未', '待登记', '待确认', '待定', '暂不', '后续细化')


def relief_issues(costs, canon, registry, csource):
    """第 33 条：失业救助对账。金额由源表比例×派生篮子现算，月数关系、两条红线与三段文本全部跨源核对。"""
    if '失业救助' not in csource:
        raise SystemExit('缺少 数据/物价生活源表.json 的 参数.失业救助：救助三列金额与三段文本只住在这份手填真源里，'
                         '缺块时门禁不得空转判绿')
    r = csource['失业救助']
    out = []
    rings = csource['圈层顺序']
    if '失业救助' not in costs['参数']:
        out.append('失业救助对账: 正典参数未带失业救助块——源表已改但产物未重跑，先跑 python 工具/build_costs.py')
        return out
    cr = costs['参数']['失业救助']
    if cr != r:
        out.append('失业救助对账: 正典参数块与源表不一致——参数块须整块由源表带入，不得在生成器里另填')

    # 月数与比例的六条结构关系：全额月数被钉在欠费宽限上，是本条唯一一条「改一边不改另一边就红」的硬耦合
    if not (0 < r['递减比例'] < r['全额比例'] < 1):
        out.append(f"失业救助对账: 比例档序须 0<递减{r['递减比例']}<全额{r['全额比例']}<1")
    if r['全额月数'] + r['递减月数'] != r['最长连发月数']:
        out.append(f"失业救助对账: 全额{r['全额月数']}月＋递减{r['递减月数']}月 != 最长连发{r['最长连发月数']}月")
    if r['全额月数'] != csource['欠费宽限月数']:
        out.append(f"失业救助对账: 全额月数 {r['全额月数']} != 欠费宽限月数 {csource['欠费宽限月数']}"
                   "——宽限期与全额期必须同期，否则失住者仍在领全额")
    if r['最长连发月数'] % r['复核月数']:
        out.append(f"失业救助对账: 最长连发 {r['最长连发月数']} 月不能被复核 {r['复核月数']} 月整除")
    if r['再申请间隔月数'] != r['最长连发月数']:
        out.append(f"失业救助对账: 再申请间隔 {r['再申请间隔月数']} 月 != 最长连发 {r['最长连发月数']} 月")

    # 逐圈层三列复算 + 两条红线：递减月须低于住所锚中位，全额月须低于本圈层最低 LVL1 生效线
    by_id = {e['id']: e for e in registry}
    floor_line = {}
    for comp in canon['公司']:
        if comp['锚点'] not in by_id:
            continue
        ring = entry_ring(by_id[comp['锚点']], by_id)
        for card in comp['岗位卡']:
            if card['岗位层'] != 'LVL1':
                continue
            line = card['红线_钛币']['住所加篮子线']
            if ring not in floor_line or line < floor_line[ring]:
                floor_line[ring] = line
    for ring in rings:
        w = costs['保障'].get(ring)
        if not w:
            out.append(f'失业救助对账: {ring} 缺保障行')
            continue
        basket = costs['篮子'][ring]
        full = round(basket * r['全额比例'], 1)
        decline = round(basket * r['递减比例'], 1)
        total = round(full * r['全额月数'] + decline * r['递减月数'], 1)
        for key, want in (('失业救助_全额月_钛币', full), ('失业救助_递减月_钛币', decline),
                          ('失业救助_连发总额_钛币', total)):
            if w.get(key) != want:
                out.append(f'失业救助对账: {ring} {key} {w.get(key)} != 复算 {want}（篮子 {basket}×比例，不得乘户均规模）')
        med = costs['住所锚中位_按圈层'][ring]
        if decline >= med:
            out.append(f'失业救助对账: {ring} 递减月 {decline} ≥ 住所锚中位 {med}——救助须付不起市场租金，才逼出 5% 兜底配额')
        if ring not in floor_line:
            out.append(f'失业救助对账: {ring} 没有 LVL1 卡可取生效线，红线无从比对')
        elif full >= floor_line[ring]:
            out.append(f'失业救助对账: {ring} 全额月 {full} ≥ 本圈层最低 LVL1 生效线 {floor_line[ring]}——不工作比最低档上班挣得多')

    # 三段文本：条数、非空、不重复、覆盖三组禁则关键词，且不得出现中断类许可词
    for key, sum_key in (('发放条件', '救助发放条件数'), ('停发情形', '救助停发情形数'), ('禁则', '救助禁则数')):
        items = r[key]
        if costs['汇总'].get(sum_key) != len(items):
            out.append(f"失业救助对账: 汇总 {sum_key} {costs['汇总'].get(sum_key)} != 源表 {len(items)} 条")
        if len(set(items)) != len(items):
            out.append(f'失业救助对账: {key} 出现重复条目')
        for s in items:
            if len(s) < 12:
                out.append(f'失业救助对账: {key}「{s}」短于 12 字，读不出可执行口径')
            for word in HALT_WORDS:
                if word in s:
                    out.append(f'失业救助对账: {key}「{s}」出现中断类许可词「{word}」——救助口径不得写成待办')
    blob = '｜'.join(r['禁则'])
    for group in RELIEF_GROUPS:
        if not all(g in blob for g in group):
            out.append(f'失业救助对账: 禁则三段未覆盖关键词组 {group}——岗位、价物减免、叙述追加三条禁令须逐条在场')
    if '不乘户均规模' not in r['口径'] + ''.join(r['发放条件']):
        out.append('失业救助对账: 口径与发放条件均无「不乘户均规模」否定式——救助按本人发放这条须写死在文本里')
    for word in HALT_WORDS:
        if word in r['口径']:
            out.append(f'失业救助对账: 口径出现中断类许可词「{word}」')
    return out


DIM_GROUPS = (('不重抽五维',), ('卡牌族',), ('企业', '资产'))


def dim_issues(params, psource, adm_src, canon):
    """第 34 条：五维开局对账。区间与上限由运行参数源表反推，再与长期习惯卡的幅度上限绑成三条等式。"""
    s = psource['技能']
    if '五维开局' not in s or '背景卡权重' not in s:
        raise SystemExit('缺少 数据/运行参数源表.json 的 参数.技能.五维开局 或 背景卡权重：'
                         '开局区间、影响上限与候选组合数只能由这两块反推，缺块时门禁不得空转判绿')
    o, bg = s['五维开局'], s['背景卡权重']
    out = []
    cs = params['参数']['技能']
    if cs.get('五维开局') != o or cs.get('背景卡权重') != bg:
        out.append('五维开局对账: 正典参数块与运行参数源表不一致——两块须整块由源表带入，重跑 python 工具/build_params.py')
    op = params.get('五维开局')
    if not op:
        out.append('五维开局对账: 正典缺派生块 五维开局——产物未重跑，区间与上限无处比对')
        return out
    lo, hi = s['五维刻度']
    span = hi - lo
    per_card = num(span * bg['单类影响占跨度'])
    per_dim = num(span * bg['同维度累计影响占跨度'])

    # 等式一／二：CRD-A3 的中文幅度上限、微调比例反推的点数、背景卡两档占比必须读成同一对数字
    a3 = next((c for c in adm_src['卡牌族'] if c['id'] == 'CRD-A3'), None)
    if not a3:
        out.append('五维开局对账: 岗位准入源表没有 CRD-A3 长期习惯卡，幅度上限无从跨源对账')
    else:
        pts = [int(x) for x in re.findall(r'(\d+)\s*点', a3['幅度上限'])]
        if pts != [per_card, per_dim]:
            out.append(f"五维开局对账: CRD-A3 幅度上限「{a3['幅度上限']}」读作 {pts}，"
                       f"与反推的单卡 {per_card}／同维度累计 {per_dim} 不符")
        if [x.strip() for x in a3['效果对象'].split('、')] != o['维度']:
            out.append(f"五维开局对账: CRD-A3 效果对象与源表 维度 五档不齐（{a3['效果对象']}）")
    if bg['单类影响占跨度'] != s['五维微调比例']['单卡占跨度上限']:
        out.append('五维开局对账: 背景卡单类影响占跨度与 五维微调比例.单卡占跨度上限 脱钩')
    if bg['同维度累计影响占跨度'] != s['五维微调比例']['同维度累计占跨度上限']:
        out.append('五维开局对账: 背景卡同维度累计影响占跨度与 五维微调比例.同维度累计占跨度上限 脱钩')

    # 派生块逐值复算：中位、区间、上限、组合数、权重和
    if num(span * o['中位占跨度']) + lo != o['中位']:
        out.append(f"五维开局对账: 中位 {o['中位']} != 刻度下界 {lo}＋跨度×中位占跨度 {o['中位占跨度']}")
    band = [num(o['中位'] - per_dim), num(o['中位'] + per_dim)]
    if op['开局区间'] != band:
        out.append(f"五维开局对账: 正典开局区间 {op['开局区间']} != 复算 {band}（中位±跨度×同维度累计影响占跨度）")
    if op['单类影响上限'] != per_card or op['同维度累计影响上限'] != per_dim:
        out.append(f"五维开局对账: 正典影响上限 {op['单类影响上限']}／{op['同维度累计影响上限']} "
                   f"!= 复算 {per_card}／{per_dim}")
    combo = 1
    for c in bg['类别']:
        combo *= c['候选数']
    if op['候选组合数'] != combo:
        out.append(f"五维开局对账: 候选组合数 {op['候选组合数']} != 五类候选数连乘 {combo}")
    if sum(c['权重'] for c in bg['类别']) != 100:
        out.append(f"五维开局对账: 权重和 {sum(c['权重'] for c in bg['类别'])} != 100")
    if op['权重和'] != sum(c['权重'] for c in bg['类别']):
        out.append('五维开局对账: 正典 权重和 与源表逐类相加不符')
    ids = [c['id'] for c in bg['类别']]
    if len(set(ids)) != len(ids) or not all(i.startswith('BG-') for i in ids):
        out.append(f'五维开局对账: 类别 id 须唯一且全部 BG- 前缀，实得 {ids}')
    if len(bg['类别']) != op['类别数'] or len(o['维度']) != op['维度数']:
        out.append('五维开局对账: 正典的 类别数／维度数 与源表条数不符')

    # 满值罕见线与刻度边界：开局最好一档加一张满额长期习惯也碰不到满值
    if not lo <= band[0] < band[1] <= hi:
        out.append(f'五维开局对账: 开局区间 {band} 越出刻度 [{lo}, {hi}]')
    if o['满值罕见线'] <= band[1]:
        out.append(f"五维开局对账: 满值罕见线 {o['满值罕见线']} ≤ 开局上界 {band[1]}——开局就给到罕见线，「单项很难达到满值」失效")
    if band[1] + per_card > hi:
        out.append(f'五维开局对账: 开局上界 {band[1]}＋单类影响上限 {per_card} 越过刻度上界 {hi}')

    # 背景卡不得挤进卡牌字典：既不进卡牌族 id，也不进持有上限的键
    if any(i.startswith('BG-') for i in (c['id'] for c in adm_src['卡牌族'])):
        out.append('五维开局对账: BG- 前缀出现在卡牌族 id 里——背景卡不是第 13 个卡牌族')
    if any(i.startswith('BG-') for i in adm_src['持有上限']):
        out.append('五维开局对账: BG- 前缀出现在持有上限的键里——背景卡不占卡牌字典名额')
    banned = {k for card in (x for comp in canon['公司'] for x in comp['岗位卡']) for k in card
              if '开局' in k or '背景卡' in k}
    if banned:
        out.append(f'五维开局对账: 岗位卡里出现开局侧字段 {sorted(banned)}——分布与权重只住参数源表，不写进 10541 张卡')

    # 三段文本与禁则关键词组，外加中断类许可词扫描
    if len(bg['禁则']) != op['禁则数']:
        out.append(f"五维开局对账: 正典 禁则数 {op['禁则数']} != 源表 {len(bg['禁则'])} 条")
    blob = '｜'.join(bg['禁则'])
    for group in DIM_GROUPS:
        if not all(g in blob for g in group):
            out.append(f'五维开局对账: 背景卡禁则未覆盖关键词组 {group}——更换不重抽、不进卡牌族、不送资产三条须逐条在场')
    for text in (o['口径'], bg['口径'], *bg['禁则']):
        for word in HALT_WORDS:
            if word in text:
                out.append(f'五维开局对账: 开局文本「{text[:24]}…」出现中断类许可词「{word}」')
    if not isinstance(bg['更换次数'], int) or bg['更换次数'] < 0:
        out.append(f"五维开局对账: 更换次数 {bg['更换次数']} 须为非负整数")
    return out


CARD_SRC_KEYS = ('口径', '规格', '卡牌族实例', '背景卡实例', '禁则')
CARD_SPEC_KEYS = ('每族条数', '总条数区间', '字段', '名称长度', '卡面正文长度', '幅度长度',
                  '互斥口径条数', '绑定域表', '禁用字符', '背景卡条数')
CARD_DOMAINS = ('专属技能标签', '资质标签', '经历标签', '通用技能标签', '场景', '释放状态',
                '大类', '片区', '五维')
CARD_BG_FORBIDDEN = ('权重', '候选数', '组合数')
CARD_ID_RE = re.compile(r'^CRD-[AB]\d-\d{3}$')
CAP_NUMBER_RE = re.compile(r'(\d+)')


def card_issues(canon, adm, card_src, params, source, registry):
    """第 35 条：卡牌实例对账——第9期 9a 落的是容器，所以三条线同时判且都允许「未展开」。

    一条判派生件与手填真源是否同源（族块齐套、逐族条数、总数与背景卡计数，正典由生成器算，
    手改一格就在这里炸出来）；一条判每条实例的结构合法性（六个字段、长度带、禁用字符、整句复述族级禁则、
    绑定对象按 绑定域 命中真实 id、幅度不越本族上限且不触及「权威」、生效触发等于本族 绑定途径、
    互斥口径同族成对且不成三元环）；一条判两条反向锁——岗位卡里 CRD- 出现次数恒为 0，
    背景卡条目里不得出现 权重／候选数／组合数（那两个数只在 运行参数源表 存一份）。
    条数带下限为 0，即整族未展开合法；一旦展开就必须落进带上，总条数带同理只在总数非零时生效。
    """
    out = []
    missing = [k for k in CARD_SRC_KEYS if k not in card_src]
    if missing:
        return [f'卡牌实例对账: 卡牌实例源表.json 缺 {list(missing)}，缺件即判红，不得以无实例可查而空转判绿']
    block = adm.get('卡牌实例')
    if not block:
        return ['卡牌实例对账: 岗位准入正典没有 卡牌实例 一节，派生件缺件不得空转判绿']
    spec = card_src['规格']
    miss_spec = [k for k in CARD_SPEC_KEYS if k not in spec]
    if miss_spec:
        return [f'卡牌实例对账: 规格块缺 {list(miss_spec)}，条数带与长度带只住在本表，缺键即无从对账']
    rows = block['实例']
    bg_rows = block['背景卡']
    fams = {f['id']: f for f in adm['卡牌族']}
    tags_by_id = {t['id']: t for t in adm['标签']}
    scenes_by_id = {s['id'] for s in adm['场景']}
    rel_by_id = {r['id'] for r in adm['释放状态']}
    major_by_id = {d['id'] for d in source['大类']}
    district_ids = {e['id'] for e in registry if e['type'] == '城市片区'}
    opening = params['参数']['技能'].get('五维开局') or {}
    bg_weight = params['参数']['技能'].get('背景卡权重') or {}
    dims = set(opening.get('维度') or [])
    candidates = sum(c['候选数'] for c in bg_weight.get('类别') or [])

    blocks = [b['族'] for b in card_src['卡牌族实例']]
    if len(blocks) != len(set(blocks)):
        out.append(f"卡牌实例对账: 源表族块重复 {sorted({b for b in blocks if blocks.count(b) > 1})}")
    if set(blocks) != set(fams):
        out.append(f'卡牌实例对账: 族块与 12 族不等，多 {sorted(set(blocks) - set(fams))} 少 {sorted(set(fams) - set(blocks))}')
    if set(spec['绑定域表']) != set(fams):
        out.append('卡牌实例对账: 规格.绑定域表 的族集合与 12 族不等，绑定域表缺族等于放行自造族')
    for fid, dom in spec['绑定域表'].items():
        if dom not in CARD_DOMAINS:
            out.append(f'卡牌实例对账: {fid} 绑定域「{dom}」不在九个域之内')
    if set(spec['每族条数']) != set(fams):
        out.append('卡牌实例对账: 规格.每族条数 的族集合与 12 族不等')

    src_rows = {b['族']: len(b['条目']) for b in card_src['卡牌族实例']}
    per_family = {}
    for fid in fams:
        got = sum(1 for r in rows if r['族'] == fid)
        per_family[fid] = got
        if src_rows.get(fid, 0) != got:
            out.append(f'卡牌实例对账: {fid} 正典 {got} 条 != 源表展开 {src_rows.get(fid, 0)} 条')
        band = spec['每族条数'].get(fid)
        if band and not (band[0] <= got <= band[1]):
            out.append(f'卡牌实例对账: {fid} 条数 {got} 越出声明带 {band[0]}—{band[1]}')
    if adm['汇总'].get('卡牌实例数') != len(rows):
        out.append(f"卡牌实例对账: 汇总 卡牌实例数 {adm['汇总'].get('卡牌实例数')} != 实际 {len(rows)}")
    if adm['汇总'].get('逐族条数') != per_family:
        out.append('卡牌实例对账: 汇总 逐族条数 与重算不符')
    if adm['汇总'].get('已展开族数') != sum(1 for v in per_family.values() if v):
        out.append('卡牌实例对账: 汇总 已展开族数 与重算不符')
    if adm['汇总'].get('未展开族数') != sum(1 for v in per_family.values() if not v):
        out.append('卡牌实例对账: 汇总 未展开族数 与重算不符')
    lo, hi = spec['总条数区间']
    if rows and not (lo <= len(rows) <= hi):
        out.append(f'卡牌实例对账: 实例总数 {len(rows)} 越出总条数带 {lo}—{hi}')

    if adm['汇总'].get('背景卡实例数') != len(bg_rows):
        out.append(f"卡牌实例对账: 汇总 背景卡实例数 {adm['汇总'].get('背景卡实例数')} != 实际 {len(bg_rows)}")
    if len(card_src['背景卡实例']['条目']) != len(bg_rows):
        out.append(f"卡牌实例对账: 背景卡正典 {len(bg_rows)} 条 != 源表展开 {len(card_src['背景卡实例']['条目'])} 条")
    if bg_rows and len(bg_rows) != spec['背景卡条数']:
        out.append(f"卡牌实例对账: 背景卡 {len(bg_rows)} 条与规格声明 {spec['背景卡条数']} 不符")
    if bg_rows and len(bg_rows) != candidates:
        out.append(f'卡牌实例对账: 背景卡 {len(bg_rows)} 条 != 运行参数五类候选数之和 {candidates}')
    if bg_weight and spec['背景卡条数'] != candidates:
        out.append(f"卡牌实例对账: 规格.背景卡条数 {spec['背景卡条数']} != 运行参数五类候选数之和 {candidates}")
    for r in bg_rows:
        hit = [k for k in CARD_BG_FORBIDDEN if k in r]
        if hit:
            out.append(f"卡牌实例对账: 背景卡 {r.get('id')} 出现 {hit}，权重与候选数只在 运行参数源表 存一份，本表不得覆写")

    seen_names = {}
    ids = set()
    for r in rows + bg_rows:
        rid = r.get('id')
        if rid in ids:
            out.append(f'卡牌实例对账: 实例 id 重复 {rid}')
        ids.add(rid)
        if not CARD_ID_RE.match(rid or ''):
            if not str(rid or '').startswith('BG-'):
                out.append(f'卡牌实例对账: 实例 id「{rid}」不合 CRD-A1-001 式')
        name = r.get('名称')
        if name in seen_names:
            out.append(f"卡牌实例对账: 名称重复「{name}」（{seen_names[name]} 与 {rid}）")
        seen_names[name] = rid
    for r in rows:
        rid, fid = r['id'], r['族']
        absent = [k for k in spec['字段'] if k not in r]
        if absent:
            out.append(f'卡牌实例对账: {rid} 缺字段 {absent}')
            continue
        for f, band in (('名称', spec['名称长度']), ('卡面正文', spec['卡面正文长度']),
                        ('幅度', spec['幅度长度'])):
            if not (band[0] <= len(str(r[f])) <= band[1]):
                out.append(f"卡牌实例对账: {rid}「{r['名称']}」{f}长度 {len(str(r[f]))} 不在 {band[0]}—{band[1]}")
        for ch in spec['禁用字符']:
            if any(ch in str(r[f]) for f in spec['字段'] if isinstance(r[f], str)):
                out.append(f'卡牌实例对账: {rid} 含禁用字符 {ch}')
        fam = fams.get(fid)
        if not fam:
            out.append(f'卡牌实例对账: {rid} 的族 {fid} 不在 12 族内')
            continue
        dom = spec['绑定域表'][fid]
        obj = r['绑定对象']
        if dom in ('专属技能标签', '资质标签', '经历标签', '通用技能标签'):
            t = tags_by_id.get(obj)
            want = {'专属技能标签': '专属技能', '资质标签': '资质',
                    '经历标签': '经历', '通用技能标签': '通用技能'}[dom]
            if not t:
                out.append(f'卡牌实例对账: {rid} 绑定对象 {obj} 不在标签字典内')
            elif t['族'] != want:
                out.append(f"卡牌实例对账: {rid} 绑定域要求{dom}，{obj} 实为「{t['族']}」")
            else:
                sub = spec['绑定子类表'].get(fid)
                if sub and t['子类'] != sub:
                    out.append(f"卡牌实例对账: {rid} 绑定子类要求 {sub}，{obj} 实为 {t['子类']}")
        elif dom == '场景':
            if obj not in scenes_by_id:
                out.append(f'卡牌实例对账: {rid} 绑定场景 {obj} 不在场景字典内')
        elif dom == '释放状态':
            if obj not in rel_by_id:
                out.append(f'卡牌实例对账: {rid} 绑定释放状态 {obj} 不在状态机内')
        elif dom == '大类':
            if obj not in major_by_id:
                out.append(f'卡牌实例对账: {rid} 绑定大类 {obj} 不在产业大类内')
        elif dom == '片区':
            if obj not in district_ids:
                out.append(f'卡牌实例对账: {rid} 绑定片区 {obj} 不在名录 20 片区内')
        elif dom == '五维':
            if obj not in dims:
                out.append(f"卡牌实例对账: {rid} 绑定维度「{obj}」不在五维之内")
        cap = fam['幅度上限']
        cap_num = CAP_NUMBER_RE.search(cap or '')
        own_num = CAP_NUMBER_RE.search(str(r['幅度']) or '')
        if cap_num:
            if not own_num:
                out.append(f"卡牌实例对账: {rid} 幅度「{r['幅度']}」没带本族上限 {cap} 要求的数值")
            elif int(own_num.group(1)) > int(cap_num.group(1)):
                out.append(f'卡牌实例对账: {rid} 幅度「{r["幅度"]}」越出本族上限「{cap}」')
        elif str(r['幅度']) != cap:
            out.append(f"卡牌实例对账: {rid} 本族上限「{cap}」无数值，幅度须逐字等于上限而非自报数值")
        if '不得触及权威' in (cap or '') and '权威' in str(r['幅度']):
            out.append(f"卡牌实例对账: {rid} 幅度「{r['幅度']}」把标签推到「权威」阶，越出本族不得触及权威的边界")
        want_path = fam['绑定途径']
        if want_path is None:
            if r['生效触发'] not in (None, '', '无'):
                out.append(f"卡牌实例对账: {rid} 本族无绑定途径，生效触发却写了「{r['生效触发']}」")
        elif r['生效触发'] != want_path:
            out.append(f"卡牌实例对账: {rid} 生效触发「{r['生效触发']}」不等于本族绑定途径 {want_path}")
        for ban in fam['禁则']:
            if ban in str(r['卡面正文']):
                out.append(f"卡牌实例对账: {rid} 卡面整句复述了族级禁则「{ban[:16]}…」")

    by_family_ids = {}
    for r in rows:
        by_family_ids.setdefault(r['族'], set()).add(r['id'])
    edges = {}
    for r in rows:
        for other in (r['互斥口径'] or []):
            if other not in by_family_ids.get(r['族'], set()):
                out.append(f"卡牌实例对账: {r['id']} 互斥口径 {other} 不在本族实例内")
                continue
            edges.setdefault(frozenset((r['id'], other)), 0)
            edges[frozenset((r['id'], other))] += 1
    for pair, n in edges.items():
        a, b = tuple(pair)
        if n != 2:
            out.append(f'卡牌实例对账: 互斥口径 {a} 与 {b} 不成对（只 {n} 处声明），持有侧无从核算')
    limit = adm['参数']['持有上限']['同族']
    adj = {}
    for pair in edges:
        a, b = tuple(pair)
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    for start in adj:
        seen = {start}
        stack = [start]
        while stack:
            cur = stack.pop()
            for nxt in adj.get(cur, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        if len(seen) > limit:
            out.append(f'卡牌实例对账: {start} 所在互斥组 {len(seen)} 张，越出同族持有上限 {limit} 张，三元环不可满足')
            break

    blob = json.dumps(canon['公司'], ensure_ascii=False)
    if 'CRD-' in blob:
        out.append(f"卡牌实例对账: 岗位卡侧出现 CRD- 引用 {blob.count('CRD-')} 处，"
                   f'卡牌实例单向引用字典 id，岗位卡不新增 CRD- 字段')
    return out


CHECKS = ['分区守恒', 'T5每大类一家', '档位区间与占比', '住所覆盖红线', '层系数单调',
          '起始年窗口', 'A08职责禁则', '公职不可申请边界', '字段黑名单', '无人机禁区',
          '引用完整性', '标签体系', '关键场景', '合同矩阵', '卡牌边界', '释放流程',
          '篮子完整性', '硬下限钳', '价物表自洽', '库存与配额',
          '参数完整性', '交通矩阵可复算', '天气年历闭合', '技能阈值同源', '事件与检查点自洽',
          '具名命名完整', '名称逐段回查', '命名池齐套', '名称禁则与长度', '零消费者对账', '产业图层对账', '职业条目对账',
          '失业救助对账', '五维开局对账', '卡牌实例对账']


def cost_issues(canon, costs, registry):
    """第 17 至 20 条：篮子完整性、硬下限钳、价物表自洽、库存与配额。"""
    out, p, cp = [], canon['参数'], costs['参数']
    rings = cp['圈层顺序']
    by_id = {e['id']: e for e in registry}

    # 17 篮子完整性：四圈层各一个年篮子，且每个值必须能由逐品类复算得出
    if sorted(costs['篮子']) != sorted(rings):
        out.append(f'篮子完整性: 圈层不齐 {sorted(costs["篮子"])}')
    if len(cp['商品圈层系数']) != 4:
        out.append('篮子完整性: 商品系数族不是四档')
    rebase = round(sum(c['三档基准价']['必需'] * c['标准月消耗量'] for c in costs['品类']), 1)
    if abs(rebase - costs['篮子基线_内湖环']) > 0.05:
        out.append(f'篮子完整性: 基线复算 {rebase} != 登记 {costs["篮子基线_内湖环"]}')
    for ring, coef in zip(rings, cp['商品圈层系数']):
        if costs['篮子'].get(ring) != round(rebase * coef, 1):
            out.append(f'篮子完整性: {ring} 未由基线×系数得出')
    if sorted(costs['季节展示']) != ['SEA-1', 'SEA-2', 'SEA-3', 'SEA-4']:
        out.append('篮子完整性: 季节展示缺档')

    # 18 硬下限钳：逐张卡的下界不得低于两条线的大值，卡上记录的生效线须与复算一致
    for comp in canon['公司']:
        z = comp['锚点']
        if z not in canon['住所锚'] or z not in by_id:
            out.append(f'硬下限钳: {z} 没有住所锚或名录条目')
            continue
        ring = entry_ring(by_id[z], by_id)
        if ring not in costs['篮子']:
            out.append(f'硬下限钳: {z} 的圈层 {ring} 没有篮子')
            continue
        anchor = canon['住所锚'][z]
        line = int(math.ceil(max(anchor / p['住所占比判据'],
                                 anchor + costs['篮子'][ring]) / p['月薪取整']) * p['月薪取整'])
        for card in comp['岗位卡']:
            if card['月薪带_钛币'][0] < line:
                out.append(f'硬下限钳: {card["id"]} 下界 {card["月薪带_钛币"][0]} < 生效线 {line}')
            if card['红线_钛币']['住所加篮子线'] != line:
                out.append(f'硬下限钳: {card["id"]} 记录的生效线 {card["红线_钛币"]["住所加篮子线"]} != 复算 {line}')

    # 19 价物表自洽：三档由两个乘数得出、精度 0.1、挂牌与维修回收单向走低
    #   参数级不变量先判，否则逐品类会先刷满 20 行打印窗口，把参数级措辞挤出 stdout
    if not 1.0 < cp['改善乘数'] < cp['奢侈乘数']:
        out.append('价物表: 派生乘数未严格递增')
    if not all(0.0 < v < 1.0 for v in (cp['维修费比例'], cp['回收系数'])):
        out.append('价物表: 维修或回收比例越出 (0,1)')
    if not all(0.0 <= v <= 1.0 for v in cp['减免比例'].values()):
        out.append('价物表: 减免比例越界')
    if len(cp['季节系数']) != 4:
        out.append('价物表: 季节系数不是四档')
    domain_by_id = {d['id']: d for d in costs['域表']}
    seen = set()
    for c in costs['品类']:
        if c['id'] in seen:
            out.append(f'价物表: 品类 id 重复 {c["id"]}')
        seen.add(c['id'])
        if c['域'] not in domain_by_id:
            out.append(f'价物表: 品类引用悬空 {c["id"]}')
            continue
        t = c['三档基准价']
        if not (t['必需'] <= t['改善'] <= t['奢侈']):
            out.append(f'价物表: 三档非单调 {c["id"]}')
        if t['改善'] != round(t['必需'] * cp['改善乘数'], 1) or t['奢侈'] != round(t['必需'] * cp['奢侈乘数'], 1):
            out.append(f'价物表: 改善或奢侈价不是由必需价乘派生系数得出 {c["id"]}')
        for v in (t['必需'], t['改善'], t['奢侈']):
            if round(v, 1) != v:
                out.append(f'价物表: 精度越出 0.1 {c["id"]}')
        if c['季节生效'] != domain_by_id[c['域']]['季节敏感']:
            out.append(f'价物表: 季节标志与域矛盾 {c["id"]}')
        if not set(c['减免归属'].values()) <= set(cp['减免比例']):
            out.append(f'价物表: 减免归属悬空 {c["id"]}')
        if c['二手适用']:
            cap = c['二手折价上限']
            if not 0.0 < cap < 1.0:
                out.append(f'价物表: 二手上限越界 {c["id"]}')
            listing, scrap = c['二手挂牌价_必需档'], c['回收价_必需档']
            if listing != round(t['必需'] * cap, 1) or scrap != round(listing * cp['回收系数'], 1):
                out.append(f'价物表: 挂牌价或回收价不是派生值 {c["id"]}')
            if not scrap < listing < t['必需']:
                out.append(f'价物表: 价格未沿 新品→二手→回收 单向走低 {c["id"]}')
        elif '二手折价上限' in c:
            out.append(f'价物表: 禁挂牌品类带了上限 {c["id"]}')
        if c['维修适用'] and c['维修费_必需档'] != round(t['必需'] * cp['维修费比例'], 1):
            out.append(f'价物表: 维修费不是派生值 {c["id"]}')

    # 20 库存与配额：176 行齐全、行合计守恒、配额向下取整保底 1 户、散居只挂聚落且恰好摊完
    rows = costs['库存']
    by_unit = {}
    for r in rows:
        by_unit.setdefault(r['单元ID'], []).append(r)
    if len(rows) != 176 or len(by_unit) != 44:
        out.append(f'库存与配额: 行数 {len(rows)} 或单元数 {len(by_unit)} 不对')
    if {r['住房类型ID'] for r in rows} != {'HOU-01', 'HOU-02', 'HOU-03', 'HOU-04'}:
        out.append(f'库存与配额: 住房类型数 {len({r["住房类型ID"] for r in rows})} != 4')
    for u, rs in sorted(by_unit.items()):
        if sum(x['总量'] for x in rs) != rs[0]['推导户数']:
            out.append(f'库存与配额: {u} Σ总量 != 推导户数')
        if abs(sum(x['类型配比'] for x in rs) - 1.0) > 1e-9:
            out.append(f'库存与配额: {u} 配比合计 != 1.00')
        if rs[0]['单元人口'] != rs[0]['登记人口'] + rs[0]['挂靠人口']:
            out.append(f'库存与配额: {u} 单元人口不自洽')
        for x in rs:
            if x['兜底配额'] != max(1, math.floor(x['总量'] * cp['兜底比例'])):
                out.append(f'库存与配额: {u}/{x["住房类型ID"]} 配额取整不符')
            if x['可分配'] != x['兜底配额'] or x['已占用'] + x['可分配'] != x['总量']:
                out.append(f'库存与配额: {u}/{x["住房类型ID"]} 占用恒等式破')
        if u.startswith('S'):
            up = rs[0]['挂靠人口'] / rs[0]['登记人口']
            if not 0.125 <= up <= 0.127:
                out.append(f'库存与配额: {u} 上浮比例 {up:.4f} 越出 12.5%—12.7%')
    if any(r['挂靠人口'] and r['单元ID'].startswith('D') for r in rows):
        out.append('库存与配额: 片区行带了散居挂靠')
    linked = sum(r['挂靠人口'] for r in rows) // 4
    if linked != costs['散居挂靠']['总人口']:
        out.append(f'库存与配额: Σ挂靠 {linked} != {costs["散居挂靠"]["总人口"]}')
    city = sum(rs[0]['推导户数'] for rs in by_unit.values())
    if city != costs['汇总']['全城户数']:
        out.append(f'库存与配额: 全城户数 {city} != 登记 {costs["汇总"]["全城户数"]}')
    if abs(city - costs['汇总']['全城人口'] / cp['户均规模']) > 44:
        out.append(f'库存与配额: 全城户数 {city} 偏离全域除法超过 44 户')
    detail = {}
    for rec in json.loads((ROOT / '数据' / '参考房价租金.json').read_text(encoding='utf-8'))['records']:
        if rec.get('parent', '').startswith('D') and 'typical_dwelling' in rec:
            detail[rec['parent']] = detail.get(rec['parent'], 0) + rec['typical_dwelling']['households']
    for d, got in sorted(detail.items()):
        if d in by_unit and got > by_unit[d][0]['推导户数']:
            out.append(f'库存与配额: {d} 居民区明细户数 {got} > 推导户数')
    return out


def param_issues(params, psource, costs, occ):
    """第 21 至 25 条：参数完整性、交通矩阵可复算、天气年历闭合、技能阈值同源、事件与检查点自洽。

    第一参数是运行参数正典（函数内简称 p 的来源），第四参数是产业就业正典——门禁必须自己独立
    算一遍矩阵与年历，不许 import build_params。
    """
    out, p = [], params['参数']
    order = ['个人', '家庭', '社区', '城市']

    # 21 参数完整性：六节无缺键，阈值严格递增，速度与系数为正，配额非负
    for group in ('技能', '季节月份', '交通', '圈层对', '天气', '事件', '检查点'):
        if group not in p:
            out.append(f'参数完整性: 缺 {group} 一节')
    if '圈层对' in p and len(p['圈层对']) != 10:
        out.append(f"参数完整性: 圈层对 {len(p['圈层对'])} 行 != 10")
    th = p['技能']['等级阈值月']
    if list(th) != ['LVL1', 'LVL2', 'LVL3', 'LVL4', 'LVL5']:
        out.append(f'参数完整性: 等级阈值键不齐 {list(th)}')
    if any(b <= a for a, b in zip(list(th.values()), list(th.values())[1:])):
        out.append('参数完整性: 等级阈值非严格递增')
    for m in p['交通']['方式']:
        if m['速度km_h'] <= 0:
            out.append(f"参数完整性: {m['码']} 速度非正")
    if p['交通']['绕行系数'] <= 0 or p['交通']['取整分钟'] <= 0:
        out.append('参数完整性: 绕行系数或取整系数非正')
    for label, v in (('每自然月', p['事件']['负面配额']['每自然月']), ('每轮', p['事件']['负面配额']['每轮'])):
        if v < 0:
            out.append(f'参数完整性: 负面配额{label}为负')
    if p['技能']['同标签每轮卡片上限'] < 0 or p['技能']['退化零使用月'] <= 0:
        out.append('参数完整性: 卡片上限或退化月数越界')

    # 22 交通矩阵可复算：逐格按公式重算；`—` 只允许出现在声明的不可用组合；几何实测对账；延后方式不得进矩阵
    #   速度、系数与覆盖清单一律取自 psource（手填源表），不取正典自带的同一份——否则派生器改写了常量也无从可查
    stats = ring_pair_stats()
    sp, by_cell = psource['交通'], {(c['圈层对'], c['方式']): c for c in params['交通矩阵']}
    want = {(pair_key(r['A'], r['B']), m['码']) for r in psource['圈层对'] for m in sp['方式']}
    if set(by_cell) != want:
        out.append(f'交通矩阵: 格子不齐 {sorted(set(by_cell) ^ want)[:4]}')
    for (key, code), cell in sorted(by_cell.items()):
        mode = next((m for m in sp['方式'] if m['码'] == code), None)
        if not mode:
            out.append(f'交通矩阵: 方式 {code} 未在源表声明')
            continue
        a, b = key.split('|')
        got = stats.get(key)
        if not got:
            out.append(f'交通矩阵: 圈层对 {key} 不在名录几何内')
            continue
        if abs(cell['中位直线km'] - got['中位直线km']) > 0.05:
            out.append(f"交通矩阵: {key} 中位直线 {cell['中位直线km']} 与实测 {got['中位直线km']} 偏差超 0.05")
        if key in mode['覆盖']:
            route = round(got['中位直线km'] * sp['绕行系数'], 2)
            mins = math.ceil((route / mode['速度km_h'] * 60 + transfer_minutes(sp, code, a, b))
                             / sp['取整分钟']) * sp['取整分钟']
            if cell['耗时分钟'] != mins or cell['路线km'] != route:
                out.append(f"交通矩阵: {key}/{code} 登记 {cell['耗时分钟']}分·{cell['路线km']}km，复算 {mins}分·{route}km")
        elif cell['耗时分钟'] is not None:
            out.append(f'交通矩阵: {key}/{code} 不在覆盖清单内却有耗时')
    deferred = {m['码'] for m in sp['延后方式']}
    for code in sorted(deferred & {c['方式'] for c in params['交通矩阵']}):
        out.append(f'交通矩阵: 延后方式 {code} 进了矩阵，耗时须待第5期清单')

    # 23 天气年历闭合：月份不重不漏、逐月展开天数、总和 365、相邻游程不同态、单游程≤10、季度次数落区间、态码在字典内、SEA 与物价同源
    sea = p['季节月份']
    months = [m for info in sea.values() for m in info['月']]
    if sorted(months) != list(range(1, 13)):
        out.append(f'天气年历: 十二个月不重不漏失败 {sorted(months)}')
    if any(info['天数'] != sum(MONTH_DAYS[m] for m in info['月']) for info in sea.values()):
        out.append('天气年历: 某季声明天数与其月份天数之和不符')
    codes = {s['码'] for s in p['天气']['态']}
    runs = p['天气']['逐月游程']
    if sorted(runs, key=int) != [str(m) for m in range(1, 13)]:
        out.append(f'天气年历: 游程月份键不齐 {sorted(runs, key=int)}')
    for mm, rr in runs.items():
        if len(expand_runs(rr)) != MONTH_DAYS[int(mm)]:
            out.append(f"天气年历: {mm} 月展开 {len(expand_runs(rr))} 天 != {MONTH_DAYS[int(mm)]}")
        if any(rr[i][0] == rr[i + 1][0] for i in range(len(rr) - 1)):
            out.append(f'天气年历: {mm} 月存在相邻同态游程')
        if any(c > 10 for _, c in rr):
            out.append(f'天气年历: {mm} 月单游程超过 10 天')
        for code, _ in rr:
            if code not in codes:
                out.append(f'天气年历: 态码 {code} 不在字典内（{mm} 月）')
    year = params['天气年历']
    if len(year) != 365:
        out.append(f'天气年历: 正典 {len(year)} 格 != 365')
    sea_lookup = sea_of(params)
    # 十二个月不重不漏是展开比对的前提：月份表被改坏时 sea_of 会静默吞掉重复键，
    # 此时只报上面那条判红，不能让门禁以 KeyError 代替判红。
    months_ok = sorted(months) == list(range(1, 13))
    expect = [(sea_lookup[mm], code) for mm in sorted(runs, key=int)
              for code in expand_runs(runs[mm])] if months_ok else []
    if months_ok and (len(expect) != len(year) or any((c['SEA'], c['态']) != e for c, e in zip(year, expect))):
        out.append('天气年历: 与逐月游程展开不符')
    for s_code, ranges in p['天气']['次数区间'].items():
        counts = {}
        for mm in sea[s_code]['月']:
            for code, n in runs[str(mm)]:
                counts[code] = counts.get(code, 0) + n
        for code, (lo, hi) in ranges.items():
            if not lo <= counts.get(code, 0) <= hi:
                out.append(f'天气年历: {s_code}/{code} 实得 {counts.get(code, 0)} 越出 [{lo}, {hi}]')
    if sorted(sea) != sorted(costs['参数']['季节系数']):
        out.append(f'天气年历: SEA 键与物价季节系数不齐 物价 {sorted(costs["参数"]["季节系数"])}')

    # 24 技能阈值与五层同源：五档递增且首档 0、键与岗位卡 LVL 码一一对应、退化比例在 (0,1)、五维刻度下界非负且上界大于下界、微调比例块三键齐套且退化下限等于跨度反推
    if list(th.values())[0] != 0:
        out.append('技能阈值: 首档不为 0')
    lvl_codes = {card['岗位层'] for comp in occ['公司'] for card in comp['岗位卡']}
    if lvl_codes != set(th):
        out.append(f'技能阈值: 与岗位卡层码不对应 {sorted(lvl_codes ^ set(th))}')
    ratio = p['技能']['退化下限比例']
    if not 0.0 < ratio < 1.0:
        out.append(f'技能阈值: 退化下限比例 {ratio} 越出 (0,1)')
    lo, hi = p['技能']['五维刻度']
    if not (lo >= 0 and hi > lo):
        out.append(f'技能阈值: 五维刻度 {p["技能"]["五维刻度"]} 下界为负或倒挂')
    fine_keys = ('单卡占跨度上限', '同维度累计占跨度上限', '退化下限占跨度')
    fine = p['技能'].get('五维微调比例') or {}
    missing = [k for k in fine_keys if k not in fine]
    if missing:
        out.append(f'技能阈值: 五维微调比例 缺键 {missing}')
    else:
        span = hi - lo
        want_floor = round(span * fine['退化下限占跨度'])
        if p['技能']['五维退化下限'] != want_floor:
            out.append(f'技能阈值: 五维退化下限 {p["技能"]["五维退化下限"]} 不等于刻度跨度 {span} 反推的 {want_floor}——刻度与下限脱钩')

    # 25 事件与检查点自洽：冷却与预告随级别单调、每轮配额不小于每自然月、保留数≥1、时刻 HH:MM、不得自助回档
    cd = p['事件']['冷却天']
    if set(cd) != set(order):
        out.append(f'事件与检查点: 冷却级别不齐 {sorted(cd)}')
    if any(cd[b] < cd[a] for a, b in zip(order, order[1:]) if a in cd and b in cd):
        out.append('事件与检查点: 冷却天须随级别单调不减')
    if p['事件']['负面配额']['每轮'] < p['事件']['负面配额']['每自然月']:
        out.append('事件与检查点: 每轮负面配额不得小于每自然月配额')
    pn = p['事件']['预告天']
    if any(pn[b] < pn[a] for a, b in zip(['社区级', '城市级'], ['社区级', '城市级'][1:])):
        out.append('事件与检查点: 预告天须随级别单调不减')
    if p['检查点']['保留日检查点数'] < 1:
        out.append('事件与检查点: 检查点保留数须 ≥1')
    if not re.match(r'^\d{2}:\d{2}$', p['检查点']['日检查点时刻']):
        out.append(f"事件与检查点: 日检查点时刻 {p['检查点']['日检查点时刻']} 不匹配 HH:MM")
    if p['检查点']['用户自助回档'] is not False:
        out.append('事件与检查点: 用户自助回档必须为 false')
    return out


def main():
    ap = ROOT / '数据' / '岗位准入正典.json'
    if not ap.exists():
        raise SystemExit('缺少 数据/岗位准入正典.json：先运行 python 工具/build_admission.py，门禁不得因无引用可查而空转判绿')
    cp = ROOT / '数据' / '物价与生活正典.json'
    if not cp.exists():
        raise SystemExit('缺少 数据/物价与生活正典.json：先运行 python 工具/build_costs.py，物价门禁不得空转判绿')
    canon = json.loads((ROOT / '数据' / '产业就业正典.json').read_text(encoding='utf-8'))
    adm = json.loads(ap.read_text(encoding='utf-8'))
    costs = json.loads(cp.read_text(encoding='utf-8'))
    pp = ROOT / '数据' / '运行参数正典.json'
    if not pp.exists():
        raise SystemExit('缺少 数据/运行参数正典.json：先运行 python 工具/build_params.py，参数门禁不得空转判绿')
    ps = ROOT / '数据' / '运行参数源表.json'
    if not ps.exists():
        raise SystemExit('缺少 数据/运行参数源表.json：门禁须按源表声明的覆盖清单复核矩阵，不得只信正典自证')
    params = json.loads(pp.read_text(encoding='utf-8'))
    psource = json.loads(ps.read_text(encoding='utf-8'))['参数']
    lp = ROOT / '数据' / '产业空间图层.json'
    if not lp.exists():
        raise SystemExit('缺少 数据/产业空间图层.json：先运行 python 工具/build_maps.py，图层门禁不得因无图层可查而空转判绿')
    layer = json.loads(lp.read_text(encoding='utf-8'))
    op = ROOT / '数据' / '职业条目源表.json'
    if not op.exists():
        raise SystemExit('缺少 数据/职业条目源表.json：职业条目正文只住在这份手填真源里，先补源表再过闸，'
                         '条目门禁不得因无条目可查而空转判绿')
    occ_source = json.loads(op.read_text(encoding='utf-8'))
    kp = ROOT / '数据' / '卡牌实例源表.json'
    if not kp.exists():
        raise SystemExit('缺少 数据/卡牌实例源表.json：卡牌实例的条数带与长度带只住在这份手填真源里，'
                         '第 35 条不得因无实例可查而空转判绿')
    card_source = json.loads(kp.read_text(encoding='utf-8'))
    naming_pool = SOURCE.get('命名') or {}
    zc = zero_counts(canon, adm)
    bad = issues(canon, SOURCE, REGISTRY, adm, costs, params, psource, layer, occ_source, card_source)
    report = {'检查项': CHECKS, '检查项数': len(CHECKS), '失败数': len(bad), '失败明细': bad[:40],
              '字典汇总': {k: adm['汇总'][k] for k in ('标签数', '场景数', '合同类型数', '卡牌族数', '释放状态数',
                                                       '卡牌实例数', '背景卡实例数')},
              '物价汇总': {'篮子': costs['篮子'], '品类数': costs['汇总']['品类数'],
                        '库存行数': costs['汇总']['库存行数'], '全城户数': costs['汇总']['全城户数'],
                        '散居挂靠余数': costs['汇总']['散居挂靠余数'],
                        '被顶起卡数': canon['汇总']['被顶起卡数'],
                        '被顶起名额数': canon['汇总']['被顶起名额数'],
                        '被顶起按圈层': canon['汇总']['被顶起按圈层']},
              '参数汇总': {'矩阵格数': params['汇总']['矩阵格数'], '可用格数': params['汇总']['可用格数'],
                        '年历格数': params['汇总']['年历格数'], '季节数': params['汇总']['季节数'],
                        '等级阈值': params['技能等级阈值']},
              '命名汇总': {'具名命名数': canon['汇总'].get('具名命名数'),
                        '字号池': len(naming_pool.get('字号池', [])), '锚点简称': len(naming_pool.get('锚点简称', {})),
                        '小类词根': len(naming_pool.get('小类词根', {})), '档位后缀': len(naming_pool.get('档位后缀', {})),
                        '顶端名称': len(naming_pool.get('顶端名称', {})),
                        '最大具名组': max(count_groups(canon['公司']).values(), default=0),
                        '名称长度区间': naming_pool.get('名称长度区间', [])},
              '零消费者汇总': {'背景小类': len(SOURCE.get('零消费者', {}).get('背景小类', [])),
                          '通用技能数': len(SOURCE.get('零消费者', {}).get('通用技能标签', [])),
                          '通用场景数': len(SOURCE.get('零消费者', {}).get('通用场景', [])),
                          '截断大类': sorted(SOURCE.get('零消费者', {}).get('上限截断大类', {})),
                          '无引用标签数': zc[0],
                          '无引用场景数': zc[1],
                          '无卡小类数': zc[2]},
              '图层汇总': {'锚点数': layer['汇总']['岗位锚点数'], '公司数': layer['汇总']['公司数'],
                        '岗位卡数': layer['汇总']['岗位卡数'], '雇员总数': layer['汇总']['雇员总数'],
                        '大类数': layer['汇总']['大类数'], '最大单锚雇员数': layer['汇总']['最大单锚雇员数'],
                        '气泡半径km': layer['汇总']['气泡半径km'], '逐圈层': layer['汇总']['逐圈层']},
              '职业条目汇总': {'源表小类行数': len(occ_source.get('小类', [])),
                          '正典条目数': len(canon.get('职业条目', [])),
                          '名称唯一数': len({e['名称'] for e in canon.get('职业条目', [])}),
                          '每类条数': occ_source.get('规格', {}).get('每类条数', []),
                          '总条数区间': occ_source.get('规格', {}).get('总条数区间', [])},
              '救助汇总': {'全额比例': COST_SOURCE['失业救助']['全额比例'],
                        '递减比例': COST_SOURCE['失业救助']['递减比例'],
                        '全额月数': COST_SOURCE['失业救助']['全额月数'],
                        '递减月数': COST_SOURCE['失业救助']['递减月数'],
                        '最长连发月数': COST_SOURCE['失业救助']['最长连发月数'],
                        '逐圈层全额月': {r: costs['保障'][r]['失业救助_全额月_钛币'] for r in COST_SOURCE['圈层顺序']},
                        '逐圈层递减月': {r: costs['保障'][r]['失业救助_递减月_钛币'] for r in COST_SOURCE['圈层顺序']},
                        '逐圈层连发总额': {r: costs['保障'][r]['失业救助_连发总额_钛币'] for r in COST_SOURCE['圈层顺序']}},
              '开局汇总': {'刻度': params['参数']['技能'].get('五维刻度'),
                        '五档': params['参数']['技能'].get('五维开局', {}).get('维度'),
                        '中位': params['参数']['技能'].get('五维开局', {}).get('中位'),
                        '满值罕见线': params['参数']['技能'].get('五维开局', {}).get('满值罕见线'),
                        '开局区间': params.get('五维开局', {}).get('开局区间'),
                        '单类影响上限': params.get('五维开局', {}).get('单类影响上限'),
                        '同维度累计影响上限': params.get('五维开局', {}).get('同维度累计影响上限'),
                        '候选组合数': params.get('五维开局', {}).get('候选组合数'),
                        '权重和': params.get('五维开局', {}).get('权重和'),
                        'CRD-A3幅度上限': next((c['幅度上限'] for c in ADM_SOURCE['卡牌族'] if c['id'] == 'CRD-A3'), None)},
              '判据': '三十五条判红（十条产业＋六条字典＋四条物价＋五条运行参数＋四条具名命名＋一条零消费者对账＋一条产业图层对账＋一条职业条目对账＋一条失业救助对账＋一条五维开局对账＋一条卡牌实例对账）；任一失败即非零退出，不允许空转判绿'}
    (ROOT / '数据' / '产业就业核验.json').write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                    encoding='utf-8')
    if bad:
        # 打印窗口与报告里的 失败明细 同宽（40 行）：具名判据排在最后，窗口过窄会把它的措辞挤出 stdout。
        for b in bad[:40]:
            print('FAIL', b)
        print(f'共 {len(bad)} 条判红，前 40 条已打印')
        raise SystemExit(1)
    print(f'全绿：三十五条判红，0 失败；公司 {canon["汇总"]["公司数"]} 家（具名 {canon["汇总"]["具名公司数"]}）'
          f'，岗位卡 {canon["汇总"]["岗位卡数"]} 张，雇员 {canon["汇总"]["雇员总数"]} 人'
          f'，被顶起 {canon["汇总"]["被顶起卡数"]} 张／{canon["汇总"]["被顶起名额数"]} 名额'
          f'，职业条目 {canon["汇总"]["职业条目数"]} 条／{canon["汇总"]["职业条目覆盖小类数"]} 小类'
          f'，图层 {layer["汇总"]["岗位锚点数"]} 锚点／{layer["汇总"]["大类数"]} 大类'
          f'，卡牌实例 {adm["汇总"]["卡牌实例数"]} 张（{adm["汇总"]["已展开族数"]} 族已展开／'
          f'{adm["汇总"]["未展开族数"]} 族未展开）／背景卡 {adm["汇总"]["背景卡实例数"]} 张')


if __name__ == '__main__':
    main()
