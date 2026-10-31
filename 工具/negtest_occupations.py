# -*- coding: utf-8 -*-
"""产业与就业层闸门的违例自检：把闸门与十份数据整批复制到临时目录，逐条改坏正典，断言闸门必须判红并给出该条自己的措辞。

闸门只会打印"全绿"，无法自证它抓得住违例；本脚本按二十五条判据反向注入，只操作临时副本，
绝不改动被守护的仓库文件。闸门只读落盘 JSON，因此临时目录里不需要 build_admission.py 与 build_costs.py，
但必须带上 anchors.py——闸门的圈层归属与住所锚都从它取。
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
        '运行参数正典.json', '运行参数源表.json']
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


# 用例改动函数的形参顺序即正典写入顺序：1 参改产业、2 参加字典、3 参加物价、4 参加运行参数
OBJ_NAMES = ['canon', 'adm', 'costs', 'params']
FILES = {'canon': '产业就业正典.json', 'adm': '岗位准入正典.json',
         'costs': '物价与生活正典.json', 'params': '运行参数正典.json'}


def cards(canon):
    return [x for comp in canon['公司'] for x in comp['岗位卡']]


def cases():
    """返回 (用例名, 改动函数, 期望出现的判红字样)；改动只动四份正典，三份源表与名录保持原样。

    形参个数就是注入范围：1 个改产业就业正典，2 个再加岗位准入正典，3 个再加物价正典，
    4 个再加运行参数正典；main 按 OBJ_NAMES 的前缀取对象，写完只回写被改的那几份。
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
                    'costs': costs_of(tmp), 'params': params_of(tmp)}
            names = OBJ_NAMES[:_arity(mutate)]
            mutate(*[objs[k] for k in names])
            payload = [(tmp / '数据' / FILES[k], objs[k]) for k in names]
            for path, obj in payload:
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
