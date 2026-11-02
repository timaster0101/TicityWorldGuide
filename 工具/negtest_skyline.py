# -*- coding: utf-8 -*-
"""天际线落位闸门的违例自检：在系统临时目录复制一份闸门＋名录＋取景几何核验，逐条把落位改坏，断言闸门必须判红。

verify_skyline.py 只会打印「闸门通过」，无法自证它抓得住违例；本脚本按它的五条判据
（扇区归属／岸距／河流余量／锚点间距／视锥）加两道对账（取景快照过期、地标清单被删空）
反向注入。夹具全部落在临时目录，绝不改动被守护的仓库文件。
跑法：python 工具/negtest_skyline.py
"""
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = 'verify_skyline.py'
TMP_PREFIX = 'skylinedir-neg-'
DATA = ['城市空间名录.json', '取景几何核验.json']


def fixture():
    fix = Path(tempfile.mkdtemp(prefix=TMP_PREFIX))
    (fix / '工具').mkdir()
    (fix / '数据').mkdir()
    shutil.copy2(ROOT / '工具' / GATE, fix / '工具' / GATE)
    for name in DATA:
        shutil.copy2(ROOT / '数据' / name, fix / '数据' / name)
    return fix


def load(fix, name):
    return json.loads((fix / '数据' / name).read_text(encoding='utf-8'))


def save(fix, name, data):
    (fix / '数据' / name).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')


def point(radius, bearing_deg):
    a = math.radians(bearing_deg)
    return [round(radius * math.sin(a), 3), round(radius * math.cos(a), 3)]


def run_gate(fix):
    proc = subprocess.run([sys.executable, str(fix / '工具' / GATE)],
                          capture_output=True, text=True, encoding='utf-8', errors='replace')
    return proc.returncode, (proc.stdout or '') + (proc.stderr or '')


def target():
    """按真源选一条被注入的地标：所属片区带扇区参数、且本条视锥余量最宽，避免顺带破别的判据。"""
    reg = json.loads((ROOT / '数据' / '城市空间名录.json').read_text(encoding='utf-8'))
    skyline = json.loads((ROOT / '数据' / '天际线落位核验.json').read_text(encoding='utf-8'))
    sectors = {e['id']: e['sector'] for e in reg['entries'] if e['type'] == '城市片区'}
    byid = {r['id']: r for r in skyline['results'] if r.get('fov')}
    candidates = [r for r in skyline['results']
                  if r['id'] in byid and r['parent'] in sectors and not r['issues']]
    best = max(candidates, key=lambda r: byid[r['id']]['fov']['slack_deg'])
    return best['id'], sectors[best['parent']]


CASE_LABELS = {
    '扇区越角': '超出片区扇区',
    '半径越带': '不在片区带',
    '落进湖面': '距钛湖岸线',
    '压在河道': '余量-',
    '锚点重叠': '与最近锚点仅',
    '视锥越限': '超出视锥限',
    '取景快照过期': '已过期',
}


def build_cases():
    lid, sec = target()
    reg = json.loads((ROOT / '数据' / '城市空间名录.json').read_text(encoding='utf-8'))
    entry = next(e for e in reg['entries'] if e['id'] == lid)
    p = entry['center_km']
    r = math.hypot(*p)
    angle = math.degrees(math.atan2(p[0], p[1])) % 360
    lake = reg['lake']
    river = max(reg['rivers'], key=lambda w: len(w['centerline_km']))
    river_point = max(river['centerline_km'], key=lambda q: math.hypot(*q))
    dwelling = next(e for e in reg['entries'] if e['type'] == '居民区')
    return lid, [
        ('扇区越角', '城市空间名录.json', lambda d: move(d, lid, point(r, sec['angle_center_deg'] + sec['angle_half_width_deg'] + 5))),
        ('半径越带', '城市空间名录.json', lambda d: move(d, lid, point(sec['outer_radius_km'] + 0.2, angle))),
        ('落进湖面', '城市空间名录.json', lambda d: move(d, lid, [0.0, round(lake['north_south_semiaxis_km'] * 0.5, 3)])),
        ('压在河道', '城市空间名录.json', lambda d: move(d, lid, [round(river_point[0], 3), round(river_point[1], 3)])),
        ('锚点重叠', '城市空间名录.json', lambda d: move(d, lid, list(dwelling['center_km']))),
        ('视锥越限', '取景几何核验.json', lambda d: flip_camera(d, entry['parent'])),
        ('取景快照过期', '取景几何核验.json', lambda d: stale(d, reg)),
    ]


def move(data, lid, center):
    hit = 0
    for e in data['entries']:
        if e['id'] == lid:
            e['center_km'] = center
            hit += 1
    assert hit == 1, '名录夹具命中 %d 条地标，应为 1 条' % hit


def flip_camera(data, parent):
    hit = 0
    for row in data['results']:
        if row['id'] == parent and row.get('facing_deg') is not None:
            row['facing_deg'] = (row['facing_deg'] + 180) % 360
            hit += 1
    assert hit == 1, '取景夹具命中 %d 个机位，应为 1 个' % hit


def stale(data, reg):
    data['checked'] = len(reg['entries']) - 1


results = []

# 对照组：夹具未注入必须判绿，否则下面七条“判红”分不清是闸门灵敏还是夹具恒红
fix = fixture()
try:
    rc, out = run_gate(fix)
    green = rc == 0 and '闸门通过' in out
    results.append(dict(case='未注入对照', expected='判绿', rc=rc, red=green))
    print(('OK ' if green else '!! ') + '未注入对照：rc=%s（应为 0 且打印通过）' % rc)
finally:
    shutil.rmtree(fix, ignore_errors=True)

lid, cases = build_cases()
for name, target_file, mutate in cases:
    fix = fixture()
    try:
        data = load(fix, target_file)
        mutate(data)
        save(fix, target_file, data)
        rc, out = run_gate(fix)
        expected = CASE_LABELS[name]
        red = rc == 1 and expected in out
        results.append(dict(case=name, entry=lid, expected=expected, rc=rc, red=red))
        print(('OK ' if red else '!! ') + '%s（%s）注入后 rc=%s，命中「%s」=%s' % (
            name, lid, rc, expected, expected in out))
        if not red:
            print(out[-600:])
    finally:
        shutil.rmtree(fix, ignore_errors=True)

# 元违例：地标清单被删空时，闸门不得因为"零条零违例"而判绿
fix = fixture()
try:
    data = load(fix, '城市空间名录.json')
    data['entries'] = [e for e in data['entries'] if e['type'] != '标志性建筑']
    save(fix, '城市空间名录.json', data)
    rc, out = run_gate(fix)
    red = rc != 0
    results.append(dict(case='地标清单被删空', expected='非零退出', rc=rc, red=red))
    print(('OK ' if red else '!! ') + '地标清单被删空：rc=%s（应为非零，不得空转判绿）' % rc)
finally:
    shutil.rmtree(fix, ignore_errors=True)

leftover = [p for p in Path(tempfile.gettempdir()).glob(TMP_PREFIX + '*') if p.is_dir()]
failed = [r['case'] for r in results if not r['red']]
print(json.dumps(dict(cases=len(results), red=len(results) - len(failed), not_red=len(failed),
                      injected_on=lid, fixture_leftover=len(leftover)), ensure_ascii=False))
if failed or leftover:
    sys.exit(1)
print('天际线落位闸门违例自检通过：%d 个违例全部判红，夹具零残留' % len(results))
