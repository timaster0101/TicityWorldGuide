# -*- coding: utf-8 -*-
"""产业与就业层闸门的违例自检：把闸门与十四份数据整批复制到临时目录，逐条改坏正典，断言闸门必须判红并给出该条自己的措辞。

闸门只会打印"全绿"，无法自证它抓得住违例；本脚本按三十五条判据反向注入，只操作临时副本，
绝不改动被守护的仓库文件。闸门只读落盘 JSON，因此临时目录里不需要 build_admission.py 与 build_costs.py，
但必须带上 anchors.py——闸门的圈层归属与住所锚都从它取。
第 30 条的对账清单住在手填源表里，所以注入范围除四份正典外还含 产业就业源表.json；其余两份源表与名录仍只读。
第 31 条对账的是产业图层派生件，因此注入范围再加 产业空间图层.json；第 32 条对账职业条目，注入范围再加手填的
职业条目源表.json；第 33 条的救助比例与月数住在手填的 物价生活源表.json，注入范围再加这一份——它的「文件被删除」
用例同样直接删夹具里那一份，用来证救助门禁在缺件时判红而不是空转放行。
第 34 条的三条等式要拿长期习惯卡的中文幅度上限做对照，所以注入范围再加 运行参数源表.json 与 岗位准入源表.json；
它的「文件被删除」用例删的是岗位准入源表那一份，用来证开局等式门禁在缺件时判红。
第 35 条的条数带与总条数带住在手填的 卡牌实例源表.json，注入范围再加这一份；它的 12 例只动 岗位准入正典 的
卡牌实例块（与 产业就业正典 的岗位卡）——带被压低的那种改坏才动源表规格块。
跑法：python 工具/negtest_occupations.py
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ['verify_occupations.py', 'anchors.py']
DATA = ['产业就业正典.json', '产业就业源表.json', '城市空间名录.json',
        '岗位准入正典.json', '岗位准入源表.json',
        '物价与生活正典.json', '物价生活源表.json', '参考房价租金.json',
        '运行参数正典.json', '运行参数源表.json', '产业空间图层.json', '职业条目源表.json',
        '卡牌实例源表.json']
TMP_PREFIX = 'occneg-'


def canon_of(tmp):
    return json.loads((tmp / '数据' / '产业就业正典.json').read_text(encoding='utf-8'))


def first(canon, pred):
    return next(x for x in canon['公司'] if pred(x))


def adm_of(tmp):
    return json.loads((tmp / '数据' / '岗位准入正典.json').read_text(encoding='utf-8'))


def costs_of(tmp):
    return json.loads((tmp / '数据' / '物价与生活正典.json').read_text(encoding='utf-8'))


def params_of(tmp):
    return json.loads((tmp / '数据' / '运行参数正典.json').read_text(encoding='utf-8'))


def source_of(tmp):
    return json.loads((tmp / '数据' / '产业就业源表.json').read_text(encoding='utf-8'))


def layer_of(tmp):
    return json.loads((tmp / '数据' / '产业空间图层.json').read_text(encoding='utf-8'))


def occ_source_of(tmp):
    return json.loads((tmp / '数据' / '职业条目源表.json').read_text(encoding='utf-8'))


def cost_source_of(tmp):
    return json.loads((tmp / '数据' / '物价生活源表.json').read_text(encoding='utf-8'))


def param_source_of(tmp):
    return json.loads((tmp / '数据' / '运行参数源表.json').read_text(encoding='utf-8'))


def adm_source_of(tmp):
    return json.loads((tmp / '数据' / '岗位准入源表.json').read_text(encoding='utf-8'))


def card_source_of(tmp):
    return json.loads((ROOT / '数据' / '卡牌实例源表.json').read_text(encoding='utf-8'))


# 用例改动函数的形参顺序即写入顺序：1 参改产业、2 参加字典、3 参加物价、4 参加运行参数、5 参加手填源表、
# 6 参加产业图层派生件，7 参加职业条目手填源表，8 参加物价生活手填源表，9 参加运行参数手填源表，
# 10 参加岗位准入手填源表，11 参加卡牌实例手填源表；改动函数往对象里塞 DELETE_MARK 即表示「夹具里这一份要删掉」，
# 用来证闸门在缺件时判红而不是空转放行（第 31、33、34 条的文件缺失分支）。
OBJ_NAMES = ['canon', 'adm', 'costs', 'params', 'source', 'layer', 'osrc', 'csrc', 'prsrc', 'asrc', 'ksrc']
DELETE_MARK = '__删除此文件__'
FILES = {'canon': '产业就业正典.json', 'adm': '岗位准入正典.json',
         'costs': '物价与生活正典.json', 'params': '运行参数正典.json',
         'source': '产业就业源表.json', 'layer': '产业空间图层.json',
         'osrc': '职业条目源表.json', 'csrc': '物价生活源表.json',
         'prsrc': '运行参数源表.json', 'asrc': '岗位准入源表.json',
         'ksrc': '卡牌实例源表.json'}


def cards(canon):
    return [x for comp in canon['公司'] for x in comp['岗位卡']]


CARD_TEXT = '这张卡只用来证明闸门抓得住违例，正文本身不作数'
# 合法幅度、生效触发与绑定对象都不写死族名单，一律从 正典的族定义与 规格.绑定域表 现取——
# 总条数带那条要一次摆满 12 族，逐族列名单会漏掉新用到的族。
CARD_BIND_TAG = {'专属技能标签': '专属技能', '资质标签': '资质',
                 '经历标签': '经历', '通用技能标签': '通用技能'}
# 大类与片区住在 产业就业源表 与名录，注入函数拿不到那两份，直接钉各自的第一条真实 id。
CARD_OK_BIND = {'大类': 'A01', '片区': 'D01'}


def card_ok_cap(fam):
    cap = fam['幅度上限']
    return cap if not any(ch.isdigit() for ch in cap) else cap.split('，')[0]


def card_bind_id(a, fid):
    dom = a['卡牌实例']['规格']['绑定域表'][fid]
    if dom == '五维':
        return '智力'
    if dom == '场景':
        return a['场景'][0]['id']
    if dom == '释放状态':
        return a['释放状态'][0]['id']
    if dom in CARD_BIND_TAG:
        sub = a['卡牌实例']['规格']['绑定子类表'].get(fid)
        for t in a['标签']:
            if t['族'] == CARD_BIND_TAG[dom] and (not sub or t['子类'] == sub):
                return t['id']
    return CARD_OK_BIND[dom]


def sync_card_summary(a):
    """第 35 条同时判「每条结构合法」与「派生件和手填真源同源」：注入正文而不同步汇总，
    就会炸出一堆与本题无关的条数红，而负测要证的是自己想动的那一条。"""
    rows = a['卡牌实例']['实例']
    per = {f['id']: sum(1 for r in rows if r['族'] == f['id']) for f in a['卡牌族']}
    a['汇总']['卡牌实例数'] = len(rows)
    a['汇总']['逐族条数'] = per
    a['汇总']['已展开族数'] = sum(1 for v in per.values() if v)
    a['汇总']['未展开族数'] = sum(1 for v in per.values() if not v)
    a['汇总']['背景卡实例数'] = len(a['卡牌实例']['背景卡'])


def add_card_rows(a, ksrc, fid, n, mutate=None):
    """n 条合法实例同时写进手填源表的族块与正典的实例块，行形态照生成器 build_card_instances 搭。
    总条数带随手放宽到 [0, 999]：那一条由 card_total_band_over 单独证，放宽是为了每张卡只炸一处红。"""
    fam = next(f for f in a['卡牌族'] if f['id'] == fid)
    block = next(b for b in ksrc['卡牌族实例'] if b['族'] == fid)
    spec = a['卡牌实例']['规格']
    ksrc['规格']['总条数区间'] = [0, 999]
    tail = []
    for _ in range(n):
        i = len(block['条目']) + 1
        item = {'名称': f'测试{fid[-2:]}卡{i:03d}', '卡面正文': CARD_TEXT,
                '绑定对象': card_bind_id(a, fid), '幅度': card_ok_cap(fam),
                '生效触发': fam['绑定途径'] or '', '互斥口径': []}
        if mutate:
            mutate(item, i)
        block['条目'].append(item)
        row = {'id': f'{fid}-{i:03d}', '族': fid, '族名': fam['名称'], '类别': fam['类别'],
               '绑定域': spec['绑定域表'][fid], '绑定途径': fam['绑定途径'],
               '幅度上限': fam['幅度上限'], '序号': i, '绑定读数': {}}
        row.update(item)
        a['卡牌实例']['实例'].append(row)
        tail.append(row)
    sync_card_summary(a)
    return tail


def add_bg_rows(a, ksrc, n, extra=None):
    """背景卡实例两边一起写：权重与候选数住在 运行参数源表，本表条目只逐张命名与取值。"""
    items = ksrc['背景卡实例']['条目']
    for _ in range(n):
        i = len(items) + 1
        item = {'名称': f'背景测试{i:03d}', '取值区间': [40, 60]}
        if extra:
            item.update(extra)
        items.append(item)
        a['卡牌实例']['背景卡'].append(dict({'id': f'BG-{i:03d}'}, **item))
    sync_card_summary(a)


def cases():
    """返回 (用例名, 改动函数, 期望出现的判红字样)；改动只动四份正典与手填的产业就业源表，
    其余两份源表与名录保持原样。

    形参个数就是注入范围：1 个改产业就业正典，2 个再加岗位准入正典，3 个再加物价正典，
    4 个再加运行参数正典，5 个再加产业就业源表（第 30 条的零消费者声明块只住在源表里，
    要证它抓得住漏登记与空声明，夹具必须能改源表），6 个再加产业空间图层派生件
    （第 31 条对账的是图层与正典，要证它抓得住手改计数与缺件放行，夹具必须能改图层），
    7 个再加职业条目手填源表（第 32 条一半判手填正文、一半判正典派生，两边都得能改）；
    main 按 OBJ_NAMES 的前缀取对象，写完只回写被改的那几份。
    """

    def conservation(c):
        c['公司'][0]['雇员数'] += 1

    def missing_anchor(c):
        anchor = c['公司'][0]['锚点']
        c['公司'] = [x for x in c['公司'] if x['锚点'] != anchor]

    def no_t5(c):
        drop = first(c, lambda x: x['档位'] == 'T5')
        c['公司'].remove(drop)

    def duplicate_t5(c):
        t5 = first(c, lambda x: x['档位'] == 'T5')
        c['公司'].append(dict(t5, id='CORP-X-99'))

    def out_of_band(c):
        row = first(c, lambda x: x['档位'] == 'T3')
        row['雇员数'] = row['雇员数'] + 400

    def over_quota_and_village(c):
        # 挑岗位规模最小的特色村落：它的单公司配额上限必然装不下 T4 的 250 人门槛，占比与落点同时成立。
        reg = json.loads((ROOT / '数据' / '城市空间名录.json').read_text(encoding='utf-8'))['entries']
        village = min((e['id'] for e in reg if e.get('type') == '特色村落' and 'daily_workers' in e),
                      key=lambda z: next(e['daily_workers'] for e in reg if e['id'] == z))
        row = first(c, lambda x: x['锚点'] == village and x['逐家具名'])
        row['档位'], row['雇员数'], row['逐家具名'] = 'T4', 250, True

    def below_red_line(c):
        card = next(x for comp in c['公司'] for x in comp['岗位卡'] if x['岗位层'] == 'LVL1')
        card['月薪带_钛币'][0] = 1

    def flat_coefficient(c):
        c['参数']['层系数']['LVL3'] = c['参数']['层系数']['LVL2']

    def year_out_of_window(c):
        c['行业']['小类'][0]['起始城市年'] = 2080

    def year_drift(c):
        card = first(c, lambda x: x['岗位卡'])['岗位卡'][0]
        card['起始城市年'] = card['起始城市年'] + 3

    def a08_wording(c):
        sub = next(s for s in c['行业']['小类']
                   if s['父大类'] == 'A08' and s['生成岗位卡'])
        sub['名称'] = sub['名称'] + '授信'

    def a08_background_card(c):
        comp = first(c, lambda x: x['大类'] == 'A08')
        comp['岗位卡'][0]['行业小类'] = 'A08-B03'

    def public_posted(c):
        first(c, lambda x: x['大类'] == 'A01')['可招聘'] = True

    def blacklisted_field(c):
        c['公司'][0]['估值'] = '12亿'

    def drone_in_no_fly(c):
        comp = first(c, lambda x: x['锚点'] == 'S02')
        comp['行业小类'], comp['名称'] = 'A15-B03', '云禾植保无人机服务队'

    # —— 第 11 至 16 条（岗位准入字典）——
    def dangling_tag(c, a):
        cards(c)[0]['准入标签'][0][0] = 'SKL-A99-B99-S1'

    def wrong_parent_subclass(c, a):
        card = next(x for x in cards(c) if x['岗位层'] == 'LVL3')
        other = next(s['id'] for s in a['标签']
                     if s['族'] == '专属技能' and s['子类'] == 'S1' and s['父小类'] != card['行业小类'])
        card['准入标签'][0][0] = other

    def missing_advance_tag(c, a):
        victim = next(t for t in a['标签'] if t['族'] == '专属技能' and t['子类'] == 'S2')
        a['标签'].remove(victim)

    def qualification_pushed_by_work(c, a):
        next(t for t in a['标签'] if t['族'] == '资质')['可推进途径'].append('WKS')

    def lvl3_scene_cleared(c, a):
        for x in cards(c):
            if x['岗位层'] == 'LVL3':
                x['关键场景'] = []

    def lvl1_scene_attached(c, a):
        scene = next(s['id'] for s in a['场景'] if s['类别'] == '行业')
        next(x for x in cards(c) if x['岗位层'] == 'LVL1' and not x['关键场景'])['关键场景'] = [scene]

    def contract_set_cleared(c, a):
        next(x for x in cards(c) if x['合同类型'] and len(x['合同类型']) > 1)['合同类型'] = []

    def contract_form_out_of_five(c, a):
        [c for c in a['合同类型'] if c['id'] == 'CTR-04'][0]['用工形态'] = '小时工'

    def card_family_pays_money(c, a):
        a['卡牌族'][0]['效果类型'] = '资金发放'

    def late_post_opens_early(c, a):
        card = next(x for x in cards(c) if x['起始城市年'] > c['setting_year'])
        card['释放状态'] = 'RLS-02'

    def t1_statistic_removed(c):
        row = first(c, lambda x: not x['逐家具名'])
        row['逐家具名'] = True

    def five_t4_in_one_zone(c):
        # 落在 T4 已达上限的那一区，否则加一家也不越界，闸门抓不到这条判据。
        counts = {}
        for x in c['公司']:
            if x['档位'] == 'T4':
                counts[x['锚点']] = counts.get(x['锚点'], 0) + 1
        anchor = max(counts, key=counts.get)
        donor = first(c, lambda x: x['锚点'] == anchor and x['档位'] == 'T4')
        c['公司'].append(dict(donor, id='CORP-X-98'))

    def coefficient_gap(c):
        c['参数']['层系数']['LVL5'] = 5.5

    # —— 第 17 至 20 条（物价与生活成本包）——
    def basket_off_baseline(c, a, s):
        s['篮子']['内湖环'] = round(s['篮子基线_内湖环'] * 1.13, 1)

    def seasonal_view_missing_slot(c, a, s):
        s['季节展示'].pop('SEA-3')

    def clamp_bypassed(c, a, s):
        card = next(x for comp in c['公司'] for x in comp['岗位卡'] if x['红线_钛币']['是否被顶起'])
        card['月薪带_钛币'][0] = card['红线_钛币']['住所四成线']

    def clamp_line_misrecorded(c, a, s):
        card = next(x for comp in c['公司'] for x in comp['岗位卡'] if x['红线_钛币']['是否被顶起'])
        card['红线_钛币']['住所加篮子线'] += 10

    def dangling_category(c, a, s):
        s['品类'][0]['域'] = 'PRD-XXXX'

    def hand_filled_upgrade_price(c, a, s):
        s['品类'][1]['三档基准价']['改善'] = round(s['品类'][1]['三档基准价']['必需'] * 1.9, 1)

    def second_hand_cap_at_one(c, a, s):
        row = next(x for x in s['品类'] if x.get('二手折价上限'))
        row['二手折价上限'] = 1.0

    def recovery_ratio_above_one(c, a, s):
        s['参数']['回收系数'] = 1.5

    def dangling_relief_ref(c, a, s):
        s['品类'][0]['减免归属']['A'] = 'WEL-Z'

    def quota_rounded_up(c, a, s):
        row = s['库存'][0]
        row['兜底配额'] += 1

    def three_house_types(c, a, s):
        for row in s['库存']:
            if row['住房类型ID'] == 'HOU-04':
                row['住房类型ID'] = 'HOU-03'

    def sparse_on_district(c, a, s):
        s['库存'][0]['挂靠人口'] += 10

    def threshold_not_monotonic(c, a, s, p):
        p['参数']['技能']['等级阈值月']['LVL3'] = 6

    def transport_cell_off_formula(c, a, s, p):
        cell = next(x for x in p['交通矩阵'] if x['耗时分钟'] is not None and x['方式'] == 'TR-BUS')
        cell['耗时分钟'] += 5

    def year_table_missing_day(c, a, s, p):
        p['天气年历'].pop(50)

    def personal_cooldown_above_city(c, a, s, p):
        p['参数']['事件']['冷却天']['个人'] = 999

    def round_quota_below_month(c, a, s, p):
        p['参数']['事件']['负面配额']['每轮'] = 1

    # —— 第 15 与 24 条的五维刻度换档（C119：点数一律按跨度反推，不许脱钩）——
    def five_stat_scale_raised_without_points(c, a, s, p):
        p['参数']['技能']['五维刻度'] = [0, 200]

    def card_five_stat_points_inflated(c, a, s, p):
        next(f for f in a['卡牌族'] if f['id'] == 'CRD-A3')['幅度上限'] = '单卡 12 点，同维度累计 20 点'

    def five_stat_floor_decoupled(c, a, s, p):
        p['参数']['技能']['五维退化下限'] = 1

    def five_stat_ratio_key_missing(c, a, s, p):
        p['参数']['技能']['五维微调比例'].pop('同维度累计占跨度上限')

    def five_stat_lower_bound_negative(c, a, s, p):
        p['参数']['技能']['五维刻度'] = [-20, 80]

    # —— 第 26 至 29 条（具名命名）——
    def named_without_name(c):
        first(c, lambda x: x['逐家具名'] and x['档位'] == 'T3')['名称'] = None

    def statistic_row_named(c):
        first(c, lambda x: not x['逐家具名'])['名称'] = '湖政恒茂政务社'

    def duplicated_name(c):
        rows = [x for x in c['公司'] if x['逐家具名'] and x['档位'] == 'T3']
        rows[1]['名称'] = rows[0]['名称']

    def hand_edited_segment(c):
        row = first(c, lambda x: x['逐家具名'] and x['档位'] == 'T3')
        row['名称'] = row['名称'][:-1] + '行'

    def apex_off_source(c):
        row = first(c, lambda x: x['档位'] == 'T5')
        row['名称'] = row['名称'].replace('集团', '公司')

    def subclass_row_dropped(c):
        # 卡片一并删掉，否则 adm 侧按小类取准入形态会 KeyError，判红措辞就变成崩溃而非门禁。
        counts = {}
        for comp in c['公司']:
            for card in comp['岗位卡']:
                counts[card['行业小类']] = counts.get(card['行业小类'], 0) + 1
        victim = min(counts, key=counts.get)
        c['行业']['小类'] = [s for s in c['行业']['小类'] if s['id'] != victim]
        for comp in c['公司']:
            comp['岗位卡'] = [x for x in comp['岗位卡'] if x['行业小类'] != victim]

    def group_over_pool(c):
        # 把 F005 的 T2 组挤到 81 家：字号池只有 80 个词，组内必然绕回，两家的名称即撞车。
        donors = [x for x in c['公司'] if x['锚点'] == 'F005' and x['档位'] == 'T2']
        for k in range(10):
            c['公司'].append(dict(donors[0], id=f'CORP-F005-X{k:02d}'))

    def banned_word_in_name(c):
        row = first(c, lambda x: x['逐家具名'] and x['档位'] == 'T3')
        row['名称'] = row['名称'][:4] + '股权' + row['名称'][6:]

    def name_out_of_length_band(c):
        row = first(c, lambda x: x['逐家具名'] and x['档位'] == 'T3')
        row['名称'] = row['名称'][:4]

    def apex_without_tier_suffix(c):
        row = first(c, lambda x: x['档位'] == 'T5')
        row['名称'] = row['名称'][:-2] + '公司'

    # —— 第 30 条（零消费者对账）——
    def background_flag_drifted(c):
        row = next(s for s in c['行业']['小类'] if s['id'] == 'A08-B03')
        row['生成岗位卡'] = True

    def subclass_left_without_company(c):
        # 把卡片最少的那个小类整体并进同大类、同起始年、同准入形态的兄弟小类：
        # 其余判据的取值都不受影响，只有第 30 条会报「声明可生成岗位卡却无一家公司落它」。
        counts = {}
        for comp in c['公司']:
            for card in comp['岗位卡']:
                counts[card['行业小类']] = counts.get(card['行业小类'], 0) + 1
        victim = min(counts, key=counts.get)
        row = next(s for s in c['行业']['小类'] if s['id'] == victim)
        sibling = next(s for s in c['行业']['小类']
                       if s['父大类'] == row['父大类'] and s['id'] != victim and s['生成岗位卡']
                       and s['起始城市年'] == row['起始城市年'] and s['准入形态'] == row['准入形态'])
        for comp in c['公司']:
            for card in comp['岗位卡']:
                if card['行业小类'] == victim:
                    card['行业小类'] = sibling['id']
                    card['id'] = card['id'].replace(victim, sibling['id'])
                    card['准入标签'] = [[t.replace(victim, sibling['id']), lv] for t, lv in card['准入标签']]

    def declared_skill_absent_from_dictionary(c, a, s, p, src):
        src['零消费者']['上限截断连带标签'].append('SKL-Q-A99')

    def declared_general_skill_unregistered(c, a, s, p, src):
        src['零消费者']['通用技能标签'].remove('SKL-C07')

    def declared_scene_already_used(c, a, s, p, src):
        src['零消费者']['通用场景'].append(next(x['关键场景'][0]
                                                for comp in c['公司'] for x in comp['岗位卡'] if x['关键场景']))

    def cap_class_not_declared(c, a, s, p, src):
        src['零消费者']['上限截断大类'] = {}

    def zero_block_dropped(c, a, s, p, src):
        src.pop('零消费者')

    # —— 第 31 条（产业图层对账）——
    # 六个形参＝再注入图层派生件；七个形参＝最后那个只读参数是夹具目录本身，用于删文件。
    def layer_anchor_dropped(c, a, s, p, src, lay):
        lay['锚点'] = [r for r in lay['锚点'] if r['锚点'] != c['公司'][0]['锚点']]

    def layer_anchor_invented(c, a, s, p, src, lay):
        extra = dict(lay['锚点'][0])
        extra['锚点'] = 'F099'
        lay['锚点'].append(extra)

    def layer_employees_drifted(c, a, s, p, src, lay):
        lay['锚点'][0]['雇员数'] += 1

    def layer_center_drifted(c, a, s, p, src, lay):
        lay['锚点'][0]['center_km'][1] += 0.5

    def layer_dominant_class_drifted(c, a, s, p, src, lay):
        row = next(r for r in lay['锚点'] if len(r['大类分布']) > 1)
        row['主导大类'] = next(i for i in sorted(row['大类分布']) if i != row['主导大类'])

    def layer_class_count_drifted(c, a, s, p, src, lay):
        lay['大类'][0]['公司数'] += 1

    def layer_class_landing_drifted(c, a, s, p, src, lay):
        row = next(r for r in lay['大类'] if r['落点数'] > 1)
        row['落点'] = row['落点'][:-1]

    def layer_ring_total_drifted(c, a, s, p, src, lay):
        lay['圈层'][0]['雇员数'] += 10

    def layer_summary_drifted(c, a, s, p, src, lay):
        lay['汇总']['雇员总数'] += 1

    def layer_radius_formula_drifted(c, a, s, p, src, lay):
        lay['锚点'][0]['气泡半径km'] = round(lay['锚点'][0]['气泡半径km'] + 0.1, 3)

    def layer_distribution_drifted(c, a, s, p, src, lay):
        row = next(r for r in lay['锚点'] if len(r['大类分布']) > 1)
        cid = sorted(row['大类分布'])[0]
        row['大类分布'][cid]['岗位卡数'] += 1

    def layer_block_dropped(c, a, s, p, src, lay):
        lay.pop('锚点')

    # —— 第 32 条（职业条目对账）——
    def occ_name_duplicated(c):
        c['职业条目'][1]['名称'] = c['职业条目'][0]['名称']

    def occ_entry_missing_from_canon(c):
        c['职业条目'].pop(0)

    def occ_id_sequence_drifted(c):
        c['职业条目'][1]['id'] = c['职业条目'][1]['id'][:-2] + '99'

    def occ_levels_drifted(c):
        row = next(e for e in c['职业条目'] if len(e['适用层']) > 1)
        row['适用层'] = row['适用层'][:1]

    def occ_quota_drifted(c):
        c['职业条目'][0]['覆盖名额'] += 1

    def occ_summary_drifted(c):
        c['汇总']['职业条目数'] += 1

    def occ_banned_word_in_text(c):
        row = next(e for e in c['职业条目'] if not e['小类'].startswith('A08'))
        row['职责'] = row['职责'] + '并做估值'

    def occ_drone_word_outside_whitelist(c):
        row = next(e for e in c['职业条目'] if e['小类'] not in ('A15-B03', 'A15-B05', 'A17-B05', 'A17-B08'))
        row['职责'] = row['职责'] + '含无人机作业'

    def occ_responsibility_too_short(c):
        c['职业条目'][0]['职责'] = '收货'

    def occ_subclass_row_dropped(c, a, s, p, src, lay, o):
        o['小类'] = o['小类'][1:]

    def occ_background_row_added(c, a, s, p, src, lay, o):
        o['小类'].append({'小类': 'A08-B03', '职业': [dict(x) for x in o['小类'][0]['职业']]})

    def occ_per_class_count_drifted(c, a, s, p, src, lay, o):
        # 正典同步长出第 6 条，让总量与展开数仍然对齐，判红只剩「越出每类」这一条变量。
        row = next(r for r in o['小类'] if len(r['职业']) == 5)
        extra = dict(row['职业'][0])
        extra['名称'] = '负测追加条目'
        row['职业'].append(extra)
        sid = row['小类']
        ref = next(e for e in c['职业条目'] if e['小类'] == sid)
        grown = dict(ref, id=f'OCC-{sid}-06', 名称=extra['名称'])
        c['职业条目'].append(grown)
        c['汇总']['职业条目数'] = len(c['职业条目'])

    def occ_spec_key_dropped(c, a, s, p, src, lay, o):
        o['规格'].pop('每类条数')

    def occ_source_file_removed(c, a, s, p, src, lay, o):
        o.clear()
        o[DELETE_MARK] = True

    def layer_file_removed(c, a, s, p, src, lay):
        # 打上删除标记，由 main 在回写阶段把夹具里的那一份 unlink 掉，而不是把内存对象再写回去。
        lay.clear()
        lay[DELETE_MARK] = True

    # ---- 第 33 条 失业救助对账 ----
    # 三列金额的复算公式同时住在源表与正典里，只改源表会让「!= 复算」顺带判红，看不出被测的那一条。
    # rederive 把正典三列与参数副本按源表重算一遍，让每条注入只剩它自己要证的那一处红。
    def rederive(costs_obj, cs):
        r = cs['参数']['失业救助']
        costs_obj['参数']['失业救助'] = json.loads(json.dumps(r, ensure_ascii=False))
        for ring, basket in costs_obj['篮子'].items():
            full = round(basket * r['全额比例'], 1)
            dec = round(basket * r['递减比例'], 1)
            w = costs_obj['保障'][ring]
            w['失业救助_全额月_钛币'] = full
            w['失业救助_递减月_钛币'] = dec
            w['失业救助_连发总额_钛币'] = round(full * r['全额月数'] + dec * r['递减月数'], 1)

    def relief_block_removed(c, a, s, p, src, lay, o, cs):
        del cs['参数']['失业救助']

    def relief_source_file_removed(c, a, s, p, src, lay, o, cs):
        cs.clear()
        cs[DELETE_MARK] = True

    def relief_ratio_flat(c, a, s, p, src, lay, o, cs):
        cs['参数']['失业救助']['全额比例'] = cs['参数']['失业救助']['递减比例']

    def relief_months_break(c, a, s, p, src, lay, o, cs):
        cs['参数']['失业救助']['递减月数'] = 3

    def relief_grace_decoupled(c, a, s, p, src, lay, o, cs):
        r = cs['参数']['失业救助']
        r['全额月数'], r['递减月数'] = 3, 3

    def relief_recheck_unaligned(c, a, s, p, src, lay, o, cs):
        cs['参数']['失业救助']['复核月数'] = 4

    def relief_reapply_gap_zero(c, a, s, p, src, lay, o, cs):
        cs['参数']['失业救助']['再申请间隔月数'] = 0

    def relief_multiplied_by_household(c, a, s, p, src, lay, o, cs):
        ring = cs['参数']['圈层顺序'][0]
        scale = cs['参数']['户均规模']
        w = s['保障'][ring]
        w['失业救助_全额月_钛币'] = round(s['篮子'][ring] * cs['参数']['失业救助']['全额比例'] * scale, 1)

    def relief_decline_over_median(c, a, s, p, src, lay, o, cs):
        cs['参数']['失业救助']['全额比例'], cs['参数']['失业救助']['递减比例'] = 0.9, 0.8
        rederive(s, cs)

    def relief_full_over_lvl1(c, a, s, p, src, lay, o, cs):
        # 只把全城最低的那一条 LVL1 生效线压到 1 钛币：改一张卡，救助侧与「硬下限钳」各出一行，
        # 落在闸门 40 行的打印窗口内；改全部 LVL1 会把窗口占满，反证不了救助这条。
        card = min((x for comp in c['公司'] for x in comp['岗位卡'] if x['岗位层'] == 'LVL1'),
                   key=lambda x: x['红线_钛币']['住所加篮子线'])
        card['红线_钛币']['住所加篮子线'] = 1

    def relief_halt_word_in_text(c, a, s, p, src, lay, o, cs):
        cs['参数']['失业救助']['发放条件'][0] += '，金额仍待确认'

    def relief_text_too_short(c, a, s, p, src, lay, o, cs):
        cs['参数']['失业救助']['禁则'][2] = '不许漫天要价'

    def relief_summary_count_drift(c, a, s, p, src, lay, o, cs):
        s['汇总']['救助停发情形数'] = 3

    def relief_negation_missing(c, a, s, p, src, lay, o, cs):
        r = cs['参数']['失业救助']
        r['口径'] = '失业救助是按圈层折算的现金发放，逐月一次入账并记流水，按户内就业人数分摊到户。'
        r['发放条件'][2] = '按户内就业人数分摊，救助金额随户数上调，不逐笔留痕'

    def relief_group_missing(c, a, s, p, src, lay, o, cs):
        cs['参数']['失业救助']['禁则'][1] = '救助不得改动品类价、服务价与交易用途，与价物表互不写回'

    def relief_canon_not_rebuilt(c, a, s, p, src, lay, o, cs):
        del s['参数']['失业救助']

    def relief_canon_param_drift(c, a, s, p, src, lay, o, cs):
        s['参数']['失业救助']['全额比例'] = 0.45

    # ---- 第 34 条 五维开局对账 ----
    # 三条等式横跨运行参数源表、岗位准入源表与两份正典，所以注入位把第九、第十个对象（两份源表）也用上了。
    def dim_block_missing(c, a, s, p, src, lay, o, cs, pr, asrc):
        del pr['参数']['技能']['五维开局']

    def dim_admission_file_removed(c, a, s, p, src, lay, o, cs, pr, asrc):
        asrc.clear()
        asrc[DELETE_MARK] = True

    def dim_crd_amount_drift(c, a, s, p, src, lay, o, cs, pr, asrc):
        next(x for x in asrc['卡牌族'] if x['id'] == 'CRD-A3')['幅度上限'] = '单卡 12 点，同维度累计 24 点'

    def dim_crd_dims_drift(c, a, s, p, src, lay, o, cs, pr, asrc):
        next(x for x in asrc['卡牌族'] if x['id'] == 'CRD-A3')['效果对象'] = '智力、情商、体力、韧性、领导力'

    def dim_crd_missing(c, a, s, p, src, lay, o, cs, pr, asrc):
        asrc['卡牌族'] = [x for x in asrc['卡牌族'] if x['id'] != 'CRD-A3']

    def dim_single_ratio_drift(c, a, s, p, src, lay, o, cs, pr, asrc):
        pr['参数']['技能']['背景卡权重']['单类影响占跨度'] = 0.15

    def dim_cum_ratio_drift(c, a, s, p, src, lay, o, cs, pr, asrc):
        pr['参数']['技能']['背景卡权重']['同维度累计影响占跨度'] = 0.25

    def dim_weight_sum_drift(c, a, s, p, src, lay, o, cs, pr, asrc):
        pr['参数']['技能']['背景卡权重']['类别'][4]['权重'] = 5

    def dim_combo_drift(c, a, s, p, src, lay, o, cs, pr, asrc):
        pr['参数']['技能']['背景卡权重']['类别'][0]['候选数'] = 7

    def dim_prefix_collision(c, a, s, p, src, lay, o, cs, pr, asrc):
        asrc['卡牌族'].append({'id': 'BG-FAM', '名称': '家庭结构', '类别': 'A', '效果类型': '五维微调'})

    def dim_holding_prefix(c, a, s, p, src, lay, o, cs, pr, asrc):
        asrc['持有上限']['BG-FAM'] = 2

    def dim_card_field_leak(c, a, s, p, src, lay, o, cs, pr, asrc):
        c['公司'][0]['岗位卡'][0]['开局区间'] = [30, 70]

    def dim_median_offscale(c, a, s, p, src, lay, o, cs, pr, asrc):
        pr['参数']['技能']['五维开局']['中位'] = 55

    def dim_rare_line_below(c, a, s, p, src, lay, o, cs, pr, asrc):
        pr['参数']['技能']['五维开局']['满值罕见线'] = 60

    def dim_id_prefix_bad(c, a, s, p, src, lay, o, cs, pr, asrc):
        pr['参数']['技能']['背景卡权重']['类别'][0]['id'] = 'FAM'

    def dim_halt_word(c, a, s, p, src, lay, o, cs, pr, asrc):
        pr['参数']['技能']['背景卡权重']['口径'] += '，候选池细则仍待确认'

    def dim_group_missing(c, a, s, p, src, lay, o, cs, pr, asrc):
        pr['参数']['技能']['背景卡权重']['禁则'][0] = '更换候选时按新一轮重新随机五个维度，逐维重新落点'

    def dim_canon_band_drift(c, a, s, p, src, lay, o, cs, pr, asrc):
        p['五维开局']['开局区间'] = [25, 75]

    def dim_canon_block_missing(c, a, s, p, src, lay, o, cs, pr, asrc):
        del p['五维开局']

    def dim_canon_param_drift(c, a, s, p, src, lay, o, cs, pr, asrc):
        del p['参数']['技能']['背景卡权重']

    def dim_canon_prohibition_count(c, a, s, p, src, lay, o, cs, pr, asrc):
        p['五维开局']['禁则数'] = 2

    def card_wrong_bind(c, a, s, p, src, lay, o, cs, pr, asrc, ksrc):
        add_card_rows(a, ksrc, 'CRD-A1', 1, lambda r, i: r.update({'绑定对象': 'SKL-9999-S1'}))

    def card_over_amplitude(c, a, s, p, src, lay, o, cs, pr, asrc, ksrc):
        add_card_rows(a, ksrc, 'CRD-A3', 1, lambda r, i: r.update({'幅度': '单卡 15 点'}))

    def card_authority_tier(c, a, s, p, src, lay, o, cs, pr, asrc, ksrc):
        add_card_rows(a, ksrc, 'CRD-A1', 1, lambda r, i: r.update({'幅度': '阶提升 1 触及权威'}))

    def card_wrong_path(c, a, s, p, src, lay, o, cs, pr, asrc, ksrc):
        add_card_rows(a, ksrc, 'CRD-B3', 1, lambda r, i: r.update({'生效触发': 'LEV'}))

    def card_name_duplicated(c, a, s, p, src, lay, o, cs, pr, asrc, ksrc):
        def same_name(r, i):
            r['名称'] = '测试卡牌001'
        add_card_rows(a, ksrc, 'CRD-A7', 2, same_name)

    def card_family_band_over(c, a, s, p, src, lay, o, cs, pr, asrc, ksrc):
        ksrc['规格']['每族条数']['CRD-A3'] = [0, 1]
        add_card_rows(a, ksrc, 'CRD-A3', 2)

    def card_total_band_over(c, a, s, p, src, lay, o, cs, pr, asrc, ksrc):
        """总条数带只在十二族全展开后生效，所以先给 12 族各摆 1 条把「全展开」凑出来
        （逐族条数带是 [0, N]，1 条不炸），再把总带收到 2—3 让 12 条越出上界。"""
        for fam in a['卡牌族']:
            add_card_rows(a, ksrc, fam['id'], 1)
        ksrc['规格']['总条数区间'] = [2, 3]

    def card_exclusive_cycle3(c, a, s, p, src, lay, o, cs, pr, asrc, ksrc):
        ids = ['CRD-A7-001', 'CRD-A7-002', 'CRD-A7-003']

        def all_others(r, i):
            r['互斥口径'] = [x for x in ids if x != f'CRD-A7-{i:03d}']
        add_card_rows(a, ksrc, 'CRD-A7', 3, all_others)

    def card_crd_in_job_card(c, a):
        c['公司'][0]['岗位卡'][0]['卡牌实例'] = 'CRD-A1-001'

    def card_bg_weight_overwrite(c, a, s, p, src, lay, o, cs, pr, asrc, ksrc):
        add_bg_rows(a, ksrc, 24, {'权重': 25})

    def card_bg_count_mismatch(c, a, s, p, src, lay, o, cs, pr, asrc, ksrc):
        add_bg_rows(a, ksrc, 1)

    def card_missing_field(c, a, s, p, src, lay, o, cs, pr, asrc, ksrc):
        add_card_rows(a, ksrc, 'CRD-A2', 1, lambda r, i: r.pop('幅度'))

    return [
        ('逐区守恒人数被改', conservation, '守恒'),
        ('整区公司缺失', missing_anchor, '守恒'),
        ('T5 少一家', no_t5, 'T5'),
        ('T5 同大类两家', duplicate_t5, 'T5'),
        ('档位越界', out_of_band, '档位区间'),
        ('超所在区配额且落特色村落', over_quota_and_village, '占比'),
        ('T1 统计条被改成具名', t1_statistic_removed, 'T1统计口径'),
        ('每区第五家 T4', five_t4_in_one_zone, 'T4:'),
        ('LVL1 跌破住所红线', below_red_line, '住所覆盖红线'),
        ('层系数非单调', flat_coefficient, '层系数非单调'),
        ('层系数顶端超 5 倍', coefficient_gap, '层系数: LVL5/LVL1'),
        ('起始年越窗', year_out_of_window, '起始年越窗'),
        ('卡片起始年漂移', year_drift, '起始年漂移'),
        ('A08 职责关键词', a08_wording, 'A08禁则'),
        ('A08 背景小类生成卡', a08_background_card, 'A08禁则'),
        ('公职岗位进招募池', public_posted, '公职边界'),
        ('字段黑名单', blacklisted_field, '字段黑名单'),
        ('无人机落进净空禁区', drone_in_no_fly, '无人机禁空'),
        ('卡片引用不存在的标签', dangling_tag, '引用完整性'),
        ('标签父小类与卡片小类不一致', wrong_parent_subclass, '引用完整性'),
        ('小类缺进阶标签', missing_advance_tag, '标签体系'),
        ('资质标签被工作途径推进', qualification_pushed_by_work, '标签体系'),
        ('LVL3 卡片场景清空', lvl3_scene_cleared, '关键场景'),
        ('LVL1 卡片挂上场景', lvl1_scene_attached, '关键场景'),
        ('卡片合同集清空', contract_set_cleared, '合同矩阵'),
        ('合同用工形态跳出五值', contract_form_out_of_five, '合同矩阵'),
        ('卡牌效果越界发钱', card_family_pays_money, '卡牌边界'),
        ('晚起始卡提前开放', late_post_opens_early, '释放流程'),
        ('篮子值不等于基线乘系数', basket_off_baseline, '未由基线×系数得出'),
        ('季节展示缺档', seasonal_view_missing_slot, '季节展示缺档'),
        ('被顶起卡退回住所四成线', clamp_bypassed, '下界'),
        ('卡上记录的生效线与复算不符', clamp_line_misrecorded, '记录的生效线'),
        ('品类引用悬空的域', dangling_category, '品类引用悬空'),
        ('改善价手填不派生', hand_filled_upgrade_price, '改善或奢侈价不是由必需价乘派生系数得出'),
        ('二手上限填成 1.0', second_hand_cap_at_one, '二手上限越界'),
        ('回收比例越出区间', recovery_ratio_above_one, '维修或回收比例越出 (0,1)'),
        ('减免归属指向不存在的档位', dangling_relief_ref, '减免归属悬空'),
        ('兜底配额手改一户', quota_rounded_up, '配额取整不符'),
        ('住房类型只剩三类', three_house_types, '住房类型数'),
        ('散居挂靠落到片区行', sparse_on_district, '片区行带了散居挂靠'),
        ('等级阈值改成非单调', threshold_not_monotonic, '等级阈值非严格递增'),
        ('手改一格交通耗时使其与公式不符', transport_cell_off_formula, '交通矩阵'),
        ('删掉年历一格使其不等于游程展开', year_table_missing_day, '天气年历: 正典'),
        ('个人冷却改成大于城市冷却', personal_cooldown_above_city, '冷却天须随级别单调不减'),
        ('每轮负面配额改成小于每自然月配额', round_quota_below_month, '每轮负面配额不得小于每自然月配额'),
        ('五维刻度改成 0—200 但卡牌点数没跟着重算', five_stat_scale_raised_without_points, '卡牌边界: CRD-A3 五维点数'),
        ('长期习惯卡的五维点数被手改大', card_five_stat_points_inflated, '不等于刻度跨度 100 反推的 [10, 20]'),
        ('五维退化下限与跨度反推值脱钩', five_stat_floor_decoupled, '技能阈值: 五维退化下限'),
        ('五维微调比例块少一个键', five_stat_ratio_key_missing, '五维微调比例 缺键'),
        ('五维刻度下界改成负数', five_stat_lower_bound_negative, '下界为负或倒挂'),
        ('具名公司的名称被清空', named_without_name, '具名命名'),
        ('T1 统计条带上名称', statistic_row_named, '具名命名'),
        ('两家非顶端公司同名', duplicated_name, '具名命名'),
        ('非顶端名称的某一段被手改', hand_edited_segment, '名称回查'),
        ('顶端名称偏离源表', apex_off_source, '顶端名称'),
        ('正典少一条小类使词根池不齐', subclass_row_dropped, '命名池'),
        ('同组挤进十家使字号绕回', group_over_pool, '短于最大'),
        ('名称里出现禁词', banned_word_in_name, '名称禁则'),
        ('名称短于源表长度区间', name_out_of_length_band, '名称禁则'),
        ('顶端名称未以档位后缀收尾', apex_without_tier_suffix, '名称禁则'),
        ('背景小类被改成可生成岗位卡', background_flag_drifted, '登记为背景小类却声明可生成岗位卡'),
        ('可生成岗位卡的小类被挪空', subclass_left_without_company, '无一张岗位卡落它'),
        ('声明的连带标签不在字典里', declared_skill_absent_from_dictionary, '在字典中不存在'),
        ('一条通用技能没登记为零消费者', declared_general_skill_unregistered, '无卡片引用却未登记为零消费者'),
        ('登记的零消费者场景其实已被引用', declared_scene_already_used, '登记为零消费者却已被卡片引用'),
        ('设了上限的大类没登记截断', cap_class_not_declared, '截断大类与源表'),
        ('零消费者声明块被删空', zero_block_dropped, '不得留空'),
        ('图层少了正典有的锚点', layer_anchor_dropped, '产业图层对账: 锚点集合与正典不一致'),
        ('图层多出正典没有的锚点', layer_anchor_invented, '产业图层对账: 锚点集合与正典不一致'),
        ('图层雇员数被手改', layer_employees_drifted, '产业图层对账:'),
        ('图层坐标偏离名录', layer_center_drifted, '坐标与名录不符'),
        ('图层主导大类改上次大类', layer_dominant_class_drifted, '主导大类'),
        ('图层大类公司数被手改', layer_class_count_drifted, '公司数 图层'),
        ('图层大类落点清单被截短', layer_class_landing_drifted, '落点'),
        ('图层圈层小计被手改', layer_ring_total_drifted, '圈层'),
        ('图层汇总雇员总数被手改', layer_summary_drifted, '汇总 雇员总数'),
        ('图层气泡半径偏离面积公式', layer_radius_formula_drifted, '不符面积公式'),
        ('图层锚点内大类分布被手改', layer_distribution_drifted, '分布 图层'),
        ('图层缺锚点一节', layer_block_dropped, "['锚点']"),
        ('图层数据文件被删除', layer_file_removed, '不得因无图层可查而空转判绿'),
        ('两条职业条目同名', occ_name_duplicated, '名称重复'),
        ('正典少一条职业条目', occ_entry_missing_from_canon, '未进正典'),
        ('职业条目组内序被改', occ_id_sequence_drifted, '与源表展开不符'),
        ('职业条目适用层被改窄', occ_levels_drifted, '字段 适用层 与重算值不符'),
        ('职业条目覆盖名额被改', occ_quota_drifted, '字段 覆盖名额 与重算值不符'),
        ('汇总职业条目数被改', occ_summary_drifted, '汇总 职业条目数'),
        ('职业条目正文混进估值口径', occ_banned_word_in_text, '出现禁词「估值」'),
        ('非低空小类的条目出现无人机', occ_drone_word_outside_whitelist, '出现禁词「无人机」'),
        ('职业条目职责短于长度带', occ_responsibility_too_short, '职责长度'),
        ('一个可出卡小类的条目行被删', occ_subclass_row_dropped, '没有任何职业条目'),
        ('背景在册小类出了条目行', occ_background_row_added, '不在可出卡小类内却出了条目'),
        ('某小类条目数超出每类上限', occ_per_class_count_drifted, '越出每类'),
        ('规格块少了每类条数', occ_spec_key_dropped, '规格缺'),
        ('职业条目源表文件被删除', occ_source_file_removed, '不得因无条目可查而空转判绿'),
        ('失业救助源表缺块', relief_block_removed, '缺块时门禁不得空转判绿'),
        ('失业救助源表文件被删除', relief_source_file_removed, '救助门禁不得因无源表可查而空转判绿'),
        ('全额与递减比例同档', relief_ratio_flat, '比例档序须'),
        ('全额月加递减月不等于最长连发', relief_months_break, '!= 最长连发'),
        ('全额月数脱离欠费宽限', relief_grace_decoupled, '!= 欠费宽限月数'),
        ('复核月数不能整除连发', relief_recheck_unaligned, '不能被复核'),
        ('再申请间隔归零', relief_reapply_gap_zero, '再申请间隔'),
        ('救助额乘了户均规模', relief_multiplied_by_household, '不得乘户均规模'),
        ('递减月高过住所锚中位', relief_decline_over_median, '≥ 住所锚中位'),
        ('全额月高过最低生效线', relief_full_over_lvl1, '≥ 本圈层最低 LVL1 生效线'),
        ('发放条件写成待确认', relief_halt_word_in_text, '出现中断类许可词'),
        ('禁则短到读不出口径', relief_text_too_short, '短于 12 字'),
        ('汇总救助条数与源表不符', relief_summary_count_drift, '!= 源表'),
        ('口径丢了不乘户均的否定式', relief_negation_missing, '「不乘户均规模」否定式'),
        ('禁则少了价物减免一条', relief_group_missing, '未覆盖关键词组'),
        ('正典没带上救助参数块', relief_canon_not_rebuilt, '正典参数未带失业救助块'),
        ('正典救助比例被手改', relief_canon_param_drift, '正典参数块与源表不一致'),
        ('五维开局源表缺块', dim_block_missing, '五维开局 或 背景卡权重'),
        ('岗位准入源表被删除', dim_admission_file_removed, '开局等式门禁不得因无源表可查而空转判绿'),
        ('长期习惯卡幅度上限被手改', dim_crd_amount_drift, 'CRD-A3 幅度上限'),
        ('长期习惯卡效果对象少一维', dim_crd_dims_drift, '效果对象与源表 维度 五档不齐'),
        ('长期习惯卡整条删除', dim_crd_missing, '岗位准入源表没有 CRD-A3'),
        ('背景卡单类占比脱离微调比例', dim_single_ratio_drift, '单类影响占跨度与 五维微调比例'),
        ('背景卡累计占比脱离微调比例', dim_cum_ratio_drift, '同维度累计影响占跨度与 五维微调比例'),
        ('背景卡权重和不为 100', dim_weight_sum_drift, '!= 100'),
        ('候选数改动使组合数不符', dim_combo_drift, '候选组合数'),
        ('背景卡前缀挤进卡牌族', dim_prefix_collision, '背景卡不是第 13 个卡牌族'),
        ('背景卡前缀挤进持有上限', dim_holding_prefix, 'BG- 前缀出现在持有上限的键里'),
        ('开局区间写进岗位卡', dim_card_field_leak, '岗位卡里出现开局侧字段'),
        ('中位脱离刻度反推', dim_median_offscale, '中位 55'),
        ('满值罕见线低过开局上界', dim_rare_line_below, '满值罕见线 60'),
        ('类别 id 丢了 BG- 前缀', dim_id_prefix_bad, '须唯一且全部 BG- 前缀'),
        ('开局文本写成待确认', dim_halt_word, '开局文本'),
        ('卡牌绑到字典外的标签', card_wrong_bind, '不在标签字典内'),
        ('长期习惯卡的点数越出单卡上限', card_over_amplitude, '越出本族上限'),
        ('技艺印记把标签推到权威阶', card_authority_tier, '推到「权威」阶'),
        ('岗位实训卡的生效触发写成 LEV', card_wrong_path, '不等于本族绑定途径 WKS'),
        ('两张卡牌同名', card_name_duplicated, '名称重复'),
        ('单族条数越出源表声明带', card_family_band_over, '越出声明带 0—1'),
        ('卡牌实例总数越出总条数带', card_total_band_over, '越出总条数带 2—3'),
        ('互斥口径结出三元环', card_exclusive_cycle3, '越出同族持有上限 2 张'),
        ('岗位卡侧新增 CRD- 引用', card_crd_in_job_card, '岗位卡侧出现 CRD- 引用'),
        ('背景卡条目覆写权重', card_bg_weight_overwrite, '本表不得覆写'),
        ('背景卡条数与规格声明不符', card_bg_count_mismatch, '与规格声明 24 不符'),
        ('卡牌实例少了字段', card_missing_field, '缺字段'),
        ('背景卡禁则少了不重抽一条', dim_group_missing, '背景卡禁则未覆盖关键词组'),
        ('正典开局区间被手改', dim_canon_band_drift, '正典开局区间'),
        ('正典缺开局派生块', dim_canon_block_missing, '正典缺派生块 五维开局'),
        ('正典参数块与源表脱节', dim_canon_param_drift, '正典参数块与运行参数源表不一致'),
        ('正典禁则数与源表不符', dim_canon_prohibition_count, '禁则数 2'),
    ]


def _arity(fn):
    import inspect
    return len(inspect.signature(fn).parameters)


def run_gate(tmp):
    r = subprocess.run([sys.executable, str(tmp / '工具' / 'verify_occupations.py')],
                       cwd=tmp, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def main():
    results, failures = [], []
    absent = [f for f in DATA if not (ROOT / '数据' / f).exists()]
    if absent:
        raise SystemExit(f'仓库缺少 {absent}：违例夹具按当前仓库文件搭造，先跑全链派生器再自检')
    for name, mutate, expected in cases():
        tmp = Path(tempfile.mkdtemp(prefix=TMP_PREFIX))
        try:
            (tmp / '工具').mkdir()
            (tmp / '数据').mkdir()
            for f in TOOLS:
                shutil.copy2(ROOT / '工具' / f, tmp / '工具' / f)
            for f in DATA:
                shutil.copy2(ROOT / '数据' / f, tmp / '数据' / f)
            rc0, _ = run_gate(tmp)
            objs = {'canon': canon_of(tmp), 'adm': adm_of(tmp),
                    'costs': costs_of(tmp), 'params': params_of(tmp), 'source': source_of(tmp),
                    'layer': layer_of(tmp), 'osrc': occ_source_of(tmp),
                    'csrc': cost_source_of(tmp), 'prsrc': param_source_of(tmp),
                    'asrc': adm_source_of(tmp), 'ksrc': card_source_of(tmp)}
            names = OBJ_NAMES[:_arity(mutate)]
            mutate(*[objs[k] for k in names])
            payload = [(tmp / '数据' / FILES[k], objs[k]) for k in names]
            for path, obj in payload:
                if obj.get(DELETE_MARK):
                    path.unlink()
                    continue
                path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
            rc, out = run_gate(tmp)
            red = rc != 0 and expected in out
            ok = rc0 == 0
            results.append(dict(case=name, rc=rc, red=red, clean_before=ok))
            print(('OK ' if red and ok else '!! ') + f'{name}：夹具原样 rc={rc0}，注入后 rc={rc}，期望字样「{expected}」')
            if not red or not ok:
                failures.append(name)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    leftover = [p for p in Path(tempfile.gettempdir()).glob(TMP_PREFIX + '*') if p.is_dir()]
    print(json.dumps(dict(cases=len(results), red=len(results) - len(failures),
                          not_red=len(failures), fixture_leftover=len(leftover)), ensure_ascii=False))
    if failures or leftover:
        sys.exit(1)
    print(f'产业就业闸门违例自检通过：{len(results)} 个违例全部判红且措辞对得上，夹具零残留')


if __name__ == '__main__':
    main()
