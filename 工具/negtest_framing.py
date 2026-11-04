# -*- coding: utf-8 -*-
"""取景几何闸门的违例自检：在系统临时目录复制一份闸门+名录+原稿，逐条改坏取景段，断言闸门必须判红。

闸门本身只会打印"全绿"，无法自证它抓得住违例；本脚本按同一条判据反向注入，
只操作临时副本，绝不改动被守护的仓库文件。跑法：python 工具/negtest_framing.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / '工具' / 'verify_framing.py'
TMP_PREFIX = 'framneg-'

# D01 改写前的旧口径：1.6米平视、机位在本片区地标南侧，正南画面里三座地标全在镜头背后。
# 留在这里只为负测用：把任何一条取景段整段换成它，闸门必须抓到"未全部入画"。
EYELEVEL = ('建议在北岸公共步道(0.000,2.200)千米，机位离地1.6米，35毫米朝南拍摄。近景为银杏落叶与栏杆，'
            '中景为小波纹湖面，远景南城和南原诸岭随空气透视变淡；L007在东侧，不塞进正南画面。'
            '用8秒沿岸平移，保留脚步和自行车铃声。晚秋黄昏太阳来自255°，光从画面右前侧斜入，镜头不越过关闭的低位亲水台阶。')
ENTRY_RE = re.compile(r'##\s+([A-Z]\d{2,3})\s+[^\n]*\n(?:[^\n]*\n)*?\*\*图像与视频取景\*\*：([^\n]*)')
COORD_RE = re.compile(r'[\(\（]\s*(-?\d+(?:\.\d+)?)\s*[,，]\s*(-?\d+(?:\.\d+)?)\s*[\)\）]')


def source_segments():
    """读真源取景段，负测按它造违例，不写死坐标与高度数字。"""
    out = {}
    for path in sorted((ROOT / '分卷' / '原稿').glob('*.md')):
        for m in ENTRY_RE.finditer(path.read_text(encoding='utf-8-sig')):
            out[m.group(1)] = m.group(2)
    return out


def cases():
    seg = source_segments()
    inner = json.loads((ROOT / '数据' / '城市空间名录.json').read_text(encoding='utf-8'))
    sectors = {e['id']: e['sector'] for e in inner['entries'] if e['type'] == '城市片区'}
    missing = [d for d in ('D01', 'D02', 'D03', 'D05', 'D11') if d not in seg or not COORD_RE.search(seg[d])]
    if missing:
        raise SystemExit('自检夹具取不到 %s 的取景段机位坐标，负测无法成立' % ','.join(missing))

    def cam(did):
        c = COORD_RE.search(seg[did])
        return '(%s,%s)' % (c.group(1), c.group(2))

    d11 = cam('D11')
    d11_low = '(%s,%.3f)' % (COORD_RE.search(seg['D11']).group(1), sectors['D11']['inner_radius_km'] - 0.9)
    isl = inner['lake']['island']['center_km']
    on_isl = '(%.3f,%.3f)' % (isl[0], isl[1])
    return [
        ('整段退回1.6米平视旧口径', 'D01', ('whole', EYELEVEL), '未全部入画'),
        ('外环片区机位落入内湖环半径带', 'D11', ('replace', d11, d11_low), '机位不在本片区扇区内'),
        ('删掉机位坐标', 'D02', ('replace', cam('D02') + '千米，', ''), '无可解析的机位坐标'),
        ('机位无说明落进钛湖水面', 'D03', ('replace', cam('D03'), '(0.000,1.000)'), '落在钛湖水面内'),
        ('俯瞰机位降到人眼高度', 'D05', ('replace', '机位离地55米', '机位离地1.6米'), '离地不低于20米'),
        ('删掉镜头焦距', 'D01', ('replace', '35毫米朝南拍摄', '朝南拍摄'), '未给镜头焦距'),
        ('机位挪到钛马岛上不写明', 'D10', ('replace', cam('D10'), on_isl), '落在钛马岛上'),
        ('岛上机位只写湖面措辞', 'D10', ('replace', cam('D10'), on_isl + '千米，湖面架机'), '落在钛马岛上'),
        ('岛上机位写明钛马岛后不得再按落水判', 'D10',
         ('replace', cam('D10'), on_isl + '千米，钛马岛上机位'), '不含:落在钛湖水面内'),
    ]


def patch(text, did, how):
    hit = False

    def sub(m):
        nonlocal hit
        if m.group(1) != did:
            return m.group(0)
        body = m.group(2)
        if how[0] == 'whole':
            new = how[1]
        elif how[1] in body:
            new = body.replace(how[1], how[2])
        else:
            return m.group(0)
        hit = True
        return m.group(0)[:m.start(2) - m.start(0)] + new

    text = ENTRY_RE.sub(sub, text)
    return text, hit


def fixture():
    fix = Path(tempfile.mkdtemp(prefix=TMP_PREFIX))
    shutil.copytree(GATE.parent, fix / '工具', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(ROOT / '分卷' / '原稿', fix / '分卷' / '原稿')
    (fix / '数据').mkdir()
    shutil.copy(ROOT / '数据' / '城市空间名录.json', fix / '数据' / '城市空间名录.json')
    return fix


def run_gate(fix):
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    proc = subprocess.run([sys.executable, str(fix / '工具' / 'verify_framing.py')],
                          capture_output=True, text=True, encoding='utf-8', errors='replace', env=env)
    return proc.returncode, (proc.stdout or '') + (proc.stderr or '')


def judge(expected, rc, out):
    """「不含:xxx」是反向断言：注入后闸门不得再报出 xxx——用来钉住「岛椭圆算干地、不按落水判」这条排除。"""
    if expected.startswith('不含:'):
        return rc == 1 and expected.split(':', 1)[1] not in out
    return rc == 1 and expected in out


results = []
for name, did, how, expected in cases():
    fix = fixture()
    try:
        hit = 0
        for path in sorted((fix / '分卷' / '原稿').glob('*.md')):
            text = path.read_text(encoding='utf-8-sig')
            patched, changed = patch(text, did, how)
            if changed:
                path.write_text(patched, encoding='utf-8')
                hit += 1
        assert hit == 1, '夹具命中 %d 处，应为 1 处' % hit
        rc, out = run_gate(fix)
        red = judge(expected, rc, out)
        results.append(dict(case=name, entry=did, expected=expected, rc=rc, red=red))
        if red:
            print('OK %s（%s）判红 rc=%s，命中「%s」' % (name, did, rc, expected))
        else:
            print('!! %s（%s）注入后闸门未判红：rc=%s，期望命中「%s」\n%s' % (name, did, rc, expected, out[-600:]))
    finally:
        shutil.rmtree(fix, ignore_errors=True)

# 元违例：整卷原稿缺失时，闸门不得因为"解析到 0 条取景段"而判绿
fix = fixture()
try:
    shutil.rmtree(fix / '分卷')
    rc, out = run_gate(fix)
    red = rc != 0
    results.append(dict(case='整卷原稿缺失', entry='全部', expected='非零退出', rc=rc, red=red))
    print(('OK ' if red else '!! ') + '整卷原稿缺失：rc=%s（应为非零，不得解析空转判绿）' % rc)
finally:
    shutil.rmtree(fix, ignore_errors=True)

leftover = [p for p in Path(tempfile.gettempdir()).glob(TMP_PREFIX + '*') if p.is_dir()]
failed = [r for r in results if not r['red']]
print(json.dumps(dict(cases=len(results), red=len(results) - len(failed), not_red=len(failed),
                      fixture_leftover=len(leftover)), ensure_ascii=False))
if failed or leftover:
    sys.exit(1)
print('取景闸门违例自检通过：%d 个违例全部判红，夹具零残留' % len(results))
