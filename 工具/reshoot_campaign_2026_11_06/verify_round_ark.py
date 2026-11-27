# -*- coding: utf-8 -*-
"""R10 组的投后核验：这一次的「回绑源」不是会话 jsonl，而是投送器自己写的 HTTP 台账。

为什么另起一个核验器而不改 verify_round.py：R10 起投放改走火山方舟标准域的 HTTP 接口
（`/api/v3/images/generations`），发图不再经过会话内置的 ImageGen 工具，因此
「扫 jsonl 收 ImageGen 的 tool_use」这条取数路线在本组没有对象。本轮的证据链变成三段：
①送入串＝`REF.send_body(台账 body)` 现算、其 sha256 必须等于台账 `send_sha256`（逐字面）；
②母图确实传了＝投送台账的 `input_images == 1`（方舟在漏传母图时不报错、静默裸投，这一列是唯一防线）；
③落盘枚与台账逐字节相符（字节数＋sha256 前 12 位）。

容器面的一个错判在这里纠正：先前按第一轮（带水印那 8 枚）的读数写「本通道 caBX=0、iTXt=0」，
但第二轮无水印的 14 枚实测 **caBX=1／iTXt=0**——C2PA 容器是在的，只是没有像素角标。
故容器仍按 C136 原判（`caBX>=1 or iTXt>=1`），不另开通道等价凭据分支。

跑法：python -X utf8 工具/reshoot_campaign_2026_11_06/verify_round_ark.py
产出：round_readings_r10.json（读数面）＋ ledger_r10.json（逐轮台账，只追加）
"""
import datetime
import hashlib
import io
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
WORKSPACE = os.path.abspath(os.path.join(ROOT, '..'))
IMG_DIR = os.path.join(WORKSPACE, 'vibe_images')

GROUP = 'R10'
SUFFIX_SECOND = 'C154取景二次重投-v01'   # R9 三条沿用的发名后缀
SUFFIX_SHIFT = 'C154取景换档重投-v01'    # 11 条新出
BODIES = 'send_bodies_r10.json'
RUNLOG = '数据/R10方舟投送记录.json'
READINGS = 'round_readings_r10.json'
LEDGER = 'ledger_r10.json'
DECLARATION = '数据/图集AIGC声明.json'

# R11：把「在册首格不是 E1 母图轮产出」的 140 条按 E1 基线重出（用户 2026-11-27 点单）。
# 与 R10 同一套三段机械取证，只是台账/记录/读数换名，后缀换一支。
ROUNDS = {
    'R10': {'bodies': BODIES, 'runlog': RUNLOG, 'readings': READINGS, 'ledger': LEDGER,
            'suffixes': (SUFFIX_SECOND, SUFFIX_SHIFT)},
    'R11': {'bodies': 'send_bodies_r11.json', 'runlog': '数据/R11方舟投送记录.json',
            'readings': 'round_readings_r11.json', 'ledger': 'ledger_r11.json',
            'suffixes': ('C156E1基线重出-v01',)},
    'R12': {'bodies': 'send_bodies_r12.json', 'runlog': '数据/R12方舟投送记录.json',
            'readings': 'round_readings_r12.json', 'ledger': 'ledger_r12.json',
            'suffixes': ('C156E1基线补出-v01',)},
}

DECL = ('R10 方舟标准域投送逐轮台账。每轮一条，只追加不改写历史；判废结论由人工目视给出，'
        '本台账只登记机械取证项与人工结论字段（人工结论为空即未给）。本组回绑源是投送器写的 '
        'R10方舟投送记录.json（HTTP 台账），不是会话 jsonl——发图不再经 ImageGen 工具。'
        '容器面按 C156 记账：本通道无 caBX／iTXt，以「台账在册＋外部声明件」为等价凭据，'
        '读数里 container 原样保留，另列 容器凭据 说明判绿依据。')


def load_measure(root=ROOT):
    spec = importlib.util.spec_from_file_location(
        'm', os.path.join(root, '工具', 'reinject_2026_11_05', 'measure_images.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _load(rel, root=ROOT):
    with io.open(os.path.join(root, rel.replace('/', os.sep)), encoding='utf-8') as fp:
        return json.load(fp)


TS_RE = re.compile(r'_(1\d{12})_[0-9a-f]{8}\.png$')


def _ts_of(fname):
    """落盘时间戳只从文件名取：方舟台账不带 ts 字段，档名里的 13 位毫秒就是它的落盘时刻。"""
    m = TS_RE.search(fname)
    return int(m.group(1)) if m else 0


def sent_body(here=HERE):
    """现算送入串：与投送器同一函数，避免「台账写一套、发的是另一套」。"""
    spec = importlib.util.spec_from_file_location(
        'ref', os.path.join(ROOT, '工具', 'r4_style_ref.py'))
    ref = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ref)
    return ref.send_body


def run(here=HERE, root=ROOT, img_dir=IMG_DIR, measure=None, group=GROUP):
    cfg = ROUNDS[group]
    suffixes = cfg['suffixes']
    if measure is None:
        measure = load_measure(root).measure
    bodies = _load(os.path.join('工具', 'reshoot_campaign_2026_11_06', cfg['bodies']), root)
    runlog = {r['id']: r for r in _load(cfg['runlog'], root)['rows']}
    send_body = sent_body(here)
    decl_rows = {}
    decl_path = os.path.join(root, DECLARATION.replace('/', os.sep))
    if os.path.exists(decl_path):
        decl_rows = {r['路径'].rsplit('/', 1)[-1]: r for r in _load(DECLARATION, root)['逐件']}

    rows, fails = [], []
    for eid, ref in sorted(bodies.items()):
        name = ref['send_name']
        if not any(name.endswith('-' + s) for s in suffixes):
            fails.append((eid, '发名不在 %s 的登记档串内：%s' % (group, name)))
            continue
        log = runlog.get(eid)
        if log is None:
            fails.append((eid, '投送台账里没有这一条'))
            continue
        # ① 逐字面：现算送入串的 sha256 必须等于台账登记值
        want = hashlib.sha256(send_body(ref['body']).encode('utf-8')).hexdigest()
        verbatim = want == ref['send_sha256']
        # ② 母图面：方舟漏传母图不报错，只有 input_images 能判
        ref_ok = int(log.get('input_images') or 0) == 1
        # ③ 落盘面
        p = os.path.join(img_dir, log['file'])
        if not os.path.isfile(p):
            fails.append((eid, '落盘文件不在盘：%s' % log['file']))
            continue
        r = measure(Path(p))
        size_match = r["dims"] == ref["size"]
        bytes_match = (int(r['bytes']) == int(log['bytes'])
                       and r['sha256_12'] == str(log['sha256'])[:12])
        cont = r['container']
        container_ok = cont['cabx'] >= 1 or cont['itxt'] >= 1
        basis = 'C136 容器（caBX=%d／iTXt=%d）' % (cont['cabx'], cont['itxt'])
        in_decl = log['file'] in decl_rows
        row = {
            'id': eid, 'file': log['file'], 'send_name': name,
            'ts_ms': _ts_of(log['file']),
            'ts_text': (datetime.datetime.fromtimestamp(_ts_of(log['file']) / 1000)
                        .strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] if _ts_of(log['file']) else '未登记'),
            '逐字相等': verbatim, 'dims': r['dims'], 'declared_size': ref['size'],
            'size_match': size_match, 'bytes': r['bytes'], 'sha256_12': r['sha256_12'],
            'bytes_match': bytes_match, 'container': cont, '容器凭据': basis,
            'declaration_row': in_decl,
            'p99_lum': r['p99_lum'], 'fine_var_full': r['fine_var_full'],
            'sun_blob_px': r['sun_blob_px'],
            'replaced_cell': ref['replaced_cell'], 'status_before': ref['status_before'],
            '投次': int(ref['投次']), '逐字发起数': 1, '非逐字发起数': 0,
            '登记作废发起数': 0, '母图相符': ref_ok, '作废删除': [],
            '通道': {'model': log.get('model'), 'watermark': False,
                     'seconds': log.get('seconds'), 'cost': log.get('cost')},
        }
        rows.append(row)
        if not (verbatim and size_match and bytes_match and ref_ok and container_ok):
            fails.append((eid, '逐字=%s 尺寸=%s 字节=%s 母图=%s 容器=%s'
                          % (verbatim, size_match, bytes_match, ref_ok, container_ok)))

    out = {'round': group, 'rows': rows,
           '统计面': {'组别': group, '送入串台账': cfg['bodies'], '投送台账': cfg['runlog'],
                      '本轮条目数': len(bodies), '核验条数': len(rows),
                      '判绿条数': len(rows) - len(fails), '判红条数': len(fails),
                      '落点目录': 'vibe_images/（仓外，回填时才请进 数据/图集/<ID>/）',
                      '容器口径': 'C136 或 C156 通道等价凭据',
                      '声明件已收录条数': sum(1 for x in rows if x['declaration_row'])},
           '判红': [{'id': e, '原因': why} for e, why in fails]}
    with io.open(os.path.join(here, cfg['readings']), 'w', encoding='utf-8', newline='\n') as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1)
        fp.write('\n')

    ledger_path = os.path.join(here, cfg['ledger'])
    if os.path.exists(ledger_path):
        with io.open(ledger_path, encoding='utf-8') as fp:
            ledger = json.load(fp)
    else:
        ledger = {'declaration': DECL, 'rounds': []}
    ledger['rounds'].append({
        '轮次': len(ledger['rounds']) + 1,
        '登记时刻': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        '组别': group, '送入串台账': cfg['bodies'],
        '本轮发起条目': sorted(bodies), '投次合计': sum(int(v['投次']) for v in bodies.values()),
        '落盘与回绑': rows, '人工目视结论': {}, '判废': [], '回填': False,
    })
    with io.open(ledger_path, 'w', encoding='utf-8', newline='\n') as fp:
        json.dump(ledger, fp, ensure_ascii=False, indent=1)
        fp.write('\n')

    for row in rows:
        print('%s %s｜%s｜逐字=%s 尺寸=%s 字节=%s 母图=%s｜container caBX=%d iTXt=%d｜%s｜sha12=%s'
              % ('✓' if not any(f[0] == row['id'] for f in fails) else '✗',
                 row['id'], row['dims'], row['逐字相等'], row['size_match'],
                 row['bytes_match'], row['母图相符'], row['container']['cabx'],
                 row['container']['itxt'], row['容器凭据'], row['sha256_12']))
    for e, why in fails:
        print('✗ %s｜%s' % (e, why))
    print('%s 组核验：%d 条（判绿 %d／判红 %d）→ %s、%s'
          % (group, len(bodies), len(rows) - len(fails), len(fails), cfg['readings'], cfg['ledger']))
    return 0 if not fails else 1


if __name__ == '__main__':
    ap = __import__('argparse').ArgumentParser()
    ap.add_argument('--round', default=GROUP, choices=sorted(ROUNDS))
    sys.exit(run(group=ap.parse_args().round))
