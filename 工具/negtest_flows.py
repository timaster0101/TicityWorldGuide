# -*- coding: utf-8 -*-
"""第5期流程与制度闸门的违例自检：把闸门与七份数据复制到临时目录，逐条改坏正典或源表，断言闸门必须判红且给出该条自己的措辞。

闸门只会打印「全绿」，无法自证它抓得住违例；本脚本按 25 条判据反向注入 28 例，只操作临时副本，
绝不改动被守护的仓库文件。跑完复核夹具零残留。
跑法：python 工具/negtest_flows.py
"""
import calendar
import datetime
import inspect
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ['verify_flows.py']
DATA = ['流程制度正典.json', '流程制度源表.json', '城市空间名录.json', '产业就业正典.json',
        '岗位准入正典.json', '运行参数正典.json', '空间通行正典.json']
TMP_PREFIX = 'flowneg-'
WEEKDAYS = ('周一', '周二', '周三', '周四', '周五', '周六', '周日')


def canon_of(tmp):
    return json.loads((tmp / '数据' / '流程制度正典.json').read_text(encoding='utf-8'))


def src_of(tmp):
    return json.loads((tmp / '数据' / '流程制度源表.json').read_text(encoding='utf-8'))


def row(rows, key, value):
    return next(r for r in rows if r[key] == value)


def _set_end(c, f):
    """改了跨度就同步结束日，好让「日期可复算」这条不被牵连，判红只落在目标判据上。"""
    year = c['setting_year']
    end = datetime.date(year, f['月'], f['日']) + datetime.timedelta(days=f['日期跨度天'] - 1)
    f['天数'] = f['日期跨度天']
    f['结束月'], f['结束日'] = end.month, end.day


def referenced(c):
    """夹具必须带上判据点名的真实文件：落点源表、承载脚本、导出产物、版本兼容对象。"""
    return sorted(set(
        [o['落点源表'] for o in c['登记对象']]
        + ['工具/' + g['承载脚本'] for g in c['门禁项']]
        + ['工具/' + t for o in c['登记对象'] for t in [o['校验工具']] + o['附校验']]
        + [e['承载产物'] for e in c['导出格式']]
        + [r['对象'] for r in c['版本兼容']]))


def build_fixture(tmp):
    (tmp / '工具').mkdir()
    (tmp / '数据').mkdir()
    for f in TOOLS + DATA:
        shutil.copy2(ROOT / ('工具' if f.endswith('.py') else '数据') / f,
                     tmp / ('工具' if f.endswith('.py') else '数据') / f)
    canon = canon_of(tmp)
    for rel in referenced(canon):
        src = ROOT / rel
        if not src.exists():
            raise SystemExit(f'夹具缺 {rel}：本仓产物不在盘上，负测不成立')
        (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, tmp / rel)
        else:
            shutil.copy2(src, tmp / rel)
    return canon, src_of(tmp)


def cases():
    """返回 (用例名, 改动函数, 期望判据名)；改动只动临时副本。"""

    def fest_weekday(c):
        f = c['节庆年历'][0]
        f['星期'] = next(w for w in WEEKDAYS if w != f['星期'])

    def fest_clash(c):
        rows = sorted(c['节庆年历'], key=lambda x: x['年内第几天'])
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                shared = set(rows[i]['范围锚点']) & set(rows[j]['范围锚点'])
                if shared:
                    rows[i]['日期跨度天'] = rows[j]['年内第几天'] - rows[i]['年内第几天'] + 1
                    _set_end(c, rows[i])
                    return
        raise AssertionError('夹具里找不到共用锚点的两个档期，排期冲突无法注入')

    def fest_cross_season(c):
        """把档期拉到「越过本月最后一天且不越出 2013 年」，让它踩进下一季的月份。"""
        run = json.loads((Path(__file__).resolve().parents[1] / '数据' /
                          '运行参数正典.json').read_text(encoding='utf-8'))['月季节']
        year = c['setting_year']
        for f in c['节庆年历']:
            if f['月'] >= 12:
                continue
            last = calendar.monthrange(year, f['月'])[1]
            if run[str(f['月'] + 1)] != f['SEA']:
                f['日期跨度天'] = last - f['日'] + 2
                _set_end(c, f)
                return
        raise AssertionError('夹具里没有可以在年内跨季的档期起点')

    def fest_anchor_gone(c):
        for f in c['节庆年历']:
            if f['级别'] == '社区' and all(a[0] in 'SR' for a in f['范围锚点']):
                f['范围锚点'] = ['S99'] + f['范围锚点'][1:]
                return
        raise AssertionError('夹具里没有可改成虚构锚点的社区级档期')

    def fest_level_wrong(c):
        for f in c['节庆年历']:
            if f['级别'] == '社区' and all(a[0] in 'S' for a in f['范围锚点']):
                f['级别'] = '片区'
                return
        raise AssertionError('夹具里没有只挂聚落锚点的社区级档期')

    def fest_form_dup(c):
        a, b = c['节庆年历'][0], c['节庆年历'][1]
        b['活动形式'] = list(a['活动形式'])

    def org_level_wrong(c):
        c['机构'][0]['层级'] = '街区'

    def org_quota_over(c):
        p = c['公职'][0]
        o = row(c['机构'], '编号', p['机构'])
        p['编制'] = o['编制'] + 1

    def gov_in_registry(c):
        c['公职'][0]['编号'] = 'L001'

    def register_target_gone(c):
        c['登记对象'][0]['落点源表'] = '数据/根本不存在的源表.json'

    def gate_tool_gone(c):
        c['门禁项'][0]['承载脚本'] = 'verify_never_written.py'

    def co_advance(c):
        c['参数']['共创转永久']['公示天'] += 1

    def delete_field(c):
        f = row(c['参数']['匿名化与删除']['字段'], '处置', '删除')
        f['保留天'] = 30

    def mediation_category(c):
        c['参数']['调解与争议']['受理主体'][1]['受理类别'] = ['DSP-99']

    def contract_row(c):
        c['合同存续'][3]['合同类型'] = 'CTR-90'

    def event_cooldown(c):
        e = row(c['事件目录'], '级别', '社区')
        e['冷却天'] = e['冷却天'] + 1

    def event_level_count(c):
        lvl = next(iter(c['汇总']['各级模板数']))
        c['汇总']['各级模板数'][lvl] += 1

    def purchase_seam(c):
        c['采购分档'][1]['金额下限_钛币'] += 1

    def relation_monotonic(c):
        c['关系层级'][3]['累计有效互动下限'] = 0

    def export_carrier(c):
        c['导出格式'][0]['承载产物'] = '根本不存在的产物.md'

    def ai_reference(c):
        c['参数']['AI自由层']['更正提示'][0]['适用'] = 'ZZ-99 无对应条目'

    def compat_version(c):
        r = row(c['版本兼容'], '对象', '数据/城市空间名录.json')
        r['声明版本'] = '9.9'

    def summary_count(c):
        c['汇总']['节庆条数'] += 1

    def disruption_allowed(c):
        c['参数']['调解与争议']['争议类别'][0]['跳过结算'] = '可直接封闭路线并临时调价结算'

    def org_nature_unknown(c):
        row(c['机构'], '编号', 'ORG-03')['性质'] = '商业公司'

    def org_edu_with_posts(c):
        """性质换成「不可挂公职」这一档，公职表一行不动——公共教育组织只该有成员与教员。"""
        row(c['机构'], '编号', 'ORG-01')['性质'] = '公共教育组织'

    def island_peak_over_grass(c):
        f = row(c['节庆年历'], '编号', 'FE-19')
        f['峰值人数'] = next(r['容量人'] for r in sp_sites() if r['类'] == '草地广场') + 800

    def island_peak_off_island(c):
        f = c['节庆年历'][0]
        assert all(a not in ('PL-01', 'PL-02', 'PL-03') for a in f['范围锚点']), f['编号']
        f['峰值人数'] = 1200

    def sp_sites():
        sp = json.loads((ROOT / '数据' / '空间通行正典.json').read_text(encoding='utf-8'))
        return sp['岛上场地']

    return [
        ('节庆星期手改', fest_weekday, '节庆日期可复算'),
        ('档期拉长撞同一锚点同一天', fest_clash, '节庆排期无冲突'),
        ('档期跨过季界', fest_cross_season, '节庆不跨季不越年'),
        ('节庆锚点改成不存在的编号', fest_anchor_gone, '节庆锚点有承载体'),
        ('聚落档期抬成片区级', fest_level_wrong, '节庆级别与范围相容'),
        ('两个档期同一套活动形式', fest_form_dup, '节庆活动形式不重复'),
        ('机构层级跳出三级', org_level_wrong, '机构三级且驻地可解'),
        ('公职编制超机构编制', org_quota_over, '公职编制不越机构与锚点规模'),
        ('公职编号撞名录条目', gov_in_registry, '公职不进岗位名录'),
        ('登记落点指向不存在的源表', register_target_gone, '登记落点在盘'),
        ('门禁项指向不存在的脚本', gate_tool_gone, '门禁项承载脚本在盘'),
        ('共创公示天脱离步骤', co_advance, '共创时限与步骤同源'),
        ('判删除却留保留期', delete_field, '删除处置与保留期自洽'),
        ('调解受理编出争议类别表外的码', mediation_category, '调解受理闭合'),
        ('合同存续少一种类型', contract_row, '合同存续与字典一一对应'),
        ('事件冷却天脱离第4期', event_cooldown, '事件冷却与第4期同源'),
        ('事件分级计数手改', event_level_count, '事件目录分级计数一致'),
        ('采购分档断开接缝', purchase_seam, '税率与采购分档自洽'),
        ('关系阈值改成不升', relation_monotonic, '关系与文化阈值单调'),
        ('导出格式指向不存在的产物', export_carrier, '界面分级全覆盖且导出有产物'),
        ('更正提示指不到任何条目', ai_reference, 'AI自由层引用闭合'),
        ('版本兼容声明与盘上脱钩', compat_version, '版本兼容逐行等于盘上'),
        ('汇总计数手改', summary_count, '汇总与逐表行数一致'),
        ('流程里写出无否定式的封闭许可', disruption_allowed, '汇总与逐表行数一致'),
        ('机构性质写出字典外', org_nature_unknown, '机构性质与公职资格同源'),
        ('带公职的机构改成不可挂公职', org_edu_with_posts, '机构性质与公职资格同源'),
        ('岛上演唱会峰值超广场容量', island_peak_over_grass, '岛上峰值人数不越广场容量'),
        ('陆地节庆登记了峰值人数', island_peak_off_island, '岛上峰值人数不越广场容量'),
    ]


def run_gate(tmp):
    r = subprocess.run([sys.executable, str(tmp / '工具' / 'verify_flows.py')],
                       cwd=tmp, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def failed_checks(tmp):
    p = tmp / '数据' / '流程制度核验.json'
    if not p.exists():
        return []
    return [k for k, v in json.loads(p.read_text(encoding='utf-8'))['details'].items() if v]


def main():
    results, failures = [], []
    for name, mutate, expected in cases():
        tmp = Path(tempfile.mkdtemp(prefix=TMP_PREFIX))
        try:
            objs = dict(zip('cs', build_fixture(tmp)))
            rc0, out0 = run_gate(tmp)
            if rc0 != 0:
                raise SystemExit(f'夹具本来就不绿（{name}）：{out0}')
            args = [p for p in inspect.signature(mutate).parameters]
            mutate(*[objs[k] for k in args])
            (tmp / '数据' / '流程制度正典.json').write_text(
                json.dumps(objs['c'], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            if 's' in args:
                (tmp / '数据' / '流程制度源表.json').write_text(
                    json.dumps(objs['s'], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            rc, out = run_gate(tmp)
            bad = failed_checks(tmp)
            red = rc != 0 and expected in out and expected in bad
            results.append(dict(case=name, red=red, only=bad == [expected]))
            print(('OK ' if red else '!! ') + f'{name}：注入后 rc={rc}，判红集合 {bad}，'
                  f'期望「{expected}」' + ('（唯一判红）' if red and bad == [expected] else '')
                  + ('' if red else '（没判红！）'))
            if not red:
                failures.append(name)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    leftover = [p for p in Path(tempfile.gettempdir()).glob(TMP_PREFIX + '*') if p.is_dir()]
    print(json.dumps(dict(cases=len(results), red=len(results) - len(failures), not_red=len(failures),
                          only_target=len([r for r in results if r['only']]),
                          fixture_leftover=len(leftover)), ensure_ascii=False))
    if failures or leftover:
        sys.exit(1)
    print(f'第5期流程闸门违例自检通过：{len(results)} 个违例全部判红且措辞对得上，夹具零残留')


if __name__ == '__main__':
    main()
