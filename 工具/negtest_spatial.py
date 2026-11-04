# -*- coding: utf-8 -*-
"""通行构件闸门的违例自检：把闸门与数据复制到临时目录，逐条改坏正典、源表或名录几何，断言闸门必须判红且给出该条自己的措辞。

闸门只会打印"全绿"，无法自证它抓得住违例；本脚本按二十五判反向注入 59 例（含钛马岛三条进岛通路 30 例），
只操作临时副本，绝不改动被守护的仓库文件。跑完复核夹具零残留。
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


def reg_of(tmp):
    return json.loads((tmp / '数据' / '城市空间名录.json').read_text(encoding='utf-8'))


OBJ_NAMES = ['canon', 'prm', 'src', 'reg']
FILES = {'canon': '空间通行正典.json', 'prm': '运行参数源表.json', 'src': '空间通行源表.json',
         'reg': '城市空间名录.json'}


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
        for code in ('FR-01', 'FR-02', 'FR-03', 'FR-07'):
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

    def outside_code_dropped(c, prm):
        rows = prm['参数']['交通']['矩阵外方式']
        rows[:] = [m for m in rows if m['码'] != 'TR-TUNNEL']

    def outside_matrix_prm(c, prm):
        prm['参数']['交通']['方式'][0]['码'] = 'TR-FERRY'

    # ―― 第7期钛马岛：岛几何在名录、场地与通路在正典、阈值在源表，三处各有自己的判红措辞 ――
    def isl_out_of_lake(c, _prm, _src, reg):
        isl = reg['lake']['island']
        isl['center_km'] = [-1.28, 1.75]          # 岛整体上挪，北半轴 0.42 顶穿湖岸椭圆

    def open_water_edit(c, _prm, _src, reg):
        reg['lake']['open_water_km2'] = 20.0

    def anchor_on_island(c, _prm, _src, reg):
        entry = next(e for e in reg['entries'] if e['id'] == 'D09')
        entry['center_km'] = [-1.28, 1.1]

    def island_deleted(c, _prm, _src, reg):
        del reg['lake']['island']

    def isl_gap_floor(c, _prm, src):
        src['参数']['容差']['岛岸到湖岸下限千米'] = 0.6

    def walk_cap_lower(c, _prm, src):
        src['参数']['容差']['岛内步行上限千米'] = 0.1

    def tunnel_grade_lower(c, _prm, src):
        src['参数']['湖底隧道']['常数']['纵坡上限百分比'] = 3.0

    def cable_clear_floor(c, _prm, src):
        src['参数']['高空缆车']['系数与常数']['缆绳净空下限m'] = 25

    def island_source_move(c, _prm, src):
        src['参数']['湖岛']['几何真源'] = '数据/别处的轮廓.json'

    def site_center_off(c):
        row(c['岛上场地'], 'PL-01')['中心km'] = [0.0, 0.0]

    def site_area_edit(c):
        row(c['岛上场地'], 'PL-01')['面积km2'] = 0.5

    def site_overlap(c):
        row(c['岛上场地'], 'PL-02')['中心km'] = list(row(c['岛上场地'], 'PL-03')['中心km'])

    def site_capacity_edit(c):
        row(c['岛上场地'], 'PL-01')['容量人'] = 45100

    def site_capacity_fake(c):
        row(c['岛上场地'], 'PL-02')['容量人'] = 1000

    def wharf_bank_add(c):
        row(c['渡位'], 'WH-06')['岸别'] = '主岸'

    def wharf_island_bank(c):
        row(c['渡位'], 'WH-13')['岸别'] = '主岸'

    def route_island_only(c):
        row(c['轮渡航线'], 'FR-07')['渡位A'] = 'WH-13'

    def route_cross_island(c):
        row(c['渡位'], 'WH-01')['坐标km'] = [-2.726, 1.1]
        row(c['渡位'], 'WH-02')['坐标km'] = [2.726, 1.1]

    def tunnel_portal_water(c):
        row(c['湖底隧道'], 'TN-01')['岸端洞口km'] = [0.0, 0.0]

    def tunnel_portal_off(c):
        row(c['湖底隧道'], 'TN-01')['岛端洞口km'] = [0.0, 0.0]

    def tunnel_cover_edit(c):
        row(c['湖底隧道'], 'TN-01')['覆土m'] = 5.0

    def tunnel_walk_far(c):
        row(c['湖底隧道'], 'TN-01')['岛端洞口km'] = [-0.74, 1.1]

    def cable_station_water(c):
        row(c['高空缆车'], 'CB-01')['岸站km'] = [0.0, 0.0]

    def cable_no_water(c):
        row(c['高空缆车'], 'CB-01')['岛站km'] = [-0.763, 2.098]

    def bridge_to_site(c):
        row(c['桥梁'], 'BR-01')['连接A'] = 'PL-01'

    def bridge_cross_island(c):
        r = row(c['桥梁'], 'BR-02')
        r['桥头A_km'] = [-2.726, 1.1]
        r['桥头B_km'] = [2.726, 1.1]

    def access_count_edit(c):
        c['汇总']['进岛通路数'] = 4

    def tunnel_table_empty(c):
        c['湖底隧道'] = []

    def cable_table_empty(c):
        c['高空缆车'] = []

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
        ('进岛隧道的方式码被删掉', outside_code_dropped, '矩阵外方式码集不合'),
        ('第4期把轮渡塞进矩阵方式', outside_matrix_prm, '同时进了矩阵方式列表'),
        ('岛北边界顶穿湖岸', isl_out_of_lake, '岛边界湖f'),
        ('净水面台账手改', open_water_edit, '湖岛几何: 净水面'),
        ('名录锚点挪进岛上', anchor_on_island, '名录锚点落进钛马岛'),
        ('名录删掉岛几何', island_deleted, '名录没有 lake.island'),
        ('岛岸到湖岸下限抬高', isl_gap_floor, '岛岸到湖岸最小'),
        ('岛内步行上限压低', walk_cap_lower, '岛内步行: 实得'),
        ('隧道纵坡上限压低', tunnel_grade_lower, '隧道纵坡: TN-01 最大'),
        ('缆绳净空下限抬高', cable_clear_floor, '缆车净空: CB-01 只有'),
        ('岛几何真源改指他处', island_source_move, '源表 湖岛.几何真源'),
        ('广场中心落到湖心', site_center_off, '场地几何: PL-01 中心在岛外'),
        ('广场面积手改', site_area_edit, '场地几何: PL-01 面积与半轴派生值不符'),
        ('两块院区压成同心', site_overlap, '场地重叠: PL-02 与 PL-03'),
        ('观演容量手改', site_capacity_edit, '场地容量: PL-01 正典'),
        ('院区挂观演容量', site_capacity_fake, '不是草地广场却登记了观演容量'),
        ('河渡位挂上岸别', wharf_bank_add, '渡位岸别:'),
        ('岛岸渡位改成主岸', wharf_island_bank, '渡位岸线: WH-13'),
        ('航线两端都落岛岸', route_island_only, '两端都在岛岸'),
        ('岸到岸航线穿岛', route_cross_island, '航线穿岛:'),
        ('隧道岸端落进湖水', tunnel_portal_water, '隧道洞口: TN-01 岸端洞口在湖水面内'),
        ('隧道岛端没上岛', tunnel_portal_off, '岛端洞口没上岛'),
        ('隧道覆土手改', tunnel_cover_edit, '隧道覆土: TN-01 正典'),
        ('隧道岛口退到东岸', tunnel_walk_far, '隧道可达:'),
        ('缆车岸站落进湖水', cable_station_water, '岸站落进钛湖水面'),
        ('缆车岛站退回岸站', cable_no_water, '缆车跨水:'),
        ('桥把岛上场地接进路网', bridge_to_site, '岛与城无桥:'),
        ('桥线横穿钛马岛', bridge_cross_island, '桥穿岛:'),
        ('汇总进岛通路数手改', access_count_edit, '汇总: 进岛通路数'),
        ('删空湖底隧道表', tunnel_table_empty, '进岛通路: 湖底隧道为空'),
        ('删空高空缆车表', cable_table_empty, '进岛通路: 高空缆车为空'),
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
            objs = {'canon': canon_of(tmp), 'prm': prm_of(tmp), 'src': src_of(tmp), 'reg': reg_of(tmp)}
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
    print(f'通行构件闸门违例自检通过：{len(results)} 个违例全部判红且措辞对得上，夹具零残留')


def _args(fn):
    import inspect
    return [p for p in inspect.signature(fn).parameters]


if __name__ == '__main__':
    main()
