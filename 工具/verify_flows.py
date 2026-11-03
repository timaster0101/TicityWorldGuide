# -*- coding: utf-8 -*-
"""第5期流程与制度闸门：把 23 条判据独立复算一遍，不依赖派生器的守卫。

读 数据/流程制度正典.json 与 数据/流程制度源表.json，再用第1—5期各正典重算一遍应当得到的值。
凡「有人改了第4期冷却」「改了合同类型字典而不补存续表」「改了名录坐标或岗位规模」「手改了正典」，
都在此判红而不是静默通过。跑法：python 工具/verify_flows.py
"""
import datetime
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOWS_PATH = ROOT / '数据' / '流程制度正典.json'
SRC_PATH = ROOT / '数据' / '流程制度源表.json'

CHECKS = [
    '节庆日期可复算', '节庆排期无冲突', '节庆不跨季不越年', '节庆锚点有承载体',
    '节庆级别与范围相容', '节庆活动形式不重复', '机构三级且驻地可解',
    '公职编制不越机构与锚点规模', '公职不进岗位名录', '登记落点在盘',
    '门禁项承载脚本在盘', '共创时限与步骤同源', '删除处置与保留期自洽',
    '调解受理闭合', '合同存续与字典一一对应', '事件冷却与第4期同源',
    '事件目录分级计数一致', '税率与采购分档自洽', '关系与文化阈值单调',
    '界面分级全覆盖且导出有产物', 'AI自由层引用闭合', '版本兼容逐行等于盘上',
    '汇总与逐表行数一致',
]

WEEKDAYS = ('周一', '周二', '周三', '周四', '周五', '周六', '周日')
GOV_LEVELS = ('城市', '片区', '社区')
DISRUPT_WORDS = ('封闭', '中断', '停航', '检修', '增加耗时', '临时调价')
NEGATIONS = ('不', '无', '禁止', '不得', '绝不')
OUTSIDE_PRE = ('拉黑', '撤销授权')


def _canon(name):
    return json.loads((ROOT / '数据' / name).read_text(encoding='utf-8'))


def _row_blobs(node, path=''):
    """按「一行登记」为单位取文本：dict 自身的标量与列表里的标量算同一行，嵌套 dict 另起一行。

    禁则句与它所属条目同读一行，才不会把「基础设施中断」这类条目名当成许可；
    真出现无否定式的许可句时，同一行里既没有「不」也没有「禁止」，就判红。
    """
    if isinstance(node, dict):
        own = []
        for k, v in node.items():
            if isinstance(v, str):
                own.append(f'{k} {v}')
            elif isinstance(v, list):
                own += [x for x in v if isinstance(x, str)]
        if own:
            yield path, ' '.join(own)
        for k, v in node.items():
            if isinstance(v, dict):
                yield from _row_blobs(v, f'{path}.{k}')
            elif isinstance(v, list):
                for i, x in enumerate(v):
                    yield from _row_blobs(x, f'{path}.{k}[{i}]')
    elif isinstance(node, list):
        for i, x in enumerate(node):
            yield from _row_blobs(x, f'{path}[{i}]')


def check_flows(flows, src, run, adm, occ, reg, sp):
    """返回 [(判据名, 违例说明), ...]；每条判据独立复算，不复用派生器的中间结果。"""
    issues = []
    year = flows['setting_year']
    by_id = {e['id']: e for e in reg['entries']}
    components = {}
    for kind, label in (('桥梁', '桥'), ('渡位', '渡位'), ('山口通道', '山口'), ('轮渡航线', '航线')):
        for r in sp[kind]:
            components[r['码']] = (r['名'], label)
    sea_of_month = run['月季节']

    # 1 节庆日期可复算
    bad = []
    for f in flows['节庆年历']:
        d = datetime.date(year, f['月'], f['日'])
        end = d + datetime.timedelta(days=f['日期跨度天'] - 1)
        if (f['星期'] != WEEKDAYS[d.weekday()] or f['SEA'] != sea_of_month[str(f['月'])]
                or f['年内第几天'] != d.timetuple().tm_yday
                or (f['结束月'], f['结束日']) != (end.month, end.day)):
            bad.append(f['编号'])
    issues.append(('节庆日期可复算', bad))

    # 2 排期无冲突（逐日逐锚点独立重排）
    seen, clash = {}, []
    for f in flows['节庆年历']:
        d = datetime.date(year, f['月'], f['日'])
        for k in range(f['日期跨度天']):
            day = d + datetime.timedelta(days=k)
            for a_id in f['范围锚点']:
                if (day.toordinal(), a_id) in seen:
                    clash.append(f'{a_id}@{day.month}-{day.day}:{seen[(day.toordinal(), a_id)]}vs{f["编号"]}')
                seen[(day.toordinal(), a_id)] = f['编号']
    issues.append(('节庆排期无冲突', clash))

    # 3 不跨季不越年
    cross = []
    for f in flows['节庆年历']:
        d = datetime.date(year, f['月'], f['日'])
        spans = {sea_of_month[str((d + datetime.timedelta(days=k)).month)] for k in range(f['日期跨度天'])}
        last = d + datetime.timedelta(days=f['日期跨度天'] - 1)
        if len(spans) > 1:
            cross.append(f'{f["编号"]} 跨季 {sorted(spans)}')
        if last.year != year:
            cross.append(f'{f["编号"]} 越出 {year} 年')
    issues.append(('节庆不跨季不越年', cross))

    # 4 锚点有承载体
    dangling = [f'{f["编号"]}:{a}' for f in flows['节庆年历'] for a in f['范围锚点']
                if a not in by_id and a not in components]
    dangling += [f'{o["编号"]}:{o["驻地锚点"]}' for o in flows['机构']
                 if o['驻地锚点'] not in by_id and o['驻地锚点'] not in components]
    issues.append(('节庆锚点有承载体', dangling))

    # 5 级别与范围相容
    mismatched = []
    for f in flows['节庆年历']:
        kinds = set()
        for a in f['范围锚点']:
            kinds.add(by_id[a]['type'] if a in by_id else '构件')
        if f['级别'] == '社区' and kinds & {'城市片区', '功能区'}:
            mismatched.append(f'{f["编号"]} 社区级却含片区或功能区')
        if f['级别'] == '片区' and not kinds & {'城市片区', '功能区'}:
            mismatched.append(f'{f["编号"]} 片区级却只有聚落或居民区')
        if f['级别'] == '城市' and ('城市片区' not in kinds or len(f['范围锚点']) < 2):
            mismatched.append(f'{f["编号"]} 城市级却未跨片区')
        if f['级别'] not in GOV_LEVELS:
            mismatched.append(f'{f["编号"]} 级别 {f["级别"]} 不合三级')
    issues.append(('节庆级别与范围相容', mismatched))

    # 6 活动形式不重复
    sig = {}
    dup = []
    for f in flows['节庆年历']:
        key = tuple(sorted(f['活动形式']))
        if key in sig:
            dup.append(f'{f["编号"]}={sig[key]}')
        sig.setdefault(key, f['编号'])
    issues.append(('节庆活动形式不重复', dup))

    # 7 机构三级且驻地可解
    org_bad = []
    for o in flows['机构']:
        if o['层级'] not in GOV_LEVELS:
            org_bad.append(f'{o["编号"]} 层级 {o["层级"]}')
        anchor = o['驻地锚点']
        if anchor in by_id and by_id[anchor]['type'] == '城市片区' and o['层级'] == '社区':
            org_bad.append(f'{o["编号"]} 社区级机构却驻在城市片区')
    posts_by_org = {}
    org_level = {o['编号']: o['层级'] for o in flows['机构']}
    for p in flows['公职']:
        posts_by_org.setdefault(p['机构'], []).append(p)
    org_bad += [f'{p["编号"]} 层级与机构 {p["机构"]} 不一致' for p in flows['公职']
                if p['机构'] in org_level and p['层级'] != org_level[p['机构']]]
    org_bad += [f'{p["编号"]} 的机构 {p["机构"]} 不存在' for p in flows['公职']
                if p['机构'] not in {o['编号'] for o in flows['机构']}]
    issues.append(('机构三级且驻地可解', org_bad))

    # 8 编制不越机构与锚点规模
    over = []
    employees = {}
    for c in occ['公司']:
        employees[c['锚点']] = employees.get(c['锚点'], 0) + c['雇员数']
    for o in flows['机构']:
        sub = sum(p['编制'] for p in posts_by_org.get(o['编号'], []))
        if sub > o['编制']:
            over.append(f'{o["编号"]} 登记 {sub} 超编制 {o["编制"]}')
    anchor_total = {}
    for o in flows['机构']:
        anchor_total[o['驻地锚点']] = anchor_total.get(o['驻地锚点'], 0) + o['编制']
    for a, total in anchor_total.items():
        if a in employees and total > employees[a]:
            over.append(f'驻地 {a} 机构编制合计 {total} 超锚点岗位规模 {employees[a]}')
    issues.append(('公职编制不越机构与锚点规模', over))

    # 9 公职不进岗位名录
    ids = set(by_id) | {c['id'] for c in occ['公司']} | {k['id'] for c in occ['公司'] for k in c['岗位卡']}
    collide = [p['编号'] for p in flows['公职'] if p['编号'] in ids]
    tagged = [p['编号'] for p in flows['公职']
              if any(x in p for x in ('标签', '准入', '合同类型', '释放状态', '薪酬'))]
    bad_level = [p['编号'] for p in flows['公职'] if p['参照层'] not in {l['层'] for l in occ['岗位层']}]
    issues.append(('公职不进岗位名录', collide + tagged + bad_level))

    # 10 登记落点在盘
    missing_target = [o['码'] for o in flows['登记对象'] if not (ROOT / o['落点源表']).exists()]
    issues.append(('登记落点在盘', missing_target))

    # 11 门禁项承载脚本在盘
    missing_tool = [g['编号'] for g in flows['门禁项'] if not (ROOT / '工具' / g['承载脚本']).exists()]
    missing_tool += [f'{o["码"]}:{t}' for o in flows['登记对象']
                     for t in [o['校验工具']] + o['附校验'] if not (ROOT / '工具' / t).exists()]
    dup_code = [g for g in {x['编号'] for x in flows['门禁项']}
                if sum(1 for y in flows['门禁项'] if y['编号'] == g) > 1]
    issues.append(('门禁项承载脚本在盘', missing_tool + [f'编号重复 {d}' for d in dup_code]))

    # 12 共创时限与步骤同源
    fx = flows['参数']['共创转永久']
    seq = [s['序号'] for s in fx['步骤']]
    bad_steps = [] if seq == list(range(1, len(seq) + 1)) else [f'序号不连续 {seq}']
    named = {s['名称']: s['时限天'] for s in fx['步骤']}
    if fx['公示天'] != named.get('公示'):
        bad_steps.append(f'公示天 {fx["公示天"]} 与步骤 {named.get("公示")}')
    objection = [v for k, v in named.items() if '异议' in k]
    if fx['异议窗口天'] not in objection:
        bad_steps.append(f'异议窗口 {fx["异议窗口天"]} 不在步骤时限里')
    issues.append(('共创时限与步骤同源', bad_steps))

    # 13 删除处置与保留期自洽
    an = flows['参数']['匿名化与删除']
    bad_fields = []
    for f in an['字段']:
        if f['处置'] == '删除' and f['保留天'] != 0:
            bad_fields.append(f'{f["码"]} 删除却留 {f["保留天"]} 天')
        if f['处置'] == '匿名化保留' and f['保留天'] <= 0:
            bad_fields.append(f'{f["码"]} 匿名化保留却无保留期')
        if f['类别'] not in ('私密', '合同事实', '公共事实', '受限'):
            bad_fields.append(f'{f["码"]} 类别 {f["类别"]}')
    anon_steps = [s['序号'] for s in an['步骤']]
    if anon_steps != list(range(1, len(anon_steps) + 1)):
        bad_fields.append(f'删除步骤序号 {anon_steps}')
    issues.append(('删除处置与保留期自洽', bad_fields))

    # 14 调解受理闭合
    md = flows['参数']['调解与争议']
    body = {b['码'] for b in md['受理主体']}
    dispute_codes = {d['码'] for d in md['争议类别']}
    med_bad = []
    for b in md['受理主体']:
        med_bad += [f'{b["码"]} 类别 {c}' for c in b['受理类别'] if c not in dispute_codes]
        if b['层级'] not in GOV_LEVELS + ('无',):
            med_bad.append(f'{b["码"]} 层级 {b["层级"]}')
        if b['前置'] != '无':
            refs = [c for c in body if c in b['前置']] + [w for w in OUTSIDE_PRE if w in b['前置']]
            if not refs:
                med_bad.append(f'{b["码"]} 前置「{b["前置"]}」指不到主体也不属流程外条件')
    uncovered = sorted(dispute_codes - {c for b in md['受理主体'] for c in b['受理类别']})
    if uncovered:
        med_bad.append(f'争议类别 {uncovered} 无受理主体')
    if md['受理主体'][0]['时限天'] != 0:
        med_bad.append('自行和解必须 0 天')
    issues.append(('调解受理闭合', med_bad))

    # 15 合同存续与字典一一对应
    want = {c['id'] for c in adm['合同类型']}
    got = {c['合同类型'] for c in flows['合同存续']}
    contract_bad = [f'缺 {x}' for x in sorted(want - got)] + [f'多 {x}' for x in sorted(got - want)]
    if len(flows['合同存续']) != len(got):
        contract_bad.append('存续表有重复类型')
    name_of = {x['id']: x['名称'] for x in adm['合同类型']}
    contract_bad += [f'{c["合同类型"]} 名称不随字典' for c in flows['合同存续']
                     if c['名称'] != name_of.get(c['合同类型'])]
    issues.append(('合同存续与字典一一对应', contract_bad))

    # 16 事件冷却与第4期同源
    cool = run['参数']['事件']['冷却天']
    advance = run['参数']['事件']['预告天']
    evt_bad = [f'{e["编号"]} 声明 {e["冷却天声明"]} 实为 {cool.get(e["级别"])}'
               for e in flows['事件目录'] if e['冷却天'] != cool.get(e['级别'])]
    evt_bad += [f'{e["编号"]} 预告 {e["预告天"]} 与第4期 {advance.get(str(e["级别"]) + "级", 0)}'
                for e in flows['事件目录']
                if e['预告天'] != advance.get(f'{e["级别"]}级', 0)]
    trig = {t['码'] for t in flows['参数']['事件目录']['触发方式']}
    evt_bad += [f'{e["编号"]} 触发 {e["触发方式"]}' for e in flows['事件目录'] if e['触发方式'] not in trig]
    quota = run['参数']['事件']['负面配额']
    if not flows['事件目录'] or sum(1 for e in flows['事件目录'] if e['负面']) > quota['每轮'] * 4:
        evt_bad.append('负面模板数与配额口径失衡')
    issues.append(('事件冷却与第4期同源', evt_bad))

    # 17 分级计数一致
    recount = {}
    for e in flows['事件目录']:
        recount[e['级别']] = recount.get(e['级别'], 0) + 1
    stated = flows['汇总']['各级模板数']
    level_bad = [] if recount == stated else [f'各级模板数 记 {stated} 实 {recount}']
    if sum(stated.values()) != flows['汇总']['事件模板数']:
        level_bad.append('各级之和与模板总数不等')
    issues.append(('事件目录分级计数一致', level_bad))

    # 18 税率与采购分档
    fin = []
    for t in flows['税种']:
        if not 0 < t['税率千分比'] < 1000:
            fin.append(f'{t["码"]} 税率 {t["税率千分比"]}')
        if t['起征_钛币'] < 0:
            fin.append(f'{t["码"]} 起征为负')
    tiers = sorted(flows['采购分档'], key=lambda x: x['金额下限_钛币'])
    for i in range(1, len(tiers)):
        if tiers[i]['金额下限_钛币'] != tiers[i - 1]['金额上限_钛币']:
            fin.append(f'{tiers[i]["档"]} 与前一档不接缝')
        if tiers[i]['公示天'] <= tiers[i - 1]['公示天']:
            fin.append(f'{tiers[i]["档"]} 公示天不随金额递增')
    if tiers and tiers[-1]['金额上限_钛币'] is not None:
        fin.append('最高采购档必须不设上限')
    issues.append(('税率与采购分档自洽', fin))

    # 19 关系与文化阈值单调
    rel, cul, rum = flows['关系层级'], flows['文化层级'], flows['传闻失真']
    thin = []
    for i in range(1, len(rel)):
        if rel[i]['累计有效互动下限'] <= rel[i - 1]['累计有效互动下限']:
            thin.append(f'关系第 {rel[i]["阶"]} 阶非单调')
    if [r['阶'] for r in rel] != list(range(1, len(rel) + 1)):
        thin.append('关系阶次不连续')
    if {c['码'] for c in cul} != {'CUL-01', 'CUL-02', 'CUL-03', 'CUL-04'}:
        thin.append('文化四层缺一')
    for i in range(1, len(rum)):
        if rum[i]['失真比例千分比'] <= rum[i - 1]['失真比例千分比']:
            thin.append(f'失真档 {rum[i]["档"]} 非单调')
    if rum and rum[-1]['判定影响'] != '禁止':
        thin.append('最高失真档未判禁止')
    issues.append(('关系与文化阈值单调', thin))

    # 20 界面分级全覆盖且导出有产物
    ui_bad = []
    if [u['优先级'] for u in flows['界面层级']] != list(range(1, len(flows['界面层级']) + 1)):
        ui_bad.append('界面优先级不连续')
    known = {u['码'] for u in flows['界面层级']} | {s['码'] for s in flows['参数']['界面与导出']['摘要跨度']}
    covered = [m for lvl in flows['参数']['界面与导出']['免打扰分级'] for m in lvl['成员']]
    if len(covered) != len(set(covered)):
        ui_bad.append('有界面项挂两个免打扰级别')
    if set(covered) != known:
        ui_bad.append(f'未分级界面项 {sorted(known - set(covered))}')
    if flows['参数']['界面与导出']['免打扰分级'][0]['成员'] != ['UI-01']:
        ui_bad.append('不可静音项被放宽')
    ui_bad += [f'{e["码"]}:{e["承载产物"]}' for e in flows['导出格式']
               if not (ROOT / e['承载产物']).exists()]
    issues.append(('界面分级全覆盖且导出有产物', ui_bad))

    # 21 AI 自由层引用闭合
    ai = flows['参数']['AI自由层']
    codes = {f['码'] for f in ai['可自由补全']} | {s['码'] for s in ai['须停止确认']}
    referenced = {w for c in ai['更正提示'] for w in c['适用'].replace('、', ' ').split() if w in codes}
    ai_bad = [f'{c["码"]} 无引用对象' for c in ai['更正提示']
              if not any(w in codes for w in c['适用'].replace('、', ' ').split())]
    ai_bad += [f'{x} 无更正通道' for x in sorted(codes - referenced)]
    if not any('不适用，一律拒绝' in s['确认主体'] for s in ai['须停止确认']):
        ai_bad.append('须停止确认里没了无确认通道的拒绝项')
    if len(codes) != len(ai['可自由补全']) + len(ai['须停止确认']):
        ai_bad.append('自由层与停止项编号撞键')
    issues.append(('AI自由层引用闭合', ai_bad))

    # 22 版本兼容逐行等于盘上
    compat_bad = []
    for r in flows['版本兼容']:
        if r['对象'] == '数据/流程制度正典.json':
            actual = flows['version']
        else:
            target = ROOT / r['对象']
            if not target.exists():
                compat_bad.append(f'{r["对象"]} 不在盘上')
                continue
            actual = json.loads(target.read_text(encoding='utf-8')).get('version')
        if r['声明版本'] != actual or r['实际版本'] != actual:
            compat_bad.append(f'{r["对象"]} 声明 {r["声明版本"]} 盘上 {actual}')
        if r['旧轮次下限'] != flows['setting_year']:
            compat_bad.append(f'{r["对象"]} 旧轮次下限 {r["旧轮次下限"]}')
    issues.append(('版本兼容逐行等于盘上', compat_bad))

    # 23 汇总与逐表行数一致 + 流程不得写进中断类许可
    counts = {
        '节庆条数': len(flows['节庆年历']), '机构数': len(flows['机构']),
        '公职条目数': len(flows['公职']), '登记对象数': len(flows['登记对象']),
        '门禁项数': len(flows['门禁项']), '合同存续数': len(flows['合同存续']),
        '事件模板数': len(flows['事件目录']), '税种数': len(flows['税种']),
        '采购档数': len(flows['采购分档']), '关系阶数': len(flows['关系层级']),
        '文化层数': len(flows['文化层级']), '失真档数': len(flows['传闻失真']),
        '界面层级数': len(flows['界面层级']), '导出格式数': len(flows['导出格式']),
        '版本兼容行数': len(flows['版本兼容']),
        '共创步骤数': len(flows['参数']['共创转永久']['步骤']),
        '删除步骤数': len(flows['参数']['匿名化与删除']['步骤']),
        '删除字段数': len(flows['参数']['匿名化与删除']['字段']),
        '调解主体数': len(flows['参数']['调解与争议']['受理主体']),
        '争议类别数': len(flows['参数']['调解与争议']['争议类别']),
        '拉黑动作数': len(flows['参数']['拉黑后合同']['动作']),
        '负面模板数': sum(1 for e in flows['事件目录'] if e['负面']),
    }
    sum_bad = [f'{k} 记 {flows["汇总"][k]} 实 {v}' for k, v in counts.items()
               if flows['汇总'].get(k) != v]
    if flows['汇总'].get('公职编制合计') != sum(p['编制'] for p in flows['公职']):
        sum_bad.append('公职编制合计与逐条不等的和')
    text_bad = [f'{path} 写了「{w}」且同行无否定式'
                for path, text in _row_blobs(flows)
                for w in DISRUPT_WORDS
                if w in text and not any(n in text for n in NEGATIONS)]
    issues.append(('汇总与逐表行数一致', sum_bad + text_bad))

    return [(name, bad) for name, bad in issues]


def main():
    if not FLOWS_PATH.exists():
        raise SystemExit('缺少 数据/流程制度正典.json：先跑 python 工具/build_flows.py')
    flows = _canon('流程制度正典.json')
    src = json.loads(SRC_PATH.read_text(encoding='utf-8'))
    run, adm = _canon('运行参数正典.json'), _canon('岗位准入正典.json')
    occ, reg, sp = _canon('产业就业正典.json'), _canon('城市空间名录.json'), _canon('空间通行正典.json')
    if src.get('version') != flows.get('version'):
        raise SystemExit(f'源表版本 {src.get("version")} 与正典版本 {flows.get("version")} 不一致：产物过期，须重跑派生器')
    for key, rows in (('节庆年历', src['参数']['节庆']['活动']), ('事件目录', src['参数']['事件目录']['模板']),
                      ('合同存续', src['参数']['拉黑后合同']['处理']), ('版本兼容', src['参数']['版本兼容']['行'])):
        if len(flows[key]) != len(rows):
            raise SystemExit(f'正典 {key} 得 {len(flows[key])} 行、源表登记 {len(rows)} 条：产物过期，须重跑派生器')
    results = check_flows(flows, src, run, adm, occ, reg, sp)
    failures = [f'{name}：{bad}' for name, bad in results if bad]
    output = dict(检查项数=len(results), 检查项=[name for name, _ in results],
                  失败数=len(failures), 失败明细=failures,
                  details={name: bad for name, bad in results},
                  rule='第5期流程与制度：节庆按 2013 公共日历复算且不冲突，公职只作背景登记且不进岗位名录，'
                       '事件冷却与预告天逐条与第4期同源，合同存续与合同类型字典一一对应，'
                       '版本兼容逐行等于盘上实际 version，汇总与逐表行数一致。')
    (ROOT / '数据' / '流程制度核验.json').write_bytes(
        (json.dumps(output, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps(dict(检查项数=len(results), 失败数=len(failures), failures=failures), ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
