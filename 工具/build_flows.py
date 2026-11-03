# -*- coding: utf-8 -*-
"""第5期流程与制度派生器：读 流程制度源表.json ＋ 第1—5期各正典，产出节庆年历、公职名录、事件目录与六张查表。

手填只有十三组登记值；星期与季节、编制小计与锚点规模、事件冷却与预告天、合同存续名称、门禁项承载脚本
与版本号一律是本文件的生成物。跑法：python 工具/build_flows.py [--out-dir DIR] [--print-summary]
"""
import argparse
import datetime
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / '数据' / '流程制度源表.json'
if not SRC_PATH.exists():
    raise SystemExit('缺少 数据/流程制度源表.json：本期所有流程查表都从它派生，不允许手填正典')
SOURCE = json.loads(SRC_PATH.read_text(encoding='utf-8'))

CANON_FILES = {
    '运行参数': ROOT / '数据' / '运行参数正典.json',
    '岗位准入': ROOT / '数据' / '岗位准入正典.json',
    '产业就业': ROOT / '数据' / '产业就业正典.json',
    '名录': ROOT / '数据' / '城市空间名录.json',
    '空间通行': ROOT / '数据' / '空间通行正典.json',
}
for _name, _path in CANON_FILES.items():
    if not _path.exists():
        raise SystemExit(f'缺少上游正典 {_name}（{_path.name}）：本期流程判据全部按它同源核对，先跑前几期派生器')

RUN = json.loads(CANON_FILES['运行参数'].read_text(encoding='utf-8'))
ADMISSION = json.loads(CANON_FILES['岗位准入'].read_text(encoding='utf-8'))
OCCUPATION = json.loads(CANON_FILES['产业就业'].read_text(encoding='utf-8'))
REGISTRY = json.loads(CANON_FILES['名录'].read_text(encoding='utf-8'))
SPATIAL = json.loads(CANON_FILES['空间通行'].read_text(encoding='utf-8'))

P = SOURCE['参数']
WEEKDAYS = ('周一', '周二', '周三', '周四', '周五', '周六', '周日')
LEVELS = ('个人', '家庭', '社区', '城市')
GOV_LEVELS = ('城市', '片区', '社区')
OUTSIDE_PRECONDITIONS = ('拉黑', '撤销授权')
SEASON_NAME = {sea: info['名'] for sea, info in RUN['参数']['季节月份'].items()}


ANCHOR_BY_ID = {e['id']: e for e in REGISTRY['entries']}
COMPONENT_BY_ID = {}
for _rows, _label in (('桥梁', '桥'), ('渡位', '渡位'), ('山口通道', '山口'), ('轮渡航线', '航线')):
    for _r in SPATIAL[_rows]:
        COMPONENT_BY_ID[_r['码']] = {'name': _r['名'], 'type': _label}
ANCHOR_EMPLOYEES = {}
for _corp in OCCUPATION['公司']:
    ANCHOR_EMPLOYEES[_corp['锚点']] = ANCHOR_EMPLOYEES.get(_corp['锚点'], 0) + _corp['雇员数']
CONTRACT_BY_ID = {c['id']: c for c in ADMISSION['合同类型']}
COOLDOWN = RUN['参数']['事件']['冷却天']
ADVANCE = RUN['参数']['事件']['预告天']
MONTH_OF_SEA = RUN['月季节']


def resolve_anchor(a_id, where):
    """锚点可以是名录条目，也可以是第5期构件；两处都查不到即退出。"""
    if a_id in ANCHOR_BY_ID:
        e = ANCHOR_BY_ID[a_id]
        return {'码': a_id, '名': e['name'], '层级': e['type'], '种类': '名录'}
    if a_id in COMPONENT_BY_ID:
        c = COMPONENT_BY_ID[a_id]
        return {'码': a_id, '名': c['name'], '层级': f'第5期{c["type"]}', '种类': '构件'}
    raise SystemExit(f'{where} 的锚点 {a_id} 既不在名录也不在第5期构件里：节庆与机构只能落在有承载体的位置')


def build_festivals():
    days_of_sea = {}
    rows, occupied = [], {}
    for f in P['节庆']['活动']:
        start = datetime.date(SOURCE['setting_year'], f['月'], f['日'])
        end = start + datetime.timedelta(days=f['天数'] - 1)
        if end.year != SOURCE['setting_year']:
            raise SystemExit(f'节庆 {f["编号"]} 自 {f["月"]}-{f["日"]} 起 {f["天数"]} 天跨过 {SOURCE["setting_year"]} 年，公共日历只在年内查表')
        sea_span = {MONTH_OF_SEA[str(d.month)] for d in _each_day(start, end)}
        if len(sea_span) > 1:
            raise SystemExit(f'节庆 {f["编号"]} 跨季节（{sorted(sea_span)}）：本期口径是一季一档，跨季须另立条目')
        sea = MONTH_OF_SEA[str(f['月'])]
        for d in _each_day(start, end):
            for a_id in f['范围锚点']:
                key = (d.toordinal(), a_id)
                if key in occupied:
                    raise SystemExit(f'节庆排期冲突：{a_id} 在 {d.month}-{d.day} 同时挂了 {occupied[key]} 与 {f["编号"]}')
                occupied[key] = f['编号']
        anchors = [resolve_anchor(a, f'节庆 {f["编号"]}') for a in f['范围锚点']]
        levels = {a['层级'] for a in anchors}
        rows.append(dict(f, 星期=WEEKDAYS[start.weekday()], 结束月=end.month, 结束日=end.day,
                         SEA=sea, 季节名=SEASON_NAME[sea], 年内第几天=start.timetuple().tm_yday,
                         锚点明细=anchors, 锚点层级数=len(levels), 日期跨度天=f['天数']))
        days_of_sea.setdefault(sea, 0)
        days_of_sea[sea] += f['天数']
    forms = {}
    for r in rows:
        sig = tuple(sorted(r['活动形式']))
        if sig in forms:
            raise SystemExit(f'节庆 {r["编号"]} 与 {forms[sig]} 的活动形式完全相同：同一套内容不得重复登记两个档期')
        forms[sig] = r['编号']
    bad_level = [r['编号'] for r in rows if r['级别'] not in GOV_LEVELS]
    if bad_level:
        raise SystemExit(f'节庆级别不在城市—片区—社区三级口径内：{bad_level}')
    for r in rows:
        kinds = {a['层级'] for a in r['锚点明细']}
        if r['级别'] == '社区' and (kinds & {'城市片区', '功能区'}):
            raise SystemExit(f'节庆 {r["编号"]} 记为社区级却挂了片区或功能区锚点：范围与级别不符')
        if r['级别'] == '片区' and not (kinds & {'城市片区', '功能区'}):
            raise SystemExit(f'节庆 {r["编号"]} 记为片区级却只有聚落或居民区锚点：聚落级活动应记为社区级')
        if r['级别'] == '城市' and ('城市片区' not in kinds or len(r['范围锚点']) < 2):
            raise SystemExit(f'节庆 {r["编号"]} 记为城市级却不足两个锚点或未含城市片区：跨片区才算城市级')
    return rows, days_of_sea


def _each_day(start, end):
    d = start
    while d <= end:
        yield d
        d += datetime.timedelta(days=1)


def build_orgs():
    posts = P['机构与公职']['公职']
    orgs = P['机构与公职']['机构']
    org_ids = {o['编号'] for o in orgs}
    post_ids = {p['编号'] for p in posts}
    if len(post_ids) != len(posts) or len(org_ids) != len(orgs):
        raise SystemExit('机构或公职编号重复：同一编号只能登记一次')
    by_org = {}
    for p in posts:
        if p['机构'] not in org_ids:
            raise SystemExit(f'公职 {p["编号"]} 挂靠的机构 {p["机构"]} 不在机构表里')
        by_org.setdefault(p['机构'], []).append(p)
    rows = []
    for o in orgs:
        if o['层级'] not in GOV_LEVELS:
            raise SystemExit(f'机构 {o["编号"]} 的层级 {o["层级"]} 不属城市—片区—社区三级')
        anchor = resolve_anchor(o['驻地锚点'], f'机构 {o["编号"]}')
        listed = by_org.get(o['编号'], [])
        sub_total = sum(p['编制'] for p in listed)
        if sub_total > o['编制']:
            raise SystemExit(f'机构 {o["编号"]} 登记公职 {sub_total} 人超过编制 {o["编制"]}：只能少不能多')
        cap = ANCHOR_EMPLOYEES.get(o['驻地锚点'])
        anchor_total = sum(x['编制'] for x in orgs if x['驻地锚点'] == o['驻地锚点'])
        if cap is not None and anchor_total > cap:
            raise SystemExit(f'驻地 {o["驻地锚点"]} 的机构编制合计 {anchor_total} 超过该锚点日常岗位规模 {cap}：改名录岗位规模须同步本节')
        mismatch = [p['编号'] for p in listed if p['层级'] != o['层级']]
        if mismatch:
            raise SystemExit(f'公职 {mismatch} 的层级与所属机构 {o["编号"]} 不一致')
        rows.append(dict(o, 驻地=anchor, 登记公职数=len(listed), 登记编制小计=sub_total,
                         锚点岗位规模=cap, 同锚点编制合计=anchor_total,
                         公职明细=[p['编号'] for p in listed]))
    return rows, posts


def check_gov_not_employable(posts):
    """公职不得进岗位名录：编号与名录、公司、岗位卡三处都不撞键。"""
    reg_ids = set(ANCHOR_BY_ID) | {c['id'] for c in OCCUPATION['公司']}
    post_cards = {k['id'] for c in OCCUPATION['公司'] for k in c['岗位卡']}
    for p in posts:
        if p['编号'] in reg_ids or p['编号'] in post_cards:
            raise SystemExit(f'公职 {p["编号"]} 与名录或岗位卡撞键：公职只作背景登记')
        if p['参照层'] not in {l['层'] for l in OCCUPATION['岗位层']}:
            raise SystemExit(f'公职 {p["编号"]} 的参照层 {p["参照层"]} 不在岗位层字典里')
        for forbidden in ('标签', '准入', '合同类型', '释放状态', '薪酬'):
            if forbidden in p:
                raise SystemExit(f'公职 {p["编号"]} 挂了可取得岗位专用字段 {forbidden}：公职不进招聘与合同')


def build_registration():
    objects = []
    for o in P['新条目登记']['对象']:
        target = ROOT / o['落点源表']
        if not target.exists():
            raise SystemExit(f'{o["码"]} 的落点源表 {o["落点源表"]} 在盘上不存在：登记入口必须唯一且真实')
        objects.append(dict(o, 落点存在=True))
    gates = []
    for g in P['新条目登记']['门禁项']:
        carrier = ROOT / '工具' / g['承载脚本']
        if not carrier.exists():
            raise SystemExit(f'门禁项 {g["编号"]} 的承载脚本 工具/{g["承载脚本"]} 不存在：判据必须挂在真跑的工具上')
        gates.append(dict(g, 承载脚本存在=True))
    codes = [g['编号'] for g in gates]
    if len(set(codes)) != len(codes):
        raise SystemExit('门禁项编号重复')
    return objects, gates


def build_flows():
    fx = P['共创转永久']
    steps = fx['步骤']
    _assert_sequence(steps, '共创转永久')
    if fx['公示天'] != next(s['时限天'] for s in steps if s['名称'] == '公示'):
        raise SystemExit('共创公示天与步骤表里的公示时限不相等：一处改了两处必须同步')
    if fx['异议窗口天'] != next(s['时限天'] for s in steps if '异议' in s['名称']):
        raise SystemExit('共创异议窗口天与步骤表里的异议处理时限不相等')
    an = P['匿名化与删除']
    allowed = {'删除', '脱敏', '匿名化保留', '按授权可见'}
    for f in an['字段']:
        if f['处置'] not in allowed:
            raise SystemExit(f'字段 {f["码"]} 的处置 {f["处置"]} 不在四种口径内')
        if f['处置'] == '删除' and f['保留天'] != 0:
            raise SystemExit(f'字段 {f["码"]} 判删除却留了保留天 {f["保留天"]}')
        if f['处置'] == '匿名化保留' and f['保留天'] <= 0:
            raise SystemExit(f'字段 {f["码"]} 匿名化保留却没写保留期限')
    _assert_sequence(an['步骤'], '匿名化与删除')
    md = P['调解与争议']
    body_ids = {b['码'] for b in md['受理主体']}
    dispute_codes = {d['码'] for d in md['争议类别']}
    dispute_name = {d['码']: d['名称'] for d in md['争议类别']}
    for b in md['受理主体']:
        if b['层级'] not in GOV_LEVELS + ('无',):
            raise SystemExit(f'调解主体 {b["码"]} 的层级 {b["层级"]} 不属三级或无')
        outside = [c for c in b['受理类别'] if c not in dispute_codes]
        if outside:
            raise SystemExit(f'调解主体 {b["码"]} 受理了争议类别表里没有的类别码：{outside}')
        if b['前置'] != '无':
            named_body = [c for c in body_ids if c in b['前置']]
            named_outside = [w for w in OUTSIDE_PRECONDITIONS if w in b['前置']]
            if not (named_body or named_outside):
                raise SystemExit(f'调解主体 {b["码"]} 的前置「{b["前置"]}」既指不到前序受理主体，'
                                 f'也不属 {OUTSIDE_PRECONDITIONS} 这几类流程外条件')
    unhandled = sorted(dispute_codes - {c for b in md['受理主体'] for c in b['受理类别']})
    if unhandled:
        raise SystemExit(f'争议类别 {unhandled} 没有任何受理主体：每类争议都必须有落点')
    if md['受理主体'][0]['时限天'] != 0:
        raise SystemExit('自行和解的时限必须是 0 天：它不是受理环节')
    for b in md['受理主体']:
        b['受理类别名'] = [dispute_name[c] for c in b['受理类别']]
    return steps, an['步骤'], md


def _assert_sequence(steps, where):
    nums = [s['序号'] for s in steps]
    if nums != list(range(1, len(steps) + 1)):
        raise SystemExit(f'{where} 的步骤序号不连续：实得 {nums}')


def build_contracts():
    rows = []
    want = {c['id'] for c in ADMISSION['合同类型']}
    got = [r['合同类型'] for r in P['拉黑后合同']['处理']]
    if len(got) != len(set(got)):
        raise SystemExit(f'拉黑后合同处理里有重复类型：{[x for x in set(got) if got.count(x) > 1]}')
    if set(got) != want:
        raise SystemExit(f'拉黑后合同处理必须与合同类型字典逐一对应：缺 {sorted(want - set(got))}，多 {sorted(set(got) - want)}')
    for r in P['拉黑后合同']['处理']:
        c = CONTRACT_BY_ID[r['合同类型']]
        if r['存续'] == '' or r['结算'] == '':
            raise SystemExit(f'{r["合同类型"]} 的存续或结算口径留空：拉黑后的处理必须逐条写满')
        rows.append(dict(r, 名称=c['名称'], 用工形态=c['用工形态'], 薪酬结算周期=c['薪酬结算周期'],
                         可叠加=c['可叠加'], 解除条件数=len(c['解除条件'])))
    return rows


def build_events():
    trigs = {t['码'] for t in P['事件目录']['触发方式']}
    rows, by_level = [], {}
    for e in P['事件目录']['模板']:
        if e['级别'] not in COOLDOWN:
            raise SystemExit(f'事件 {e["编号"]} 的级别 {e["级别"]} 不在第4期四级冷却口径里')
        if e['冷却天声明'] != COOLDOWN[e['级别']]:
            raise SystemExit(f'事件 {e["编号"]} 声明冷却 {e["冷却天声明"]} 天，第4期该级冷却是 {COOLDOWN[e["级别"]]} 天：改了参数须同步目录')
        if e['触发方式'] not in trigs:
            raise SystemExit(f'事件 {e["编号"]} 的触发方式 {e["触发方式"]} 不在四种之内')
        advance = ADVANCE.get(f'{e["级别"]}级')
        if e['级别'] in ('社区', '城市') and advance is None:
            raise SystemExit(f'第4期缺 {e["级别"]}级预告天，社区与城市级事件必须带预告')
        by_level.setdefault(e['级别'], []).append(e)
        rows.append(dict(e, 冷却天=COOLDOWN[e['级别']], 预告天=advance or 0,
                         占用负面配额=e['负面'], 触发方式名=next(t['名称'] for t in P['事件目录']['触发方式'] if t['码'] == e['触发方式'])))
    for lvl, items in by_level.items():
        if len({i['名称'] for i in items}) != len(items):
            raise SystemExit(f'{lvl}级事件目录里有同名模板')
    return rows, by_level


def build_finance():
    tax = P['公共财政']['税种']
    for t in tax:
        if not 0 < t['税率千分比'] < 1000:
            raise SystemExit(f'税种 {t["码"]} 的税率千分比 {t["税率千分比"]} 越界：简化税制只放开 0—100%')
        if t['起征_钛币'] < 0:
            raise SystemExit(f'税种 {t["码"]} 的起征点为负')
    tiers = sorted(P['公共财政']['采购分档'], key=lambda x: x['金额下限_钛币'])
    for i in range(1, len(tiers)):
        if tiers[i]['金额下限_钛币'] != tiers[i - 1]['金额上限_钛币']:
            raise SystemExit(f'采购分档不接缝：{tiers[i - 1]["档"]} 上限 {tiers[i - 1]["金额上限_钛币"]} 对不上 {tiers[i]["档"]} 下限 {tiers[i]["金额下限_钛币"]}')
        if tiers[i]['公示天'] <= tiers[i - 1]['公示天']:
            raise SystemExit(f'采购公示天须随金额分档递增：{tiers[i]["档"]} 反而不高于前一档')
    if tiers[-1]['金额上限_钛币'] is not None:
        raise SystemExit('最高采购档必须不设上限，否则大额采购无归属')
    return tax, tiers


def build_relations():
    rel = sorted(P['关系与文化阈值']['关系层级'], key=lambda x: x['阶'])
    for i in range(1, len(rel)):
        if rel[i]['累计有效互动下限'] <= rel[i - 1]['累计有效互动下限']:
            raise SystemExit(f'关系阈值非单调：第 {rel[i]["阶"]} 阶下限 {rel[i]["累计有效互动下限"]} 不高于第 {rel[i - 1]["阶"]} 阶')
    if [r['阶'] for r in rel] != list(range(1, len(rel) + 1)):
        raise SystemExit('关系阶次不连续')
    cul = P['关系与文化阈值']['文化层级']
    if {c['码'] for c in cul} != {'CUL-01', 'CUL-02', 'CUL-03', 'CUL-04'}:
        raise SystemExit('文化四层被改动：底座、片区、社区与传闻层缺一不可')
    rum = sorted(P['关系与文化阈值']['传闻失真'], key=lambda x: x['档'])
    for i in range(1, len(rum)):
        if rum[i]['失真比例千分比'] <= rum[i - 1]['失真比例千分比']:
            raise SystemExit(f'传闻失真档位非单调：{rum[i]["档"]}')
    if rum[-1]['判定影响'] != '禁止':
        raise SystemExit('最高失真档必须判禁止扩散，否则传闻层会进判定')
    return rel, cul, rum


def build_ui():
    ui = sorted(P['界面与导出']['层级'], key=lambda x: x['优先级'])
    if [u['优先级'] for u in ui] != list(range(1, len(ui) + 1)):
        raise SystemExit('界面优先级不连续或重复')
    known = {u['码'] for u in ui} | {s['码'] for s in P['界面与导出']['摘要跨度']}
    covered = set()
    for lvl in P['界面与导出']['免打扰分级']:
        for member in lvl['成员']:
            if member not in known:
                raise SystemExit(f'免打扰级别 {lvl["级"]} 点名了不存在的界面项 {member}')
            if member in covered:
                raise SystemExit(f'界面项 {member} 挂在两个免打扰级别下')
            covered.add(member)
    if covered != known:
        raise SystemExit(f'有界面项没归入免打扰分级：{sorted(known - covered)}')
    if P['界面与导出']['免打扰分级'][0]['成员'] != ['UI-01']:
        raise SystemExit('不可静音项只能是最高的事实条：放宽即失去「只有生效构成事实」这条口径')
    exports = []
    for ex in P['界面与导出']['导出格式']:
        target = ROOT / ex['承载产物']
        if not target.exists():
            raise SystemExit(f'导出格式 {ex["码"]} 声称能出 {ex["承载产物"]}，但该产物不在盘上：不承诺没有承载体的格式')
        exports.append(dict(ex, 产物存在=True))
    return ui, exports


def build_ai():
    free = P['AI自由层']['可自由补全']
    stop = P['AI自由层']['须停止确认']
    codes = {f['码'] for f in free} | {s['码'] for s in stop}
    referenced = set()
    for c in P['AI自由层']['更正提示']:
        refs = [w for w in c['适用'].replace('、', ' ').split() if w in codes]
        if not refs:
            raise SystemExit(f'更正提示 {c["码"]} 没引用任何自由层或停止项：它无的放矢')
        referenced.update(refs)
    if referenced != codes:
        raise SystemExit(f'自由层或停止项缺更正通道：{sorted(codes - referenced)}')
    if not any('不适用，一律拒绝' in s['确认主体'] for s in stop):
        raise SystemExit('须停止确认里必须保留无确认通道的拒绝项，否则公职与中断类禁令会被“走确认”绕过')
    return free, stop


def build_compat():
    rows = []
    for r in P['版本兼容']['行']:
        target = ROOT / r['对象']
        if r['对象'] == '数据/流程制度正典.json':
            actual = SOURCE['version']
        else:
            if not target.exists():
                raise SystemExit(f'版本兼容行点名 {r["对象"]}，该文件不在盘上')
            actual = json.loads(target.read_text(encoding='utf-8')).get('version')
        if r['声明版本'] != actual:
            raise SystemExit(f'{r["对象"]} 声明版本 {r["声明版本"]}，盘上是 {actual}：改了正典版本必须同步兼容矩阵')
        if r['旧轮次下限'] != SOURCE['setting_year']:
            raise SystemExit(f'{r["对象"]} 的旧轮次下限 {r["旧轮次下限"]} 与基准年 {SOURCE["setting_year"]} 不一致')
        rows.append(dict(r, 实际版本=actual, 一致=True))
    return rows


def build_canon():
    festivals, days_of_sea = build_festivals()
    orgs, posts = build_orgs()
    check_gov_not_employable(posts)
    objects, gates = build_registration()
    co_steps, anon_steps, med = build_flows()
    contracts = build_contracts()
    events, by_level = build_events()
    tax, tiers = build_finance()
    rel, cul, rum = build_relations()
    ui, exports = build_ui()
    free, stop = build_ai()
    compat = build_compat()
    canon = dict(SOURCE)
    canon['节庆年历'] = sorted(festivals, key=lambda f: f['年内第几天'])
    canon['机构'] = orgs
    canon['公职'] = posts
    canon['登记对象'] = objects
    canon['门禁项'] = gates
    canon['事件目录'] = events
    canon['合同存续'] = contracts
    canon['税种'] = tax
    canon['采购分档'] = tiers
    canon['关系层级'] = rel
    canon['文化层级'] = cul
    canon['传闻失真'] = rum
    canon['界面层级'] = ui
    canon['导出格式'] = exports
    canon['版本兼容'] = compat
    canon['汇总'] = {
        '节庆条数': len(festivals), '节庆占天次': sum(f['日期跨度天'] for f in festivals),
        '节庆逐季占天': dict(sorted(days_of_sea.items())),
        '机构数': len(orgs), '公职条目数': len(posts),
        '公职编制合计': sum(p['编制'] for p in posts), '机构编制合计': sum(o['编制'] for o in orgs),
        '登记对象数': len(objects), '门禁项数': len(gates),
        '共创步骤数': len(co_steps), '删除步骤数': len(anon_steps), '删除字段数': len(P['匿名化与删除']['字段']),
        '调解主体数': len(med['受理主体']), '争议类别数': len(med['争议类别']),
        '拉黑动作数': len(P['拉黑后合同']['动作']), '合同存续数': len(contracts),
        '事件模板数': len(events), '各级模板数': {lvl: len(v) for lvl, v in sorted(by_level.items())},
        '负面模板数': sum(1 for e in events if e['负面']), '随机触发数': sum(1 for e in events if e['触发方式'] == 'TRG-RANDOM'),
        '税种数': len(tax), '采购档数': len(tiers),
        '关系阶数': len(rel), '文化层数': len(cul), '失真档数': len(rum),
        '界面层级数': len(ui), '导出格式数': len(exports),
        '自由层条数': len(free), '停止确认条数': len(stop), '版本兼容行数': len(compat),
        '口径': '本期只登记流程与制度的固定值：时限按公共日计，一律查表，零随机、零逐人模拟。'
                '公职只作背景存在，不进岗位名录、招聘、合同与账本；调解只收尾不裁决；'
                '拉黑与撤销授权不单方解除已生效合同；事件冷却与预告天与第4期同源；'
                '任何流程都不得中断供给、封闭路线或增加交通耗时。'
    }
    return canon


def _cell(v):
    if v is None:
        return '—'
    if isinstance(v, bool):
        return '是' if v else '否'
    if isinstance(v, dict):
        return '、'.join(f'{k} {x}' for k, x in v.items())
    if isinstance(v, list):
        return '、'.join(str(x) for x in v)
    return str(v)


def _md(v):
    return _cell(v).replace('|', '\\|')


def render_table(canon):
    p = canon['参数']
    L = ['# 流程与制度总表', '',
         f'本文件由 `工具/build_flows.py` 生成，基准年 {canon["setting_year"]}，货币 钛币（TT），禁止手改。', '',
         f'规模：节庆与纪念日 {canon["汇总"]["节庆条数"]} 条（占 {canon["汇总"]["节庆占天次"]} 天次）、'
         f'机构 {canon["汇总"]["机构数"]} 个、背景公职 {canon["汇总"]["公职条目数"]} 条（编制合计 '
         f'{canon["汇总"]["公职编制合计"]}，机构编制合计 {canon["汇总"]["机构编制合计"]}）、'
         f'事件模板 {canon["汇总"]["事件模板数"]} 条、合同存续 {canon["汇总"]["合同存续数"]} 条。', '']

    L += ['## 一、节庆与纪念日年历（2013 公共日历，零随机）', '',
          '| 编号 | 名称 | 类型 | 级别 | 起 | 止 | 星期 | 年内第几天 | SEA | 季节 | 天数 | 锚点 |',
          '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for f in canon['节庆年历']:
        L.append(f'| {f["编号"]} | {f["名称"]} | {f["类型"]} | {f["级别"]} | {f["月"]}-{f["日"]:02d} | '
                 f'{f["结束月"]}-{f["结束日"]:02d} | {f["星期"]} | {f["年内第几天"]} | {f["SEA"]} | {f["季节名"]} | '
                 f'{f["日期跨度天"]} | {_md([a["码"] + " " + a["名"] for a in f["锚点明细"]])} |')
    L += ['', '| 季 | 占天次 |', '| --- | --- |']
    for sea, n in canon['汇总']['节庆逐季占天'].items():
        L.append(f'| {sea}（{SEASON_NAME[sea]}） | {n} |')

    L += ['', '## 二、公共机构与背景公职（不进岗位名录）', '',
          '| 编号 | 名称 | 层级 | 驻地 | 驻地类型 | 编制 | 登记公职数 | 登记编制小计 | 锚点岗位规模 | 公开信息 |',
          '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for o in canon['机构']:
        L.append(f'| {o["编号"]} | {o["名称"]} | {o["层级"]} | {o["驻地"]["码"]} {o["驻地"]["名"]} | '
                 f'{o["驻地"]["层级"]} | {o["编制"]} | {o["登记公职数"]} | {o["登记编制小计"]} | '
                 f'{_cell(o["锚点岗位规模"])} | {o["公开信息"]} |')
    L += ['', '| 编号 | 名称 | 机构 | 层级 | 参照层 | 编制 | 职责 |', '| --- | --- | --- | --- | --- | --- | --- |']
    for g in canon['公职']:
        L.append(f'| {g["编号"]} | {g["名称"]} | {g["机构"]} | {g["层级"]} | {g["参照层"]} | {g["编制"]} | {g["职责"]} |')

    L += ['', '## 三、新条目登记与门禁项', '',
          '| 码 | 名称 | 必填字段 | 落点源表 | 校验工具 | 附校验 |', '| --- | --- | --- | --- | --- | --- |']
    for o in canon['登记对象']:
        L.append(f'| {o["码"]} | {o["名称"]} | {_md(o["必填字段"])} | {o["落点源表"]} | {o["校验工具"]} | '
                 f'{_md(o["附校验"])} |')
    L += ['', '| 编号 | 名称 | 判据 | 承载脚本 |', '| --- | --- | --- | --- |']
    for g in canon['门禁项']:
        L.append(f'| {g["编号"]} | {g["名称"]} | {g["判据"]} | 工具/{g["承载脚本"]} |')

    L += ['', '## 四、共创转永久审核', '', f'公示 {p["共创转永久"]["公示天"]} 天，异议窗口 '
          f'{p["共创转永久"]["异议窗口天"]} 天，同内容生效冷却 {p["共创转永久"]["生效冷却天"]} 天。', '',
          '| 序号 | 名称 | 责任主体 | 时限天 | 可跳过按规则结算 | 产出记录 |', '| --- | --- | --- | --- | --- | --- |']
    for s in canon['参数']['共创转永久']['步骤']:
        L.append(f'| {s["序号"]} | {s["名称"]} | {s["责任主体"]} | {s["时限天"]} | '
                 f'{_cell(s["可跳过按规则结算"])} | {s["产出记录"]} |')

    L += ['', '## 五、匿名化与删除', '', '| 码 | 名称 | 类别 | 处置 | 保留天 | 依据主题 |',
          '| --- | --- | --- | --- | --- | --- |']
    for f in p['匿名化与删除']['字段']:
        L.append(f'| {f["码"]} | {f["名称"]} | {f["类别"]} | {f["处置"]} | {f["保留天"]} | 第{f["依据主题"]}主题 |')
    L += ['', '| 序号 | 名称 | 责任主体 | 时限天 | 产出记录 |', '| --- | --- | --- | --- | --- |']
    for s in p['匿名化与删除']['步骤']:
        L.append(f'| {s["序号"]} | {s["名称"]} | {s["责任主体"]} | {s["时限天"]} | {s["产出记录"]} |')

    L += ['', '## 六、调解受理与争议类别', '', '| 码 | 名称 | 层级 | 受理类别 | 时限天 | 结果形态 | 前置 |',
          '| --- | --- | --- | --- | --- | --- | --- |']
    for b in p['调解与争议']['受理主体']:
        L.append(f'| {b["码"]} | {b["名称"]} | {b["层级"]} | '
                 f'{_md([c + " " + n for c, n in zip(b["受理类别"], b["受理类别名"])])} | {b["时限天"]} | '
                 f'{_md(b["结果形态"])} | {b["前置"]} |')
    L += ['', '| 码 | 名称 | 涉及账本 | 可跳过按规则结算 | 跳过结算 | 记录方式 |', '| --- | --- | --- | --- | --- | --- |']
    for d in p['调解与争议']['争议类别']:
        L.append(f'| {d["码"]} | {d["名称"]} | {d["涉及账本"]} | {_cell(d["可否跳过按规则结算"])} | '
                 f'{d["跳过结算"]} | {d["记录方式"]} |')

    L += ['', '## 七、拉黑与撤销授权后的合同存续', '',
          '| 合同类型 | 名称 | 用工形态 | 结算周期 | 存续 | 用人方为拉黑方 | 共同财产 | 结算 | 解除条件数 |',
          '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for c in canon['合同存续']:
        L.append(f'| {c["合同类型"]} | {c["名称"]} | {c["用工形态"]} | {c["薪酬结算周期"]} | {c["存续"]} | '
                 f'{c["用人方为拉黑方"]} | {c["共同财产"]} | {c["结算"]} | {c["解除条件数"]} |')

    L += ['', '## 八、四级事件目录与模板', '', '| 码 | 名称 | 口径 |', '| --- | --- | --- |']
    for t in p['事件目录']['触发方式']:
        L.append(f'| {t["码"]} | {t["名称"]} | {t["口径"]} |')
    L += ['', '| 编号 | 名称 | 级别 | 冷却天 | 预告天 | 触发方式 | 负面 | 占用负面配额 | 涉及账本 |',
          '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for e in canon['事件目录']:
        L.append(f'| {e["编号"]} | {e["名称"]} | {e["级别"]} | {e["冷却天"]} | {e["预告天"]} | {e["触发方式名"]} | '
                 f'{_cell(e["负面"])} | {_cell(e["占用负面配额"])} | {e["涉及账本"]} |')

    L += ['', '## 九、公共财政：税种与采购分档', '',
          '| 码 | 名称 | 税基 | 税率千分比 | 起征（钛币） | 结算周期 | 减免挂钩 |', '| --- | --- | --- | --- | --- | --- | --- |']
    for t in canon['税种']:
        L.append(f'| {t["码"]} | {t["名称"]} | {t["税基"]} | {t["税率千分比"]} | {t["起征_钛币"]} | '
                 f'{t["结算周期"]} | {t["减免挂钩"]} |')
    L += ['', '| 档 | 金额下限 | 金额上限 | 受理主体 | 流程 | 公示天 | 异议天 |',
          '| --- | --- | --- | --- | --- | --- | --- |']
    for t in canon['采购分档']:
        L.append(f'| {t["档"]} | {t["金额下限_钛币"]} | {_cell(t["金额上限_钛币"])} | {t["受理主体"]} | '
                 f'{_md(t["流程"])} | {t["公示天"]} | {t["异议天"]} |')

    L += ['', '## 十、关系与文化阈值', '', '| 阶 | 名称 | 累计有效互动下限 | 可见范围 | 可解锁动作 |',
          '| --- | --- | --- | --- | --- |']
    for r in canon['关系层级']:
        L.append(f'| {r["阶"]} | {r["名称"]} | {r["累计有效互动下限"]} | {r["可见范围"]} | {_md(r["可解锁动作"])} |')
    L += ['', '| 码 | 名称 | 范围 | 登记入口 | 可差异 | 口径 |', '| --- | --- | --- | --- | --- | --- |']
    for c in canon['文化层级']:
        L.append(f'| {c["码"]} | {c["名称"]} | {c["范围"]} | {c["登记入口"]} | {_cell(c["可差异"])} | {c["口径"]} |')
    L += ['', '| 档 | 名称 | 失真比例千分比 | 判定影响 | 口径 |', '| --- | --- | --- | --- | --- |']
    for r in canon['传闻失真']:
        L.append(f'| {r["档"]} | {r["名称"]} | {r["失真比例千分比"]} | {r["判定影响"]} | {r["口径"]} |')

    L += ['', '## 十一、界面层级、免打扰与导出格式', '',
          '| 码 | 优先级 | 名称 | 内容 | 刷新频率 | 免打扰级别 |', '| --- | --- | --- | --- | --- | --- |']
    quiet_of = {}
    for lvl in p['界面与导出']['免打扰分级']:
        for m in lvl['成员']:
            quiet_of[m] = f'{lvl["级"]} {lvl["名称"]}'
    for u in canon['界面层级']:
        L.append(f'| {u["码"]} | {u["优先级"]} | {u["名称"]} | {u["内容"]} | {u["刷新频率"]} | '
                 f'{quiet_of.get(u["码"], "未分级")} |')
    L += ['', '| 码 | 名称 | 跨度天 | 覆盖 | 免打扰分级 |', '| --- | --- | --- | --- | --- |']
    for s in p['界面与导出']['摘要跨度']:
        L.append(f'| {s["码"]} | {s["名称"]} | {s["跨度天"]} | {s["覆盖"]} | {quiet_of.get(s["码"], "未分级")} |')
    L += ['', '| 码 | 格式 | 承载产物 | 在盘 | 用途 | 可访问性检查 |', '| --- | --- | --- | --- | --- | --- |']
    for e in canon['导出格式']:
        L.append(f'| {e["码"]} | {e["格式"]} | {e["承载产物"]} | {"是" if e["产物存在"] else "否"} | {e["用途"]} | '
                 f'{_md(e["可访问性检查"])} |')

    L += ['', '## 十二、AI 自由层与停止确认', '', '| 码 | 名称 | 边界 |', '| --- | --- | --- |']
    for f in p['AI自由层']['可自由补全']:
        L.append(f'| {f["码"]} | {f["名称"]} | {f["边界"]} |')
    L += ['', '| 码 | 名称 | 依据主题 | 确认主体 | 口径 |', '| --- | --- | --- | --- | --- |']
    for s in p['AI自由层']['须停止确认']:
        L.append(f'| {s["码"]} | {s["名称"]} | 第{s["依据主题"]}主题 | {s["确认主体"]} | {s["口径"]} |')
    L += ['', '| 码 | 名称 | 适用 | 形式 | 记录 |', '| --- | --- | --- | --- | --- |']
    for c in p['AI自由层']['更正提示']:
        L.append(f'| {c["码"]} | {c["名称"]} | {c["适用"]} | {c["形式"]} | {c["记录"]} |')

    L += ['', '## 十三、版本兼容矩阵', '',
          '| 对象 | 声明版本 | 实际版本 | 一致 | 旧轮次下限 | 兼容策略 | 破坏性变更 | 登记入口 |',
          '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in canon['版本兼容']:
        L.append(f'| {r["对象"]} | {r["声明版本"]} | {r["实际版本"]} | {_cell(r["一致"])} | {r["旧轮次下限"]} | '
                 f'{r["兼容策略"]} | {_md(r["破坏性变更"])} | {r["登记入口"]} |')

    L += ['', '## 十四、各组禁则与口径', '']
    for key in ('节庆', '机构与公职', '新条目登记', '共创转永久', '匿名化与删除', '调解与争议',
                '拉黑后合同', '事件目录', '公共财政', '关系与文化阈值', '界面与导出', 'AI自由层', '版本兼容'):
        sec = p[key]
        L.append(f'- **{key}** 口径：{sec.get("口径", "（本节无独立口径句）")}')
        for rule in sec.get('禁则', []):
            L.append(f'  - 禁则：{rule}')
    L += ['', '## 十五、检查点与负面配额同源读数', '', '| 项 | 值 |', '| --- | --- |']
    L.append(f'| 各级冷却天（第4期） | {_cell(COOLDOWN)} |')
    L.append(f'| 预告天（第4期） | {_cell(ADVANCE)} |')
    L.append(f'| 负面配额（第4期） | {_cell(RUN["参数"]["事件"]["负面配额"])} |')
    L.append(f'| 本期负面模板数 | {canon["汇总"]["负面模板数"]} |')
    return '\n'.join(L) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out-dir', default=str(ROOT / '数据'))
    ap.add_argument('--print-summary', action='store_true')
    args = ap.parse_args()
    canon = build_canon()
    if args.print_summary:
        print(json.dumps(canon['汇总'], ensure_ascii=False))
        return
    out = Path(args.out_dir)
    (out / '流程制度正典.json').write_bytes(
        (json.dumps(canon, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    (out / '流程制度总表.md').write_text(render_table(canon), encoding='utf-8')
    print(json.dumps(canon['汇总'], ensure_ascii=False))


if __name__ == '__main__':
    main()
