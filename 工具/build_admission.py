# -*- coding: utf-8 -*-
"""岗位准入字典生成器：读 岗位准入源表.json ＋ 产业就业源表.json ＋ 卡牌实例源表.json，确定性展开标签、场景、合同、卡牌族、卡牌实例与状态机。

脚本内不内嵌任何大类／小类名称，全部从源表读取；卡牌实例的正文与条数／长度带只住在 卡牌实例源表.json，
本文件只按 绑定域 反查真实对象并派生 id 与读数；不读名录与定价，与空间层零耦合。
跑法：python 工具/build_admission.py [--out-dir DIR]
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = json.loads((ROOT / '数据' / '岗位准入源表.json').read_text(encoding='utf-8'))
OCC = json.loads((ROOT / '数据' / '产业就业源表.json').read_text(encoding='utf-8'))


def build_tags():
    tags = []
    for s in OCC['小类']:
        for kind, spec in SOURCE['专属标签'].items():
            tags.append({'id': 'SKL-' + s['id'] + '-' + kind, '名称': s['名称'] + spec['后缀'],
                         '族': '专属技能', '子类': kind, '父大类': s['父大类'], '父小类': s['id'],
                         '可推进途径': list(spec['途径']), '可由日常活动推进': 'LEV' in spec['途径']})
    for c in SOURCE['通用技能池']:
        tags.append({'id': c['id'], '名称': c['名称'], '族': '通用技能', '子类': None, '父大类': None,
                     '父小类': None, '可推进途径': list(c['途径']), '可由日常活动推进': True})
    for d in OCC['大类']:
        tags.append({'id': 'SKL-Q-' + d['id'], '名称': d['名称'] + SOURCE['资质标签']['后缀'], '族': '资质',
                     '子类': None, '父大类': d['id'], '父小类': None,
                     '可推进途径': list(SOURCE['资质标签']['途径']), '可由日常活动推进': False})
        for i, suffix in enumerate(SOURCE['经历标签']['后缀'], start=1):
            tags.append({'id': 'SKL-E-' + d['id'] + '-' + str(i), '名称': d['名称'] + suffix, '族': '经历',
                         '子类': None, '父大类': d['id'], '父小类': None,
                         '可推进途径': list(SOURCE['经历标签']['途径']), '可由日常活动推进': False})
    return tags


def common_tag_split():
    pool = [c['id'] for c in SOURCE['通用技能池']]
    return {d['id']: [pool[(3 * i + k) % len(pool)] for k in range(3)] for i, d in enumerate(OCC['大类'])}


def build_scenes():
    all_classes = [d['id'] for d in OCC['大类']]
    base = SOURCE['通用场景'][0]
    scenes = [{**g, '类别': '通用', '适用大类': list(all_classes)} for g in SOURCE['通用场景']]
    for d in OCC['大类']:
        for key, spec in SOURCE['行业场景后缀'].items():
            scenes.append({'id': 'SCN-' + d['id'] + '-' + key, '名称': d['名称'] + spec['后缀'],
                           '类别': '行业', '适用大类': [d['id']], '触发岗位层': list(spec['触发岗位层']),
                           '参与方': '本人、班组或科室、外部接收方', '前置标签': ['SKL-Q-' + d['id']],
                           '结果口径': dict(base['结果口径']), '可跳过按规则结算': True,
                           '跳过结算': base['跳过结算'], '每人物每城市年频次上限': 2,
                           '可由卡牌豁免': spec['可由卡牌豁免']})
    return scenes


def contracts_for(level, tier, form):
    """按 (岗位层 × 公司档 × 小类准入形态) 取合同集；空集即源表矩阵无解，报错退出而不是静默回退。"""
    pool = [c['id'] for c in SOURCE['合同类型'] if level in c['可适用岗位层'] and tier in c['可适用公司档']]
    rule = SOURCE['准入形态合同过滤'][form]
    pool = [c for c in pool if c in rule['仅']] if isinstance(rule, dict) else [c for c in pool if c not in rule]
    if not pool:
        raise SystemExit('合同矩阵无解：' + level + ' ' + tier + ' ' + form + '，请回源表调矩阵，不要放宽门禁')
    return pool


def counts(tags):
    by = {}
    for t in tags:
        by[t['族']] = by.get(t['族'], 0) + 1
    return by


CARD_SOURCE_KEYS = ('口径', '规格', '卡牌族实例', '背景卡实例', '禁则')


def load_card_source():
    path = ROOT / '数据' / '卡牌实例源表.json'
    if not path.exists():
        raise SystemExit('缺少 数据/卡牌实例源表.json：卡牌正文属手填真源，生成器不代填文本，'
                         '门禁第 35 条也不得因无实例可查而空转判绿')
    doc = json.loads(path.read_text(encoding='utf-8'))
    missing = [k for k in CARD_SOURCE_KEYS if k not in doc]
    if missing:
        raise SystemExit(f'卡牌实例源表.json 缺 {missing}：条数带、长度带与绑定域表只住在本表「规格」块，生成器不内嵌常量')
    return doc


CARD_SOURCE = load_card_source()

# 四个标签域在本文件的标签集里反查，场景与释放状态同理，大类在本文件已读的产业就业源表里；
# 名录片区与运行参数五维两域不在本生成器的读取面内（本文件不读名录与定价），读数里如实写「由闸门对账」，
# 存在性由门禁第 35 条按同一份真源判，不在此处伪造命中。
TAG_DOMAIN_FAMILY = {'专属技能标签': '专属技能', '资质标签': '资质',
                     '经历标签': '经历', '通用技能标签': '通用技能'}


def card_binding(domain, sub, obj, tag_by_id, scene_by_id, rel_by_id, major_by_id):
    if domain in TAG_DOMAIN_FAMILY:
        t = tag_by_id.get(obj)
        if not t:
            return {'解析': '未命中', '域': domain}
        return {'解析': '命中', '域': domain, '名称': t['名称'], '标签族': t['族'], '子类': t['子类'],
                '父大类': t['父大类'], '父小类': t['父小类'], '可推进途径': t['可推进途径'],
                '族相符': t['族'] == TAG_DOMAIN_FAMILY[domain],
                '子类相符': True if sub is None else t['子类'] == sub}
    if domain == '场景':
        s = scene_by_id.get(obj)
        if not s:
            return {'解析': '未命中', '域': domain}
        return {'解析': '命中', '域': domain, '名称': s['名称'], '类别': s['类别'],
                '适用大类': s['适用大类']}
    if domain == '释放状态':
        r = rel_by_id.get(obj)
        return {'解析': '命中' if r else '未命中', '域': domain, '名称': r}
    if domain == '大类':
        m = major_by_id.get(obj)
        return {'解析': '命中' if m else '未命中', '域': domain, '名称': m}
    return {'解析': '由闸门对账', '域': domain}


def build_card_instances(tags, scenes):
    spec = CARD_SOURCE['规格']
    fam_by_id = {f['id']: f for f in SOURCE['卡牌族']}
    tag_by_id = {t['id']: t for t in tags}
    scene_by_id = {s['id']: s for s in scenes}
    rel_by_id = {r['id']: r['名称'] for r in SOURCE['释放状态']}
    major_by_id = {d['id']: d['名称'] for d in OCC['大类']}
    rows = []
    for block in CARD_SOURCE['卡牌族实例']:
        fid = block['族']
        fam = fam_by_id.get(fid)
        domain = spec['绑定域表'].get(fid)
        sub = spec['绑定子类表'].get(fid)
        for i, item in enumerate(block['条目'], start=1):
            row = {'id': f'{fid}-{i:03d}', '族': fid,
                   '族名': fam['名称'] if fam else None,
                   '类别': fam['类别'] if fam else None,
                   '绑定域': domain, '绑定途径': fam['绑定途径'] if fam else None,
                   '幅度上限': fam['幅度上限'] if fam else None,
                   '序号': i}
            for k in spec['字段']:
                row[k] = item.get(k)
            row['绑定读数'] = card_binding(domain, sub, item.get('绑定对象'),
                                          tag_by_id, scene_by_id, rel_by_id, major_by_id)
            rows.append(row)
    per_family = {fid: sum(1 for r in rows if r['族'] == fid) for fid in spec['每族条数']}
    bg = [{'id': f"BG-{i:03d}", **item} for i, item in enumerate(CARD_SOURCE['背景卡实例']['条目'], start=1)]
    return rows, bg, per_family


def render_table(canon):
    s, g = canon['汇总'], canon['场景']
    L = ['# 钛湖城岗位准入字典总表', '',
         '正典来源：`数据/岗位准入源表.json`＋`数据/产业就业源表.json`；本文件由生成器输出，禁止手改。', '',
         '## 1. 口径说明', '',
         f"- 标签 {s['标签数']} 条＝专属 {s['专属标签数']}（{s['覆盖小类数']} 小类 × 2）＋通用 {s['通用标签数']} ＋资质 {s['资质标签数']} ＋经历 {s['经历标签数']}。",
         f"- 场景 {s['场景数']} 项＝通用 {s['通用场景数']} ＋行业 {s['行业场景数']}；合同 {s['合同类型数']} 类；卡牌族 {s['卡牌族数']} 族（能力类 {s['能力类族数']}＋学习类 {s['学习类族数']}）；释放状态 {s['释放状态数']} 态。",
         '- 阶四值 ' + '／'.join(canon['阶']) + '；非阶要求 ' + '／'.join(canon['非阶要求']) + '。升阶与退化阈值已由第4期运行参数落定，口径见《运行参数设定》与 `数据/运行参数正典.json` 的 `技能等级阈值`；本字典与岗位卡只引用标签 ID，不复述阈值。',
         '- 加班口径统一：工作日 1.5 倍、休息日 2 倍、法定节假日 3 倍，每月封顶 36 小时；接单与临时项目按约定单价，不套加班口径。',
         '- 卡牌全局禁则五条：' + '；'.join(canon['参数']['全局禁则']) + '。', '',
         '## 2. 标签统计（按大类）', '', '| 大类 | 专属标签 | 资质标签 | 经历标签 | 分配到的通用标签 |', '|---|---|---|---|---|']
    for d in OCC['大类']:
        n_sub = sum(1 for x in OCC['小类'] if x['父大类'] == d['id'])
        L.append(f"| {d['id']} {d['名称']} | {n_sub * 2} | 1 | 2 | {'、'.join(canon['通用标签分配'][d['id']])} |")
    L += ['', '## 3. 通用技能池', '', '| id | 名称 | 可推进途径 |', '|---|---|---|']
    for c in canon['标签']:
        if c['族'] == '通用技能':
            L.append(f"| {c['id']} | {c['名称']} | {'、'.join(c['可推进途径'])} |")
    L += ['', '## 4. 关键工作场景', '', '| id | 名称 | 类别 | 触发岗位层 | 适用大类 | 前置标签 | 年频次上限 | 可卡牌豁免 |',
          '|---|---|---|---|---|---|---|---|']
    for x in g:
        L.append(f"| {x['id']} | {x['名称']} | {x['类别']} | {'、'.join(x['触发岗位层'])} | {len(x['适用大类'])} 类 "
                 f"| {'、'.join(x['前置标签'])} | {x['每人物每城市年频次上限']} | {'是' if x['可由卡牌豁免'] else '否'} |")
    L += ['', '## 5. 合同类型', '', '| id | 名称 | 用工形态 | 月工时上限 | 结算周期 | 试用期_城市年 | 年休假_天 | 可叠加 | 可适用岗位层 | 可适用公司档 | 占用名额 |',
          '|---|---|---|---|---|---|---|---|---|---|---|']
    for c in canon['合同类型']:
        cap = c['月工时上限_相对174']
        L.append(f"| {c['id']} | {c['名称']} | {c['用工形态']} | {'不预设' if cap is None else f'{cap:.2f}'} "
                 f"| {c['薪酬结算周期']} | {c['试用期_城市年']:.2f} | {c['年休假基准_天']} "
                 f"| {'是' if c['可叠加'] else '否'} | {'—'.join([c['可适用岗位层'][0], c['可适用岗位层'][-1]])} "
                 f"| {'、'.join(c['可适用公司档'])} | {'是' if c['占用名额'] else '否'} |")
    L += ['', '## 6. 卡牌族', '', '| id | 名称 | 类别 | 效果类型 | 效果对象 | 幅度上限 | 获取来源 | 绑定途径 | 跨轮继承 |',
          '|---|---|---|---|---|---|---|---|---|']
    for f in canon['卡牌族']:
        L.append(f"| {f['id']} | {f['名称']} | {f['类别']} | {f['效果类型']} | {f['效果对象']} | {f['幅度上限']} "
                 f"| {f['获取来源']} | {f['绑定途径'] or '无'} | {'是' if f['跨轮继承'] else '否'} |")
    L += ['', f"持有上限：同族 {canon['参数']['持有上限']['同族']} 张、总持有 {canon['参数']['持有上限']['总持有']} 张、"
               f"跨轮继承 {canon['参数']['持有上限']['跨轮继承']} 张。", '',
          '## 7. 岗位释放状态机', '', '| id | 名称 | 说明 | 合法去向 |', '|---|---|---|---|']
    for r in canon['释放状态']:
        L.append(f"| {r['id']} | {r['名称']} | {r['说明']} | {'、'.join(r['去向']) or '终态'} |")
    rule = canon['参数']['释放规则']
    L += ['', f"状态判定：卡片 `起始城市年` 晚于 {canon['setting_year']}（{rule['基准年说明']}）取 {rule['晚于基准年']}，"
               f"否则取 {rule['否则']}；释放去向白名单 {'、'.join(rule['释放去向白名单'])}；名额回流口径：{rule['名额回流']}；"
               f"再求职匹配键：{rule['再求职匹配键']}，优先级 {'→'.join(rule['优先级'])}。留白：{rule['留白']}。", '']
    cards_spec = canon['卡牌实例']['规格']
    L += ['', '## 8. 卡牌实例（第9期 9a：容器）', '',
          f"实例 {canon['汇总']['卡牌实例数']} 张、已展开族 {canon['汇总']['已展开族数']} 族、"
          f"未展开族 {canon['汇总']['未展开族数']} 族、背景卡实例 {canon['汇总']['背景卡实例数']} 张；"
          f"总条数带 {cards_spec['总条数区间'][0]}—{cards_spec['总条数区间'][1]}（未展开态记 0，不判越带）。", '',
          '| 族 | 绑定域 | 绑定子类 | 条数带 | 实得条数 |', '|---|---|---|---|---|']
    for fid, band in cards_spec['每族条数'].items():
        L.append(f"| {fid} | {cards_spec['绑定域表'][fid]} | {cards_spec['绑定子类表'][fid] or '—'} "
                 f"| {band[0]}—{band[1]} | {canon['汇总']['逐族条数'][fid]} |")
    L += ['', f"每条实例字段：{'、'.join(cards_spec['字段'])}；名称长度 {cards_spec['名称长度'][0]}—"
               f"{cards_spec['名称长度'][1]}、卡面正文长度 {cards_spec['卡面正文长度'][0]}—"
               f"{cards_spec['卡面正文长度'][1]}、幅度长度 {cards_spec['幅度长度'][0]}—"
               f"{cards_spec['幅度长度'][1]}、互斥口径最多 {cards_spec['互斥口径条数'][1]} 条；"
               f"禁用字符 {'、'.join(cards_spec['禁用字符'])}。条数带下限 0 表示该族本期未展开。", '',
          f"口径：{canon['卡牌实例']['口径']}", '']
    for k, v in canon['卡牌实例']['禁则'].items():
        L.append(f'- {k}：{v}')
    return chr(10).join(L) + chr(10)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--out-dir', default=None)
    args = parser.parse_args()
    out = Path(args.out_dir) if args.out_dir else ROOT / '数据'
    tags, scenes = build_tags(), build_scenes()
    cards, background_cards, per_family = build_card_instances(tags, scenes)
    by = counts(tags)
    canon = {
        'version': '1.0', 'fictional': True, 'setting_year': SOURCE['setting_year'],
        'currency': SOURCE['currency'], 'currency_name': SOURCE['currency_name'],
        'declaration': '本文件由 工具/build_admission.py 从 岗位准入源表.json＋产业就业源表.json＋卡牌实例源表.json 生成，属派生正典；修改请改源表并重跑生成器与 build_occupations.py，不要手改本文件。逐条职业内容属第6期，逐张卡牌实例的第9期只落容器（规格、字段与 12 个空族块），卡牌正文 0 张、属待 9b／9c 点单项。',
        '阶': SOURCE['阶'], '非阶要求': SOURCE['非阶要求'], '途径': SOURCE['途径'],
        '层级标签绑定': SOURCE['层级标签绑定'],
        '参数': {'持有上限': SOURCE['持有上限'],
                 '全局禁则': SOURCE['全局禁则'], '卡牌效果类型': SOURCE['卡牌效果类型'],
                 '卡牌类别': SOURCE['卡牌类别'], '释放规则': SOURCE['释放规则']},
        '标签': tags, '场景': scenes, '合同类型': SOURCE['合同类型'],
        '准入形态合同过滤': SOURCE['准入形态合同过滤'], '卡牌族': SOURCE['卡牌族'],
        '释放状态': SOURCE['释放状态'], '通用标签分配': common_tag_split(),
        '卡牌实例': {'规格': CARD_SOURCE['规格'], '口径': CARD_SOURCE['口径'],
                     '禁则': CARD_SOURCE['禁则'], '实例': cards, '背景卡': background_cards},
        '汇总': {'标签数': len(tags), '专属标签数': by.get('专属技能', 0), '通用标签数': by.get('通用技能', 0),
                 '资质标签数': by.get('资质', 0), '经历标签数': by.get('经历', 0),
                 '覆盖小类数': len({t['父小类'] for t in tags if t['父小类']}),
                 '场景数': len(scenes), '通用场景数': sum(1 for s in scenes if s['类别'] == '通用'),
                 '行业场景数': sum(1 for s in scenes if s['类别'] == '行业'),
                 '合同类型数': len(SOURCE['合同类型']), '卡牌族数': len(SOURCE['卡牌族']),
                 '能力类族数': sum(1 for f in SOURCE['卡牌族'] if f['类别'] == 'A'),
                 '学习类族数': sum(1 for f in SOURCE['卡牌族'] if f['类别'] == 'B'),
                 '释放状态数': len(SOURCE['释放状态']), '大类数': len(OCC['大类']),
                 '卡牌实例数': len(cards), '逐族条数': per_family,
                 '已展开族数': sum(1 for v in per_family.values() if v),
                 '未展开族数': sum(1 for v in per_family.values() if not v),
                 '背景卡实例数': len(background_cards),
                 '口径': '标签、场景、合同、卡牌族与状态机构成岗位准入字典；卡片只引用 ID，不复述文本。'
                         '四阶的名称与层级映射在本期定义；升到各阶所需的经验月数与每轮卡牌上限已由第4期运行参数落定，'
                         '口径见《运行参数设定》与 `数据/运行参数正典.json`，本字典只引用标签 ID。'},
    }
    (out / '岗位准入总表.md').write_bytes(render_table(canon).encode('utf-8'))
    (out / '岗位准入正典.json').write_bytes(json.dumps(canon, ensure_ascii=False, indent=2).encode('utf-8') + b'\n')
    print(json.dumps(canon['汇总'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
