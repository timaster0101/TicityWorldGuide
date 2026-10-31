# -*- coding: utf-8 -*-
"""产业与就业层闸门：十条判红全部落在数据层，任一失败即非零退出。跑法：python 工具/verify_occupations.py"""
import json, math, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = json.loads((ROOT / '数据' / '产业就业源表.json').read_text(encoding='utf-8'))
REGISTRY = json.loads((ROOT / '数据' / '城市空间名录.json').read_text(encoding='utf-8'))['entries']


def issues(canon, source, registry, adm):
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
          '引用完整性', '标签体系', '关键场景', '合同矩阵', '卡牌边界', '释放流程']


def main():
    ap = ROOT / '数据' / '岗位准入正典.json'
    if not ap.exists():
        raise SystemExit('缺少 数据/岗位准入正典.json：先运行 python 工具/build_admission.py，门禁不得因无引用可查而空转判绿')
    canon = json.loads((ROOT / '数据' / '产业就业正典.json').read_text(encoding='utf-8'))
    adm = json.loads(ap.read_text(encoding='utf-8'))
    bad = issues(canon, SOURCE, REGISTRY, adm)
    report = {'检查项': CHECKS, '检查项数': len(CHECKS), '失败数': len(bad), '失败明细': bad[:40],
              '字典汇总': {k: adm['汇总'][k] for k in ('标签数', '场景数', '合同类型数', '卡牌族数', '释放状态数')},
              '判据': '十六条判红（十条产业＋六条字典）；任一失败即非零退出，不允许空转判绿'}
    (ROOT / '数据' / '产业就业核验.json').write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                    encoding='utf-8')
    if bad:
        for b in bad[:20]:
            print('FAIL', b)
        raise SystemExit(1)
    print(f'全绿：十六条判红，0 失败；公司 {canon["汇总"]["公司数"]} 家（具名 {canon["汇总"]["具名公司数"]}）'
          f'，岗位卡 {canon["汇总"]["岗位卡数"]} 张，雇员 {canon["汇总"]["雇员总数"]} 人')


if __name__ == '__main__':
    main()
