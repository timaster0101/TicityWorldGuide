# -*- coding: utf-8 -*-
"""第5期构件闸门的违例自检：把闸门与四份数据复制到临时目录，逐条改坏正典或第4期源表，断言闸门必须判红且给出该条自己的措辞。

闸门只会打印"全绿"，无法自证它抓得住违例；本脚本按十八判反向注入 27 例，只操作临时副本，
绝不改动被守护的仓库文件。跑完复核夹具零残留。
跑法：python 工具/negtest_spatial.py
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ['verify_spatial.py', 'anchors.py']
DATA = ['城市空间名录.json', '空间通行正典.json', '空间通行源表.json', '运行参数源表.json',
        '参考房价租金.json']  # anchors.py 在导入时就读房价租金，夹具必须带上
TMP_PREFIX = 'spneg-'


def canon_of(tmp):
    return json.loads((tmp / '数据' / '空间通行正典.json').read_text(encoding='utf-8'))


def prm_of(tmp):
    return json.loads((tmp / '数据' / '运行参数源表.json').read_text(encoding='utf-8'))


def src_of(tmp):
    return json.loads((tmp / '数据' / '空间通行源表.json').read_text(encoding='utf-8'))


OBJ_NAMES = ['canon', 'prm', 'src']
FILES = {'canon': '空间通行正典.json', 'prm': '运行参数源表.json', 'src': '空间通行源表.json'}


def row(rows, code):
    return next(r for r in rows if r['码'] == code)


def cases():
    """返回 (用例名, 改动函数, 期望判红字样)；改动只动临时副本，形参个数即注入范围。"""

    def bridge_span(c):
        row(c['桥梁'], 'BR-01')['跨度m'] = 999.9

    def bridge_off_axis(c):
        r = row(c['桥梁'], 'BR-01')
        r['桥头A_km'] = [-1.798 + 1.0, 7.558 + 1.0]
        r['桥头B_km'] = [-2.202 + 1.0, 7.442 + 1.0]

    def bridge_parallel(c):
        r = row(c['桥梁'], 'BR-01')
        r['桥头B_km'] = [-2.2, 9.0]

    def bridge_ratio(c):
        r = row(c['桥梁'], 'BR-01')
        r['桥头A_km'] = [-1.798, 7.558]
        r['桥头B_km'] = [-1.798 + 4 * (r['桥头A_km'][0] - -2.202), 7.558 + 4 * (7.558 - 7.442)]

    def bridge_in_lake(c):
        r = row(c['桥梁'], 'BR-02')
        r['桥头A_km'] = [0.0, 0.0]
        r['桥头B_km'] = [1.0, 0.0]

    def wharf_off_bank(c):
        row(c['渡位'], 'WH-06')['坐标km'] = [-3.4, 10.6]

    def wharf_off_lakeline(c):
        row(c['渡位'], 'WH-01')['坐标km'] = [0.0, 2.6]

    def route_mixed_water(c):
        row(c['轮渡航线'], 'FR-01')['渡位B'] = 'WH-06'

    def route_minutes(c):
        row(c['轮渡航线'], 'FR-01')['耗时分钟'] = 25

    def route_segment(c):
        row(c['轮渡航线'], 'FR-01')['航段km'] = 5.0

    def pass_inside_basin(c):
        row(c['山口通道'], 'PA-01')['讫点km'] = [10.0, 10.0]

    def pass_near_anchor(c, _prm, src):
        src['参数']['容差']['山外讫点离任一锚点下限千米'] = 25.0

    def pass_box_exit(c):
        row(c['山口通道'], 'PA-03')['盆界交点km'] = [10.0, 32.0]

    def pass_walking_line(c):
        row(c['山口通道'], 'PA-04')['班线每日'] = 5

    def pass_no_line(c):
        row(c['山口通道'], 'PA-01')['班线每日'] = 0

    def pass_flag(c):
        row(c['山口通道'], 'PA-01')['载客'] = False

    def pass_kind_missing(c):
        c['山口通道'] = [r for r in c['山口通道'] if r['码'] != 'PA-04']

    def pass_minutes(c):
        row(c['山口通道'], 'PA-01')['耗时分钟'] = 90

    def pass_km(c):
        row(c['山口通道'], 'PA-02')['里程km'] = 50.0

    def lake_no_ferry(c):
        for code in ('FR-01', 'FR-02', 'FR-03'):
            row(c['轮渡航线'], code)['临'] = 'W02'

    def river_no_bridge(c):
        c['桥梁'] = [r for r in c['桥梁'] if r['跨越'] != 'W02']

    def ring_uncovered(c):
        for r in c['桥梁'] + c['轮渡航线']:
            r['A圈层'] = r['B圈层'] = '内湖环'
        for r in c['山口通道']:
            r['门户圈层'] = '内湖环'

    def matrix_pair_key(c):
        row(c['桥梁'], 'BR-01')['圈层对'] = '内湖环|内湖环'

    def summary_count(c):
        c['汇总']['桥梁数'] = 99

    def code_format(c):
        row(c['轮渡航线'], 'FR-01')['码'] = 'FERRY-1'

    def heads_same_side(c):
        r = row(c['桥梁'], 'BR-01')
        r['桥头B_km'] = list(r['桥头A_km'])

    def deferred_prm(c, prm):
        prm['参数']['交通']['延后方式'].append({'码': 'TR-FERRY', '名': '轮渡', '待': '旧口径'})

    def outside_prm(c, prm):
        prm['参数']['交通']['矩阵外方式'][0]['真源'] = '数据/别处的表.json'

    def outside_matrix_prm(c, prm):
        prm['参数']['交通']['方式'][0]['码'] = 'TR-FERRY'

    return [
        ('桥跨度手改', bridge_span, '桥跨度:'),
        ('桥头整体离开河道轴线', bridge_off_axis, '中点离轴'),
        ('桥轴改成顺河走向', bridge_parallel, '桥正交:'),
        ('跨度拉到水宽三点二倍以上', bridge_ratio, '桥倍数:'),
        ('桥位落进钛湖椭圆', bridge_in_lake, '桥穿湖:'),
        ('河渡位退上滩地', wharf_off_bank, '渡位贴岸:'),
        ('湖渡位脱离岸线', wharf_off_lakeline, '渡位岸线:'),
        ('航线两端一湖一河', route_mixed_water, '航线渡位:'),
        ('航线耗时手改', route_minutes, '航线耗时:'),
        ('航段距离手改', route_segment, '航线耗时:'),
        ('山口讫点落回盆界内', pass_inside_basin, '山口盆界:'),
        ('山口讫点离锚点下限抬高', pass_near_anchor, '山口盆界:'),
        ('盆界交点手改', pass_box_exit, '山口交点:'),
        ('不载客类挂上班线', pass_walking_line, '山口班线:'),
        ('载客类班线清零', pass_no_line, '载客类班线每日必须大于 0'),
        ('载客标志与六类字典相反', pass_flag, '载客标志'),
        ('六类字典缺实例', pass_kind_missing, '没有实例'),
        ('山口耗时手改', pass_minutes, '山口耗时:'),
        ('山口里程手改', pass_km, '正典里程'),
        ('湖航线改成临河', lake_no_ferry, '跨水覆盖: 钛湖'),
        ('删空某条河的桥梁', river_no_bridge, '没有桥梁构件'),
        ('四表圈层全改内湖环', ring_uncovered, '没有任何通行构件服务'),
        ('汇总计数手改', summary_count, '汇总: 计数与四表行数不一致'),
        ('构件编号格式破坏', code_format, '编号格式不合'),
        ('两桥头合并到同岸', heads_same_side, '同侧'),
        ('圈层对键名与两端圈层不符', matrix_pair_key, '圈层对键名不规范'),
        ('第4期延后方式加回轮渡', deferred_prm, '延后方式应只剩 TR-AIR'),
        ('第4期矩阵外方式真源改指', outside_prm, '的真源没指向空间通行源表'),
        ('第4期把轮渡塞进矩阵方式', outside_matrix_prm, '同时进了矩阵方式列表'),
    ]


def run_gate(tmp):
    r = subprocess.run([sys.executable, str(tmp / '工具' / 'verify_spatial.py')],
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
            rc0, out0 = run_gate(tmp)
            objs = {'canon': canon_of(tmp), 'prm': prm_of(tmp), 'src': src_of(tmp)}
            names = OBJ_NAMES[:len(_args(mutate))]
            mutate(*[objs[k] for k in names])
            for k in names:
                (tmp / '数据' / FILES[k]).write_text(
                    json.dumps(objs[k], ensure_ascii=False, indent=2), encoding='utf-8')
            rc, out = run_gate(tmp)
            red = rc != 0 and expected in out
            ok = rc0 == 0
            results.append(dict(case=name, red=red, clean_before=ok))
            print(('OK ' if red and ok else '!! ') + f'{name}：夹具原样 rc={rc0}，注入后 rc={rc}，'
                  f'期望字样「{expected}」' + ('' if ok else '（夹具本来就不绿！）') + ('' if red else '（没判红！）'))
            if not red or not ok:
                failures.append(name)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    leftover = [p for p in Path(tempfile.gettempdir()).glob(TMP_PREFIX + '*') if p.is_dir()]
    print(json.dumps(dict(cases=len(results), red=len(results) - len(failures), not_red=len(failures),
                          fixture_leftover=len(leftover)), ensure_ascii=False))
    if failures or leftover:
        sys.exit(1)
    print(f'第5期构件闸门违例自检通过：{len(results)} 个违例全部判红且措辞对得上，夹具零残留')


def _args(fn):
    import inspect
    return [p for p in inspect.signature(fn).parameters]


if __name__ == '__main__':
    main()
