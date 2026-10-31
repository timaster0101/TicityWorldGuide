# -*- coding: utf-8 -*-
"""产业与就业层闸门：二十五条判红全部落在数据层（十条产业＋六条字典＋四条物价＋五条运行参数），任一失败即非零退出。跑法：python 工具/verify_occupations.py"""
import json, math, re
from pathlib import Path

from anchors import entry_ring, RINGS, pair_key, ring_pair_stats

ROOT = Path(__file__).resolve().parents[1]
SOURCE = json.loads((ROOT / '数据' / '产业就业源表.json').read_text(encoding='utf-8'))
REGISTRY = json.loads((ROOT / '数据' / '城市空间名录.json').read_text(encoding='utf-8'))['entries']

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


def issues(canon, source, registry, adm, costs, params, psource):
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
    out += adm_issues(canon, adm)
    out += cost_issues(canon, costs, registry)
    out += param_issues(params, psource, costs, canon)
    return out

def adm_issues(canon, adm):
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
            nums = [int(x) for x in re.findall(r'(\d+)\s*点', f['幅度上限'])]
            if not nums or max(nums) > 4 or any(n > 2 for n in nums[:1]):
                out.append(f'卡牌边界: {f["id"]} 五维点数越界')
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



CHECKS = ['分区守恒', 'T5每大类一家', '档位区间与占比', '住所覆盖红线', '层系数单调',
          '起始年窗口', 'A08职责禁则', '公职不可申请边界', '字段黑名单', '无人机禁区',
          '引用完整性', '标签体系', '关键场景', '合同矩阵', '卡牌边界', '释放流程',
          '篮子完整性', '硬下限钳', '价物表自洽', '库存与配额',
          '参数完整性', '交通矩阵可复算', '天气年历闭合', '技能阈值同源', '事件与检查点自洽']


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

    # 24 技能阈值与五层同源：五档递增且首档 0、键与岗位卡 LVL 码一一对应、退化比例在 (0,1)、五维刻度正且下界小于上界
    if list(th.values())[0] != 0:
        out.append('技能阈值: 首档不为 0')
    lvl_codes = {card['岗位层'] for comp in occ['公司'] for card in comp['岗位卡']}
    if lvl_codes != set(th):
        out.append(f'技能阈值: 与岗位卡层码不对应 {sorted(lvl_codes ^ set(th))}')
    ratio = p['技能']['退化下限比例']
    if not 0.0 < ratio < 1.0:
        out.append(f'技能阈值: 退化下限比例 {ratio} 越出 (0,1)')
    lo, hi = p['技能']['五维刻度']
    if not (lo > 0 and hi > lo):
        out.append(f'技能阈值: 五维刻度 {p["技能"]["五维刻度"]} 不正或倒挂')

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
    bad = issues(canon, SOURCE, REGISTRY, adm, costs, params, psource)
    report = {'检查项': CHECKS, '检查项数': len(CHECKS), '失败数': len(bad), '失败明细': bad[:40],
              '字典汇总': {k: adm['汇总'][k] for k in ('标签数', '场景数', '合同类型数', '卡牌族数', '释放状态数')},
              '物价汇总': {'篮子': costs['篮子'], '品类数': costs['汇总']['品类数'],
                        '库存行数': costs['汇总']['库存行数'], '全城户数': costs['汇总']['全城户数'],
                        '散居挂靠余数': costs['汇总']['散居挂靠余数'],
                        '被顶起卡数': canon['汇总']['被顶起卡数'],
                        '被顶起名额数': canon['汇总']['被顶起名额数'],
                        '被顶起按圈层': canon['汇总']['被顶起按圈层']},
              '参数汇总': {'矩阵格数': params['汇总']['矩阵格数'], '可用格数': params['汇总']['可用格数'],
                        '年历格数': params['汇总']['年历格数'], '季节数': params['汇总']['季节数'],
                        '等级阈值': params['技能等级阈值']},
              '判据': '二十五条判红（十条产业＋六条字典＋四条物价＋五条运行参数）；任一失败即非零退出，不允许空转判绿'}
    (ROOT / '数据' / '产业就业核验.json').write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                    encoding='utf-8')
    if bad:
        for b in bad[:20]:
            print('FAIL', b)
        raise SystemExit(1)
    print(f'全绿：二十五条判红，0 失败；公司 {canon["汇总"]["公司数"]} 家（具名 {canon["汇总"]["具名公司数"]}）'
          f'，岗位卡 {canon["汇总"]["岗位卡数"]} 张，雇员 {canon["汇总"]["雇员总数"]} 人'
          f'，被顶起 {canon["汇总"]["被顶起卡数"]} 张／{canon["汇总"]["被顶起名额数"]} 名额')


if __name__ == '__main__':
    main()
